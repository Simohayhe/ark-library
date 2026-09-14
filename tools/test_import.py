# -*- coding: utf-8 -*-
"""取り込み〜逆算〜交配プランの通しテスト。

実機のエクスポートファイルがまだ無いので、既知のレベル内訳から
ゲームと同じ表示値を計算して ini / Export Gun ファイルを組み立て、
それを読み戻して元のレベルに戻るかを確認する。
"""
import io
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import ark, breeding, stats
from arklib.creature import FEMALE, GENDERLESS, MALE, Creature
from arklib.importers import dino_export_ini, export_gun, import_file
from arklib.library import Library
from arklib.multipliers import ServerMultipliers
from arklib.species import SpeciesDB

# ゲーム内の表示 (日本語クライアント) を模した、ステータスセクションのキー名。
# 並び順だけで決まるので、この名前は何でも構わないことの確認も兼ねる。
JA_STAT_KEYS = ["体力", "スタミナ", "気絶", "酸素量", "食料", "水分", "温度",
                "重量", "近接攻撃力", "移動速度", "温度耐性", "作成速度"]

OFFSET_STATS = dino_export_ini.OFFSET_STATS

PASS, FAIL = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print("  OK   %-46s %s" % (name, got))
    else:
        FAIL.append(name)
        print("  NG   %-46s got=%s want=%s" % (name, got, want))


def make_export_ini(sp, sm, levels_wild, levels_dom, level, state="bred",
                    imprint=0.0, taming_eff=1.0, name="", sex=FEMALE,
                    ark_id=(123456789, 987654321), mutations=(0, 0),
                    parents=None, levels_mut=None):
    """ARK の「恐竜のエクスポート」が書くであろう ini を組み立てる。"""
    wild_total = sum(levels_wild) + sum(levels_mut or [0] * 12)
    lines = ["[DinoDownload]"]
    lines.append("DinoID1=%d" % ark_id[0])
    lines.append("DinoID2=%d" % ark_id[1])
    lines.append("DinoClass=Blueprint'%s_C'" % sp.bp)
    lines.append("DinoNameTag=%s" % sp.name)
    lines.append("bIsFemale=%s" % ("True" if sex == FEMALE else "False"))
    lines.append("bNeutered=False")
    lines.append("TamedName=%s" % name)
    lines.append("TamerString=ぺんぎん族")
    if state == "bred":
        lines.append("ImprinterName=ゆう")
        lines.append("DinoImprintingQuality=%.6f" % imprint)
        lines.append("BabyAge=1.000000")
    elif state == "tamed":
        lines.append("ImprinterName=")
    lines.append("CharacterLevel=%d" % level)
    lines.append("RandomMutationsMale=%d" % mutations[0])
    lines.append("RandomMutationsFemale=%d" % mutations[1])
    for i in range(6):
        lines.append("ColorSet[%d]=(R=0.500000,G=0.250000,B=0.100000,A=1.000000)" % i)
    if parents:
        lines.append(
            "DinoAncestors[0]=MaleName=%s - Lvl %d;MaleDinoID1=%d;MaleDinoID2=%d;"
            "FemaleName=%s - Lvl %d;FemaleDinoID1=%d;FemaleDinoID2=%d"
            % parents)

    lines.append("[Max Character Status Values]")
    for s in range(ark.STATS_COUNT):
        if sp.stats[s] is None:
            lines.append("%s=0.000000" % JA_STAT_KEYS[s])
            continue
        lw = wild_total if s == ark.TORPIDITY else levels_wild[s]
        lm = 0 if s == ark.TORPIDITY else (levels_mut or [0] * 12)[s]
        v = stats.calc_value(sp, s, lw, lm, levels_dom[s], state != "wild",
                             taming_eff=taming_eff, imprinting_bonus=imprint,
                             imprint_stat_scale=sm.imprint_stat_scale)
        if s in OFFSET_STATS:
            v -= 1.0
        lines.append("%s=%.6f" % (JA_STAT_KEYS[s], v))
    return "\n".join(lines) + "\n"


def make_export_gun_sav(sp, sm, levels_wild, levels_dom, levels_mut, level,
                        imprint=0.0, taming_eff=1.0, name="", sex=FEMALE):
    """Export Gun の .sav (GVAS に JSON を 1 個詰めたもの) を組み立てる。"""
    wild_total = sum(levels_wild) + sum(levels_mut)
    stat_list = []
    for s in range(ark.STATS_COUNT):
        lw = wild_total if s == ark.TORPIDITY else levels_wild[s]
        lm = 0 if s == ark.TORPIDITY else levels_mut[s]
        v = 0.0
        if sp.stats[s] is not None:
            v = stats.calc_value(sp, s, lw, lm, levels_dom[s], True,
                                 taming_eff=taming_eff, imprinting_bonus=imprint,
                                 imprint_stat_scale=sm.imprint_stat_scale)
            if s in OFFSET_STATS:
                v -= 1.0
        stat_list.append({"Wild": lw, "Tamed": levels_dom[s], "Mutated": lm,
                          "Value": v})
    doc = {
        "Version": 1,
        "DinoName": name,
        "SpeciesName": sp.name,
        "TribeName": "ぺんぎん族",
        "OwningPlayerName": "ゆう",
        "ImprinterName": "ゆう" if imprint > 0 else "",
        "OwningPlayerID": 1,
        "DinoID1": "111111111",
        "DinoID2": "222222222",
        "Ancestry": {"MaleName": "父", "MaleDinoId1": "3", "MaleDinoId2": "4",
                     "FemaleName": "母", "FemaleDinoId1": "5", "FemaleDinoId2": "6"},
        "BlueprintPath": sp.bp,
        "Stats": stat_list,
        "ColorSetIndices": [1, 2, 3, 4, 5, 6],
        "IsFemale": sex == FEMALE,
        "RandomMutationsMale": 3,
        "RandomMutationsFemale": 2,
        "TameEffectiveness": taming_eff,
        "BaseCharacterLevel": level,
        "DinoImprintingQuality": imprint,
    }
    payload = json.dumps(doc, ensure_ascii=False).encode("utf-8") + b"\x00"
    blob = b"GVAS" + b"\x00" * 16
    blob += b"DinoExportGunSave_C\x00"
    blob += b"JsonProperty\x00" + b"StrProperty\x00"
    blob += b"\x00" * 9
    blob += struct.pack("<i", len(payload)) + payload
    return blob


def main():
    db = SpeciesDB()
    sm = ServerMultipliers.official("asa")
    db.apply_multipliers(sm, "asa")
    rex = db.get("Rex")
    print("種族DB %d 件 / Rex = %s" % (len(db), rex.bp))

    tmp = tempfile.mkdtemp(prefix="arklib_test_")

    # ---- [1] 交配産の ini -------------------------------------------
    print("\n[1] 標準エクスポート (.ini) / 交配産")
    lw = [0] * 12
    lw[ark.HEALTH] = 45
    lw[ark.STAMINA] = 38
    lw[ark.OXYGEN] = 12
    lw[ark.FOOD] = 20
    lw[ark.WEIGHT] = 41
    lw[ark.MELEE] = 46
    ld = [0] * 12
    ld[ark.HEALTH] = 20
    ld[ark.WEIGHT] = 10
    level = 1 + sum(lw) + sum(ld)
    text = make_export_ini(rex, sm, lw, ld, level, state="bred", imprint=0.47,
                           name="ノワール", sex=FEMALE)
    p = os.path.join(tmp, "Rex_bred.ini")
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(text)

    r = import_file(p, db, sm)
    check("1.1 取り込み成功", r.ok, True)
    if r.ok:
        c = r.creature
        check("1.2 種族", c.species_name, "Rex")
        check("1.3 名前", c.name, "ノワール")
        check("1.4 性別", c.sex, FEMALE)
        check("1.5 状態", c.state, "bred")
        check("1.6 レベル", c.level, level)
        check("1.7 刷り込み", round(c.imprint, 3), 0.47)
        check("1.8 野生レベル内訳", [c.levels_wild[s] for s in breeding.BREEDING_STATS],
              [lw[s] for s in breeding.BREEDING_STATS])
        check("1.9 強化レベル内訳", [c.levels_dom[s] for s in breeding.BREEDING_STATS],
              [ld[s] for s in breeding.BREEDING_STATS])
        check("1.10 ID", c.ark_id, (123456789 << 32) | 987654321)
    else:
        print("      " + " / ".join(r.problems))

    # ---- [2] テイム個体 (効率が未知) ---------------------------------
    print("\n[2] 標準エクスポート (.ini) / テイム個体・効率はファイルに無い")
    lw2 = [0] * 12
    lw2[ark.HEALTH] = 30
    lw2[ark.STAMINA] = 21
    lw2[ark.OXYGEN] = 15
    lw2[ark.FOOD] = 25
    lw2[ark.WEIGHT] = 18
    lw2[ark.MELEE] = 33
    ld2 = [0] * 12
    ld2[ark.MELEE] = 12
    te = 0.764
    level2 = 1 + sum(lw2) + sum(ld2)
    text = make_export_ini(rex, sm, lw2, ld2, level2, state="tamed",
                           taming_eff=te, name="テイム子", sex=MALE,
                           ark_id=(555, 666))
    p2 = os.path.join(tmp, "Rex_tamed.ini")
    with io.open(p2, "w", encoding="utf-8") as f:
        f.write(text)
    r2 = import_file(p2, db, sm)
    check("2.1 取り込み成功", r2.ok, True)
    if r2.ok:
        c2 = r2.creature
        check("2.2 野生レベル内訳", [c2.levels_wild[s] for s in breeding.BREEDING_STATS],
              [lw2[s] for s in breeding.BREEDING_STATS])
        check("2.3 強化レベル内訳", [c2.levels_dom[s] for s in breeding.BREEDING_STATS],
              [ld2[s] for s in breeding.BREEDING_STATS])
        check("2.4 テイム効率の復元", round(c2.taming_eff or 0, 3), te)
        print("       候補 %d 通り / %s" % (len(r2.solutions), " ".join(r2.notes)))
    else:
        print("      " + " / ".join(r2.problems))

    # ---- [3] Export Gun --------------------------------------------
    print("\n[3] Export Gun (.sav)")
    lm3 = [0] * 12
    lm3[ark.MELEE] = 6          # 変異 3 回
    blob = make_export_gun_sav(rex, sm, lw, ld, lm3, level + 6, imprint=1.0,
                               name="変異持ち")
    p3 = os.path.join(tmp, "Rex_gun.sav")
    with io.open(p3, "wb") as f:
        f.write(blob)
    r3 = import_file(p3, db, sm)
    check("3.1 取り込み成功", r3.ok, True)
    if r3.ok:
        c3 = r3.creature
        check("3.2 野生レベル", [c3.levels_wild[s] for s in breeding.BREEDING_STATS],
              [lw[s] for s in breeding.BREEDING_STATS])
        check("3.3 変異レベル", c3.levels_mut[ark.MELEE], 6)
        check("3.4 継承レベル(野生+変異)", c3.bl(ark.MELEE), lw[ark.MELEE] + 6)
        check("3.5 変異カウンタ", (c3.mutations_father, c3.mutations_mother), (3, 2))
        check("3.6 色", c3.colors[:6], [1, 2, 3, 4, 5, 6])
    else:
        print("      " + " / ".join(r3.problems))

    # ---- [3.5] セクション名が翻訳されていても読めるか ----------------
    print("\n[3.5] セクション名が日本語のエクスポート")
    text = make_export_ini(rex, sm, lw, ld, level, state="bred", imprint=0.47,
                           name="日本語鯖の子", sex=FEMALE, ark_id=(777, 888))
    text = text.replace("[Max Character Status Values]", "[最大キャラクターステータス値]")
    p35 = os.path.join(tmp, "Rex_ja.ini")
    with io.open(p35, "w", encoding="utf-8") as f:
        f.write(text)
    r35 = import_file(p35, db, sm)
    check("3.5.1 取り込み成功", r35.ok, True)
    if r35.ok:
        check("3.5.2 野生レベル内訳",
              [r35.creature.levels_wild[s] for s in breeding.BREEDING_STATS],
              [lw[s] for s in breeding.BREEDING_STATS])
    else:
        print("      " + " / ".join(r35.problems))

    # ---- [3.6] 実機のエクスポート (回帰テスト) ------------------------
    print("\n[3.6] 実機 ASA のエクスポートファイル")
    _real_file_check(db)

    # ---- [3.7] 強化レベルを振ったテイム個体 --------------------------
    print("\n[3.7] 強化レベルを振ったテイム個体 (前は読めなくなっていた)")
    _leveled_tamed_check(db, sm, rex, tmp)

    # ---- [4] ライブラリ保存と重複判定 --------------------------------
    print("\n[4] ライブラリ (SQLite)")
    dbfile = os.path.join(tmp, "library.db")
    lib = Library(dbfile)
    r4 = import_file(p, db, sm, library=lib, server="Ragnarok")
    check("4.1 初回は追加", r4.action, "added")
    r5 = import_file(p, db, sm, library=lib, server="Ragnarok")
    check("4.2 同じ個体は更新", r5.action, "updated")
    check("4.3 件数は 1", lib.count(), 1)
    import_file(p3, db, sm, library=lib, server="Ragnarok")
    check("4.4 別個体は追加される", lib.count(), 2)
    summary = lib.species_summary()
    check("4.5 種族まとめ", (summary[0]["species_name"], summary[0]["n"]), ("Rex", 2))
    got = lib.get(r4.creature.uid)
    check("4.6 読み戻し", got.levels_wild, r4.creature.levels_wild)
    lib.close()

    # ---- [5] 交配プラン ---------------------------------------------
    print("\n[5] 交配プラン")
    pop = _make_population(rex)
    tops = breeding.top_levels(pop)
    check("5.1 最高体力", tops[ark.HEALTH], 45)
    check("5.2 最高近接", tops[ark.MELEE], 50)
    cover, missing = breeding.minimal_cover(pop, tops)
    check("5.3 必要個体数", len(cover), 3)
    check("5.4 届かないステなし", len(missing), 0)
    pairs = breeding.rank_pairs(pop, limit=3)
    check("5.5 ペア候補あり", len(pairs) >= 1, True)
    best = pairs[0]
    print("       推奨: %s" % best.describe(rex).replace("\n", "\n       "))
    plan = breeding.plan_to_best(pop)
    check("5.6 世代数", plan["generations"], 2)
    print("       手順:")
    for st in plan["steps"]:
        print("         第%d世代 %s × %s → %s (確率 %.1f%%, 平均 %.1f 匹)"
              % (st.generation, st.a.display_name, st.b.display_name,
                 st.result_label, st.probability * 100, st.eggs_needed))
    fin = plan["final"]
    check("5.7 最終個体が全最高値", all(fin.bl(s) >= lv for s, lv in tops.items()), True)
    check("5.8 最終個体の素レベル", fin.base_level(), 1 + sum(tops.values()))

    # ---- [6] 変異の推定 --------------------------------------------
    print("\n[6] 親からの変異推定")
    mother = pop[0]
    father = pop[1]
    child = [max(mother.bl(s), father.bl(s)) for s in range(12)]
    child[ark.HEALTH] += 2          # 体力に変異 1 回
    mlw, mlm, notes = breeding.infer_mutations(child, mother, father)
    check("6.1 変異ステを特定", mlm[ark.HEALTH], 2)
    check("6.2 他は変異なし", sum(mlm) - mlm[ark.HEALTH], 0)
    print("       " + " / ".join(notes))

    # ---- [8] 逆算の速さ ---------------------------------------------
    print("\n[8] 逆算の速さ (強化レベルを振ったテイム個体)")
    _speed_check(db, sm, rex)

    # ---- [7] 性別が無い種族 -----------------------------------------
    print("\n[7] 性別が無い種族 (メイグアナ)")
    _genderless_check(db, sm, tmp)

    print("\n" + "=" * 66)
    print("%d 件成功 / %d 件失敗" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失敗: " + ", ".join(FAIL))
    print("テストファイル: %s" % tmp)
    return 1 if FAIL else 0


def _real_file_check(db):
    """実機で吐かれた ini (カワウソ) を読み戻す。

    この個体は名前が `F H47 S24 W37 M26` になっていて、飼い主が付けた
    ステータスのメモがそのまま答えになっている。サーバーは公式相当だが
    **重量のテイムLv倍率だけ 2 倍**。
    """
    from arklib.multipliers import IDX_LEVEL_DOM

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "real_asa_otter.ini")
    if not os.path.isfile(path):
        print("  -- fixture が無いので飛ばします")
        return

    sm = ServerMultipliers.official("asa")
    sm.stat[ark.WEIGHT][IDX_LEVEL_DOM] = 2.0
    db.apply_multipliers(sm, "asa")

    ec = dino_export_ini.parse_file(path)
    check("3.6.1 種族", ec.species_tag, "Otter")
    check("3.6.2 名前 (これが答え)", ec.name, "F H47 S24 W37 M26")
    check("3.6.3 レベル", ec.level, 211)
    check("3.6.4 性別", ec.sex, FEMALE)
    # BabyAge=1 は成体でも書かれるので、これを交配産と誤判定しないこと
    check("3.6.5 状態はテイム個体", ec.state, "tamed")

    r = import_file(path, db, sm)
    check("3.6.6 取り込み成功", r.ok, True)
    if not r.ok:
        print("      " + " / ".join(r.problems))
        return
    c = r.creature
    check("3.6.7 体力", c.bl(ark.HEALTH), 47)
    check("3.6.8 スタミナ", c.bl(ark.STAMINA), 24)
    check("3.6.9 重量", c.bl(ark.WEIGHT), 37)
    check("3.6.10 近接", c.bl(ark.MELEE), 26)
    check("3.6.11 重量に振った強化レベル", c.levels_dom[ark.WEIGHT], 5)
    check("3.6.12 テイム効率", round((c.taming_eff or 0) * 100, 1), 95.0)
    check("3.6.13 解は一意", r.ambiguous, False)
    check("3.6.14 飼い主", c.owner, "Simon")
    db.apply_multipliers(ServerMultipliers.official("asa"), "asa")


def _leveled_tamed_check(db, sm, rex, tmp):
    """テイム個体に強化レベルを振っても逆算できるか。

    以前はテイム効率の候補を 40 件で打ち切っていたため、強化レベルを
    15 も振ると正解の効率が候補から漏れて読めなくなっていた。
    """
    from arklib.library import Library
    from arklib.importers import import_file

    te = 0.78
    lw = [0] * 12
    for s, v in ((ark.HEALTH, 60), (ark.STAMINA, 21), (ark.OXYGEN, 15),
                 (ark.FOOD, 25), (ark.WEIGHT, 18), (ark.MELEE, 33)):
        lw[s] = v
    lib = Library(os.path.join(tmp, "leveled.db"))

    def make(ld_map, name, ark_id=(4242, 4242)):
        ld = [0] * 12
        for s, v in ld_map.items():
            ld[s] = v
        level = 1 + sum(lw) + sum(ld)
        text = make_export_ini(rex, sm, lw, ld, level, state="tamed",
                               taming_eff=te, name=name, sex=MALE, ark_id=ark_id)
        p = os.path.join(tmp, name + ".ini")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    # まだ何も振っていない状態
    r = import_file(make({}, "テイム直後"), db, sm, library=lib, server="t")
    check("3.7.1 強化なしは読める", r.ok, True)
    check("3.7.2 テイム効率", round((r.creature.taming_eff or 0), 2), 0.78)

    # 振ったあと。前回の野生レベルを手がかりにできる
    for n in (20, 60, 150):
        r = import_file(make({ark.HEALTH: n // 2, ark.MELEE: n - n // 2},
                             "強化%d" % n), db, sm, library=lib, server="t")
        ok = (r.ok and r.creature.levels_wild[ark.HEALTH] == 60
              and r.creature.levels_dom[ark.MELEE] == n - n // 2)
        check("3.7.3 強化 %d を振っても読める" % n, ok, True)

    # はじめて見る個体 (手がかりなし) でも、そこそこ振ってあれば読めること
    r = import_file(make({ark.HEALTH: 15, ark.MELEE: 15}, "初見",
                         ark_id=(777, 888)), db, sm, library=lib, server="t")
    check("3.7.4 初見でも強化 30 なら読める", r.ok, True)
    lib.close()


def _speed_check(db, sm, rex):
    """一次式の近道が本当の計算と一致すること、そして速いこと。

    ステータス値は野生レベルについても強化レベルについても一次なので、
    2 点だけ計算して残りは掛け算・足し算で出している (extractor._line_at /
    extraction._Line)。ここが狂うと逆算の答えが静かに変わるので見張る。
    """
    import time

    from arklib import extraction, extractor

    # --- 近道と本当の計算が合うか (種族とステータスを一通り) ---
    bad = []
    checked = 0
    for sp in [s2 for s2 in db.all if s2.in_asa][:120]:
        ex = extractor.Extraction(sp, 100, {}, "tamed", 0.8, 0.0, 1.0)
        for s2 in sp.displayed_stat_indices():
            if sp.stats[s2] is None:
                continue
            for ld in (0, 1, 7, 30):
                got = extractor._line_at(sp, ex, s2, ld)
                want0 = extractor._calc(sp, s2, ex, 0, ld)
                want1 = extractor._calc(sp, s2, ex, 1, ld)
                checked += 1
                if (abs(got[0] - want0) > 1e-9 * max(1.0, abs(want0))
                        or abs(got[1] - (want1 - want0))
                        > 1e-9 * max(1.0, abs(want1))):
                    bad.append((sp.name, s2, ld, got, (want0, want1 - want0)))
    check("8.1 近道の値が本当の計算と一致 (%d 通り)" % checked, len(bad), 0)
    if bad:
        for b in bad[:3]:
            print("      %s" % (b,))

    line_bad = []
    for sp in [s2 for s2 in db.all if s2.in_asa][:120]:
        for s2 in sp.displayed_stat_indices():
            if sp.stats[s2] is None:
                continue
            line = extraction._Line(sp, s2, 0.73, 0.0, 1.0)
            for ld in (0, 3, 40):
                b0, k0 = line.at(ld)
                w0 = extraction._calc(sp, s2, 0, ld, 0.73, 0.0, 1.0)
                w1 = extraction._calc(sp, s2, 1, ld, 0.73, 0.0, 1.0)
                if (abs(b0 - w0) > 1e-9 * max(1.0, abs(w0))
                        or abs(k0 - (w1 - w0)) > 1e-9 * max(1.0, abs(w1))):
                    line_bad.append((sp.name, s2, ld))
    check("8.2 効率側の近道も一致", len(line_bad), 0)

    # --- 速さ ---
    lw = [0] * 12
    for s2 in (ark.HEALTH, ark.STAMINA, ark.OXYGEN, ark.FOOD, ark.WEIGHT,
               ark.MELEE):
        lw[s2] = 30
    ld = [0] * 12
    ld[ark.HEALTH] = 30
    ld[ark.WEIGHT] = 30
    wild_total = sum(lw)
    vals = {}
    for s2 in range(ark.STATS_COUNT):
        if rex.stats[s2] is None:
            continue
        lvl = wild_total if s2 == ark.TORPIDITY else lw[s2]
        dd = 0 if s2 == ark.TORPIDITY else ld[s2]
        vals[s2] = stats.calc_value(rex, s2, lvl, 0, dd, True, taming_eff=0.95)
    level = 1 + wild_total + sum(ld)

    t = time.perf_counter()
    r = extraction.extract_levels(rex, level, vals, sm, state="tamed",
                                  budget=30.0)
    dt = (time.perf_counter() - t) * 1000
    check("8.3 強化60のテイム個体が解ける", r.ok, True)
    if r.ok:
        check("8.4 野生レベルが合っている",
              [r.levels_wild[s2] for s2 in (ark.HEALTH, ark.MELEE)],
              [lw[ark.HEALTH], lw[ark.MELEE]])
        check("8.5 強化レベルが合っている",
              [r.levels_dom[s2] for s2 in (ark.HEALTH, ark.WEIGHT)],
              [ld[ark.HEALTH], ld[ark.WEIGHT]])
    # 前は 400ms 近くかかっていた。遅い機械でも 300ms は超えないはず
    check("8.6 %.0f ms で終わる (300ms 未満)" % dt, dt < 300, True)


MAEGUANA_BP = "/Game/ASA/Dinos/Maelizard/Maelizard_Character_BP.Maelizard_Character_BP"


def _genderless_check(db, sm, tmp):
    """メイグアナのような雌雄の無い種族は U として取り込む。

    ARK のエクスポートは bIsFemale=False と書いてくるので、そのまま読むと
    全部オスになり、交配の相手が 1 体も出なくなる。
    """
    sp = db.by_bp(MAEGUANA_BP)
    if sp is None:
        print("  -- メイグアナが種族DBに無いので飛ばします")
        return
    check("7.1 性別の無い種族と分かる", sp.no_gender, True)
    lw = [0] * 12
    lw[ark.HEALTH] = 30
    lw[ark.MELEE] = 25
    lib = Library(os.path.join(tmp, "genderless.db"))
    uids = []
    for i, (name, hp, me) in enumerate([("メイ1", 30, 25), ("メイ2", 12, 44)]):
        lw[ark.HEALTH], lw[ark.MELEE] = hp, me
        text = make_export_ini(sp, sm, lw, [0] * 12, 1 + hp + me, state="bred",
                               name=name, sex=MALE,
                               ark_id=(500 + i, 600 + i))
        p = os.path.join(tmp, "Maeguana_%d.ini" % i)
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(text)
        r = import_file(p, db, sm, library=lib, server="Astraeos")
        check("7.%d 取り込み成功 (%s)" % (2 + i, name), r.ok, True)
        if not r.ok:
            print("      " + " / ".join(r.problems))
            lib.close()
            return
        check("7.%d 性別は U" % (4 + i), r.creature.sex, GENDERLESS)
        uids.append(r.creature.uid)

    pool = lib.all_creatures()
    pairs = breeding.rank_pairs(pool, stat_list=[ark.HEALTH, ark.MELEE],
                                species_db=db)
    check("7.6 交配表ができる", len(pairs), 1)
    check("7.7 頭数は U でまとめる",
          lib.species_summary()[0]["genderless"], 2)

    # 古いデータ (性別不明 '-' で入っていたもの) を直せるか
    lib.db.execute("UPDATE creatures SET sex = '-'")
    lib.db.commit()
    check("7.8 直す前は交配できない",
          len(breeding.rank_pairs(lib.all_creatures(), stat_list=[ark.HEALTH],
                                  species_db=db)), 0)
    check("7.9 移行で 2 体直る", lib.fix_genderless(db), 2)
    check("7.10 直ったら交配できる",
          len(breeding.rank_pairs(lib.all_creatures(), stat_list=[ark.HEALTH],
                                  species_db=db)), 1)
    check("7.11 二度目は何もしない", lib.fix_genderless(db), 0)
    lib.close()


def _make_population(sp):
    """最高ステがばらけた Rex の群れ。"""
    def mk(name, sex, hp, st, wt, me, muts=0):
        c = Creature(species_bp=sp.bp, species_name=sp.display_name, name=name,
                     sex=sex, state="bred", level=1 + hp + st + wt + me)
        c.levels_wild[ark.HEALTH] = hp
        c.levels_wild[ark.STAMINA] = st
        c.levels_wild[ark.WEIGHT] = wt
        c.levels_wild[ark.MELEE] = me
        c.mutations_father = muts
        return c

    return [
        mk("体力番長", MALE, 45, 20, 25, 30),
        mk("近接番長", FEMALE, 30, 22, 26, 50, muts=3),
        mk("重量番長", FEMALE, 28, 25, 40, 31),
        mk("凡骨", MALE, 20, 18, 22, 25),
    ]


if __name__ == "__main__":
    sys.exit(main())
