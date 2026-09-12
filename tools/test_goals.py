# -*- coding: utf-8 -*-
"""狙い方 (最高 / ゼロ)、名前のモード、色の交配のテスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import ark, breeding, colors, naming, records
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

    print("\n" + "=" * 66)
    print("%d 件成功 / %d 件失敗" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失敗: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
