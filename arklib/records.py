# -*- coding: utf-8 -*-
"""取り込んだ個体が「記録更新かどうか」を判定する。

    NEW   … ライブラリの今までの最高を **超えた**
    TIE   … 今の最高と **同じ** (最高値の持ち主のひとり)
    NONE  … 最高には届いていない

比べる相手は「同じ種族・同じサーバーの、自分以外の生きている個体」。
自分自身を数えてしまうと、2 回目の取り込みで必ず TIE になってしまうため
除外する (同じ生物を何度エクスポートしても判定が変わらないようにする)。
"""
from . import ark
from .creature import BREEDING_STATS, STATUS_DEAD

NEW = "new"
TIE = "tie"
NONE = ""

# まとめたときの強さの順
RANK = {NEW: 2, TIE: 1, NONE: 0}


class RecordCheck(object):
    def __init__(self, creature, stat_list):
        self.creature = creature
        self.stat_list = list(stat_list)
        self.per_stat = {}        # stat -> NEW / TIE / NONE
        self.previous = {}        # stat -> それまでの最高レベル (居なければ None)
        self.first_of_species = False

    @property
    def overall(self):
        best = NONE
        for v in self.per_stat.values():
            if RANK[v] > RANK[best]:
                best = v
        return best

    @property
    def new_stats(self):
        return [s for s, v in self.per_stat.items() if v == NEW]

    @property
    def tie_stats(self):
        return [s for s, v in self.per_stat.items() if v == TIE]

    def label(self):
        if self.first_of_species:
            return "この種族ははじめて"
        if self.overall == NEW:
            return "自己ベスト更新"
        if self.overall == TIE:
            return "いまの最高と同じ"
        return ""


def check(creature, others, stat_list=None, include_dead=False):
    """others は同種の他個体 (自分を含んでいても除外する)。"""
    stat_list = list(stat_list or BREEDING_STATS)
    # uid はまだ付いていないことがある (保存前に判定するため)。
    # ゲーム内 ID でも弾かないと、取り込み直しのたびに TIE になってしまう。
    pool = [c for c in others
            if c.uid != creature.uid
            and not (creature.ark_id and c.ark_id == creature.ark_id)
            and (include_dead or c.status != STATUS_DEAD)]

    res = RecordCheck(creature, stat_list)
    res.first_of_species = not pool
    for s in stat_list:
        if s == ark.TORPIDITY:
            continue
        levels = [c.bl(s) for c in pool]
        prev = max(levels) if levels else None
        res.previous[s] = prev
        mine = creature.bl(s)
        if prev is None:
            res.per_stat[s] = NONE       # 比べる相手が居ない
        elif mine > prev:
            res.per_stat[s] = NEW
        elif mine == prev and mine > 0:
            res.per_stat[s] = TIE
        else:
            res.per_stat[s] = NONE
    return res
