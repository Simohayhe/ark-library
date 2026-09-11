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

from . import ark, extractor, stats
from .creature import STATE_BRED, STATE_TAMED, STATE_WILD
from .multipliers import IDX_TAMING_MULT

# 逆算した効率を同一視する丸め桁
TE_ROUND = 6
# 返すテイム効率候補の上限
MAX_TE_CANDIDATES = 40


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
                   imprint=0.0, taming_eff=None, game="asa"):
    """表示値からレベルの内訳を割り出す。

    values : {statIndex: 表示値} または長さ 12 のリスト
    戻り値 : ExtractResult
    """
    vals = _as_dict(species, values)
    res = ExtractResult()

    if state == STATE_TAMED and taming_eff is None:
        cands = taming_eff_candidates(species, level, vals, server_multipliers,
                                      imprint, game)
        if not cands:
            res.problems.append("テイム効率の候補が見つかりませんでした")
            return res
        res.notes.append("テイム効率をファイルから取れないため逆算しました")
    else:
        cands = [1.0 if state != STATE_TAMED else taming_eff]

    found = []
    for te in cands:
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
    return res


def taming_eff_candidates(species, level, values, sm, imprint=0.0, game="asa"):
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
        return [1.0]

    wild_totals = _wild_totals(sp, level, values, sm, imprint, game)
    if not wild_totals:
        return []

    probe = dep[0]
    others = dep[1:]
    cands = {}
    for wild_total in wild_totals:
        dom_total = level - 1 - wild_total
        if dom_total < 0:
            continue
        st = sp.stats[probe]
        can_dom = st.inc_dom != 0
        for ld in (range(0, dom_total + 1) if can_dom else (0,)):
            for lw in range(0, wild_total + 1):
                te = _solve_te(sp, probe, values[probe], lw, ld, imprint,
                               sm.imprint_stat_scale)
                if te is None or not (0.0 < te <= 1.0001):
                    continue
                te = min(te, 1.0)
                key = round(te, TE_ROUND)
                if key in cands:
                    continue
                # ほかの効率依存ステータスでも整数レベルが立つかを先に見る
                if not all(_has_integer_levels(sp, s, values[s], te, wild_total,
                                               dom_total, imprint,
                                               sm.imprint_stat_scale)
                           for s in others):
                    continue
                cands[key] = te
                if len(cands) >= MAX_TE_CANDIDATES:
                    break
            if len(cands) >= MAX_TE_CANDIDATES:
                break
    # 効率の高い順に試す (ふつうは高い方が正解)
    return sorted(cands.values(), reverse=True)


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


def _has_integer_levels(sp, s, target, te, wild_total, dom_total, imprint,
                        imprint_scale):
    """効率 te のもとで、このステータスに整数レベルの組み合わせがあるか。"""
    st = sp.stats[s]
    tol = stats.displayed_aberration(target, ark.precision(s))
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
