# -*- coding: utf-8 -*-
"""名前の組み立てと、記録更新の判定のテスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import ark, naming, records
from arklib.creature import FEMALE, MALE, STATUS_DEAD, Creature

PASS, FAIL = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print("  OK   %-44s %s" % (name, got))
    else:
        FAIL.append(name)
        print("  NG   %-44s got=%s want=%s" % (name, got, want))


def mk(name="", sex=MALE, hp=10, st=10, wt=10, me=10, mut_me=0, uid=None,
       ark_id=0, status="alive"):
    c = Creature(species_bp="bp/Rex", species_name="Rex", name=name, sex=sex,
                 state="bred", uid=uid, ark_id=ark_id, status=status)
    c.levels_wild[ark.HEALTH] = hp
    c.levels_wild[ark.STAMINA] = st
    c.levels_wild[ark.WEIGHT] = wt
    c.levels_wild[ark.MELEE] = me
    c.levels_mut[ark.MELEE] = mut_me
    return c


def main():
    print("[1] 名前の組み立て")
    male = mk(sex=MALE, hp=10, st=10, wt=10, me=10)
    check("1.1 オスの既定形", naming.make_name(male), "M H10 S10 W10 M10")
    female = mk(sex=FEMALE, hp=47, st=24, wt=37, me=26)
    check("1.2 メス", naming.make_name(female), "F H47 S24 W37 M26")
    check("1.3 性別なし", naming.make_name(female, with_sex=False),
          "H47 S24 W37 M26")
    check("1.4 ステータスを選ぶ",
          naming.make_name(female, [ark.HEALTH, ark.MELEE]), "F H47 M26")
    mutant = mk(sex=MALE, me=20, mut_me=4)
    check("1.5 変異ぶんを足したレベルで出す", naming.make_name(mutant),
          "M H10 S10 W10 M24")
    check("1.6 変異に印を付ける",
          naming.make_name(mutant, mutation_mark="*"), "M H10 S10 W10 M24*")
    check("1.7 性別不明なら先頭を省く",
          naming.make_name(mk(sex="-")), "H10 S10 W10 M10")
    check("1.8 速度は D (スタミナと衝突しない)",
          naming.LETTERS[ark.SPEED], "D")

    print("\n[2] 記録の判定")
    stat_list = [ark.HEALTH, ark.STAMINA, ark.WEIGHT, ark.MELEE]
    old = [mk("既存1", uid=1, hp=40, st=20, wt=30, me=25),
           mk("既存2", uid=2, hp=35, st=30, wt=28, me=20)]

    newbie = mk("新入り", uid=None, hp=45, st=20, wt=10, me=25)
    r = records.check(newbie, old, stat_list)
    check("2.1 体力は更新", r.per_stat[ark.HEALTH], records.NEW)
    check("2.2 スタミナは届かず", r.per_stat[ark.STAMINA], records.NONE)
    check("2.3 近接はタイ", r.per_stat[ark.MELEE], records.TIE)
    check("2.4 総合は更新扱い", r.overall, records.NEW)
    check("2.5 見出し", r.label(), "自己ベスト更新")

    tie_only = mk("タイ", uid=None, hp=40, st=10, wt=10, me=10)
    r2 = records.check(tie_only, old, stat_list)
    check("2.6 タイだけなら総合もタイ", r2.overall, records.TIE)
    check("2.7 見出し", r2.label(), "いまの最高と同じ")

    weak = mk("凡骨", uid=None, hp=10, st=10, wt=10, me=10)
    check("2.8 届かなければ無印",
          records.check(weak, old, stat_list).overall, records.NONE)

    first = records.check(mk("初代", uid=None, hp=40), [], stat_list)
    check("2.9 1体目は「はじめて」", first.first_of_species, True)
    check("2.10 1体目は記録扱いにしない", first.overall, records.NONE)

    # 同じ個体を取り込み直したとき、自分自身と比べてタイにならないこと
    same = mk("既存1", uid=None, ark_id=999, hp=40, st=20, wt=30, me=25)
    stored = mk("既存1", uid=1, ark_id=999, hp=40, st=20, wt=30, me=25)
    r3 = records.check(same, [stored, old[1]], stat_list)
    check("2.11 取り込み直しで自分とタイにならない",
          r3.per_stat[ark.HEALTH], records.NEW)

    dead = mk("故人", uid=9, hp=99, status=STATUS_DEAD)
    r4 = records.check(mk("生者", uid=None, hp=50), old + [dead], stat_list)
    check("2.12 死んだ個体は比較から外す", r4.per_stat[ark.HEALTH], records.NEW)

    # ---- [3] 種族ごとの命名規則 -------------------------------------
    print("\n[3] 種族ごとの命名規則")
    import tempfile

    from arklib.library import Library
    from ui.autoimport import AutoImport

    lib = Library(os.path.join(tempfile.mkdtemp(prefix="naming_"), "n.db"))
    auto = AutoImport.__new__(AutoImport)          # 画面は作らずに設定だけ使う
    auto.st = type("St", (), {"library": lib})()
    common = {"naming_stats": [ark.HEALTH, ark.STAMINA, ark.WEIGHT, ark.MELEE],
              "naming_mode": naming.MODE_ALL,
              "naming_with_sex": True,
              "naming_mutation_mark": ""}
    auto.get = lambda k: common.get(k)

    boar = Creature(species_bp="bp/Daeodon", species_name="Daeodon", sex=MALE)
    for st_, lv in ((ark.HEALTH, 44), (ark.STAMINA, 20), (ark.FOOD, 41),
                    (ark.WEIGHT, 37), (ark.MELEE, 26)):
        boar.levels_wild[st_] = lv
    boar.mutations_father = 23

    def named(bp):
        r = auto.naming_rule(bp)
        return naming.make_name(boar, r["stats"], r["with_sex"],
                                mutation_mark=r["mark"], mode=r["mode"])

    check("3.1 未設定なら共通の設定", named("bp/Daeodon"), "M H44 S20 W37 M26")
    auto.set_naming_rule("bp/Daeodon",
                         {"stats": [ark.HEALTH, ark.FOOD, ark.WEIGHT, ark.MELEE],
                          "mode": naming.MODE_ALL, "with_sex": True, "mark": ""})
    check("3.2 ダエオドンだけ食料を乗せる", named("bp/Daeodon"), "M H44 F41 W37 M26")
    check("3.3 他の種族は変わらない", named("bp/Argentavis"), "M H44 S20 W37 M26")
    check("3.4 この種族だけの設定だと分かる",
          auto.has_own_naming("bp/Daeodon"), True)
    check("3.5 触っていない種族は共通のまま",
          auto.has_own_naming("bp/Argentavis"), False)

    # 形式も種族ごとに変えられる (オーバーフロー系統だけ OF にする)
    auto.set_naming_rule("bp/Rex", {"stats": [], "mode": naming.MODE_MUTATIONS,
                                    "with_sex": True, "mark": ""})
    check("3.6 Rex だけ OF 形式", named("bp/Rex"), "M 23")
    check("3.7 ダエオドンは巻き添えにならない",
          named("bp/Daeodon"), "M H44 F41 W37 M26")

    # 性別と変異マークも種族ごと
    auto.set_naming_rule("bp/Otter", {"stats": [ark.HEALTH], "mode": naming.MODE_ALL,
                                      "with_sex": False, "mark": "*"})
    boar.levels_mut[ark.HEALTH] = 2
    check("3.8 性別なし・変異マークあり", named("bp/Otter"), "H46*")
    boar.levels_mut[ark.HEALTH] = 0

    auto.set_naming_rule("bp/Daeodon", None)
    check("3.9 共通設定に戻せる", named("bp/Daeodon"), "M H44 S20 W37 M26")
    check("3.10 戻したら印も消える", auto.has_own_naming("bp/Daeodon"), False)

    # 昔の「ステータスだけ」の設定も読める
    lib.set_setting("naming_stats_bp/Trike", [ark.HEALTH, ark.MELEE])
    check("3.11 古い設定からの引き継ぎ", named("bp/Trike"), "M H44 M26")

    # 共通の形式を変えると、種族ごとに決めていないものが追従する
    common["naming_mode"] = naming.MODE_ZEROS
    check("3.12 共通を変えると未設定の種族が追従",
          named("bp/Argentavis"), "M 0なし")
    check("3.13 種族ごとに決めた方は動かない", named("bp/Rex"), "M 23")
    lib.close()

    print("\n" + "=" * 60)
    print("%d 件成功 / %d 件失敗" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失敗: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
