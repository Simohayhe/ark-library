# -*- coding: utf-8 -*-
"""エクスポートを見張って、出た瞬間に取り込む常駐サービス。

ゲーム内で「恐竜のエクスポート」を押す
    → DinoExports にファイルが増える
        → ここが見つけて取り込む
            → 名前をクリップボードにコピー
            → オーバーレイを出す
            → 記録更新なら音を変えて知らせる

アプリが起動している間ずっと動く (取り込み画面を開いていなくてもよい)。
"""
import os
import threading
import time
import tkinter as tk

from arklib import ark, naming, records, sounds
from arklib.importers import detect_kind, import_file

from .overlay import StatOverlay

# 既定値。設定はライブラリの settings テーブルに入れる
DEFAULTS = {
    "auto_import": True,
    "auto_import_interval": 2000,        # ミリ秒
    "naming_copy": True,
    "naming_stats": None,                # None なら naming.DEFAULT_STATS
    "naming_with_sex": True,
    "naming_mutation_mark": "",
    "naming_fill_empty": True,           # 名前が空の個体にはこの名前を入れておく
    "overlay_enabled": True,
    "overlay_seconds": 5.0,
    "overlay_position": "top",
    "sound_enabled": True,
    "sound_volume": 0.6,
}


class AutoImport(object):
    def __init__(self, app):
        self.app = app
        self.st = app.state_obj
        self.overlay = StatOverlay(app, self.get("overlay_position"),
                                   self.get("overlay_seconds"))
        self.log_sinks = []           # 取り込み画面がログを受け取るために登録する
        self.running = False
        self._job = None
        self._busy = False
        self._sound_cache = os.path.join(
            os.path.dirname(self.st.library.path), "sounds")
        threading.Thread(target=self._prebuild_sounds, daemon=True).start()

    # ---- 設定 ----------------------------------------------------------

    def get(self, key):
        return self.st.library.get_setting(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.st.library.set_setting(key, value)
        if key in ("overlay_position", "overlay_seconds"):
            self.overlay.position = self.get("overlay_position")
            self.overlay.seconds = float(self.get("overlay_seconds") or 5)

    def sound_spec(self, event):
        specs = self.st.library.get_setting("sound_specs", {}) or {}
        return specs.get(event) or sounds.EVENT_DEFAULTS.get(event)

    def set_sound_spec(self, event, spec):
        specs = dict(self.st.library.get_setting("sound_specs", {}) or {})
        specs[event] = spec
        self.st.library.set_setting("sound_specs", specs)

    def naming_stats(self):
        got = self.get("naming_stats")
        return list(got) if got else list(naming.DEFAULT_STATS)

    def folder(self):
        return self.st.library.get_setting("import_folder", "") or ""

    # ---- 開始 / 停止 ---------------------------------------------------

    def start(self):
        if self.running:
            return
        self.running = True
        self._tick()

    def stop(self):
        self.running = False
        if self._job is not None:
            try:
                self.app.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def apply_setting(self):
        """設定が変わったときに呼ぶ。"""
        if self.get("auto_import"):
            self.start()
        else:
            self.stop()

    # ---- 見張り --------------------------------------------------------

    def _tick(self):
        if not self.running:
            return
        try:
            self._scan()
        except Exception as e:              # 見張りが例外で止まらないように
            self._log("見張りでエラー: %s" % e, "ng")
        interval = int(self.get("auto_import_interval") or 2000)
        self._job = self.app.after(max(500, interval), self._tick)

    def _scan(self):
        folder = self.folder()
        if not folder or not os.path.isdir(folder) or self._busy:
            return
        lib = self.st.library
        new_files = []
        for n in sorted(os.listdir(folder)):
            if detect_kind(n) is None:
                continue
            p = os.path.join(folder, n)
            m = _mtime(p)
            if m <= 0 or lib.was_imported(p, m):
                continue
            # 書き込み途中のファイルを掴まないよう、少し落ち着くまで待つ
            if time.time() - m < 0.4:
                continue
            new_files.append((m, p))
        if not new_files:
            return
        new_files.sort()
        self._busy = True
        try:
            for _m, p in new_files:
                self.handle_file(p)
        finally:
            self._busy = False

    # ---- 1 ファイルの処理 ----------------------------------------------

    def handle_file(self, path, announce=True):
        """取り込んで、音・オーバーレイ・クリップボードまでやる。"""
        lib = self.st.library
        sm = self.st.multipliers.with_single_player_applied()
        server = self.st.server

        # 記録の判定を挟みたいので、ここでは保存しない
        res = import_file(path, self.st.species_db, sm, library=None,
                          server=server, game=self.st.game,
                          parent_lookup=lib.by_ark_id)

        if not res.ok:
            lib.mark_imported(path, _mtime(path), None, "ng")
            self._log("失敗  %s" % os.path.basename(path), "ng")
            for p in res.problems:
                self._log("      " + p, "ng")
            if announce:
                self._play("fail")
                if self.get("overlay_enabled"):
                    self.overlay.show_error(os.path.basename(path), res.problems)
            return res

        cr = res.creature
        others = lib.by_species(cr.species_bp, server or None, include_dead=False)
        stat_list = [s for s in res.species.displayed_stat_indices()
                     if s != ark.TORPIDITY]
        check = records.check(cr, others, stat_list)

        name_text = naming.make_name(
            cr, self.naming_stats(), bool(self.get("naming_with_sex")),
            mutation_mark=self.get("naming_mutation_mark") or "")
        if self.get("naming_fill_empty") and not cr.name:
            cr.name = name_text

        _uid, action = lib.save(cr)
        lib.mark_imported(path, _mtime(path), cr.uid, "ok")

        copied = False
        if announce and self.get("naming_copy"):
            copied = self._copy(name_text)

        head = "更新" if action == "updated" else "追加"
        extra = check.label()
        self._log("%s  %s %s Lv%d  %s%s"
                  % (head, cr.species_name, cr.sex_ja, cr.level, name_text,
                     ("  ← " + extra) if extra else ""),
                  "upd" if action == "updated" else "ok")
        if res.ambiguous:
            self._log("      ⚠ レベルの内訳が %d 通り考えられます"
                      % len(res.solutions), "ng")

        if announce:
            self._play(_event_for(check))
            if self.get("overlay_enabled"):
                self.overlay.show_creature(cr, res.species, check, name_text,
                                           copied, action)
        self.app.reload_pages()
        return res

    # ---- 小物 ----------------------------------------------------------

    def _copy(self, text):
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(text)
            self.app.update_idletasks()
            return True
        except tk.TclError:
            return False

    def _play(self, event):
        if not self.get("sound_enabled"):
            return
        vol = float(self.get("sound_volume") or 0.6)
        sounds.play_async(self.sound_spec(event), vol, self._sound_cache,
                          fallback=sounds.EVENT_DEFAULTS.get(event, "builtin:ok"))

    def preview(self, event):
        """設定画面の試聴用 (音の ON/OFF に関係なく鳴らす)。"""
        vol = float(self.get("sound_volume") or 0.6)
        sounds.play_async(self.sound_spec(event), vol, self._sound_cache,
                          fallback=sounds.EVENT_DEFAULTS.get(event, "builtin:ok"))

    def _prebuild_sounds(self):
        try:
            sounds.prebuild(self._sound_cache)
        except Exception:
            pass

    def _log(self, text, tag="note"):
        for sink in list(self.log_sinks):
            try:
                sink(text, tag)
            except Exception:
                pass


def _event_for(check):
    if check.overall == records.NEW:
        return "record"
    if check.overall == records.TIE:
        return "tie"
    return "success"


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
