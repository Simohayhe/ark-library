# -*- coding: utf-8 -*-
"""染料色 (ID 128 以降) を公式 wiki から取り込んで data/colors.json に足す。

    python tools/build_dye_db.py [保存済みの Color_IDs の生データ]

なぜ要るか
----------
ARKStatsExtractor の values.json に入っているのは**生物色 100 色だけ**で、
染料色 (ID 128〜254) の定義が無い。ARK ASA では

    ID 1〜127    生物色 (実際に定義があるのは 1〜100、101〜127 は欠番)
    ID 128〜254  染料色。野生には出ない。変異・染料・イベント飴でのみ付く
    ID 255       未設定

という並びで、染料色は ASA-values.json の ``dyeStartIndex: 128`` が示している。
定義が無いと、標準エクスポート (ini) は色を RGBA で持っているので、変異で
染料色が付いた個体を「いちばん近い生物色」に取り違えてしまう。

出どころは公式 wiki の Color IDs。1 行がそのまま
``{{Color ID|128|Burn Coloring|srgb=360000|ue=0.033, 0.0, 0.0}}`` の形なので
そこから読む。生物色 (1〜100) は values.json 側と突き合わせて検算する。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
OUT = os.path.join(PROJ, "data", "colors.json")

WIKI_URL = "https://ark.wiki.gg/wiki/Color_IDs?action=raw"

# {{Color ID|128|Burn Coloring|srgb=360000|ue=0.033, 0.0, 0.0}}
ENTRY = re.compile(
    r"\{\{Color ID\|(\d+)\|([^|}]+)\|srgb=([0-9A-Fa-f]{6})"
    r"(?:\|ue=([0-9.]+),\s*([0-9.]+),\s*([0-9.]+))?")

# ASA の染料はこの ID から (ASA-values.json の dyeStartIndex と同じ)
DYE_FIRST_ID = 128


def fetch():
    import urllib.request
    req = urllib.request.Request(WIKI_URL,
                                 headers={"User-Agent": "ark-library/1.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8",
                                                                 "replace")


def asa_section(text):
    """染料の節のうち ASA のタブだけを取り出す。

    wiki は <tabber> で ASA と ASE を並べていて、ASE 側は ID の振り方が
    違う (201 始まり)。混ぜると壊れるので ASA だけ見る。
    """
    start = text.find("==Lists of dyes==")
    if start < 0:
        return ""
    body = text[start:]
    head = body.find("ARK: Survival Ascended=")
    if head < 0:
        return body
    body = body[head:]
    end = body.find("|-|")          # 次のタブ (ASE) の手前まで
    return body[:end] if end > 0 else body


def parse(text):
    out = {}
    for m in ENTRY.finditer(text):
        cid = int(m.group(1))
        name = m.group(2).strip()
        if m.group(4) is None:
            continue
        rgba = [round(float(m.group(i)), 6) for i in (4, 5, 6)] + [0.0]
        out[cid] = [name, rgba]
    return out


def main():
    text = (io.open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1
            else fetch())

    creatures = parse(text[:text.find("==Lists of dyes==")])
    dyes = parse(asa_section(text))
    dyes = {k: v for k, v in dyes.items() if k >= DYE_FIRST_ID}
    print("wiki から: 生物色 %d 件 / 染料色 %d 件 (ID %d〜%d)"
          % (len(creatures), len(dyes),
             min(dyes) if dyes else 0, max(dyes) if dyes else 0))
    if not dyes:
        print("染料色が取れませんでした。書式が変わったかもしれません。")
        return 1

    with io.open(OUT, encoding="utf-8-sig") as f:
        data = json.load(f)
    have = {int(k): v for k, v in data["colors"].items()}

    # 生物色を突き合わせて、出どころが信用できるか確かめる
    same = diff = 0
    for cid, (name, rgba) in sorted(creatures.items()):
        got = have.get(cid)
        if not got:
            continue
        if all(abs(a - b) < 0.002 for a, b in zip(got[1][:3], rgba[:3])):
            same += 1
        else:
            diff += 1
            if diff <= 5:
                print("   ちがい ID %3d %-16s wiki %s / values %s"
                      % (cid, name, rgba[:3], got[1][:3]))
    print("生物色の検算: 一致 %d / 不一致 %d" % (same, diff))
    if diff > len(creatures) * 0.05:
        print("不一致が多すぎます。取り込みを中止します。")
        return 1

    added = 0
    for cid, entry in sorted(dyes.items()):
        if str(cid) in data["colors"]:
            continue
        data["colors"][str(cid)] = entry
        added += 1
    data.setdefault("source", {})["dye_source"] = WIKI_URL
    data["source"]["dye_first_id"] = DYE_FIRST_ID

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("data/colors.json に染料色 %d 件を足しました (合計 %d 色)"
          % (added, len(data["colors"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
