# -*- coding: utf-8 -*-
"""ステータス逆算。

ゲーム内の表示値から「野生レベル / 強化レベル」の内訳を割り出す。
ARK Smart Breeding の中核機能で、ARKStatsExtractor/Extraction.cs にあたる。

考え方
------
サーバー倍率が確定していれば、ステータス値は

    V = f(Lw, Ld)      Lw について一次、Ld についても一次

なので、Ld を仮定すれば Lw は割り算ひとつで出る。あとは

    ・気絶値から「野生レベルの合計」が分かる
    ・レベル = 1 + 野生レベル合計 + 強化レベル合計

という 2 つの制約で、ステータスごとの候補の組み合わせを絞り込む。
解が一つに定まらないことは普通にあるので、その場合は候補を全部返す。

変異レベルについて
------------------
ASA の変異レベルは野生レベルと同じ伸び方をする (mutationMult が既定 1) ため、
表示値だけでは野生レベルと区別できない。ここでは合算して「野生レベル」として
返し、変異の内訳は血統側 (変異カウンタ) で管理する。
"""
import math

from . import ark, stats
from .multipliers import ServerMultipliers

# 組み合わせ探索で返す解の上限
MAX_SOLUTIONS = 50


class Extraction(object):
    def __init__(self, species, level, values, state="bred", taming_eff=1.0,
                 imprint=0.0, imprint_scale=1.0):
        self.species = species
        self.level = level
        self.values = dict(values)
        self.state = state
        self.taming_eff = 1.0 if state == "bred" else taming_eff
        self.imprint = imprint
        self.imprint_scale = imprint_scale

        self.wild_total = None
        self.dom_total = None
        self.solutions = []      # [{stat: (Lw, Ld)}, ...]
        self.problems = []
        self.notes = []

    # ---- 結果の見かた --------------------------------------------------

    @property
    def ok(self):
        return bool(self.solutions)

    @property
    def unique(self):
        return len(self.solutions) == 1

    @property
    def domesticated(self):
        return self.state != "wild"

    def best(self):
        return self.solutions[0] if self.solutions else None

    def describe(self):
        sp = self.species
        out = []
        if not self.ok:
            out.append("逆算できませんでした。")
            out.extend("  ! " + p for p in self.problems)
            return "\n".join(out)

        out.append("%s Lv%d  野生レベル計 %d / 強化レベル計 %d"
                   % (sp.display_name, self.level, self.wild_total, self.dom_total))
        if not self.unique:
            out.append("解が %d 通りあります (表示値だけでは一つに決まらない)。"
                       % len(self.solutions))
        for n, sol in enumerate(self.solutions[:5], 1):
            if len(self.solutions) > 1:
                out.append("  [解 %d]" % n)
            for s in sp.displayed_stat_indices():
                if s not in sol:
                    continue
                lw, ld = sol[s]
                v = self.values.get(s)
                out.append("    %-10s %10s   野生 %3d  強化 %3d"
                           % (sp.stat_name(s), stats.format_value(s, v), lw, ld))
            tor = self.values.get(ark.TORPIDITY)
            if tor is not None:
                out.append("    %-10s %10s   野生 %3d"
                           % (sp.stat_name(ark.TORPIDITY),
                              stats.format_value(ark.TORPIDITY, tor), self.wild_total))
        if len(self.solutions) > 5:
            out.append("  ... 他 %d 通り" % (len(self.solutions) - 5))
        out.extend("  * " + n for n in self.notes)
        return "\n".join(out)


def _calc(sp, s, ex, lw, ld):
    return stats.calc_value(sp, s, lw, 0, ld, ex.domesticated,
                            taming_eff=ex.taming_eff,
                            imprinting_bonus=ex.imprint,
                            imprint_stat_scale=ex.imprint_scale,
                            round_to_ingame=False)


_TOL_CACHE = {}


def _tolerance(s, value):
    """表示値の丸め誤差の幅。同じ値で何万回も呼ばれるので覚えておく。"""
    key = (s, value)
    got = _TOL_CACHE.get(key)
    if got is None:
        got = stats.displayed_aberration(value, ark.precision(s))
        if len(_TOL_CACHE) > 4096:
            _TOL_CACHE.clear()
        _TOL_CACHE[key] = got
    return got


def _wild_levels_for(sp, ex, s, ld, cap):
    """強化レベルを ld と仮定したときに、観測値と整合する野生レベルを列挙する。"""
    target = ex.values[s]
    tol = _tolerance(s, target)
    v0 = _calc(sp, s, ex, 0, ld)
    v1 = _calc(sp, s, ex, 1, ld)
    slope = v1 - v0
    if abs(slope) < 1e-12:
        # このステータスは野生レベルで動かない
        return list(range(0, cap + 1)) if abs(target - v0) <= tol else []
    x = (target - v0) / slope
    span = tol / abs(slope)
    out = []
    for lw in range(int(math.floor(x - span)), int(math.ceil(x + span)) + 1):
        if 0 <= lw <= cap and abs(v0 + lw * slope - target) <= tol:
            out.append(lw)
    return out


def _total_wild_levels(sp, ex):
    """気絶値から野生レベルの合計を出す。"""
    s = ark.TORPIDITY
    if s not in ex.values or sp.stats[s] is None:
        return []
    cap = max(ex.level, 1) * 2 + 10
    return _wild_levels_for(sp, ex, s, 0, cap)


def _search(options, wild_total, dom_total, limit=MAX_SOLUTIONS):
    """各ステータスの (Lw, Ld) 候補から、両方の合計が一致する組を全部探す。

    options: [(stat, [(lw, ld), ...]), ...]
    """
    n = len(options)
    # 候補が少ないステータスから決めていくと枝が早く枯れる
    order = sorted(range(n), key=lambda i: len(options[i][1]))

    # i 番目以降で最低限積み上がる量 (枝刈り用)
    min_w = [0] * (n + 1)
    min_d = [0] * (n + 1)
    max_w = [0] * (n + 1)
    max_d = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        combos = options[order[i]][1]
        min_w[i] = min_w[i + 1] + min(c[0] for c in combos)
        min_d[i] = min_d[i + 1] + min(c[1] for c in combos)
        max_w[i] = max_w[i + 1] + max(c[0] for c in combos)
        max_d[i] = max_d[i + 1] + max(c[1] for c in combos)

    solutions = []
    chosen = [None] * n

    def rec(i, aw, ad):
        if len(solutions) >= limit:
            return
        if aw + min_w[i] > wild_total or ad + min_d[i] > dom_total:
            return
        if aw + max_w[i] < wild_total or ad + max_d[i] < dom_total:
            return
        if i == n:
            if aw == wild_total and ad == dom_total:
                solutions.append({options[k][0]: chosen[k] for k in range(n)})
            return
        idx = order[i]
        for lw, ld in options[idx][1]:
            chosen[idx] = (lw, ld)
            rec(i + 1, aw + lw, ad + ld)
            if len(solutions) >= limit:
                return
        chosen[idx] = None

    rec(0, 0, 0)
    return solutions


def extract(species, level, values, server_multipliers=None, state="bred",
            taming_eff=1.0, imprint=0.0, game="asa"):
    """ステータスの表示値から野生 / 強化レベルの内訳を割り出す。

    species : Species
    level   : 表示レベル
    values  : {statIndex: 表示値}。%表示のものは小数で (125.8% → 1.258)
    state   : 'bred' / 'tamed' / 'wild'
    """
    sm = server_multipliers or ServerMultipliers()
    sp = species
    sp.apply(sm, game)

    ex = Extraction(sp, level, values, state, taming_eff, imprint,
                    sm.imprint_stat_scale)

    if state == "tamed" and taming_eff is None:
        ex.problems.append("テイム効率が不明です。テイム直後に表示される値を入れてください")
        return ex

    # --- 野生レベルの合計 (気絶値から) --------------------------------
    totals = _total_wild_levels(sp, ex)
    if not totals:
        ex.problems.append("気絶値から野生レベルの合計を出せません。"
                           "気絶値の入力か、サーバー倍率の設定を確認してください")
        return ex

    # --- レベル配分の候補を作る ---------------------------------------
    lev_stats = [s for s in sp.displayed_stat_indices()
                 if s != ark.TORPIDITY and s in ex.values and sp.stats[s] is not None]
    if not lev_stats:
        ex.problems.append("ステータスの入力がありません")
        return ex

    all_solutions = []
    used_total = None
    for wild_total in totals:
        dom_total = level - 1 - wild_total
        if dom_total < 0:
            continue
        if not ex.domesticated and dom_total != 0:
            continue

        options = []
        broke = False
        for s in lev_stats:
            st = sp.stats[s]
            can_wild = sp.can_have_wild_levels(s)
            can_dom = ex.domesticated and st.inc_dom != 0
            combos = []
            dom_range = range(0, dom_total + 1) if can_dom else (0,)
            for ld in dom_range:
                cap = wild_total if can_wild else 0
                for lw in _wild_levels_for(sp, ex, s, ld, cap):
                    combos.append((lw, ld))
            if not combos:
                broke = True
                ex.problems.append(
                    "%s の値 %s に合うレベルの組み合わせがありません"
                    % (sp.stat_name(s), stats.format_value(s, ex.values[s])))
                break
            options.append((s, combos))
        if broke:
            continue

        sols = _search(options, wild_total, dom_total)
        if sols:
            all_solutions = sols
            used_total = (wild_total, dom_total)
            break

    if not all_solutions:
        if not ex.problems:
            ex.problems.append(
                "レベルの合計が合いません。刷り込み%・テイム効率・"
                "サーバー倍率のいずれかがずれている可能性があります")
        return ex

    ex.wild_total, ex.dom_total = used_total
    ex.solutions = all_solutions
    if len(totals) > 1:
        ex.notes.append("気絶値から求めた野生レベル合計に幅があります (%s)。"
                        "%d として解きました" % (totals, ex.wild_total))
    if len(all_solutions) >= MAX_SOLUTIONS:
        ex.notes.append("解が多すぎるため %d 通りで打ち切りました" % MAX_SOLUTIONS)
    return ex


def levels_to_values(species, levels_wild, levels_dom, server_multipliers=None,
                     state="bred", taming_eff=1.0, imprint=0.0,
                     levels_mut=None, game="asa"):
    """逆算の検算用。レベルの内訳から表示値を作り直す。"""
    sm = server_multipliers or ServerMultipliers()
    sp = species
    sp.apply(sm, game)
    wild_total = sum(levels_wild.values()) + sum((levels_mut or {}).values())
    out = {}
    for s in sp.displayed_stat_indices() + [ark.TORPIDITY]:
        if sp.stats[s] is None:
            continue
        lw = wild_total if s == ark.TORPIDITY else levels_wild.get(s, 0)
        lm = 0 if s == ark.TORPIDITY else (levels_mut or {}).get(s, 0)
        ld = levels_dom.get(s, 0)
        out[s] = stats.calc_value(sp, s, lw, lm, ld, state != "wild",
                                  taming_eff=taming_eff,
                                  imprinting_bonus=imprint,
                                  imprint_stat_scale=sm.imprint_stat_scale)
    return out
