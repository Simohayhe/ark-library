# -*- coding: utf-8 -*-
"""狙い方 (最高 / ゼロ)、名前のモード、色の交配のテスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import ark, breeding, colors, ideal, naming, records
from arklib.creature import FEMALE, GENDERLESS, MALE, Creature

PASS, FAIL = [], []
MAX, MIN = breeding.MAX, breeding.MIN


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print("  OK   %-46s %s" % (name, got))
    else:
        FAIL.append(name)
        print("  NG   %-46s got=%s want=%s" % (name, got, want))


def near(name, got, want, tol=1e-6):
    check(name, abs(got - want) < tol, True)


def mk(name="", sex=MALE, hp=10, st=10, ox=10, fd=10, wt=10, me=10, uid=None,
       mut=0, color=None):
    c = Creature(species_bp="bp/Rex", species_name="Rex", name=name, sex=sex,
                 state="bred", uid=uid)
    for s, lv in ((ark.HEALTH, hp), (ark.STAMINA, st), (ark.OXYGEN, ox),
                  (ark.FOOD, fd), (ark.WEIGHT, wt), (ark.MELEE, me)):
        c.levels_wild[s] = lv
    c.mutations_father = mut
    if color:
        c.colors = list(color) + [0] * (6 - len(color))
    return c


def main():
    HP, ST, OX, FD, WT, ME = (ark.HEALTH, ark.STAMINA, ark.OXYGEN, ark.FOOD,
                              ark.WEIGHT, ark.MELEE)

    print("[1] 目標の向き")
    goals = {HP: MAX, ME: MAX, OX: MIN, FD: MIN}
    pool = [mk("高HP", MALE, hp=40, ox=12, fd=15),
            mk("低酸素", FEMALE, hp=20, ox=0, fd=15),
            mk("低食料", FEMALE, hp=25, ox=9, fd=0, me=30)]
    t = breeding.target_levels(pool, goals)
    check("1.1 体力は最高値", t[HP], 40)
    check("1.2 酸素は最低値", t[OX], 0)
    check("1.3 食料は最低値", t[FD], 0)
    check("1.4 ゼロ狙いの達成判定", OX in breeding.covered_stats(pool[1], t, goals), True)
    check("1.5 高い酸素は未達", OX in breeding.covered_stats(pool[0], t, goals), False)

    print("\n[2] 継承の確率 (高い方 55% / 低い方 45%)")
    p_max = breeding.PairPlan(mk(sex=MALE, hp=40), mk(sex=FEMALE, hp=10),
                              {HP: 40}, goals={HP: MAX})
    near("2.1 最高狙いは 55%", p_max.probability, 0.55)
    p_min = breeding.PairPlan(mk(sex=MALE, ox=20), mk(sex=FEMALE, ox=0),
                              {OX: 0}, goals={OX: MIN})
    near("2.2 ゼロ狙いは 45%", p_min.probability, 0.45)
    check("2.3 ゼロ狙いの最良の子は低い方", p_min.best_child[OX], 0)
    mixed = breeding.PairPlan(mk(sex=MALE, hp=40, ox=20), mk(sex=FEMALE, hp=10, ox=0),
                              {HP: 40, OX: 0}, goals={HP: MAX, OX: MIN})
    near("2.4 混ざると 0.55*0.45", mixed.probability, 0.55 * 0.45)
    check("2.5 両方そろう子", (mixed.best_child[HP], mixed.best_child[OX]), (40, 0))

    print("\n[3] Lv1 個体 (全ステゼロ) を目指す")
    all_min = {s: MIN for s in (HP, ST, OX, FD, WT, ME)}
    zero_pool = [mk("素体A", MALE, hp=0, st=0, ox=5, fd=5, wt=5, me=5),
                 mk("素体B", FEMALE, hp=5, st=5, ox=0, fd=0, wt=0, me=0)]
    tz = breeding.target_levels(zero_pool, all_min)
    check("3.1 全部 0 が目標", sorted(tz.values()), [0] * 6)
    plan = breeding.plan_to_best(zero_pool, goals=all_min)
    fin = plan["final"]
    check("3.2 1 世代で届く", plan["generations"], 1)
    check("3.3 最終個体は素Lv1", fin.base_level(), 1)
    near("3.4 その確率は 0.45^6", plan["steps"][0].probability, 0.45 ** 6)

    print("\n[3.5] 目標の数え方")
    mixed2 = breeding.PairPlan(mk(sex=MALE, hp=40, ox=20),
                               mk(sex=FEMALE, hp=10, ox=0),
                               {HP: 40, OX: 0}, goals={HP: MAX, OX: MIN})
    check("3.5.1 両方の目標を満たす", mixed2.top_count, 2)
    bad = breeding.PairPlan(mk(sex=MALE, hp=10, ox=20),
                            mk(sex=FEMALE, hp=10, ox=20),
                            {HP: 40, OX: 0}, goals={HP: MAX, OX: MIN})
    check("3.5.2 どちらも届かない", bad.top_count, 0)

    print("\n[4] 名前のモード")
    cr = mk("", MALE, hp=47, st=24, ox=0, fd=0, wt=37, me=26, mut=20)
    cr.mutations_mother = 3
    order = [HP, ST, OX, FD, WT, ME]
    check("4.1 ぜんぶ", naming.make_name(cr, order, True), "M H47 S24 O0 F0 W37 M26")
    check("4.2 ゼロだけ",
          naming.make_name(cr, order, True, mode=naming.MODE_ZEROS), "M O0 F0")
    check("4.3 OF (変異数)",
          naming.make_name(cr, order, True, mode=naming.MODE_MUTATIONS),
          "M 23 (20/3)")
    clean = mk("", FEMALE, hp=1, st=1, ox=1, fd=1, wt=1, me=1)
    check("4.4 ゼロが無いとき",
          naming.make_name(clean, order, True, mode=naming.MODE_ZEROS), "F 0なし")

    print("\n[5] 記録判定 (ゼロ狙い)")
    others = [mk("既存", uid=1, ox=4)]
    lower = mk("新入り", uid=None, ox=1)
    r = records.check(lower, others, goals={OX: MIN})
    check("5.1 低いほうが記録", r.per_stat[OX], records.NEW)
    check("5.2 見出し", r.label(), "今までで一番低い")
    higher = mk("高い", uid=None, ox=9)
    check("5.3 高いのは記録でない",
          records.check(higher, others, goals={OX: MIN}).per_stat[OX], records.NONE)
    tie = mk("同じ", uid=None, ox=4)
    check("5.4 並んだらタイ",
          records.check(tie, others, goals={OX: MIN}).per_stat[OX], records.TIE)

    print("\n[6] 色")
    check("6.1 色データが読める", colors.count() >= 90, True)
    check("6.2 RGBA から ID", colors.closest_id((1.0, 0.0, 0.0, 0.0)),
          colors.all_ids()[0])
    check("6.3 使っていない領域は 0", colors.closest_id((0.0, 0.0, 0.0, 1.0)), 0)
    check("6.4 色名", colors.name_of(colors.closest_id((1.0, 0.0, 0.0, 0.0))), "Red")

    m = mk("父", MALE, color=[10, 20, 0, 0, 0, 0])
    f = mk("母", FEMALE, color=[10, 33, 0, 0, 0, 0])
    cp = breeding.ColorPair(m, f, {0: 10, 1: 20})
    check("6.5 両親が持つ領域は確定", cp.sure_regions, [0])
    check("6.6 片方だけの領域は五分五分", cp.risky_regions, [1])
    near("6.7 確率は 50%", cp.probability, 0.5)
    impossible = breeding.ColorPair(m, f, {1: 99})
    check("6.8 どちらも持たない色は無理", impossible.possible, False)
    near("6.9 その確率は 0", impossible.probability, 0.0)
    inv = breeding.color_inventory([m, f], [0, 1])
    check("6.10 色の持ち主が引ける", sorted(inv[1]), [20, 33])
    ranked = breeding.rank_color_pairs([m, f], {0: 10, 1: 20})
    check("6.11 ペアを並べられる", len(ranked), 1)

    print("\n[7] あとから親が揃ったときの変異の割り出し")
    import tempfile

    from arklib.library import Library

    lib = Library(os.path.join(tempfile.mkdtemp(prefix="mut_"), "lib.db"))
    dad = mk("父", MALE, hp=30, me=40)
    dad.ark_id = 111
    mom = mk("母", FEMALE, hp=30, me=35)
    mom.ark_id = 222
    kid = mk("子", MALE, hp=30, me=42)          # 近接が父より +2 = 変異
    kid.ark_id = 333
    kid.father_ark_id, kid.mother_ark_id = 111, 222
    for c in (kid, dad, mom):                   # 子を先に入れる
        lib.save(c)
    check("7.1 取り込み直後は変異が分からない",
          lib.by_ark_id(333).levels_mut[ME], 0)
    fixed, looked, notes = breeding.reassign_mutations(lib)
    check("7.2 親が見つかった", looked, 1)
    check("7.3 直した", fixed, 1)
    check("7.4 近接に変異 +2", lib.by_ark_id(333).levels_mut[ME], 2)
    check("7.5 野生ぶんは父から", lib.by_ark_id(333).levels_wild[ME], 40)
    check("7.6 継承レベルは変わらない", lib.by_ark_id(333).bl(ME), 42)
    again = breeding.reassign_mutations(lib)[0]
    check("7.7 二度目は何も変えない", again, 0)
    lib.close()

    print("\n[8] 性別が無い種族 (メイグアナなど)")
    u1 = mk("U1", GENDERLESS, hp=40, me=10)
    u2 = mk("U2", GENDERLESS, hp=10, me=40)
    u3 = mk("U3", GENDERLESS, hp=20, me=20)
    check("8.1 交配に使える", u1.can_breed(), True)
    check("8.2 性別なしと分かる", u1.is_genderless, True)
    check("8.3 同じ種族なら組める", breeding.can_mate(u1, u2), True)
    check("8.4 自分とは組めない", breeding.can_mate(u1, u1), False)
    check("8.5 M/F とは組めない", breeding.can_mate(u1, mk("M", MALE)), False)
    check("8.6 全部の組み合わせが出る",
          len(list(breeding.iter_pairs([u1, u2, u3]))), 3)
    check("8.7 並び順は名前順",
          [c.display_name for c in breeding.order_pair(u2, u1)], ["U1", "U2"])
    ranked = breeding.rank_pairs([u1, u2, u3], stat_list=[ark.HEALTH, ark.MELEE])
    check("8.8 おすすめペアが出る", len(ranked), 3)
    best = ranked[0]
    check("8.9 一番良いのは 40/40 持ち同士",
          sorted([best.male.display_name, best.female.display_name]),
          ["U1", "U2"])
    check("8.10 名前の先頭は U", naming.make_name(u1, [ark.HEALTH]), "U H40")
    mixed = [u1, u2, mk("M", MALE), mk("F", FEMALE)]
    check("8.11 混ざっていても取り違えない",
          sorted("".join(sorted([a.display_name, b.display_name]))
                 for a, b in breeding.iter_pairs(mixed)), ["FM", "U1U2"])
    dead = mk("U4", GENDERLESS)
    dead.status = "dead"
    check("8.12 死亡は除く", breeding.can_mate(u1, dead), False)

    print("\n[8.5] イベント色 / 変異色の見分け")
    REX = "/Game/PrimalEarth/Dinos/Rex/Rex_Character_BP.Rex_Character_BP"
    wild_ids = colors.possible_ids(REX, 0)
    check("8.5.1 野生パレットが引ける", len(wild_ids) > 0, True)
    natural = wild_ids[0]
    odd = next(c for c in colors.all_ids() if c not in wild_ids)
    print("       Rex の Body 野生色: %s  / 野生に無い色: %d (%s)"
          % (wild_ids, odd, colors.name_of(odd)))

    check("8.5.2 野生色は natural",
          colors.classify(REX, 0, natural, bred=False), colors.NATURAL)
    check("8.5.3 交配産でも野生色は natural",
          colors.classify(REX, 0, natural, bred=True), colors.NATURAL)
    check("8.5.4 テイム個体の野生外はイベント色",
          colors.classify(REX, 0, odd, bred=False), colors.EVENT)
    check("8.5.5 交配産の野生外は変異色",
          colors.classify(REX, 0, odd, bred=True), colors.MUTATION)
    check("8.5.6 色なしは判定しない",
          colors.classify(REX, 0, 0, bred=True), colors.UNKNOWN)
    check("8.5.7 色データの無い種族は判定しない",
          colors.classify("bp/しらない生物", 0, 5, bred=True), colors.UNKNOWN)

    check("8.5.8 印は ★ (イベント)",
          colors.mark_of(REX, 0, odd, bred=False), "★")
    check("8.5.9 印は ◆ (変異)",
          colors.mark_of(REX, 0, odd, bred=True), "◆")
    check("8.5.10 野生色に印は付かない",
          colors.mark_of(REX, 0, natural, bred=True), "")

    six = [natural, 0, 0, 0, odd, 0]
    got = colors.odd_colors(REX, six, bred=True)
    check("8.5.11 野生外だけ拾う", [(i, c) for i, c, _k in got], [(4, odd)])
    check("8.5.12 一行にまとめられる",
          colors.describe_odd(REX, six, bred=True).startswith("変異色:"), True)
    check("8.5.13 テイムならイベント色と言う",
          colors.describe_odd(REX, six, bred=False).startswith("イベント色:"), True)
    check("8.5.14 ふつうの個体は空",
          colors.describe_odd(REX, [natural, 0, 0, 0, 0, 0], bred=True), "")

    # ---- 染料域 (ID 128 以降) は野生に出ない ----
    # ASA-values.json の dyeStartIndex と公式 wiki より
    #   1〜127 生物色 (定義は 1〜100) / 128〜254 染料色 / 255 未設定
    check("8.5.15 染料の始まりは 128", colors.DYE_FIRST_ID, 128)
    check("8.5.16 染料色が入っている", len(colors.dye_ids()), 127)
    check("8.5.17 生物色は 100 色", len(colors.creature_ids()), 100)
    check("8.5.18 127 以下は染料ではない", colors.is_dye(100), False)
    check("8.5.19 128 は染料", colors.is_dye(128), True)
    check("8.5.20 254 も染料", colors.is_dye(254), True)
    check("8.5.21 255 は未設定なので染料ではない", colors.is_dye(255), False)
    check("8.5.22 染料色に名前がある",
          colors.name_of(128), "Burn Coloring")
    check("8.5.23 染料色に色が引ける", bool(colors.hex_of(254)), True)

    # 種族のパレットを見るまでもなく野生ではない
    check("8.5.24 染料色は種族に関係なく野生外",
          colors.is_natural(REX, 0, 128), False)
    check("8.5.25 色データの無い種族でも染料色は分かる",
          colors.is_natural("bp/しらない生物", 0, 128), False)
    check("8.5.26 交配産の染料色は変異色",
          colors.classify(REX, 0, 128, bred=True), colors.MUTATION)
    check("8.5.27 テイムの染料色はイベント色",
          colors.classify(REX, 0, 200, bred=False), colors.EVENT)
    check("8.5.28 説明に染料域と書く",
          "[染料域]" in colors.describe_odd(REX, [128, 0, 0, 0, 0, 0],
                                            bred=True), True)

    # 表示値 (RGBA) から引き直すとき、生物色と染料色で
    # まったく同じ RGBA のものが 7 組ある。生物色の方を採る
    check("8.5.29 赤は 131 でなく 1",
          colors.closest_id((1.0, 0.0, 0.0, 0.0)), 1)
    check("8.5.30 白は 233 でなく 18",
          colors.closest_id((1.0, 1.0, 1.0, 0.0)), 18)
    check("8.5.31 染料にしか無い色は染料として引ける",
          colors.closest_id(colors.rgba_of(128)), 128)
    check("8.5.32 染料の端も引ける",
          colors.closest_id(colors.rgba_of(254)), 254)

    # ---- 定義の無い ID は判定しない ----
    #   0        その領域を使っていない
    #   101〜127 欠番 (ゲームに定義が無い)
    #   255      未設定 (ASA)
    # ここを「野生に無い色」と数えると、存在しない色名で変異色だと
    # 言ってしまう
    check("8.5.33 0 は色なし", colors.label_of(0), "なし")
    check("8.5.34 0 は定義なし", colors.is_defined(0), False)
    check("8.5.35 0 は判定しない",
          colors.classify(REX, 0, 0, bred=True), colors.UNKNOWN)
    check("8.5.36 0 に印は付かない", colors.mark_of(REX, 0, 0, True), "")

    check("8.5.37 101 は欠番", colors.is_defined(101), False)
    check("8.5.38 127 も欠番", colors.is_defined(127), False)
    check("8.5.39 100 は定義あり", colors.is_defined(100), True)
    check("8.5.40 128 は定義あり", colors.is_defined(128), True)
    check("8.5.41 欠番は判定しない",
          colors.classify(REX, 0, 101, bred=True), colors.UNKNOWN)
    check("8.5.42 欠番に印は付かない", colors.mark_of(REX, 0, 101, True), "")
    check("8.5.43 欠番はそう書く", colors.label_of(101), "定義の無い色 (101)")

    check("8.5.44 255 は未設定", colors.UNDEFINED_COLOR_ID, 255)
    check("8.5.45 255 はそう書く", colors.label_of(255), "未設定 (255)")
    check("8.5.46 255 は染料ではない", colors.is_dye(255), False)
    check("8.5.47 255 は判定しない",
          colors.classify(REX, 0, 255, bred=True), colors.UNKNOWN)

    # ASE では 227 が未設定の印だが、ASA の 227 はふつうの染料色
    check("8.5.48 ASA の 227 は染料色", colors.is_dye(227), True)
    check("8.5.49 227 に名前がある", colors.name_of(227), "Gunmetal Coloring")

    check("8.5.50 欠番と未設定だけなら何も出ない",
          colors.odd_colors(REX, [0, 101, 255, 0, 0, 0], bred=True), [])
    check("8.5.51 その説明も空",
          colors.describe_odd(REX, [0, 101, 255, 0, 0, 0], bred=True), "")
    check("8.5.52 まともな染料色は今まで通り拾う",
          [c for _i, c, _k in colors.odd_colors(REX, [128, 101, 255, 0, 0, 0],
                                                bred=True)], [128])

    print("\n[9] 理想個体 (目標) までの近さ")
    OX, ME2 = ark.OXYGEN, ark.MELEE
    idl = ideal.Ideal({ark.HEALTH: 50, ME2: 40, OX: 0}, {0: 14})
    perfect = mk("完璧", MALE, hp=50, me=40, ox=0, color=[14])
    half = mk("半分", FEMALE, hp=25, me=40, ox=10, color=[6])
    pool = [perfect, half]
    refs = ideal.refs_from(pool)
    check("9.1 目標どおりなら 100%", idl.score(perfect, refs).percent, 100.0)
    check("9.2 届いていれば達成", idl.score(perfect, refs).reached, True)
    near("9.3 半分だと下がる", idl.score(half, refs).percent, 37.5)
    check("9.4 足りない項目が分かる",
          sorted(i.label for i in idl.score(half, refs).short),
          sorted(["体力", "酸素", "領域0"]))
    check("9.5 近い順に並ぶ",
          [c.display_name for _s, c in ideal.rank(pool, idl, refs)],
          ["完璧", "半分"])

    # ステータスは遠いほど % が低い
    far = mk("遠い", MALE, hp=10, me=10, ox=10, color=[14])
    mid = mk("中くらい", MALE, hp=40, me=30, ox=5, color=[14])
    check("9.6 遠いほど低い",
          idl.score(far, refs).percent < idl.score(mid, refs).percent, True)
    check("9.7 目標を超えても 100% 止まり",
          idl.score(mk("超え", MALE, hp=99, me=99, ox=0, color=[14]),
                    refs).percent, 100.0)

    # 色は合っているかどうかだけ (近い色という考え方は無い)
    wrong = mk("色違い", MALE, hp=50, me=40, ox=0, color=[15])
    sc = idl.score(wrong, refs)
    check("9.8 色が違えばその項目は 0",
          [i.score for i in sc.items if i.kind == ideal.KIND_COLOR], [0.0])
    check("9.9 ステだけ満点なら 75%", round(sc.percent), 75)

    # ゼロ狙いは「群れでいちばん悪い値」を基準に下がる
    zero = ideal.Ideal({OX: 0})
    check("9.10 0 なら満点", zero.score(perfect, {OX: 20}).percent, 100.0)
    near("9.11 半分まで下げたら 50%", zero.score(half, {OX: 20}).percent, 50.0)

    # 子の評価は色を数えない
    sc2 = idl.score_levels({ark.HEALTH: 50, ME2: 40, OX: 0}, stats_only=True)
    check("9.12 子はステだけで見る", len(sc2.items), 3)
    check("9.13 子が理想どおり", sc2.reached, True)

    # 個体から理想を作る / 保存して読み戻す
    from_c = ideal.Ideal.from_creature(perfect, [ark.HEALTH, ME2, OX], [0])
    check("9.14 個体から作れる", from_c.stats[ark.HEALTH], 50)
    check("9.15 色も拾う", from_c.colors[0], 14)
    lib2 = Library(os.path.join(tempfile.mkdtemp(prefix="ideal_"), "lib.db"))
    ideal.save(lib2, "bp/Rex", from_c)
    back = ideal.load(lib2, "bp/Rex")
    check("9.16 保存して読み戻せる", back.to_dict(), from_c.to_dict())
    check("9.17 素レベルが出る", back.base_level(), 91)
    ideal.save(lib2, "bp/Rex", None)
    check("9.18 消せる", ideal.load(lib2, "bp/Rex").empty, True)
    check("9.19 決めていなければ 0 件",
          ideal.rank(pool, ideal.Ideal(), refs), [])
    lib2.close()

    print("\n" + "=" * 66)
    print("%d 件成功 / %d 件失敗" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失敗: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
