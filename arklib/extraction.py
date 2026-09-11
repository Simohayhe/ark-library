# -*- coding: utf-8 -*-
"""取り込み用の逆算ラッパー。

標準の「恐竜のエクスポート」にはレベルの内訳が入っていないので、表示値から
野生 / 強化レベルを割り出す (arklib.extractor)。そのうえで 2 点面倒を見る。

1. **テイム効率が書かれていない**
   交配産は効率 100% 固定なので問題ないが、テイム個体は効率が分からない。
   効率は「テイム時乗算ボーナス (Affinity) を持つステータス」(ふつう体力と
   近接攻撃力) にしか効かないので、そのステータスの表示値から逆に効率を
   求められる。レベルを仮定すれば効率は割り算ひとつで出るので、候補を
   作って総当たりで検証する。

2. **変異レベルの内訳が分からない**
   表示値では野生レベルと変異レベルが区別できない。親がライブラリに居れば
   「親より 2 レベル高い = そのステータスに変異」と分かるので、そこから
   野生 / 変異に振り分ける (arklib.breeding.infer_mutations)。
"""
import math
import time

from . import ark, extractor, stats
from .creature import STATE_BRED, STATE_TAMED, STATE_WILD
from .multipliers import IDX_TAMING_MULT

# 逆算した効率を同一視する丸め桁
TE_ROUND = 6
# 候補が無限に増えないための保険。ふつうここまで行かない
MAX_TE_CANDIDATES = 20000
# 「テイム時のレベルの増え方」と噛み合わない候補を試す上限。
# 噛み合う候補で解けたら、そちらは一切見ない
MAX_UNLIKELY_TE = 150
# 逆算にかけてよい時間 (秒)。強化レベルを大量に振った個体は候補が増えるので、
# ここで頭打ちにする。取り込みは 0.2 秒ごとに回るので止まって見えないように
TIME_BUDGET = 1.2


class ExtractResult(object):
    def __init__(self):
        self.ok = False
        self.levels_wild = [0] * ark.STATS_COUNT
        self.levels_dom = [0] * ark.STATS_COUNT
        self.wild_total = 0
        self.dom_total = 0
        self.taming_eff = None
        self.solutions = []        # 候補が複数あるときの全解 [(levels_wild, levels_dom, te), ...]
        self.ambiguous = False
        self.problems = []
        self.notes = []

    @property
    def solution_count(self):
        return len(self.solutions)

    def describe(self):
        if not self.ok:
            return "逆算できませんでした: " + " / ".join(self.problems)
        head = "野生レベル計 %d / 強化レベル計 %d" % (self.wild_total, self.dom_total)
        if self.taming_eff is not None:
            head += " / テイム効率 %.1f%%" % (self.taming_eff * 100)
        if self.ambiguous:
            head += "  (候補 %d 通り)" % self.solution_count
        return head


def extract_levels(species, level, values, server_multipliers, state=STATE_BRED,
                   imprint=0.0, taming_eff=None, game="asa", known_wild=None,
                   budget=None):
    """表示値からレベルの内訳を割り出す。

    values     : {statIndex: 表示値} または長さ 12 のリスト
    known_wild : 前に同じ個体を取り込んでいるなら、そのときの野生レベル。
                 野生レベルはテイム後に変わらないので、これが分かっていると
                 テイム効率の候補が一気に絞れる (強化レベルを振った個体に効く)
    戻り値     : ExtractResult
    """
    vals = _as_dict(species, values)
    res = ExtractResult()

    if state == STATE_TAMED and taming_eff is None:
        cands = taming_eff_candidates(species, level, vals, server_multipliers,
                                      imprint, game, known_wild=known_wild)
        if not cands:
            res.problems.append("テイム効率の候補が見つかりませんでした")
            return res
        res.notes.append("テイム効率をファイルから取れないため逆算しました")
    else:
        cands = [(1.0 if state != STATE_TAMED else taming_eff, True)]

    found = []
    budget = TIME_BUDGET if budget is None else budget
    started = time.perf_counter()
    stopped_early = False
    for te, likely in cands:
        # 「ありそうな効率」で解けたなら、それ以外は見ない。
        # 混ぜると、たまたま数字が合うだけの効率まで候補に入ってしまう
        if found and not likely:
            break
        if time.perf_counter() - started > budget:
            stopped_early = True
            break
        ex = extractor.extract(species, level, vals, server_multipliers,
                               state=state, taming_eff=te, imprint=imprint,
                               game=game)
        if not ex.ok:
            continue
        for sol in ex.solutions:
            lw = [0] * ark.STATS_COUNT
            ld = [0] * ark.STATS_COUNT
            for s, (w, d) in sol.items():
                lw[s] = w
                ld[s] = d
            lw[ark.TORPIDITY] = ex.wild_total
            found.append((lw, ld, te, ex.wild_total, ex.dom_total))
        if found and state != STATE_TAMED:
            break

    if not found:
        res.problems.append("レベルの組み合わせが見つかりませんでした "
                            "(サーバー倍率・刷り込み率の設定を確認してください)")
        if state == STATE_TAMED and level - 1 > 0:
            res.problems.append(
                "テイム個体に強化レベルをたくさん振っていると、表示値だけでは"
                "決まらないことがあります。テイム直後に一度エクスポートしておくか、"
                "Export Gun を使うと確実です")
        return res

    # 同じレベル配分に落ちる解をまとめる
    uniq = {}
    for lw, ld, te, wt, dt in found:
        key = (tuple(lw), tuple(ld))
        if key not in uniq:
            uniq[key] = (lw, ld, te, wt, dt)

    sols = list(uniq.values())
    # 効率が高い = きれいにテイムできた解を先に見せる
    sols.sort(key=lambda t: (-(t[2] or 0), sum(t[1])))

    res.ok = True
    res.solutions = [(lw, ld, te) for lw, ld, te, _, _ in sols]
    res.ambiguous = len(sols) > 1
    lw, ld, te, wt, dt = sols[0]
    res.levels_wild = lw
    res.levels_dom = ld
    res.taming_eff = te
    res.wild_total = wt
    res.dom_total = dt
    if res.ambiguous:
        res.notes.append("表示値だけでは一つに決まらず %d 通りの候補があります"
                         % len(sols))
    if stopped_early:
        res.notes.append("候補が多いので途中で打ち切りました "
                         "(強化レベルを振った個体は決まりにくい)")
    return res


def taming_eff_candidates(species, level, values, sm, imprint=0.0, game="asa",
                          known_wild=None):
    """テイム効率の候補を作る。

    効率が効くステータス (Affinity != 0) の表示値から、レベルを仮定して
    効率を逆算する。効率についてステータス値は一次式なので、te=0 と te=1 の
    2 点を計算すれば逆向きに解ける。
    """
    sp = species
    sp.apply(sm, game)

    dep = [s for s in sp.displayed_stat_indices()
           if s != ark.TORPIDITY and sp.stats[s] is not None
           and sp.stats[s].mult_affinity > 0 and s in values]
    if not dep:
        # 効率が表示値に出ない種族。効率は決められないので 100% とみなす
        return [(1.0, True)]

    wild_totals = _wild_totals(sp, level, values, sm, imprint, game)
    if not wild_totals:
        return []

    probe = dep[0]
    others = dep[1:]
    cands = {}       # 丸めた効率 -> (効率, 野生レベル合計)
    for wild_total in wild_totals:
        dom_total = level - 1 - wild_total
        if dom_total < 0:
            continue
        st = sp.stats[probe]
        can_dom = st.inc_dom != 0
        # 前回の野生レベルが分かっているなら、そこだけ見ればいい
        lw_range = (range(0, wild_total + 1) if not known_wild
                    else [known_wild[probe]])
        for ld in (range(0, dom_total + 1) if can_dom else (0,)):
            for lw in lw_range:
                te = _solve_te(sp, probe, values[probe], lw, ld, imprint,
                               sm.imprint_stat_scale)
                if te is None or not (0.0 < te <= 1.0001):
                    continue
                te = min(te, 1.0)
                key = round(te, TE_ROUND)
                if key in cands:
                    continue
                # ほかの効率依存ステータスでも整数レベルが立つかを先に見る。
                # このステータスで使ったぶんは残らないので、上限を減らして
                # 渡す (候補がぐっと減る)
                if not all(_has_integer_levels(sp, s, values[s], te,
                                               wild_total - lw, dom_total - ld,
                                               imprint, sm.imprint_stat_scale)
                           for s in others):
                    continue
                cands[key] = (te, wild_total)
                if len(cands) >= MAX_TE_CANDIDATES:
                    break
            if len(cands) >= MAX_TE_CANDIDATES:
                break

    # テイムしたときのレベルの増え方と噛み合うものを先に試す。
    # 噛み合う候補があれば、そうでないものは見ない (ここを混ぜると、
    # たまたま数字が合うだけの間違った効率を拾ってしまう)
    likely, unlikely = [], []
    for te, wild_total in cands.values():
        (likely if tame_level_fits(wild_total, te) else unlikely).append(te)
    likely.sort(reverse=True)
    unlikely.sort(reverse=True)
    return ([(te, True) for te in likely]
            + [(te, False) for te in unlikely[:MAX_UNLIKELY_TE]])


def tame_level_fits(wild_total, te):
    """テイム後の野生レベル合計が、その効率で説明できるか。

    ARK では、レベル L の野生個体をテイムすると

        テイム後のレベル = int(L * (1 + 0.5 * テイム効率))

    になる (ARKStatsExtractor/DummyCreatures.cs と同じ式)。増えたぶんは
    野生レベルとして各ステータスにばらまかれるので、**テイム後の野生レベル
    合計と効率の組み合わせには決まった形がある**。これに合わない効率は、
    たまたま数字が合っただけの可能性が高い。
    """
    after = wild_total + 1                     # 表示レベル = 1 + 野生レベル合計
    for before in range(1, after + 1):
        got = int(before * (1.0 + 0.5 * te))
        if got == after:
            return True
        if got > after:
            break
    return False


# ---- 内部 --------------------------------------------------------------


def _as_dict(species, values):
    if isinstance(values, dict):
        return {int(k): float(v) for k, v in values.items() if v is not None}
    out = {}
    for s, v in enumerate(values):
        if v is None:
            continue
        if species.stats[s] is None and s != ark.TORPIDITY:
            continue
        out[s] = float(v)
    return out


def _wild_totals(sp, level, values, sm, imprint, game):
    ex = extractor.Extraction(sp, level, values, STATE_TAMED, 1.0, imprint,
                              sm.imprint_stat_scale)
    return extractor._total_wild_levels(sp, ex)


def _calc(sp, s, lw, ld, te, imprint, imprint_scale):
    return stats.calc_value(sp, s, lw, 0, ld, True, taming_eff=te,
                            imprinting_bonus=imprint,
                            imprint_stat_scale=imprint_scale,
                            round_to_ingame=False)


def _solve_te(sp, s, target, lw, ld, imprint, imprint_scale):
    v0 = _calc(sp, s, lw, ld, 0.0, imprint, imprint_scale)
    v1 = _calc(sp, s, lw, ld, 1.0, imprint, imprint_scale)
    span = v1 - v0
    if abs(span) < 1e-12:
        return None
    return (target - v0) / span


_TOL_CACHE = {}


def _tolerance(s, target):
    """表示値の丸め誤差の幅。同じ値で何度も呼ばれるので覚えておく。"""
    key = (s, target)
    got = _TOL_CACHE.get(key)
    if got is None:
        got = stats.displayed_aberration(target, ark.precision(s))
        if len(_TOL_CACHE) > 4096:
            _TOL_CACHE.clear()
        _TOL_CACHE[key] = got
    return got


def _has_integer_levels(sp, s, target, te, wild_total, dom_total, imprint,
                        imprint_scale):
    """効率 te のもとで、このステータスに整数レベルの組み合わせがあるか。"""
    if wild_total < 0 or dom_total < 0:
        return False
    st = sp.stats[s]
    tol = _tolerance(s, target)
    can_dom = st.inc_dom != 0
    for ld in (range(0, dom_total + 1) if can_dom else (0,)):
        v0 = _calc(sp, s, 0, ld, te, imprint, imprint_scale)
        v1 = _calc(sp, s, 1, ld, te, imprint, imprint_scale)
        slope = v1 - v0
        if abs(slope) < 1e-12:
            if abs(target - v0) <= tol:
                return True
            continue
        x = (target - v0) / slope
        span = tol / abs(slope)
        for lw in range(int(math.floor(x - span)), int(math.ceil(x + span)) + 1):
            if 0 <= lw <= wild_total and abs(v0 + lw * slope - target) <= tol:
                return True
    return False
