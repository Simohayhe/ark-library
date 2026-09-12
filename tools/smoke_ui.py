# -*- coding: utf-8 -*-
"""画面とダイアログを一通り開いて例外が出ないかを見るだけのテスト。"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.app import App
from ui import theme

db = sys.argv[1]
errors = []


def _check(cond, message):
    if not cond:
        raise AssertionError(message)


def step(name, fn):
    try:
        fn()
        print("  OK   %s" % name)
    except Exception:
        errors.append(name)
        print("  NG   %s" % name)
        traceback.print_exc()


app = App(db)
app.update()

for page in ("library", "import", "settings"):
    step("画面: %s" % page, lambda p=page: (app.show(p), app.update()))

lib_page = app._pages["library"]
app.show("library")
app.update()

# 交配計画はライブラリ画面の中に畳まれている
step("交配計画を開く", lambda: (lib_page._toggle_plan(), app.update(),
                                _check(lib_page.plan_open, "開かない")))
for tab in ("pairs", "plan", "mutation", "color"):
    step("交配計画のタブ: %s" % tab,
         lambda t=tab: (lib_page.plan_page._set_tab(t),
                        lib_page.plan_page.recalc(), app.update()))
step("個体を選ぶと相手を探す",
     lambda: (lib_page.table.select_by(lambda r: True), app.update(),
              _check(lib_page.plan_page.focus_creature is not None,
                     "対象が渡っていない")))

def genderless_plan():
    """性別が無い種族 (メイグアナ) でも交配のペアが出るか。"""
    bps = [r["species_bp"] for r in lib_page._summary
           if (app.state_obj.species_db.by_bp(r["species_bp"]) or None)
           and app.state_obj.species_db.by_bp(r["species_bp"]).no_gender]
    if not bps:
        print("       (性別なしの個体が居ないので飛ばします)")
        return
    lib_page._select_species(bps[0])
    app.update()
    lib_page.table.select_by(lambda r: True)
    app.update()
    c = lib_page.plan_page.focus_creature
    _check(c is not None and c.is_genderless, "U の個体が渡っていない")
    lib_page.plan_page._set_tab("pairs")
    lib_page.plan_page.recalc()
    app.update()
    rows = lib_page.plan_page.pair_table.rows
    _check(any(r.get("_obj") is not None for r in rows),
           "交配のペアが 1 件も出ない")


step("性別なし種族の交配表", genderless_plan)


def pairs_focus_filter():
    """選んだ個体を含むペアだけに絞れるか。"""
    lib_page._select_species(lib_page._species_bps[0])
    app.update()
    lib_page.table.select_by(lambda r: True)
    app.update()
    me = lib_page.plan_page.focus_creature
    _check(me is not None, "個体が渡っていない")
    lib_page.plan_page._set_tab("pairs")
    lib_page.plan_page.recalc()
    app.update()
    everything = len(lib_page.plan_page.pair_table.rows)
    lib_page.plan_page.only_focus.set(True)
    lib_page.plan_page._refill_pairs()
    app.update()
    narrowed = lib_page.plan_page.pair_table.rows
    _check(narrowed, "絞ったら 1 件も残らなかった")
    for r in narrowed:
        p = r["_obj"]
        _check(me.uid in (p.male.uid, p.female.uid), "関係ないペアが残っている")
    _check(len(narrowed) <= everything, "絞ったのに増えた")
    lib_page.plan_page.only_focus.set(False)
    lib_page.plan_page._refill_pairs()
    app.update()


step("おすすめペアの絞り込み", pairs_focus_filter)

step("交配計画を閉じる", lambda: (lib_page._toggle_plan(), app.update(),
                                  _check(not lib_page.plan_open, "閉じない")))

step("実数値表示の切り替え", lambda: (lib_page.show_values.set(True),
                                     lib_page._fill_table(),
                                     lib_page.show_values.set(False),
                                     lib_page._fill_table(), app.update()))
step("死亡を含める", lambda: (lib_page.include_dead.set(True), lib_page.reload(),
                             lib_page.include_dead.set(False), lib_page.reload(),
                             app.update()))
step("検索", lambda: (lib_page.query.set("ク"), lib_page._fill_table(),
                      lib_page.query.set(""), lib_page._fill_table(), app.update()))
step("並べ替え", lambda: [lib_page.table.sort_by(c.key)
                          for c in lib_page.table.cols] and app.update())
step("行の選択", lambda: (lib_page.table.select_by(lambda r: True), app.update()))


def open_detail():
    from ui.detail import CreatureDialog
    c = lib_page.table.selected_obj()
    d = CreatureDialog(lib_page, app, c)
    app.update()
    d.destroy()


step("個体の詳細ダイアログ", open_detail)


def row_menu():
    """右クリックのメニューが組み立てられるか (出すと止まるので中身だけ)。"""
    row = lib_page.table.selected_row()
    _check(row is not None, "行が選ばれていない")
    m = lib_page._build_row_menu(row)
    _check(m is not None, "メニューができない")
    _check(int(m.index("end")) >= 6, "項目が足りない")
    m.destroy()
    app.update()


step("行の右クリックメニュー", row_menu)


def edit_stats():
    from ui.edit_dialog import StatEditDialog
    from arklib import ark
    c = lib_page.table.selected_obj()
    d = StatEditDialog(lib_page, app, c)
    app.update()
    before = c.bl(ark.HEALTH)
    d.wild[ark.HEALTH].set(str(before + 3))
    d._preview()
    d._save()
    app.update()
    got = app.state_obj.library.get(c.uid)
    _check(got.bl(ark.HEALTH) == before + 3,
           "体力が変わっていない (%d)" % got.bl(ark.HEALTH))
    _check(got.ambiguous is False, "手直ししたのに ambiguous が残っている")
    # 元に戻す
    d2 = StatEditDialog(lib_page, app, got)
    d2.wild[ark.HEALTH].set(str(before))
    d2._save()
    app.update()


step("ステータスの編集", edit_stats)


def edit_colors():
    from ui.edit_dialog import ColorEditDialog
    c = lib_page.table.selected_obj()
    d = ColorEditDialog(lib_page, app, c)
    app.update()
    region = sorted(d.buttons)[0]
    d._set(region, 14)
    d._save()
    app.update()
    got = app.state_obj.library.get(c.uid)
    _check(got.colors[region] == 14, "色が変わっていない")


step("色の編集", edit_colors)


def ideal_flow():
    """理想個体を決めて、一覧に % が出るか。"""
    from arklib import ideal as arkideal
    from ui.ideal_dialog import IdealDialog
    c = lib_page.table.selected_obj()
    d = IdealDialog(lib_page, app, lib_page.species_bp,
                    lib_page.species.display_name, lib_page.stat_list,
                    creatures=lib_page.creatures, selected=c)
    app.update()
    d._from_selected()          # 選んだ個体をそのまま理想にする
    d._save()
    app.update()
    idl = arkideal.load(app.state_obj.library, lib_page.species_bp)
    _check(not idl.empty, "理想個体が保存されていない")
    lib_page._select_species(lib_page.species_bp)
    app.update()
    keys = [col.key for col in lib_page.table.cols]
    _check("ideal" in keys, "理想の列が出ていない")
    row = next(r for r in lib_page.table.rows if r["_obj"].uid == c.uid)
    _check(row["_ideal"] >= 99.9, "元にした個体が 100%% にならない (%s)"
           % row["ideal"])
    # ペアの表にも出る
    lib_page.plan_page._set_tab("pairs")
    lib_page.plan_page.recalc()
    app.update()
    prow = lib_page.plan_page.pair_table.rows
    if prow and prow[0].get("_obj") is not None:
        _check("_ideal" in prow[0], "ペアに理想の列が出ていない")
    # 片付ける
    arkideal.save(app.state_obj.library, lib_page.species_bp, None)
    lib_page._select_species(lib_page.species_bp)
    lib_page.table.select_by(lambda r: True)      # 次のテストのために選び直す
    app.update()


step("理想個体の設定と達成率", ideal_flow)


def open_status():
    from ui.page_library import _StatusDialog
    c = lib_page.table.selected_obj()
    d = _StatusDialog(lib_page, app.state_obj.library, c, lambda: None)
    app.update()
    d.destroy()


step("状態ダイアログ", open_status)


def species_switch():
    for i in range(len(lib_page._species_bps)):
        lib_page._select_species(lib_page._species_bps[i])
        app.update()


step("種族の切り替え", species_switch)

imp = app._pages["import"]
step("取り込み: 自動検出", lambda: (imp._autodetect(quiet=True), app.update()))
step("取り込み: 見張りの開始と停止",
     lambda: (imp.watching.set(True), imp._toggle_watch(),
              imp.watching.set(False), imp._toggle_watch(), app.update()))

step("画面: alerts", lambda: (app.show("alerts"), app.update()))
al = app._pages["alerts"]
step("通知: 名前の見本", lambda: (al._refresh_preview(), app.update()))
step("通知: オーバーレイを出してみる",
     lambda: (al._preview_overlay(), app.update(),
              _check(app.autoimport.overlay.win is not None, "出ていない"),
              app.autoimport.overlay.hide()))
step("通知: 設定の保存", lambda: (al._save_naming(), al._save_overlay(),
                                 al._save_auto(), app.update()))

def _naming_dialog():
    from ui.naming_dialog import SpeciesNamingDialog
    d = SpeciesNamingDialog(lib_page, app, lib_page.species_bp,
                            lib_page.species.display_name, lib_page.stat_list)
    app.update()
    d._save()
    _check(app.autoimport.naming_stats(lib_page.species_bp) ==
           app.state_obj.library.get_setting(
               "naming_stats_%s" % lib_page.species_bp), "種族別設定が効かない")
    d._clear()
    app.update()
    d.destroy()


step("種族ごとの名前設定", _naming_dialog)

step("種族データに追加ぶんが入っている",
     lambda: _check(app.state_obj.species_db.extra_count >= 1, "extra が 0"))
step("ボアラトスが引ける",
     lambda: _check(app.state_obj.species_db.get("Boaratos") is not None,
                    "見つからない"))

st = app._pages["settings"]
step("設定: プリセット", lambda: (st._official(), st._vanilla(), app.update()))
step("設定: 倍率の手入力を読み戻す",
     lambda: (st.cells[(7, 2)].set("2"), st._collect(), app.update(),
              _check(st.sm.stat[7][2] == 2.0, "重量テイムLvが 2 にならない")))
step("設定: 数字でない入力をはじく",
     lambda: (st.cells[(7, 2)].set("あ"),
              _check(bool(st._collect()), "不正な値を見逃した"),
              st.cells[(7, 2)].set("1"), st._collect(), app.update()))

# ---- 自動取り込みの通し ----------------------------------------------
import shutil
import time
import tempfile

from arklib import ark, naming, records
from arklib.multipliers import IDX_LEVEL_DOM, ServerMultipliers

fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "real_asa_otter.ini")
auto = app.autoimport
auto.set("sound_enabled", False)          # 実機で鳴らすとうるさいので黙らせる
watch_dir = tempfile.mkdtemp(prefix="arklib_watch_")
app.state_obj.library.set_setting("import_folder", watch_dir)


def _put_fixture():
    dst = os.path.join(watch_dir, "DinoExport_test.ini")
    shutil.copyfile(fixture, dst)
    # 見張りは「書き込み直後のファイル」を一度見送るので、時刻を少し戻しておく
    old = time.time() - 5
    os.utime(dst, (old, old))


if os.path.isfile(fixture):
    # 倍率が合っていないサーバーだと失敗する。そのときの見た目も確かめる
    step("自動取り込み: 倍率が合わないと失敗扱い", lambda: (
        _put_fixture(), auto._scan(), app.update(),
        _check(auto.overlay.win is not None, "失敗のオーバーレイが出ていない")))

    def _fix_server():
        sm = ServerMultipliers.official("asa")
        sm.stat[ark.WEIGHT][IDX_LEVEL_DOM] = 2.0
        app.state_obj.library.save_server("テスト鯖", sm.to_dict(), [],
                                          is_default=True)
        app.state_obj.use_server("テスト鯖")
        app.state_obj.library.forget_imported()

    step("自動取り込み: 倍率を直す", lambda: (_fix_server(), app.update()))

    def _import_ok():
        lib = app.state_obj.library
        # 同じ DB で二度目を流しても結果が変わらないように、前回のぶんを消す
        for c in lib.all_creatures():
            if c.species_name == "Otter":
                lib.delete(c.uid)
        lib.forget_imported()
        before = app.state_obj.library.count()
        _put_fixture()
        auto._scan()
        app.update()
        after = app.state_obj.library.count()
        _check(after == before + 1, "個体が増えていない (%d→%d)" % (before, after))
        got = [c for c in app.state_obj.library.all_creatures()
               if c.species_name == "Otter"]
        _check(bool(got), "カワウソが入っていない")
        c = got[0]
        _check(c.bl(ark.HEALTH) == 47, "体力が 47 でない: %d" % c.bl(ark.HEALTH))
        want = naming.make_name(c, auto.naming_stats(), True)
        _check(want == "F H47 S24 W37 M26", "名前がおかしい: %s" % want)
        _check(c.name == want, "名前が個体に入っていない: %s" % c.name)
        _check(app.clipboard_get() == want, "クリップボードに入っていない")
        _check(auto.overlay.win is not None, "オーバーレイが出ていない")

    step("自動取り込み: 取り込み→名前コピー→オーバーレイ", _import_ok)

    def _first_of_species():
        lib = app.state_obj.library
        c = [x for x in lib.all_creatures() if x.species_name == "Otter"][0]
        others = lib.by_species(c.species_bp, None, False)
        r = records.check(c, others, [ark.HEALTH, ark.MELEE])
        _check(r.first_of_species, "1 体目なのに first_of_species が False")

    step("自動取り込み: 1体目の判定", _first_of_species)

    step("自動取り込み: 同じファイルは二度取り込まない", lambda: (
        auto._scan(), app.update(),
        _check(len([c for c in app.state_obj.library.all_creatures()
                    if c.species_name == "Otter"]) == 1, "重複した")))

    step("オーバーレイを消す",
         lambda: (auto.overlay.hide(), app.update(),
                  _check(auto.overlay.win is None, "消えていない")))
    shutil.rmtree(watch_dir, ignore_errors=True)

app.destroy()
print("\n%s" % ("すべて通過" if not errors else "失敗: " + ", ".join(errors)))
sys.exit(1 if errors else 0)
