# -*- coding: utf-8 -*-
"""ARK のステータス定義まわりの定数。

ARKStatsExtractor/ARKBreedingStats/Ark.cs の Stats クラスに対応する。
"""

STATS_COUNT = 12

HEALTH = 0
STAMINA = 1
TORPIDITY = 2
OXYGEN = 3
FOOD = 4
WATER = 5
TEMPERATURE = 6
WEIGHT = 7
MELEE = 8
SPEED = 9
TEMPERATURE_FORTITUDE = 10
CRAFTING_SPEED = 11

# ゲーム内のステータス表示順 (Ark.cs の StatsDisplayOrder 相当)
DISPLAY_ORDER = [HEALTH, STAMINA, OXYGEN, FOOD, WEIGHT, MELEE, SPEED, TORPIDITY]

NAMES_EN = [
    "Health", "Stamina", "Torpidity", "Oxygen", "Food", "Water",
    "Temperature", "Weight", "Melee Damage", "Movement Speed",
    "Temperature Fortitude", "Crafting Speed",
]

NAMES_JA = [
    "体力", "スタミナ", "気絶値", "酸素量", "食料", "水分",
    "温度", "重量", "近接攻撃力", "移動速度",
    "温度耐性", "作成速度",
]

# 発光生物 (Bulbdog 等) はステータスの意味が変わる。species.statNames の上書き用。
_PERCENT_STATS = frozenset((MELEE, SPEED, TEMPERATURE_FORTITUDE, CRAFTING_SPEED))


def is_percentage(stat_index):
    """割合表示 (%) のステータスか。"""
    return stat_index in _PERCENT_STATS


def precision(stat_index):
    """ゲーム内表示の小数点以下桁数。%表示のものは 0.1% 単位なので 3 桁。"""
    return 3 if is_percentage(stat_index) else 1


def displayed_decimals(stat_index):
    """入力欄に出す桁数 (%表示は 100 倍した値で 1 桁)。"""
    return 1


def has_flag(flags, stat_index):
    return bool(flags & (1 << stat_index))


# ゲーム内で 1 レベル分として数えられない = トーピダーは強化できない
NOT_LEVELABLE_DOM = frozenset((TORPIDITY,))
