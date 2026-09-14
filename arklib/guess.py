# -*- coding: utf-8 -*-
"""知らない種族を当てる。

Mod の生物は、公開されている種族データが無いと取り込めない。ただ Mod の生物には
**既存の生物をそのまま使い回したもの (見た目だけ違う)** がかなり多い。そういう
個体は、既存の種族の計算式に当てはめるとぴったり解ける。

ここでは全種族を総当たりして「その計算式で矛盾なくレベルが立つ種族」を探す。

    候補が 1 つに絞れたら … ほぼ確実にその種族の使い回し
    複数出たら          … 見た目や用途から人が選ぶ (レベルが低いと絞りきれない)
    0 件               … 本当に独自のステータスを持つ生物。データが要る

当てた結果は「読み替え」として覚えておき、次からは自動で同じ種族として扱う。
"""
import time

from . import ark, extraction
from .creature import STATE_BRED, STATE_TAMED

# 1 種族あたりにかけてよい秒数と、全体の打ち切り。
# 総当たりは 400 種族ぶん回るので、1 種族に既定の 1.2 秒を許すと最悪
# 8 分かかってしまう。当てるだけなら浅く探せば十分
PER_SPECIES_BUDGET = 0.2
TOTAL_BUDGET = 6.0


# %表示のステータスは「100% からの増分」で入っているので、1.0 は「持っていない」
OFFSET_STATS = frozenset((ark.MELEE, ark.SPEED, ark.TEMPERATURE_FORTITUDE,
                          ark.CRAFTING_SPEED))


def meaningful_stats(values):
    """エクスポートに実際の値が入っているステータスだけを拾う。

    使っていないステータスは 0 (%表示のものは 100% = 1.0) で埋められている。
    そこを外さないと「持っているステータスの顔ぶれ」で絞り込めない。
    """
    out = set()
    for s, v in values.items():
        if s == ark.TORPIDITY or v is None:
            continue
        if s in OFFSET_STATS:
            if abs(float(v) - 1.0) > 1e-9:
                out.add(s)
        elif v:
            out.add(s)
    return out


class Guess(object):
    def __init__(self, species, result):
        self.species = species
        self.result = result

    @property
    def solutions(self):
        return self.result.solution_count

    @property
    def unique(self):
        return self.result.solution_count == 1

    @property
    def wild_total(self):
        return self.result.wild_total

    def __repr__(self):
        return "<Guess %s x%d>" % (self.species.display_name, self.solutions)


def guess_species(species_db, level, values, server_multipliers,
                  state=STATE_TAMED, imprint=0.0, game="asa", limit=10,
                  asa_only=True, breedable_only=True, budget=None):
    """表示値に当てはまる種族を探す。当てはまり方が良い順に返す。

    values は {statIndex: 表示値}。%表示のものは小数で (246.3% → 2.463)。
    budget は総当たり全体にかけてよい秒数 (既定 TOTAL_BUDGET)。
    """
    used = meaningful_stats(values)
    out = []
    deadline = time.perf_counter() + (TOTAL_BUDGET if budget is None else budget)
    for sp in species_db.all:
        if time.perf_counter() > deadline:
            break
        if asa_only and not sp.in_asa:
            continue
        if breedable_only and not sp.is_breedable():
            continue
        # ここで顔ぶれによる足切りはしない。エクスポートには使っていない
        # ステータスも 0 で埋まっていて、当てにならないため。
        # 実際に逆算が通るかどうかだけで判断する
        try:
            res = extraction.extract_levels(
                sp, level, values, server_multipliers, state=state,
                imprint=imprint,
                taming_eff=1.0 if state != STATE_TAMED else None, game=game,
                budget=PER_SPECIES_BUDGET)
        except Exception:
            continue
        if res.ok:
            out.append(Guess(sp, res))

    # 解が一つに決まるものを優先し、次に「表示するステータスの顔ぶれ」が
    # 近いものを上に持ってくる
    def rank(g):
        shown = set(s for s in g.species.displayed_stat_indices()
                    if s != ark.TORPIDITY)
        return (g.solutions, len(shown ^ (used & shown)) + len(shown - used),
                g.species.display_name)

    out.sort(key=rank)
    return out[:limit] if limit else out


def describe(guesses, max_lines=8):
    if not guesses:
        return "当てはまる種族が見つかりませんでした。"
    lines = ["当てはまりそうな種族:"]
    for g in guesses[:max_lines]:
        mark = "◎" if g.unique else "○"
        lines.append("  %s %-22s (解 %d 通り / 野生レベル計 %s)"
                     % (mark, g.species.display_name, g.solutions, g.wild_total))
    if len(guesses) > max_lines:
        lines.append("  ... 他 %d 件" % (len(guesses) - max_lines))
    return "\n".join(lines)
