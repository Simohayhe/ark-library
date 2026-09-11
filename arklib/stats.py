# -*- coding: utf-8 -*-
"""ステータス値の計算。

ARKStatsExtractor/ARKBreedingStats/Stats.cs の StatValueCalculation を移植したもの。

計算式 (割合式ステータス = ほぼ全部):

    野生値 Vw = B * (1 + Lw*Iw + Lm*Im)
    飼育値 V  = (Vw * TBHM * imprintM + Ta) * (1 + TE*Tm) * (1 + Ld*Id)

    imprintM = 1 + 刷り込み係数[stat] * 刷り込み率 * BabyImprintingStatScaleMultiplier

加算式ステータス (statLevelUpsAdditive が立っているもの) は

    V = ((B + Lw*Iw + Lm*Im) * TBHM * imprintM + Ta) * (1 + TE*Tm) + Ld*Id

Iw / Id / Ta / Tm にはサーバー倍率が既に掛かっている (species.apply() 参照)。
"""
import math

from . import ark


def calc_value(species, stat_index, level_wild, level_mut, level_dom,
               domesticated, taming_eff=0.0, imprinting_bonus=0.0,
               imprint_stat_scale=1.0, round_to_ingame=True):
    """1 ステータスの表示値を求める。

    species        : apply() 済みの Species
    level_wild     : 野生レベル (不明なら -1)
    level_mut      : 変異レベル (ASA)
    level_dom      : テイム後に振ったレベル
    domesticated   : テイム済み / 交配産なら True
    taming_eff     : テイム効率 0..1 (交配産は 1.0)
    imprinting_bonus : 刷り込み率 0..1
    imprint_stat_scale : BabyImprintingStatScaleMultiplier
    """
    st = species.stats[stat_index]
    if st is None:
        return 0.0

    # ステータス自体はあるがレベルが不明 (-1) のときは -1 を返す
    if level_wild < 0 and st.inc_wild != 0:
        return -1.0

    add = 0.0
    dom_mult = 1.0
    imprint_m = 1.0
    tamed_base_hp = 1.0

    if domesticated:
        add = st.add_tamed
        aff = st.mult_affinity
        # 乗算ボーナスは正のときだけテイム効率が掛かる
        # (マイナスのボーナスは効率が低くてもマシにならない)
        if aff >= 0:
            aff = aff * taming_eff
        dom_mult = (1.0 + aff) if taming_eff >= 0 else 1.0

        if imprinting_bonus > 0 and species.imprint[stat_index] != 0:
            imprint_m = 1.0 + species.imprint[stat_index] * imprinting_bonus * imprint_stat_scale

        if stat_index == ark.HEALTH:
            tamed_base_hp = species.tbhm
    else:
        level_dom = 0

    wild_inc = level_wild * st.inc_wild + level_mut * st.inc_mut
    dom_inc = level_dom * st.inc_dom

    if st.as_percentage:
        result = (st.base * (1.0 + wild_inc) * tamed_base_hp * imprint_m + add) * dom_mult * (1.0 + dom_inc)
    else:
        result = ((st.base + wild_inc) * tamed_base_hp * imprint_m + add) * dom_mult + dom_inc

    if result <= 0:
        return 0.0
    result = min(result, st.cap)

    if round_to_ingame:
        return round_half_up(result, ark.precision(stat_index))
    return result


def round_half_up(value, digits):
    """C# の MidpointRounding.AwayFromZero 相当。Python の round は銀行丸めなので使えない。"""
    if value != value or value in (float("inf"), float("-inf")):
        return value
    f = 10.0 ** digits
    v = value * f
    # 浮動小数の誤差で 0.5 の判定がずれるのを避ける
    v = math.floor(abs(v) + 0.5 + 1e-9)
    return math.copysign(v, value) / f


def displayed_aberration(displayed_value, decimals=1, high_precision=False):
    """ARK の表示値が持つ誤差の幅。Stats.cs の DisplayedAberration を移植。

    ARK 内部は float なので、表示された値には丸め誤差が乗る。逆算では
    「この幅に入っていれば一致」とみなす。
    """
    ARK_DISPLAY_ERROR = 0.06
    MIN_ERROR = 0.001
    # ステータス計算を通すと誤差が増える。ASA は 18 以上必要とのことで 20 を使う。
    CALC_ERROR_FACTOR = 20.0

    scaled = displayed_value * (100 if decimals == 3 else 1)
    if high_precision or scaled > 1e6:
        return max(MIN_ERROR, float_precision(displayed_value) * CALC_ERROR_FACTOR)
    return ARK_DISPLAY_ERROR * (0.01 if decimals == 3 else 1.0)


def float_precision(value):
    """float32 で表現したときの最小刻み幅。"""
    v = abs(float(value))
    if v == 0:
        return 1.4e-45
    exponent = math.floor(math.log(v, 2))
    return 2.0 ** (exponent - 23)


def calc_all(species, levels_wild, levels_mut, levels_dom, domesticated,
             taming_eff=1.0, imprinting_bonus=0.0, imprint_stat_scale=1.0):
    """12 ステータス分まとめて計算する。"""
    return [
        calc_value(species, s,
                   levels_wild[s] if levels_wild else 0,
                   levels_mut[s] if levels_mut else 0,
                   levels_dom[s] if levels_dom else 0,
                   domesticated, taming_eff, imprinting_bonus, imprint_stat_scale)
        for s in range(ark.STATS_COUNT)
    ]


def format_value(stat_index, value):
    """ゲーム内表示に合わせた文字列。%表示のものは 100 倍する。"""
    if value is None or value < 0:
        return "?"
    if ark.is_percentage(stat_index):
        return "%.1f%%" % (value * 100)
    return "%.1f" % value


def parse_value(stat_index, text):
    """ゲーム内表示の文字列を内部値に戻す。'350.5%' → 3.505"""
    t = (text or "").strip().replace(",", "").rstrip("%").strip()
    if not t:
        return None
    v = float(t)
    if ark.is_percentage(stat_index):
        v /= 100.0
    return v
