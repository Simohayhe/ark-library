# -*- coding: utf-8 -*-
"""種族ごとの命名規則。

水生生物のように酸素がいつも 0 の種族もあれば、ダエオドンのように食料値まで
名前に入れたい種族もある。オーバーフロー系統だけ OF 表記にしたい、という
使い方もある。ここでその種族だけの決め方を覚えさせる。

決めなければ「通知」画面の設定 (全種族共通) が使われる。
"""
import tkinter as tk

from arklib import ark, naming

from . import theme
from .page_alerts import NAMING_ORDER, STAT_LABEL


class SpeciesNamingDialog(tk.Toplevel):
    def __init__(self, parent, app, species_bp, species_name, stat_list=None):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.auto = app.autoimport
        self.species_bp = species_bp
        self.species_name = species_name
        self.title("命名規則 - %s" % species_name)
        self.transient(parent)
        self.resizable(False, False)

        rule = self.auto.naming_rule(species_bp)

        tk.Label(self, text="%s の命名規則" % species_name,
                 bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="この種族のみの設定です。未設定の場合は"
                            "「通知」画面の設定 (全種族共通) が使われます。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left", wraplength=460).pack(anchor="w", padx=20)

        # ---- 形式 ----
        tk.Label(self, text="形式", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=20, pady=(12, 2))
        self.mode = tk.StringVar(value=rule["mode"])
        mrow = tk.Frame(self, bg=theme.BG)
        mrow.pack(anchor="w", padx=20)
        for key, label, hint in naming.MODES:
            tk.Radiobutton(mrow, text=label, variable=self.mode, value=key,
                           command=self._preview, bg=theme.BG, fg=theme.INK,
                           selectcolor=theme.FIELD, activebackground=theme.BG,
                           activeforeground=theme.INK, font=theme.F.get("ui"),
                           bd=0, highlightthickness=0).pack(side="left",
                                                            padx=(0, 10))
        self.mode_hint = tk.Label(self, text="", bg=theme.BG, fg=theme.INK_SUB,
                                  font=theme.F.get("small"))
        self.mode_hint.pack(anchor="w", padx=20)

        # ---- ステータス ----
        tk.Label(self, text="含めるステータス", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=20, pady=(10, 2))
        # その種族が実際に持っているステータスだけ出す
        usable = [s for s in NAMING_ORDER
                  if stat_list is None or s in stat_list]
        self.vars = {}
        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(fill="x", padx=20)
        for i, s in enumerate(usable):
            v = tk.BooleanVar(value=s in rule["stats"])
            self.vars[s] = v
            tk.Checkbutton(grid, text="%s (%s)" % (STAT_LABEL.get(s, ark.NAMES_JA[s]),
                                                   naming.LETTERS[s]),
                           variable=v, command=self._preview, bg=theme.BG,
                           fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.BG, activeforeground=theme.INK,
                           font=theme.F.get("ui"), bd=0, highlightthickness=0,
                           anchor="w").grid(row=i // 3, column=i % 3, sticky="w",
                                            padx=(0, 12))

        # ---- 性別・変異マーク ----
        extra = tk.Frame(self, bg=theme.BG)
        extra.pack(anchor="w", padx=20, pady=(10, 0))
        self.with_sex = tk.BooleanVar(value=rule["with_sex"])
        tk.Checkbutton(extra, text="先頭に性別 (M / F / U) を付加",
                       variable=self.with_sex, command=self._preview,
                       bg=theme.BG, fg=theme.INK, selectcolor=theme.FIELD,
                       activebackground=theme.BG, activeforeground=theme.INK,
                       font=theme.F.get("ui"), bd=0,
                       highlightthickness=0).pack(side="left", padx=(0, 16))
        tk.Label(extra, text="変異マーク", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(0, 4))
        self.mark = tk.StringVar(value=rule["mark"])
        e = theme.soft_entry(extra, textvariable=self.mark, width=4, bg=theme.BG)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda _e: self._preview())

        self.preview = tk.Label(self, text="", bg=theme.FIELD, fg=theme.INK,
                                font=theme.F.get("ui_b"), padx=10, pady=6,
                                anchor="w")
        self.preview.pack(fill="x", padx=20, pady=(12, 0))

        self.status = tk.Label(
            self, text="", bg=theme.BG, fg=theme.INK_SUB,
            font=theme.F.get("small"))
        self.status.pack(anchor="w", padx=20, pady=(6, 0))

        box = tk.Frame(self, bg=theme.BG)
        box.pack(padx=20, pady=14)
        theme.RoundButton(box, "この種族に適用", self._save, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "共通設定に戻す", self._clear, kind="soft",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

        self._refresh_status()
        self._preview()
        self.grab_set()

    # ---- 中身 ----------------------------------------------------------

    def _chosen(self):
        return [s for s in NAMING_ORDER if self.vars.get(s) and self.vars[s].get()]

    def _rule(self):
        return {"stats": self._chosen() or list(naming.DEFAULT_STATS),
                "mode": self.mode.get(),
                "with_sex": bool(self.with_sex.get()),
                "mark": self.mark.get()[:2]}

    def _refresh_status(self):
        self.status.configure(
            text=("現在: この種族のみの設定" if self.auto.has_own_naming(self.species_bp)
                  else "現在: 全種族共通の設定"))

    def _preview(self):
        from .page_alerts import _sample_creature
        rule = self._rule()
        self.mode_hint.configure(
            text=dict((k, h) for k, _l, h in naming.MODES).get(rule["mode"], ""))
        text = naming.make_name(_sample_creature(), rule["stats"],
                                rule["with_sex"], mutation_mark=rule["mark"],
                                mode=rule["mode"])
        self.preview.configure(text="プレビュー:  " + text)

    def _save(self):
        if not self._chosen() and self.mode.get() == naming.MODE_ALL:
            self.status.configure(text="ステータスを 1 つ以上選択してください")
            return
        self.auto.set_naming_rule(self.species_bp, self._rule())
        self._refresh_status()
        self.status.configure(text="この種族のみの設定にしました")

    def _clear(self):
        self.auto.set_naming_rule(self.species_bp, None)
        rule = self.auto.naming_rule(self.species_bp)
        for s, v in self.vars.items():
            v.set(s in rule["stats"])
        self.mode.set(rule["mode"])
        self.with_sex.set(rule["with_sex"])
        self.mark.set(rule["mark"])
        self._refresh_status()
        self.status.configure(text="全種族共通の設定に戻しました")
        self._preview()
