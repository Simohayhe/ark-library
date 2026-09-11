# -*- coding: utf-8 -*-
"""種族データの追加 (同梱の追加ぶん / Mod / 種族当て) のテスト。

通信はしない。Mod の取り込みは、手元で作った値ファイルを食わせて確かめる。
"""
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arklib import ark, guess, modvalues, stats
from arklib.creature import FEMALE
from arklib.importers import import_file, resolve_species
from arklib.multipliers import ServerMultipliers
from arklib.species import SpeciesDB
from test_import import make_export_ini

PASS, FAIL = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print("  OK   %-46s %s" % (name, got))
    else:
        FAIL.append(name)
        print("  NG   %-46s got=%s want=%s" % (name, got, want))


def main():
    db = SpeciesDB()
    sm = ServerMultipliers.official("asa")
    db.apply_multipliers(sm, "asa")

    print("[1] 同梱の追加ぶん (ARKStatsExtractor にまだ無い生物)")
    check("1.1 追加ぶんがある", db.extra_count >= 1, True)
    sp = db.get("Boaratos")
    check("1.2 ボアラトスが引ける", sp is not None and sp.display_name, "Boaratos")
    check("1.3 ASA 扱い", sp.in_asa, True)
    check("1.4 交配できる", sp.is_breedable(), True)
    # wiki の Base と、レベル 0 のときの値が合うか
    want = {ark.HEALTH: 1050.0, ark.STAMINA: 400.0, ark.OXYGEN: 150.0,
            ark.FOOD: 5000.0, ark.WEIGHT: 500.0, ark.TORPIDITY: 5000.0}
    got = {s: stats.calc_value(sp, s, 0, 0, 0, False) for s in want}
    check("1.5 Lv1 の値が wiki と一致", got, want)
    check("1.6 近接は 100%", stats.calc_value(sp, ark.MELEE, 0, 0, 0, False), 1.0)
    # 野生レベル 1 つで +20% (体力)
    check("1.7 野生 1 レベルで +210",
          stats.calc_value(sp, ark.HEALTH, 1, 0, 0, False), 1260.0)

    print("\n[2] 名前での引き当て (パスが違っても通る)")
    got, _bp = resolve_species(db, "/Game/Mods/Elsewhere/Boaratos_Character_BP."
                                   "Boaratos_Character_BP", "Boaratos")
    check("2.1 パス違いでも名前で引ける", got.display_name, "Boaratos")
    got, _bp = resolve_species(db, "Blueprint'/Game/PrimalEarth/Dinos/Rex/"
                                   "Rex_Character_BP.Rex_Character_BP_C'", "")
    check("2.2 ふつうのパスはそのまま", got.display_name, "Rex")

    print("\n[3] 取り込みの通し (ボアラトス)")
    lw = [0] * 12
    for s, v in ((ark.HEALTH, 30), (ark.STAMINA, 20), (ark.OXYGEN, 10),
                 (ark.FOOD, 12), (ark.WEIGHT, 15), (ark.MELEE, 25)):
        lw[s] = v
    level = 1 + sum(lw)
    text = make_export_ini(sp, sm, lw, [0] * 12, level, state="bred", imprint=0.0,
                           name="ボアラトス試験", sex=FEMALE, ark_id=(9, 9))
    path = os.path.join(tempfile.mkdtemp(prefix="boa_"), "boaratos.ini")
    io.open(path, "w", encoding="utf-8").write(text)
    r = import_file(path, db, sm)
    check("3.1 取り込める", r.ok, True)
    if r.ok:
        c = r.creature
        check("3.2 種族", c.species_name, "Boaratos")
        check("3.3 レベル内訳",
              [c.levels_wild[s] for s in (ark.HEALTH, ark.STAMINA, ark.OXYGEN,
                                          ark.FOOD, ark.WEIGHT, ark.MELEE)],
              [30, 20, 10, 12, 15, 25])

    print("\n[4] 知らない種族を当てる")
    vals = {s: stats.calc_value(sp, s, lw[s] if s != ark.TORPIDITY else sum(lw),
                                0, 0, True, taming_eff=1.0)
            for s in sp.displayed_stat_indices()}
    got = guess.guess_species(db, level, vals, sm, state="bred")
    check("4.1 候補が出る", len(got) >= 1, True)
    check("4.2 一番手はボアラトス", got[0].species.display_name, "Boaratos")
    check("4.3 解は一つ", got[0].unique, True)
    check("4.4 使っていないステは数えない",
          ark.WATER in guess.meaningful_stats({ark.WATER: 0.0}), False)
    check("4.5 %ステの 100% は「無い」扱い",
          ark.MELEE in guess.meaningful_stats({ark.MELEE: 1.0}), False)

    print("\n[5] Mod の値ファイルを取り込む")
    fake = {
        "version": "1.0", "format": "1.16-mod-remap",
        "mod": {"id": "999999", "tag": "TestMod", "title": "テスト用 Mod",
                "ASA": True},
        "species": [{
            "name": "TestCritter",
            "blueprintPath": "/Game/Mods/Test/Critter_Character_BP.Critter_Character_BP",
            "fullStatsRaw": [[200, 0.2, 0.27, 0.5, 0], [150, 0.1, 0.1, 0, 0],
                             [300, 0.06, 0, 0.5, 0], [150, 0.1, 0.1, 0, 0],
                             [1200, 0.1, 0.1, 0, 0.15], None, None,
                             [80, 0.02, 0.04, 0, 0], [1, 0.05, 0.1, 0.4, 0.35],
                             [1, 0, 0.01, 0.3, 0], None, None],
            "breeding": {"maturationTime": 100000, "gestationTime": 10000,
                         "matingCooldownMin": 64800, "matingCooldownMax": 172800},
        }],
    }
    tmp_lib = os.path.join(tempfile.mkdtemp(prefix="mods_"), "library.db")
    path, n = modvalues.install_from_dict(fake, "999999-TestMod.json", tmp_lib)
    check("5.1 入れられる", n, 1)
    check("5.2 置き場所", os.path.isfile(path), True)
    got_list = modvalues.installed(tmp_lib)
    check("5.3 一覧に出る", [m["mod"].get("title") for m in got_list], ["テスト用 Mod"])
    db2 = SpeciesDB(library_path=tmp_lib)
    check("5.4 種族DB に合流する", db2.mod_count, 1)
    critter = db2.get("TestCritter")
    check("5.5 引ける", critter is not None and critter.display_name, "TestCritter")
    db2.apply_multipliers(sm, "asa")
    check("5.6 計算できる",
          stats.calc_value(critter, ark.HEALTH, 0, 0, 0, False), 200.0)
    check("5.7 外せる", modvalues.remove("999999-TestMod.json", tmp_lib), True)
    check("5.8 外したら消える", modvalues.installed(tmp_lib), [])

    print("\n" + "=" * 66)
    print("%d 件成功 / %d 件失敗" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失敗: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
