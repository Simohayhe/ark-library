# -*- coding: utf-8 -*-
"""Mod の生物データを足す窓。

ARK Smart Breeding が配っている Mod ごとの種族データ (Obelisk) から選んで入れる。
入れると次の起動から、その Mod の生物も取り込めるようになる。

通信は別スレッドでやって、画面は after() で覗きに行く
(tkinter を別スレッドから触ると落ちるため)。
"""
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from arklib import modvalues

from . import theme

POLL_MS = 120


class ModsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.title("Mod の生物を追加")
        self.transient(parent)
        self.geometry("720x560")

        self._lock = threading.Lock()
        self._result = None
        self._alive = True
        self.catalog = []

        tk.Label(self, text="Mod の生物を追加", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=18, pady=(14, 2))
        tk.Label(self, text="ARK Smart Breeding が配っている Mod のデータを入れます。"
                            "入れた Mod の生物は、次の起動から取り込めるようになります。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left", wraplength=660).pack(anchor="w", padx=18)

        # 入れてあるもの
        installed_card = theme.Card(self, bg=theme.BG)
        installed_card.pack(fill="x", padx=18, pady=(10, 4))
        ib = installed_card.body
        tk.Label(ib, text="入れてある Mod", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w")
        self.installed_box = tk.Listbox(ib, bg=theme.FIELD, fg=theme.INK, bd=0,
                                        highlightthickness=0, height=4,
                                        selectbackground=theme.PINK,
                                        selectforeground=theme.ON_ACCENT,
                                        font=theme.F.get("ui"))
        self.installed_box.pack(fill="x", pady=(4, 4))
        row = tk.Frame(ib, bg=theme.CARD)
        row.pack(fill="x")
        theme.RoundButton(row, "外す", self._remove, kind="danger",
                          bg=theme.CARD).pack(side="left")
        theme.RoundButton(row, "ファイルから入れる", self._install_file, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=6)

        # 選べるもの
        pick_card = theme.Card(self, bg=theme.BG)
        pick_card.pack(fill="both", expand=True, padx=18, pady=(6, 4))
        pb = pick_card.body
        head = tk.Frame(pb, bg=theme.CARD)
        head.pack(fill="x")
        tk.Label(head, text="配られている Mod", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(side="left")
        self.query = tk.StringVar()
        e = theme.soft_entry(head, textvariable=self.query, width=20, bg=theme.CARD)
        e.pack(side="right")
        e.bind("<KeyRelease>", lambda _e: self._fill_catalog())
        tk.Label(head, text="絞り込み", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="right", padx=6)

        self.list_box = tk.Listbox(pb, bg=theme.FIELD, fg=theme.INK, bd=0,
                                   highlightthickness=0,
                                   selectbackground=theme.PINK,
                                   selectforeground=theme.ON_ACCENT,
                                   font=theme.F.get("ui"))
        self.list_box.pack(fill="both", expand=True, pady=(4, 4))
        self.list_box.bind("<Double-Button-1>", lambda _e: self._install_selected())

        self.status = tk.Label(self, text="一覧を取りに行っています…", bg=theme.BG,
                               fg=theme.INK_SUB, font=theme.F.get("small"))
        self.status.pack(anchor="w", padx=18)

        box = tk.Frame(self, bg=theme.BG)
        box.pack(pady=(6, 14))
        theme.RoundButton(box, "これを入れる", self._install_selected,
                          kind="primary", bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

        self._refresh_installed()
        self.grab_set()
        self._start(self._catalog_worker)

    # ---- スレッド ------------------------------------------------------

    def _start(self, worker, *args):
        threading.Thread(target=worker, args=args, daemon=True).start()
        self.after(POLL_MS, self._poll)

    def _put(self, kind, value):
        with self._lock:
            self._result = (kind, value)

    def _poll(self):
        if not self._alive:
            return
        with self._lock:
            got, self._result = self._result, None
        if got is None:
            self.after(POLL_MS, self._poll)
            return
        kind, value = got
        if kind == "catalog":
            self.catalog = value
            self._fill_catalog()
            self.status.configure(text="%d 件。使っている Mod を選んでください。"
                                       % len(value))
        elif kind == "installed":
            path, n = value
            self.status.configure(text="入れました (%d 種)。"
                                       "アプリを開き直すと使えます。" % n)
            self._refresh_installed()
            self.st.species_db = type(self.st.species_db)(
                library_path=self.st.library.path)
            self.st.apply_multipliers()
            self.app.reload_pages()
        elif kind == "error":
            self.status.configure(text=str(value))
            messagebox.showerror("Mod の追加", str(value), parent=self)

    def _catalog_worker(self):
        try:
            self._put("catalog", modvalues.fetch_catalog())
        except Exception as e:
            self._put("error", "一覧を取れませんでした (%s)" % e)

    def _install_worker(self, file_name):
        try:
            self._put("installed",
                      modvalues.install(file_name, self.st.library.path))
        except Exception as e:
            self._put("error", "入れられませんでした (%s)" % e)

    # ---- 一覧 ----------------------------------------------------------

    def _refresh_installed(self):
        self.installed_box.delete(0, "end")
        self._installed = modvalues.installed(self.st.library.path)
        for m in self._installed:
            mod = m["mod"] or {}
            self.installed_box.insert(
                "end", " %s  (%d 種)" % (mod.get("title") or m["file"], m["count"]))
        if not self._installed:
            self.installed_box.insert("end", " (まだ何も入っていません)")

    def _fill_catalog(self):
        q = (self.query.get() or "").strip().lower()
        self.list_box.delete(0, "end")
        self._shown = []
        for m in self.catalog:
            text = "%s %s %s" % (m["title"], m["tag"], m["author"])
            if q and q not in text.lower():
                continue
            self._shown.append(m)
            self.list_box.insert("end", " %-46s %s" % (m["title"][:46], m["author"]))

    def _install_selected(self):
        sel = self.list_box.curselection()
        if not sel or not getattr(self, "_shown", None):
            return
        m = self._shown[sel[0]]
        self.status.configure(text="%s を入れています…" % m["title"])
        self._start(self._install_worker, m["file"])

    def _install_file(self):
        path = filedialog.askopenfilename(
            parent=self, title="ASB の値ファイル (json)",
            filetypes=[("json", "*.json"), ("すべて", "*.*")])
        if not path:
            return
        try:
            _p, n = modvalues.install_from_file(path, self.st.library.path)
        except Exception as e:
            messagebox.showerror("Mod の追加", "読めませんでした: %s" % e, parent=self)
            return
        self.status.configure(text="入れました (%d 種)。" % n)
        self._refresh_installed()

    def _remove(self):
        sel = self.installed_box.curselection()
        if not sel or not getattr(self, "_installed", None):
            return
        if sel[0] >= len(self._installed):
            return
        m = self._installed[sel[0]]
        name = (m["mod"] or {}).get("title") or m["file"]
        if not messagebox.askyesno("外す", "%s を外しますか？" % name, parent=self):
            return
        modvalues.remove(m["file"], self.st.library.path)
        self._refresh_installed()
        self.status.configure(text="外しました。アプリを開き直すと反映されます。")

    def destroy(self):
        self._alive = False
        tk.Toplevel.destroy(self)
