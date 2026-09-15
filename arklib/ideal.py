# -*- coding: utf-8 -*-
"""理想個体 (目標) と、そこまでの近さ。

種族ごとに「こういう個体が欲しい」を一つ決めておくと、手持ちがそれに何 %
近いかが出る。交配の途中で「あとどれが足りないのか」を見失わないための機能。

採点の考え方
------------
    ステータス (目標が 1 以上)  足りないぶんだけ % が下がる。
                                40/50 なら 80%。遠いほど低い。
    ステータス (目標が 0)       ゼロ狙い。0 なら満点。離れるほど下がる。
                                下がり方の基準は「群れでいちばん悪い値」。
    色                          同じ色かどうかだけ。色に「近い・遠い」は
                                無いので、違えば 0、合っていれば満点。

全体の % は、狙っている項目 (ステータス + 色) の平均。
"""
from . import ark
from . import colors as arkcolors

KIND_STAT = "stat"
KIND_COLOR = "color"

# ゼロ狙いの基準が分からないときの目安レベル
DEFAULT_ZERO_REF = 20


class Item(object):
    """採点の 1 項目。"""

    __slots__ = ("kind", "index", "label", "want", "have", "score")

    def __init__(self, kind, index, label, want, have, score):
        self.kind = kind
        self.index = index
        self.label = label
        self.want = want
        self.have = have
        self.score = score

    @property
    def ok(self):
        return self.score >= 0.999

    @property
    def text(self):
        """画面に出す「いま / 目標」。"""
        if self.kind == KIND_COLOR:
            if self.ok:
                return "%s 一致" % self.label
            return "%s %s → %s" % (self.label,
                                   arkcolors.label_of(self.have),
                                   arkcolors.label_of(self.want))
        return "%s %d/%d" % (self.label, self.have, self.want)

    def __repr__(self):
        return "<Item %s %.2f>" % (self.label, self.score)


class Score(object):
    def __init__(self, items):
        self.items = list(items)

    @property
    def percent(self):
        if not self.items:
            return 0.0
        return 100.0 * sum(i.score for i in self.items) / len(self.items)

    @property
    def reached(self):
        return bool(self.items) and all(i.ok for i in self.items)

    @property
    def short(self):
        """まだ足りない項目。"""
        return [i for i in self.items if not i.ok]

    def summary(self):
        if not self.items:
            return "理想個体 未設定"
        if self.reached:
            return "目標達成 (100%)"
        return "到達率 %.0f%%  未達: %s" % (
            self.percent, "、".join(i.text for i in self.short))

    def __repr__(self):
        return "<Score %.0f%%>" % self.percent


class Ideal(object):
    """狙っている個体の姿。

    stats  {ステータス番号: 目標レベル}   0 を入れるとゼロ狙い
    colors {色領域: 色 ID}
    """

    def __init__(self, stats=None, colors=None, note=""):
        self.stats = {}
        self.colors = {}
        self.note = note or ""
        for k, v in (stats or {}).items():
            try:
                self.stats[int(k)] = max(0, int(v))
            except (TypeError, ValueError):
                continue
        for k, v in (colors or {}).items():
            try:
                cid = int(v)
            except (TypeError, ValueError):
                continue
            if cid > 0:
                self.colors[int(k)] = cid

    # ---- 中身 ----------------------------------------------------------

    @property
    def empty(self):
        return not self.stats and not self.colors

    def __len__(self):
        return len(self.stats) + len(self.colors)

    def to_dict(self):
        return {"stats": {str(k): v for k, v in self.stats.items()},
                "colors": {str(k): v for k, v in self.colors.items()},
                "note": self.note}

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(d.get("stats"), d.get("colors"), d.get("note"))

    @classmethod
    def from_creature(cls, creature, stat_list=None, regions=None):
        """いまある個体をそのまま理想にする。"""
        stat_list = list(stat_list or [])
        stats = {s: creature.bl(s) for s in stat_list}
        colors = {}
        for i in (regions or []):
            cid = creature.colors[i] if i < len(creature.colors) else 0
            if cid:
                colors[i] = cid
        return cls(stats, colors)

    def base_level(self):
        """この理想どおりの個体の素レベル。"""
        return 1 + sum(self.stats.values())

    def describe(self, species_bp=None):
        parts = []
        for s in sorted(self.stats):
            parts.append("%s%d" % (_short(s), self.stats[s]))
        for i in sorted(self.colors):
            name = (arkcolors.region_name(species_bp, i) if species_bp
                    else "領域%d" % i)
            parts.append("%s=%s" % (name, arkcolors.label_of(self.colors[i])))
        return " ".join(parts) or "(未設定)"

    # ---- 採点 ----------------------------------------------------------

    def score(self, creature, refs=None, species_bp=None):
        """個体が理想に何 % 近いか。"""
        return Score(self._items(_levels_of(creature), creature.colors,
                                 refs, species_bp))

    def score_levels(self, levels, colors=None, refs=None, species_bp=None,
                     stats_only=False):
        """レベルの並びだけで採点する (これから作る子の評価など)。

        stats_only=True なら色は数えない。子の色は親しだいで決まらないため。
        """
        items = self._items(levels, colors, refs, species_bp,
                            stats_only=stats_only)
        return Score(items)

    def _items(self, levels, colors, refs, species_bp, stats_only=False):
        refs = refs or {}
        items = []
        for s in sorted(self.stats):
            want = self.stats[s]
            have = int(levels.get(s, 0) if hasattr(levels, "get") else levels[s])
            items.append(Item(KIND_STAT, s, _short(s), want, have,
                              _stat_score(want, have, refs.get(s))))
        if stats_only:
            return items
        colors = list(colors or [])
        for i in sorted(self.colors):
            want = self.colors[i]
            have = colors[i] if i < len(colors) else 0
            label = (arkcolors.region_name(species_bp, i) if species_bp
                     else "領域%d" % i)
            # 色に「近い」は無い。同じ ID かどうかだけ
            items.append(Item(KIND_COLOR, i, label, want, have,
                              1.0 if have == want else 0.0))
        return items


def _levels_of(creature):
    return {s: creature.bl(s) for s in range(ark.STATS_COUNT)}


def _stat_score(want, have, ref=None):
    if want > 0:
        return min(1.0, max(0.0, float(have) / want))
    # ゼロ狙い。0 なら満点、群れでいちばん悪い値まで行くと 0 点
    if have <= 0:
        return 1.0
    base = ref if (ref and ref > 0) else DEFAULT_ZERO_REF
    if have >= base:
        return 0.0
    return max(0.0, 1.0 - float(have) / base)


def _short(s):
    from .ark import NAMES_JA
    return {ark.HEALTH: "体力", ark.STAMINA: "スタミナ", ark.OXYGEN: "酸素",
            ark.FOOD: "食料", ark.WEIGHT: "重量", ark.MELEE: "近接",
            ark.SPEED: "速度", ark.CRAFTING_SPEED: "作成",
            ark.TEMPERATURE_FORTITUDE: "温耐"}.get(s, NAMES_JA[s])


# ---- 群れ全体 ----------------------------------------------------------


def refs_from(creatures, stat_list=None):
    """ゼロ狙いの採点に使う「いちばん悪い値」。"""
    out = {}
    for c in creatures or []:
        for s in (stat_list or range(ark.STATS_COUNT)):
            lv = c.bl(s)
            if lv > out.get(s, 0):
                out[s] = lv
    return out


def rank(creatures, ideal, refs=None, species_bp=None):
    """理想に近い順。[(Score, 個体)] を返す。"""
    if ideal is None or ideal.empty:
        return []
    refs = refs if refs is not None else refs_from(creatures)
    scored = [(ideal.score(c, refs, species_bp), c) for c in creatures or []]
    scored.sort(key=lambda t: -t[0].percent)
    return scored


# ---- 保存 --------------------------------------------------------------


def setting_key(species_bp):
    return "ideal_%s" % species_bp


def load(library, species_bp):
    if not species_bp:
        return Ideal()
    return Ideal.from_dict(library.get_setting(setting_key(species_bp), None))


def save(library, species_bp, ideal):
    if not species_bp:
        return
    if ideal is None or ideal.empty:
        library.set_setting(setting_key(species_bp), None)
        return
    library.set_setting(setting_key(species_bp), ideal.to_dict())
