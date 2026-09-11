# -*- coding: utf-8 -*-
"""ARKStatsExtractor のデータにまだ入っていない生物を足す。

    python tools/build_extra_species.py     → data/extra_species.json

ASA に追加されたばかりの生物は、ARK Smart Breeding のデータ (values.json /
ASA-values.json) に載るまで時間がかかる。載っていない生物はここで手当てする。

値の作り方
----------
ステータスの生の並びは [B, Iw, Id, Ta, Tm]。

    B  … レベル 1 のときの値
    Iw … 野生レベル 1 つあたりの増分 (**B に対する割合**)
    Id … テイム後のレベル 1 つあたりの増分 (割合)
    Ta … テイムしたときの加算ボーナス
    Tm … テイムしたときの乗算ボーナス (テイム効率が掛かる)

**B と Iw は wiki の「Base」「Wild +/Lv」からそのまま出せる** (Iw = 増分 ÷ B)。
Id / Ta / Tm は wiki の表からは決められないので、**同じ表の見え方をする
既存の生物から借りる**。借り元が違えば、テイム個体の逆算だけがずれる
(交配で使う野生レベルには影響しない)。

借り元と数値の出どころは下の SOURCES に書いてある。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)

from arklib import ark  # noqa: E402

HEALTH, STAMINA, TORPIDITY = ark.HEALTH, ark.STAMINA, ark.TORPIDITY
OXYGEN, FOOD, WEIGHT = ark.OXYGEN, ark.FOOD, ark.WEIGHT
MELEE, SPEED = ark.MELEE, ark.SPEED

SPECIES_DB = os.path.join(PROJ, "data", "species.json")
OUT = os.path.join(PROJ, "data", "extra_species.json")

# (追加する生物, 借り元の生物, 出どころ)
SOURCES = [
    ("Boaratos", "Daeodon",
     "https://wikily.gg/ja/ark-survival-ascended/dinosaurs/boaratos/"),
]


def load_species(name, bp_part=None):
    with io.open(SPECIES_DB, encoding="utf-8-sig") as f:
        data = json.load(f)
    for rec in data["species"]:
        if rec["name"] == name and (bp_part is None or bp_part in rec["bp"]):
            return rec
    raise KeyError(name)


def build(base_name, bp_part, new_name, bp, wiki, breeding, notes):
    """借り元の生物をもとに、B と Iw だけ差し替えた 1 件を作る。

    wiki      : {stat: (Base, 野生の増分)}   … wiki の表そのまま
    breeding  : {"gestation": 秒, "maturation": 秒, ...}
    """
    src = load_species(base_name, bp_part)
    rec = json.loads(json.dumps(src))          # 深いコピー
    rec["name"] = new_name
    rec["displayName"] = new_name      # 借り元の名前が残らないように
    rec["bp"] = bp
    rec["asa"] = True
    rec.pop("variants", None)
    rec.pop("matesWith", None)         # 借り元と交配できるわけではない
    rec["basedOn"] = base_name
    rec["notes"] = notes

    for stat, (base, per_level) in wiki.items():
        entry = rec["statsRaw"][stat]
        if entry is None:
            raise ValueError("借り元に無いステータス: %d" % stat)
        entry[0] = float(base)
        # 野生の増分は「B に対する割合」に直す
        entry[1] = round(float(per_level) / float(base), 6) if base else 0.0

    if breeding:
        rec.setdefault("breeding", {})
        rec["breeding"].update(breeding)
    return rec


def main():
    boaratos = build(
        base_name="Daeodon", bp_part="/Dinos/Daeodon/",
        new_name="Boaratos",
        # 本物のパスはエクスポートで確かめる。名前 (DinoNameTag) でも引けるので、
        # パスが違っていても取り込みは通る
        bp=("/Game/Mods/Astraeos/Assets/CoreBlueprints/Creatures/Boaratos/"
            "Boaratos_Character_BP.Boaratos_Character_BP"),
        wiki={
            HEALTH: (1050.0, 210.0),    # +20%/Lv
            STAMINA: (400.0, 40.0),     # +10%/Lv
            TORPIDITY: (5000.0, 300.0),  # +6%/Lv
            OXYGEN: (150.0, 15.0),
            FOOD: (5000.0, 500.0),
            WEIGHT: (500.0, 10.0),      # +2%/Lv
            MELEE: (1.0, 0.05),         # 100% / +5%
            SPEED: (1.0, 0.0),
        },
        breeding={
            "incubation": 0.0,
            "gestation": 28571.429,     # 7 時間 56 分 (ダエオドンと同じ)
            "maturation": 295200.0,     # 3 日 10 時間
            # 再交配の間隔は wiki に無いので、ふつうの陸生と同じ 18〜48 時間
            "cdMin": 64800.0,
            "cdMax": 172800.0,
        },
        notes=("ベースと野生の増分は wikily.gg の表から。テイム側の係数 "
               "(Id/Ta/Tm)・刷り込み・気絶は Daeodon から借りている "
               "(wiki のテイム増分がダエオドンと完全に一致するため)。"
               "ブループリントパスは推定。"))

    out = {
        "source": {
            "generator": "tools/build_extra_species.py",
            "why": ("ARK Smart Breeding のデータにまだ載っていない生物を、"
                    "wiki の数値と既存生物の係数から組み立てたもの"),
            "entries": [{"name": n, "basedOn": b, "url": u} for n, b, u in SOURCES],
        },
        "species": [boaratos],
    }
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote %s (%d 種)" % (OUT, len(out["species"])))
    for rec in out["species"]:
        print("  %s (%s をもとに)" % (rec["name"], rec.get("basedOn")))
        for s in (HEALTH, STAMINA, TORPIDITY, OXYGEN, FOOD, WEIGHT, MELEE, SPEED):
            e = rec["statsRaw"][s]
            if e:
                print("    %-6s B=%-8g Iw=%-8g Id=%-6g Ta=%-4g Tm=%g"
                      % (ark.NAMES_JA[s], e[0], e[1], e[2], e[3], e[4]))


if __name__ == "__main__":
    main()
