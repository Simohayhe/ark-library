# -*- coding: utf-8 -*-
"""動作確認用のデモ DB を作る。

    python tools/seed_demo.py <出力先.db>

実在のサーバー設定 (C:\\ArkServers\\*\\...\\Game.ini) があればそれを読んで
倍率プロファイルに入れる。個体は適当にばらけた Rex と Argentavis。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import ark, paths, stats
from arklib.creature import FEMALE, MALE, STATUS_CRYO, STATUS_DEAD, Creature
from arklib.library import Library
from arklib.multipliers import ServerMultipliers
from arklib.species import SpeciesDB

NAMES_M = ["クロ", "ゲンブ", "タイガ", "ノワール", "ライデン", "ガイア", "ムサシ",
           "テツ", "ジーク"]
NAMES_F = ["サクラ", "ユキ", "ヒメ", "モモ", "ルナ", "アヤメ", "スズ", "コハク",
           "ナデシコ"]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "demo.db"
    if os.path.exists(out):
        os.remove(out)
    lib = Library(out)
    db = SpeciesDB()

    # --- サーバー倍率 ---
    servers = paths.local_server_configs()
    used = []
    for name, game_ini, gus in servers[:3]:
        files = [f for f in (game_ini, gus) if f]
        try:
            sm = ServerMultipliers.from_ini(*files)
        except Exception:
            continue
        lib.save_server(name, sm.to_dict(), files, is_default=not used)
        used.append(name)
    if not used:
        sm = ServerMultipliers.official("asa")
        lib.save_server("公式相当", sm.to_dict(), [], is_default=True)
        used = ["公式相当"]
    server = used[0]
    prof = lib.default_server()
    sm = ServerMultipliers.from_dict(prof["multipliers"])
    db.apply_multipliers(sm.with_single_player_applied(), "asa")
    lib.set_setting("current_server", server)
    print("サーバー: %s (%s)" % (server, ", ".join(used)))

    rnd = random.Random(7)
    total = 0
    for species_name, count in (("Rex", 14), ("Argentavis", 8), ("Pyromane", 3)):
        sp = db.get(species_name)
        if sp is None:
            continue
        breed_stats = [s for s in sp.displayed_stat_indices() if s != ark.TORPIDITY]
        for i in range(count):
            sex = MALE if i % 2 == 0 else FEMALE
            name = (NAMES_M if sex == MALE else NAMES_F)[i % 9]
            lw = [0] * ark.STATS_COUNT
            lm = [0] * ark.STATS_COUNT
            ld = [0] * ark.STATS_COUNT
            for s in breed_stats:
                lw[s] = rnd.randint(18, 38)
            # 1 ステータスだけ尖らせる
            star = breed_stats[i % len(breed_stats)]
            lw[star] = rnd.randint(42, 48)
            muts = 0
            if i % 5 == 0:
                lm[star] = 2 * rnd.randint(1, 3)
                muts = lm[star] // 2
            ld[ark.HEALTH] = rnd.choice([0, 10, 20])
            level = 1 + sum(lw) + sum(lm) + sum(ld)

            c = Creature(
                species_bp=sp.bp, species_name=sp.display_name, name=name,
                sex=sex, state="bred", level=level, server=server,
                imprint=rnd.choice([0.0, 0.47, 1.0]),
                mutations_father=muts, mutations_mother=0,
                source="demo", owner="ゆう", tribe="ぺんぎん族",
                ark_id=rnd.randint(1, 2 ** 40),
            )
            c.levels_wild = lw
            c.levels_mut = lm
            c.levels_dom = ld
            wild_total = sum(lw) + sum(lm)
            for s in range(ark.STATS_COUNT):
                if sp.stats[s] is None:
                    continue
                l = wild_total if s == ark.TORPIDITY else lw[s]
                mm = 0 if s == ark.TORPIDITY else lm[s]
                c.values[s] = stats.calc_value(
                    sp, s, l, mm, ld[s], True, taming_eff=1.0,
                    imprinting_bonus=c.imprint,
                    imprint_stat_scale=sm.imprint_stat_scale)
            if i == count - 1:
                c.status = STATUS_CRYO
                c.notes = "クライオ保管中"
            if i == 3 and species_name == "Rex":
                c.status = STATUS_DEAD
                c.notes = "ギガに踏まれた"
            lib.save(c)
            total += 1

    print("%d 体入れました → %s" % (total, out))
    lib.close()


if __name__ == "__main__":
    main()
