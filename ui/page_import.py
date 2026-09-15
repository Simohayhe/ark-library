# -*- coding: utf-8 -*-
"""取り込み画面。

ゲーム内で「恐竜のエクスポート」を押すと
    <ARKインストール>\\ShooterGame\\Saved\\DinoExports\\ に ini が増える。
そのフォルダを見張って、増えたぶんだけ取り込む。
"""
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from arklib import importers, paths

from . import theme


class ImportPage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.auto = app.autoimport
        self.folder = tk.StringVar()
        self.server = tk.StringVar(value=self.st.server)
        self.watching = tk.BooleanVar(value=bool(self.auto.get("auto_import")))

        self._build()
        self._init_folder()
        self.folder.trace_add("write", lambda *_a: self._remember_folder())
        self.auto.log_sinks.append(self._say)

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        tk.Label(self, text="インポート", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(self,
                 text="ゲーム内で生物のインベントリから「恐竜のエクスポート」を実行すると、"
                      "下記フォルダにファイルが生成されます。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=16)

        card = theme.Card(self, bg=theme.BG)
        card.pack(fill="x", padx=16, pady=(10, 6))
        b = card.body

        row = tk.Frame(b, bg=theme.CARD)
        row.pack(fill="x", pady=(2, 6))
        tk.Label(row, text="フォルダ", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        self.folder_entry = theme.soft_entry(row, textvariable=self.folder)
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        theme.RoundButton(row, "参照", self._browse, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=2)
        theme.RoundButton(row, "自動検出", self._autodetect, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=2)

        row2 = tk.Frame(b, bg=theme.CARD)
        row2.pack(fill="x", pady=(0, 6))
        tk.Label(row2, text="サーバー", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        self.server_box = ttk.Combobox(row2, textvariable=self.server, width=22,
                                       style="Cute.TCombobox")
        self.server_box.pack(side="left")
        tk.Label(row2, text="この倍率設定で逆算します",
                 bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=8)

        row3 = tk.Frame(b, bg=theme.CARD)
        row3.pack(fill="x", pady=(4, 2))
        theme.RoundButton(row3, "新規分をインポート", self._import_new,
                          kind="primary", bg=theme.CARD).pack(side="left", padx=(0, 4))
        theme.RoundButton(row3, "全件を再読み込み", self._import_all, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)
        theme.RoundButton(row3, "ファイルを選択", self._import_files, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)
        tk.Checkbutton(row3, text="自動インポート (エクスポートを検知)",
                       variable=self.watching,
                       command=self._toggle_watch, bg=theme.CARD, fg=theme.INK,
                       selectcolor=theme.FIELD, activebackground=theme.CARD,
                       font=theme.F.get("small"), bd=0,
                       highlightthickness=0).pack(side="left", padx=(10, 0))

        # まとめて取り込むと 1 件ずつ時間がかかることがあるので、
        # いま何件目を読んでいるかを出す (止まっているように見せない)
        self.progress = tk.Label(b, text="", bg=theme.CARD, fg=theme.INK_SUB,
                                 font=theme.F.get("small"), anchor="w")
        self.progress.pack(fill="x", pady=(4, 0))
        self._cancel = False

        log_card = theme.Card(self, bg=theme.BG)
        log_card.pack(fill="both", expand=True, padx=16, pady=(4, 14))
        lb = log_card.body
        head = tk.Frame(lb, bg=theme.CARD)
        head.pack(fill="x")
        tk.Label(head, text="ログ", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        theme.RoundButton(head, "クリア", self._clear_log, kind="ghost",
                          bg=theme.CARD).pack(side="right")

        wrap = tk.Frame(lb, bg=theme.CARD)
        wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.log = tk.Text(wrap, bg=theme.FIELD, fg=theme.INK, bd=0,
                           highlightthickness=0, wrap="word", height=14,
                           font=theme.F.get("ui"), padx=10, pady=8)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical",
                           style="Cute.Vertical.TScrollbar", command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set, state="disabled")
        self.log.tag_configure("ok", foreground=theme.MINT)
        self.log.tag_configure("upd", foreground=theme.SKY)
        self.log.tag_configure("ng", foreground=theme.RED)
        self.log.tag_configure("note", foreground=theme.INK_SUB)

    # ---- 画面 ----------------------------------------------------------

    def on_show(self):
        names = self.st.server_names()
        self.server_box.configure(values=names)
        if not self.server.get() and names:
            self.server.set(names[0])
        if not self.folder.get():
            self._init_folder()

    def reload(self):
        self.on_show()

    def _init_folder(self):
        saved = self.st.library.get_setting("import_folder", "")
        if saved and os.path.isdir(saved):
            self.folder.set(saved)
            return
        self._autodetect(quiet=True)

    def _autodetect(self, quiet=False):
        found = paths.dino_export_dirs()
        existing = [f for f in found if f[2]]
        if existing:
            self.folder.set(existing[0][0])
            self._say("エクスポート先を見つけました: %s (%s)"
                      % (existing[0][0], existing[0][1]), "note")
            for p, label, _e in existing[1:]:
                self._say("  ほかの候補: %s (%s)" % (p, label), "note")
        elif found:
            self.folder.set(found[0][0])
            self._say("フォルダはまだ作られていません。ゲーム内で一度エクスポートすると"
                      "できます: %s" % found[0][0], "note")
        elif not quiet:
            messagebox.showwarning(
                "ARK ライブラリ",
                "ARK のインストール先が分かりませんでした。\n"
                "DinoExports フォルダを「参照」から指定してください。", parent=self)

    def _browse(self):
        d = filedialog.askdirectory(parent=self, title="DinoExports フォルダ",
                                    initialdir=self.folder.get() or "/")
        if d:
            self.folder.set(d)

    # ---- 取り込み ------------------------------------------------------

    def _import_new(self):
        self._run(skip_known=True)

    def _import_all(self):
        if not messagebox.askyesno(
                "全件を再読み込み",
                "フォルダ内の全ファイルを再読み込みします。\n"
                "既存の個体は更新されるため重複しません。", parent=self):
            return
        self._run(skip_known=False)

    def _import_files(self):
        files = filedialog.askopenfilenames(
            parent=self, title="エクスポートファイルを選ぶ",
            initialdir=self.folder.get() or "/",
            filetypes=[("ARK エクスポート", "*.ini *.sav *.json"), ("すべて", "*.*")])
        if not files:
            return
        self._import_list(list(files))

    def _run(self, skip_known=True):
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("ARK ライブラリ",
                                   "フォルダが見つかりません。", parent=self)
            return
        self.st.library.set_setting("import_folder", folder)
        files = []
        for n in sorted(os.listdir(folder)):
            if importers.detect_kind(n) is not None:
                files.append(os.path.join(folder, n))
        if not skip_known:
            self.st.library.forget_imported()
        self._import_list(files, skip_known=skip_known, quiet_empty=True)

    def _import_list(self, files, skip_known=False, quiet_empty=False):
        lib = self.st.library
        files.sort(key=lambda p: _mtime(p))       # 親を先に入れたい

        todo = [p for p in files
                if not (skip_known and lib.was_imported(p, _mtime(p)))]
        skipped = len(files) - len(todo)

        added = updated = failed = 0
        self._cancel = False
        started = time.time()
        for i, p in enumerate(todo, 1):
            if self._cancel:
                self._say("中断しました (%d/%d 件)" % (i - 1, len(todo)), "note")
                break
            self._progress("%d/%d  %s を処理中…"
                           % (i, len(todo), os.path.basename(p)))
            # 手で取り込むときは、時間をかけてでも解きにいく。
            # 逆算が速くなったので、4 秒でも前の 8 秒より広く探せる
            r = self.auto.handle_file(p, announce=False, budget=4.0)
            if r.ok:
                if r.action == "updated":
                    updated += 1
                else:
                    added += 1
            else:
                failed += 1
        self._progress("")

        total = added + updated + failed
        if total > 1:
            self._say("%d 件を %.1f 秒で処理" % (total, time.time() - started),
                      "note")
        if total == 0 and not quiet_empty:
            self._say("新規ファイルはありません。", "note")
        elif total == 0:
            self._say("新しいファイルはありませんでした (%d 件は前回と同じ)。"
                      % skipped, "note")
        else:
            self._say("― 追加 %d / 更新 %d / 失敗 %d ―" % (added, updated, failed),
                      "note")
        self.app.reload_pages(except_key="import")

    def _progress(self, text):
        """いま何件目かを出して、画面を描き直す。

        取り込みは 1 件に数百 ms かかることがある。まとめて読むと固まって
        見えるので、1 件ごとに描き直して進み具合を見せる。
        """
        try:
            self.progress.configure(text=text)
            self.update()
        except tk.TclError:
            pass

    # ---- 見張り --------------------------------------------------------

    def _toggle_watch(self):
        on = bool(self.watching.get())
        self.auto.set("auto_import", on)
        self.auto.apply_setting()
        self.app.refresh_status()
        if on:
            self._say("自動取り込みを入れました。ゲーム内でエクスポートすると"
                      "そのまま入ります。", "note")
        else:
            self._say("自動取り込みを止めました。", "note")

    def _remember_folder(self):
        folder = (self.folder.get() or "").strip()
        if folder:
            self.st.library.set_setting("import_folder", folder)

    # ---- ログ ----------------------------------------------------------

    def _say(self, text, tag="note"):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M  ") + text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
