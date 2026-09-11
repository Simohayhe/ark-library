# -*- coding: utf-8 -*-
"""ARKStatsExtractor の values.json / ASA-values.json から色データを作る。

    python tools/build_color_db.py [values.json] [ASA-values.json]
        → data/colors.json

中身
----
    colors  : 色 ID → (名前, [r, g, b, a])。ID はゲーム内の色番号で 1 始まり。
              values.json の colorDefinitions の並び順がそのまま ID になる
              (ARKStatsExtractor/ArkColors.cs と同じ数え方)。
    species : ブループリントパス → 6 つの色領域。
              領域ごとに「名前」と「その領域に出うる色 ID」が入る。
              使わない領域は null。

ASA は ASA-values.json 側の定義で上書きする (同じ blueprintPath でマージ)。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

_REL = os.path.join(os.path.dirname(PROJ), "ARKStatsExtractor",
                    "ARKBreedingStats", "json", "values")
DEFAULT_ASE = os.path.join(_REL, "values.json")
DEFAULT_ASA = os.path.join(_REL, "ASA-values.json")

REGION_COUNT = 6


def load(path):
    with io.open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def build_color_table(base):
    """colorDefinitions を ID 付きの表にする。ID は 1 始まり。"""
    out = {}
    by_name = {}
    for i, entry in enumerate(base.get("colorDefinitions") or [], start=1):
        name, rgba = entry[0], entry[1]
        out[i] = [name, [round(float(v), 6) for v in rgba]]
        by_name[name] = i
    return out, by_name


def regions_of(species, by_name):
    """種族の colors を [{name, ids}] にする。使わない領域は None。"""
    colors = species.get("colors")
    if not colors:
        return None
    out = []
    for region in colors[:REGION_COUNT]:
        if not region:
            out.append(None)
            continue
        ids = sorted(by_name[n] for n in (region.get("colors") or [])
                     if n in by_name)
        out.append({"name": region.get("name") or "", "ids": ids})
    while len(out) < REGION_COUNT:
        out.append(None)
    return out


def main():
    ase_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ASE
    asa_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_ASA
    base = load(ase_path)
    over = load(asa_path)

    colors, by_name = build_color_table(base)
    print("色定義: %d 色" % len(colors))

    species = {}
    for src, label in ((base, "ASE"), (over, "ASA")):
        n = 0
        for sp in src.get("species") or []:
            bp = sp.get("blueprintPath")
            if not bp:
                continue
            regions = regions_of(sp, by_name)
            if regions is None:
                continue
            species[bp] = regions          # ASA が後なので上書きされる
            n += 1
        print("  %s: 色領域つき %d 種" % (label, n))

    out = {
        "source": {
            "ase_values_version": base.get("version"),
            "asa_values_version": over.get("version"),
            "generator": "tools/build_color_db.py",
        },
        "colors": {str(k): v for k, v in sorted(colors.items())},
        "species": species,
    }
    path = os.path.join(PROJ, "data", "colors.json")
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=False)
    print("書き出し: %s (%.1f KB)" % (path, os.path.getsize(path) / 1024.0))


if __name__ == "__main__":
    main()
