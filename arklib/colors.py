# -*- coding: utf-8 -*-
"""生物の色。

ARK の生物は色領域を最大 6 つ持っていて、それぞれに「色 ID」(1〜100 くらい) が
入っている。交配では**領域ごとに独立して、どちらかの親の色をそのまま貰う**
(ふつうは 50% ずつ)。だから色は「混ざらない」。狙った色を出すには、その色を
持っている親を用意して掛け合わせるしかない。

エクスポートの中身
------------------
    Export Gun (.sav/.json) … ColorSetIndices に **色 ID がそのまま**入っている
    標準エクスポート (.ini) … ColorSet[n]=(R=..,G=..,B=..,A=..) と **色そのもの**が
                              入っているので、いちばん近い定義色を探して ID に直す

(R=0,G=0,B=0,A=1) は「その領域は使っていない」の意味で、ID 0 とする。
"""
import io
import json
import os
import sys

REGION_COUNT = 6
NO_COLOR = 0

# ARK ASA の色 ID の並び (ASA-values.json の dyeStartIndex と公式 wiki より)
#
#     1〜127    生物色。実際に定義があるのは 1〜100 で、101〜127 は欠番
#     128〜254  染料色。**野生には出ない**。変異・染料・イベント飴でのみ付く
#     255       未設定
#
# つまり ID が 128 以上なら、種族のパレットを見るまでもなく野生の色ではない。
DYE_FIRST_ID = 128
UNSET_COLOR_ID = 255

_DATA = None


def _find_data(name):
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [os.path.dirname(here)]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots.insert(0, base)
    roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    for root in roots:
        path = os.path.join(root, "data", name)
        if os.path.isfile(path):
            return path
    return os.path.join(roots[0], "data", name)


def _load():
    global _DATA
    if _DATA is None:
        try:
            with io.open(_find_data("colors.json"), encoding="utf-8-sig") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {"colors": {}, "species": {}}
        _DATA = {
            "colors": {int(k): v for k, v in (raw.get("colors") or {}).items()},
            "species": raw.get("species") or {},
            "source": raw.get("source") or {},
        }
    return _DATA


def available():
    return bool(_load()["colors"])


def count():
    return len(_load()["colors"])


# ---- 1 色ぶんの情報 ----------------------------------------------------


def name_of(color_id):
    got = _load()["colors"].get(int(color_id or 0))
    if not got:
        return "" if not color_id else "色%d" % color_id
    return got[0]


def rgba_of(color_id):
    got = _load()["colors"].get(int(color_id or 0))
    return list(got[1]) if got else None


def hex_of(color_id):
    """画面に出すための #RRGGBB。無い色は None。"""
    rgba = rgba_of(color_id)
    if not rgba:
        return None
    r, g, b = rgba[0], rgba[1], rgba[2]
    return "#%02X%02X%02X" % (_c(r), _c(g), _c(b))


def _c(v):
    return max(0, min(255, int(round(float(v) * 255))))


def label_of(color_id):
    if not color_id:
        return "なし"
    return "%s (%d)" % (name_of(color_id), color_id)


def all_ids():
    return sorted(_load()["colors"])


# ---- RGBA → 色 ID ------------------------------------------------------


def closest_id(rgba):
    """エクスポートに入っていた色に、いちばん近い定義色の ID を返す。

    ARKStatsExtractor/ArkColors.ClosestColorId と同じ考え方 (RGBA の距離)。
    """
    if not rgba:
        return NO_COLOR
    r, g, b, a = (list(rgba) + [0, 0, 0, 0])[:4]
    # 黒くて不透明 = その領域は使っていない
    if r == 0 and g == 0 and b == 0 and a == 1:
        return NO_COLOR
    best_id, best_d = NO_COLOR, None
    # ID の小さい順に見る。生物色と染料色で RGBA が丸かぶりのものが 7 組
    # あり (Red と Red Coloring など)、表示値からは区別できない。
    # そのときは生物色の方を採る (野生で出るのはそちらなので)
    for cid in sorted(_load()["colors"]):
        c = _load()["colors"][cid][1]
        d = ((c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2
             + (c[3] - a) ** 2)
        if best_d is None or d < best_d:
            best_id, best_d = cid, d
    return best_id


def ids_from_rgba_map(color_rgba):
    """{領域番号: (r,g,b,a)} を 6 個の色 ID に直す。"""
    out = [NO_COLOR] * REGION_COUNT
    for idx, rgba in (color_rgba or {}).items():
        if 0 <= int(idx) < REGION_COUNT:
            out[int(idx)] = closest_id(rgba)
    return out


# ---- 種族の色領域 ------------------------------------------------------


def regions(species_bp):
    """その種族の色領域。[{name, ids} または None] を 6 個。"""
    got = _load()["species"].get(species_bp)
    if not got:
        return [None] * REGION_COUNT
    out = list(got)[:REGION_COUNT]
    while len(out) < REGION_COUNT:
        out.append(None)
    return out


def used_regions(species_bp):
    """使っている領域の番号だけ。"""
    return [i for i, r in enumerate(regions(species_bp)) if r]


def region_name(species_bp, index):
    got = regions(species_bp)
    r = got[index] if 0 <= index < len(got) else None
    return (r or {}).get("name") or "領域%d" % index


def possible_ids(species_bp, index):
    """その領域に野生で出うる色 ID。空なら分からない。"""
    got = regions(species_bp)
    r = got[index] if 0 <= index < len(got) else None
    return list((r or {}).get("ids") or [])


# ---- 野生の色か、そうでないか ------------------------------------------
#
# 種族ごとに「その領域に野生で出る色」が決まっている。そこに無い色が付いて
# いたら、野生では出ないはずの色ということになる。出どころは 2 つ。
#
#     テイム / 野生の個体   … イベント中に湧いた個体 (イベントカラー)
#     交配産の個体          … 色変異、または親から継いだイベントカラー
#
# どちらも「珍しい色」なので、一覧とオーバーレイで印を付けて知らせる。

NATURAL = "natural"       # その種族の野生色
EVENT = "event"           # 野生では出ない色 + テイム/野生個体 = イベント由来
MUTATION = "mutation"     # 野生では出ない色 + 交配産 = 変異 (または親譲り)
UNKNOWN = "unknown"       # 色データが無くて判断できない

MARKS = {EVENT: "★", MUTATION: "◆"}
KIND_JA = {NATURAL: "野生色", EVENT: "イベント色", MUTATION: "変異色",
           UNKNOWN: "不明"}


def is_dye(color_id):
    """染料域 (ID 128 以降) の色か。野生には出ない色。"""
    try:
        return DYE_FIRST_ID <= int(color_id or 0) < UNSET_COLOR_ID
    except (TypeError, ValueError):
        return False


def is_natural(species_bp, index, color_id):
    """その領域に野生で出る色か。分からなければ None。"""
    if not color_id:
        return None
    # 染料域は種族に関係なく野生では出ない。パレットを見るまでもない
    if is_dye(color_id):
        return False
    ids = possible_ids(species_bp, index)
    if not ids:
        return None
    return int(color_id) in ids


def classify(species_bp, index, color_id, bred=False):
    """色の出どころを見当づける。"""
    got = is_natural(species_bp, index, color_id)
    if got is None:
        return UNKNOWN
    if got:
        return NATURAL
    return MUTATION if bred else EVENT


def mark_of(species_bp, index, color_id, bred=False):
    """一覧のセルに添える印。ふつうの色なら空。"""
    return MARKS.get(classify(species_bp, index, color_id, bred), "")


def odd_colors(species_bp, colors, bred=False):
    """野生では出ない色だけを拾う。[(領域番号, 色ID, 種類)]"""
    out = []
    for i, cid in enumerate(list(colors or [])[:REGION_COUNT]):
        if not cid:
            continue
        kind = classify(species_bp, i, cid, bred)
        if kind in (EVENT, MUTATION):
            out.append((i, int(cid), kind))
    return out


def describe_odd(species_bp, colors, bred=False):
    """「イベント色: 体 = Glacial (96)」のような一行。無ければ空。"""
    got = odd_colors(species_bp, colors, bred)
    if not got:
        return ""
    kind = got[0][2]
    parts = []
    for i, cid, _k in got:
        # 染料域は「そもそも野生に存在しない色」なので、その旨を添える
        note = " [染料域]" if is_dye(cid) else ""
        parts.append("%s = %s%s" % (region_name(species_bp, i),
                                    label_of(cid), note))
    return "%s: %s" % (KIND_JA.get(kind, kind), "、".join(parts))


def creature_ids():
    """野生に出うる側の色 ID (生物色)。"""
    return [c for c in all_ids() if c < DYE_FIRST_ID]


def dye_ids():
    """染料域の色 ID。"""
    return [c for c in all_ids() if is_dye(c)]
