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

for page in ("library", "plan", "import", "settings"):
    step("画面: %s" % page, lambda p=page: (app.show(p), app.update()))

for tab in ("pairs", "plan", "mutation"):
    step("交配プランのタブ: %s" % tab,
         lambda t=tab: (app._pages["plan"]._set_tab(t),
                        app._pages["plan"].recalc(), app.update()))

lib_page = app._pages["library"]
app.show("library")
app.update()

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
