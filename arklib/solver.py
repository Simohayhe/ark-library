# -*- coding: utf-8 -*-
"""サーバー倍率の逆算。

管理者から Game.ini を貰えないサーバーで、ゲーム内の表示値だけから
PerLevelStatsMultiplier_* と BabyImprintingStatScaleMultiplier を割り出す。

考え方
------
ステータス値は各倍率について「一次式」になっている。倍率 m について

    V(m) = v0 + m * (v1 - v0)        v0 = V(m=0), v1 = V(m=1)

なので、レベル配分 Lw を仮定すれば m は割り算ひとつで出る。逆に m を
仮定すれば Lw も割り算ひとつで出る。そこで

    1. 各ステータス × 各 Lw から m を逆算して「候補」を作る
    2. 候補ごとに、全ステータスで整数 Lw が立ち、その合計が
       気絶値から求めた野生レベル合計と一致するかを検証する
    3. 複数個体で共通して成立した候補だけ残す

という手順で解く。照合はすべて「表示値の誤差幅に入っているか」で行うので、
ゲーム内表示が小数1桁に丸められていても壊れない。

気絶値 (Torpidity) は野生レベル倍率が常に 1 で、かつ他の全ステータスの
野生レベル合計がそのまま乗る。これを合計レベルの錨に使う。
(ARKStatsExtractor/importExportGun/ImportExportGun.cs も Torpidity の
 LevelWild を常に 1 として扱っている)

推奨サンプル
------------
**孵化直後で一度もレベルを振っていないベビー**。
    強化Lv = 0 / 刷り込み = 0% / テイム効率 = 100%
と既知の条件が揃い、未知数がレベル配分と倍率だけになる。3〜4 体あれば
たいてい一つに絞れる。
"""
import math

from . import ark, stats
from .multipliers import ServerMultipliers

# 逆算した倍率を同一視する丸め桁
ROUND_DIGITS = 4
# ありえない倍率は捨てる
MULT_MIN, MULT_MAX = 0.05, 50.0


class Observation(object):
    """ゲーム内で読み取った個体 1 体分の情報。

    species     : Species
    level       : 表示されているレベル
    values      : {statIndex: 表示値}。%表示のものは小数で (125.8% → 1.258)
    state       : 'bred'(交配産) / 'tamed'(テイム) / 'wild'(野生)
    taming_eff  : テイム効率 0..1。交配産は 1.0
    imprint     : 刷り込み率 0..1
    dom_levels  : {statIndex: 自分で振ったレベル数}。省略は 0
    """

    def __init__(self, species, level, values, state="bred",
                 taming_eff=1.0, imprint=0.0, dom_levels=None, label=None):
        self.species = species
        self.level = level
        self.values = dict(values)
        self.state = state
        self.taming_eff = 1.0 if state == "bred" else taming_eff
        self.imprint = imprint
        self.dom_levels = dict(dom_levels or {})
        self.label = label or "%s Lv%s" % (species.name, level)

    @property
    def domesticated(self):
        return self.state != "wild"

    def dom(self, s):
        return self.dom_levels.get(s, 0)

    def total_dom(self):
        return sum(self.dom_levels.values())

    def target_stats(self):
        """倍率の手がかりに使えるステータス (気絶値以外の表示ステータス)。

        apply() 前でも使えるように、判定には生データ (stats_raw) を見る。
        """
        sp = self.species
        return [s for s in sp.displayed_stat_indices()
                if s != ark.TORPIDITY and s in self.values
                and sp.stats_raw[s] is not None and sp.can_have_wild_levels(s)]

    def warnings(self):
        w = []
        if self.state == "tamed":
            w.append("テイム個体はテイム効率が値に効く。交配産のほうが精度が出る")
        if self.imprint > 0:
            w.append("刷り込み %d%% が乗っている。刷り込み倍率が未確定だと誤差になる"
                     % round(self.imprint * 100))
        if self.total_dom() > 0:
            w.append("強化レベルが %d 振られている。数が正確でないと外れる"
                     % self.total_dom())
        return w


# ---------------------------------------------------------------- 内部ヘルパ

def _calc(sp, s, obs, lw, imprint_scale=1.0):
    return stats.calc_value(sp, s, lw, 0, obs.dom(s), obs.domesticated,
                            taming_eff=obs.taming_eff,
                            imprinting_bonus=obs.imprint,
                            imprint_stat_scale=imprint_scale,
                            round_to_ingame=False)


def _tolerance(s, value):
    """表示値が持つ誤差幅 (Stats.cs DisplayedAberration 相当)。"""
    return stats.displayed_aberration(value, ark.precision(s))


class _StatProbe(object):
    """あるステータスについて V(Lw) の一次式を扱う小道具。

    inc_wild を差し替えて 2 点計算するだけで、V = v0 + Lw*slope が得られる。
    """

    def __init__(self, sp, obs, s, wild_mult, imprint_scale=1.0):
        self.sp, self.obs, self.s = sp, obs, s
        self.raw_iw = sp.stats_raw[s][1]
        st = sp.stats[s]
        saved = st.inc_wild
        try:
            st.inc_wild = self.raw_iw * wild_mult
            self.v0 = _calc(sp, s, obs, 0, imprint_scale)
            self.v1 = _calc(sp, s, obs, 1, imprint_scale)
        finally:
            st.inc_wild = saved
        self.slope = self.v1 - self.v0
        self.target = obs.values[s]
        self.tol = _tolerance(s, self.target)

    def levels(self, cap):
        """観測値と整合する整数 Lw を列挙する (0..cap)。"""
        if abs(self.slope) < 1e-12:
            # このステータスは野生レベルで動かない → 値が合うなら Lw は何でもよい
            return list(range(0, cap + 1)) if abs(self.target - self.v0) <= self.tol else []
        x = (self.target - self.v0) / self.slope
        out = []
        span = self.tol / abs(self.slope)
        for lw in range(int(math.floor(x - span)), int(math.ceil(x + span)) + 1):
            if 0 <= lw <= cap and abs(self.v0 + lw * self.slope - self.target) <= self.tol:
                out.append(lw)
        return out

    def implied_multipliers(self, cap):
        """Lw を 0..cap で仮定したときに導かれる野生倍率を列挙する。

        self は倍率 1 で作られている前提 (v0/slope が倍率 1 のときの値)。
        """
        if abs(self.slope) < 1e-12:
            return []
        out = []
        for lw in range(1, cap + 1):
            # target = v0 + lw * slope * m
            m = (self.target - self.v0) / (lw * self.slope)
            if MULT_MIN <= m <= MULT_MAX:
                out.append(round(m, ROUND_DIGITS))
        return out

    def matches_zero(self):
        """Lw=0 で値が合うか (合うなら倍率に関係なく成立する)。"""
        return abs(self.target - self.v0) <= self.tol


# ---------------------------------------------------------------- 合計野生Lv

def total_wild_levels(obs, base_mult=None):
    """気絶値から野生レベルの合計を求める。

    気絶値の野生レベル倍率は常に 1 なので、他の倍率が未知でも使える。
    戻り値は「ありえる合計レベルのリスト」。
    """
    sp = obs.species
    s = ark.TORPIDITY
    if s not in obs.values or sp.stats_raw[s] is None:
        return []

    sm = (base_mult or ServerMultipliers()).copy()
    sm.stat[s][3] = 1.0            # 気絶値の野生倍率は常に 1
    sp.apply(sm)                   # ← 参照する前に必ず適用しておく
    if sp.stats[s] is None:
        return []

    probe = _StatProbe(sp, obs, s, 1.0)
    if abs(probe.slope) < 1e-12:
        return []
    cap = max(obs.level, 1) * 2 + 10
    return probe.levels(cap)


# ---------------------------------------------------------------- 野生倍率

def _feasible_levels(pools, totals):
    """各ステータスの Lw 候補から、合計が totals のいずれかになる組を探す。"""
    if not pools:
        return None
    tset = set(totals)
    max_total = max(tset)
    order = sorted(range(len(pools)), key=lambda i: len(pools[i]))
    # 後ろに残っている最小値の合計 (枝刈り用)
    suffix_min = [0] * (len(order) + 1)
    for i in range(len(order) - 1, -1, -1):
        suffix_min[i] = suffix_min[i + 1] + min(pools[order[i]])

    result = [None] * len(pools)

    def rec(i, acc):
        if acc + suffix_min[i] > max_total:
            return False
        if i == len(order):
            return acc in tset
        idx = order[i]
        for v in pools[idx]:
            result[idx] = v
            if rec(i + 1, acc + v):
                return True
        return False

    return list(result) if rec(0, 0) else None


def _check_multiplier(obs, m, totals, base_mult, imprint_scale=1.0):
    """倍率 m がこの個体で成立するか。成立すれば {stat: Lw} を返す。"""
    if not totals:
        return None
    sp = obs.species
    sp.apply(base_mult)
    target_stats = obs.target_stats()
    if not target_stats:
        return None
    cap = max(totals)
    pools = []
    for s in target_stats:
        lv = _StatProbe(sp, obs, s, m, imprint_scale).levels(cap)
        if not lv:
            return None
        pools.append(lv)
    combo = _feasible_levels(pools, totals)
    if combo is None:
        return None
    return dict(zip(target_stats, combo))


def _niceness(m):
    """サーバー設定として「ありそうな値」ほど高スコア。"""
    if abs(m - 1.0) < 1e-9:
        return 100
    for step, score in ((1.0, 80), (0.5, 60), (0.25, 40), (0.1, 20), (0.05, 10)):
        if abs(m / step - round(m / step)) < 1e-6:
            return score
    return 0


def solve_wild_multiplier(observations, base_mult=None, imprint_scale=1.0,
                          extra_candidates=(), verbose=False):
    """複数個体から、全ステータス共通の野生レベル倍率を絞り込む。

    戻り値: [{"value":倍率, "niceness":点, "levels":{個体名:{stat:Lw}}}, ...]
    """
    base = base_mult or ServerMultipliers()
    prepared = []
    for obs in observations:
        totals = total_wild_levels(obs, base)
        if not totals:
            if verbose:
                print("  %s: 気絶値から合計レベルを出せない → 除外" % obs.label)
            continue
        prepared.append((obs, totals))
    if not prepared:
        return []

    # --- 候補の生成 ---------------------------------------------------
    cands = set()
    for m in (1.0,):
        cands.add(m)
    for m in extra_candidates:
        cands.add(round(float(m), ROUND_DIGITS))
    for obs, totals in prepared:
        sp = obs.species
        sp.apply(base)
        cap = max(totals)
        for s in obs.target_stats():
            probe = _StatProbe(sp, obs, s, 1.0, imprint_scale)
            cands.update(probe.implied_multipliers(cap))
    # 端数のブレを吸収するため、近い「きれいな値」も候補に足す
    for m in list(cands):
        for step in (0.05, 0.1, 0.25, 0.5, 1.0):
            snapped = round(round(m / step) * step, ROUND_DIGITS)
            if MULT_MIN <= snapped <= MULT_MAX:
                cands.add(snapped)

    if verbose:
        print("  倍率候補 %d 個を検証" % len(cands))

    # --- 全個体で成立するものだけ残す ---------------------------------
    results = []
    for m in sorted(cands):
        levels = {}
        ok = True
        for obs, totals in prepared:
            got = _check_multiplier(obs, m, totals, base, imprint_scale)
            if got is None:
                ok = False
                break
            levels[obs.label] = got
        if ok:
            results.append({"value": m, "niceness": _niceness(m), "levels": levels})

    # 近い値がまとまって残ることがあるので、きれいな値を代表にして畳む
    results.sort(key=lambda r: r["value"])
    folded = []
    for r in results:
        if folded and abs(r["value"] - folded[-1]["value"]) < 0.02:
            if r["niceness"] > folded[-1]["niceness"]:
                folded[-1] = r
            continue
        folded.append(r)

    folded.sort(key=lambda r: (-r["niceness"], abs(r["value"] - 1.0)))
    return folded


# ---------------------------------------------------------------- 強化倍率

def solve_dom_multiplier(species, stat_index, value_before, value_after,
                         points_added=1, dom_levels_before=0, base_mult=None):
    """レベルを振る前後の値から PerLevelStatsMultiplier_DinoTamed を出す。

    ステータス値は強化レベルについても一次式なので、野生レベルが分からなくても
    「1 ポイント振って差分を見る」だけで確定する。もっとも手軽で確実な手段。

    戻り値: (倍率, 誤差幅) または None
    """
    sp = species
    sp.apply(base_mult or ServerMultipliers())
    st = sp.stats[stat_index]
    if st is None:
        return None
    raw_id = sp.stats_raw[stat_index][2]
    if raw_id == 0:
        return None

    n, ld = points_added, dom_levels_before
    tol = _tolerance(stat_index, value_after) + _tolerance(stat_index, value_before)

    if st.as_percentage:
        # V = Vd * (1 + Ld*x)      x = Id_raw * IdM
        # V_after/V_before = (1 + (Ld+n)x) / (1 + Ld*x)
        ratio = value_after / value_before
        denom = n - (ratio - 1.0) * ld
        if abs(denom) < 1e-12:
            return None
        x = (ratio - 1.0) / denom
        span = (tol / value_before) / (n * raw_id)
    else:
        # V = ... + Ld*x なので差分がそのまま n*x
        x = (value_after - value_before) / n
        span = tol / (n * raw_id)

    idm = x / raw_id
    if not (MULT_MIN <= idm <= MULT_MAX):
        return None
    return idm, abs(span)


# ---------------------------------------------------------------- 刷り込み倍率

def solve_imprint_scale(species, stat_index, value_no_imprint, value_with_imprint,
                        imprint, base_mult=None):
    """同一個体の刷り込み前後の値から BabyImprintingStatScaleMultiplier を出す。

    刷り込み 0% のときと p% のときを比べる (その間にレベルを振らないこと)。
    """
    sp = species
    sp.apply(base_mult or ServerMultipliers())
    im = sp.imprint[stat_index]
    if not im or imprint <= 0 or value_no_imprint <= 0:
        return None
    # V_with / V_without = 1 + im * p * IBM   (加算ボーナス Ta の分だけ厳密には
    # ずれるが、Ta は Iw に比べて十分小さいので実用上は無視できる)
    ratio = value_with_imprint / value_no_imprint
    return (ratio - 1.0) / (im * imprint)


# ---------------------------------------------------------------- 交配時間系

def solve_breeding_multipliers(species, observed):
    """ゲーム内の残り時間表示から交配系の倍率を出す。

    observed の各値は実測秒数:
        incubation : 卵を置いた瞬間の孵化までの秒数
        gestation  : 胎生の出産までの秒数
        maturation : 孵化直後の成体までの秒数
        cuddle     : 刷り込み間隔 (秒)
        mating_cd  : 交配後クールダウン (秒、最短側)
    """
    br = species.breeding
    if not br or not observed:
        return {}
    out = {}
    if observed.get("incubation") and br["incubation"] > 0:
        out["EggHatchSpeedMultiplier"] = br["incubation"] / observed["incubation"]
    if observed.get("gestation") and br["gestation"] > 0:
        out["EggHatchSpeedMultiplier"] = br["gestation"] / observed["gestation"]
    if observed.get("maturation") and br["maturation"] > 0:
        out["BabyMatureSpeedMultiplier"] = br["maturation"] / observed["maturation"]
    if observed.get("cuddle"):
        out["BabyCuddleIntervalMultiplier"] = observed["cuddle"] / (8 * 3600.0)
    if observed.get("mating_cd") and br["cdMin"] > 0:
        out["MatingIntervalMultiplier"] = observed["mating_cd"] / br["cdMin"]
    return out
