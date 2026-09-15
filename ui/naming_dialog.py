# -*- coding: utf-8 -*-
"""種族ごとの「名前に入れるステータス」。

水生生物のように酸素がいつも 0 の種族もあれば、酸素と食料まで名前に入れたい
種族もある。ここでその種族だけの決め方を覚えさせる。

    決めなければ「取り込み通知」画面の設定 (全種族共通) が使われる。
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
        self.title("名前の付け方 - %s" % species_name)
        self.transient(parent)
        self.resizable(False, False)

        tk.Label(self, text="%s の命名に含めるステータス" % species_name,
                 bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="この種族のみの設定です。未設定の場合は"
                            "「通知」画面の設定 (全種族共通) が使われます。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left", wraplength=420).pack(anchor="w", padx=20)

        # その種族が実際に持っているステータスだけ出す
        usable = [s for s in NAMING_ORDER
                  if stat_list is None or s in stat_list]
        current = self.auto.naming_stats(species_bp)
        self.vars = {}
        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(fill="x", padx=20, pady=(10, 4))
        for i, s in enumerate(usable):
            v = tk.BooleanVar(value=s in current)
            self.vars[s] = v
            tk.Checkbutton(grid, text="%s (%s)" % (STAT_LABEL.get(s, ark.NAMES_JA[s]),
                                                   naming.LETTERS[s]),
                           variable=v, command=self._preview, bg=theme.BG,
                           fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.BG, activeforeground=theme.INK,
                           font=theme.F.get("ui"), bd=0, highlightthickness=0,
                           anchor="w").grid(row=i // 3, column=i % 3, sticky="w",
                                            padx=(0, 12))

        self.preview = tk.Label(self, text="", bg=theme.FIELD, fg=theme.INK,
                                font=theme.F.get("ui_b"), padx=10, pady=6,
                                anchor="w")
        self.preview.pack(fill="x", padx=20, pady=(8, 0))

        has_own = self.st.library.get_setting(
            "naming_stats_%s" % species_bp, None) is not None
        self.status = tk.Label(
            self, text=("現在: この種族のみの設定"
                        if has_own else "現在: 全種族共通の設定"),
            bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"))
        self.status.pack(anchor="w", padx=20, pady=(6, 0))

        box = tk.Frame(self, bg=theme.BG)
        box.pack(padx=20, pady=14)
        theme.RoundButton(box, "この種族に適用", self._save, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "共通設定に戻す", self._clear, kind="soft",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

        self._preview()
        self.grab_set()

    # ---- 中身 ----------------------------------------------------------

    def _chosen(self):
        return [s for s in NAMING_ORDER if self.vars.get(s) and self.vars[s].get()]

    def _preview(self):
        from .page_alerts import _sample_creature
        cr = _sample_creature()
        stat_list = self._chosen() or list(naming.DEFAULT_STATS)
        text = naming.make_name(cr, stat_list,
                                bool(self.auto.get("naming_with_sex")),
                                mutation_mark=self.auto.get("naming_mutation_mark") or "",
                                mode=self.auto.get("naming_mode") or naming.MODE_ALL)
        self.preview.configure(text="プレビュー:  " + text)

    def _save(self):
        chosen = self._chosen()
        if not chosen:
            self.status.configure(text="1 つ以上選択してください")
            return
        self.st.library.set_setting("naming_stats_%s" % self.species_bp, chosen)
        self.status.configure(text="この種族のみの設定にしました")

    def _clear(self):
        self.st.library.set_setting("naming_stats_%s" % self.species_bp, None)
        for s, v in self.vars.items():
            v.set(s in self.auto.naming_stats())
        self.status.configure(text="全種族共通の設定に戻しました")
        self._preview()
