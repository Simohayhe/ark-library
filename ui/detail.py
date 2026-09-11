# -*- coding: utf-8 -*-
"""個体の詳細ダイアログ。ステータスの内訳と血統を見て、メモを付ける。"""
import tkinter as tk
from tkinter import messagebox

from arklib import ark, breeding, stats
from arklib.creature import STATUS_JA, ark_id_display

from . import theme
from .page_library import SHORT_JA, stat_columns


class CreatureDialog(tk.Toplevel):
    def __init__(self, master, app, creature, on_changed=None):
        tk.Toplevel.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.creature = creature
        self.on_changed = on_changed
        self.title(creature.display_name)
        self.transient(master)
        self.geometry("620x620")

        self.name_var = tk.StringVar(value=creature.name)
        self.notes_var = tk.StringVar(value=creature.notes)
        self._build()
        self.grab_set()

    def _build(self):
        c = self.creature
        sp = self.st.species_db.by_bp(c.species_bp)

        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text="%s %s" % (c.species_name, c.sex_ja), bg=theme.BG,
                 fg=theme.INK, font=theme.F.get("head")).pack(side="left")
        tk.Label(head, text="Lv%d (素 Lv%d / 強化 %d)"
                 % (c.level, c.base_level(), c.dom_level_total()),
                 bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=10)

        # ---- ステータスの内訳 ----
        card = theme.Card(self, bg=theme.BG)
        card.pack(fill="x", padx=16, pady=(6, 4))
        b = card.body
        grid = tk.Frame(b, bg=theme.CARD)
        grid.pack(fill="x")
        heads = ["ステータス", "ゲーム内の値", "野生", "変異", "強化", "継承"]
        for i, h in enumerate(heads):
            tk.Label(grid, text=h, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small")).grid(row=0, column=i, sticky="e",
                                                     padx=6, pady=(0, 2))
        tops = {}
        if sp is not None:
            siblings = self.st.library.by_species(c.species_bp, None, False)
            tops = breeding.top_levels(siblings, stat_columns(sp))
        show = stat_columns(sp) if sp is not None else [
            s for s in range(ark.STATS_COUNT) if c.values[s]]
        for r, s in enumerate(show, 1):
            is_top = tops.get(s) is not None and c.bl(s) >= tops[s] and tops[s] > 0
            fg = theme.PINK_DK if is_top else theme.INK
            tk.Label(grid, text=(SHORT_JA.get(s, ark.NAMES_JA[s]) + (" ★" if is_top else "")),
                     bg=theme.CARD, fg=fg, font=theme.F.get("ui")).grid(
                row=r, column=0, sticky="w", padx=6)
            vals = [stats.format_value(s, c.values[s]) if c.values[s] else "-",
                    c.levels_wild[s], c.levels_mut[s], c.levels_dom[s], c.bl(s)]
            for i, v in enumerate(vals, 1):
                tk.Label(grid, text=str(v), bg=theme.CARD, fg=fg,
                         font=theme.F.get("ui")).grid(row=r, column=i, sticky="e",
                                                      padx=6)
        tk.Label(grid, text="気絶値", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).grid(row=len(show) + 1, column=0,
                                                 sticky="w", padx=6, pady=(4, 0))
        tk.Label(grid, text=stats.format_value(ark.TORPIDITY, c.values[ark.TORPIDITY])
                 if c.values[ark.TORPIDITY] else "-",
                 bg=theme.CARD, fg=theme.INK_SUB, font=theme.F.get("small")).grid(
            row=len(show) + 1, column=1, sticky="e", padx=6, pady=(4, 0))
        tk.Label(grid, text="%d" % c.wild_level_total(), bg=theme.CARD,
                 fg=theme.INK_SUB, font=theme.F.get("small")).grid(
            row=len(show) + 1, column=2, sticky="e", padx=6, pady=(4, 0))

        # ---- 素性 ----
        card2 = theme.Card(self, bg=theme.BG)
        card2.pack(fill="x", padx=16, pady=4)
        b2 = card2.body
        rows = [
            ("種別", "%s / %s" % (c.state_ja, STATUS_JA.get(c.status, c.status))),
            ("刷り込み", "%d%%" % round(c.imprint * 100) if c.imprint else "なし"),
            ("テイム効率", "%.1f%%" % (c.taming_eff * 100)
             if c.taming_eff is not None else "-"),
            ("変異カウンタ", "父側 %d / 母側 %d (合計 %d)"
             % (c.mutations_father, c.mutations_mother, c.mutations_total)),
            ("父", c.father_name or ("ID %s" % ark_id_display(c.father_ark_id)
                                    if c.father_ark_id else "-")),
            ("母", c.mother_name or ("ID %s" % ark_id_display(c.mother_ark_id)
                                    if c.mother_ark_id else "-")),
            ("飼い主 / 部族", "%s / %s" % (c.owner or "-", c.tribe or "-")),
            ("サーバー", c.server or "-"),
            ("ゲーム内ID", ark_id_display(c.ark_id) or "-"),
            ("取り込み元", c.source_file or c.source),
        ]
        for i, (k, v) in enumerate(rows):
            tk.Label(b2, text=k, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small"), width=12, anchor="w").grid(
                row=i, column=0, sticky="w")
            tk.Label(b2, text=str(v), bg=theme.CARD, fg=theme.INK,
                     font=theme.F.get("small"), anchor="w",
                     wraplength=430, justify="left").grid(row=i, column=1, sticky="w")

        if c.ambiguous:
            tk.Label(self, text="⚠ この個体は表示値だけではレベルの内訳が一つに"
                                "決まりませんでした。Export Gun で取り直すか、"
                                "サーバー倍率の設定を見直すと確定します。",
                     bg=theme.BG, fg=theme.RED, font=theme.F.get("small"),
                     wraplength=560, justify="left").pack(anchor="w", padx=16, pady=2)

        # ---- 編集 ----
        card3 = theme.Card(self, bg=theme.BG)
        card3.pack(fill="x", padx=16, pady=4)
        b3 = card3.body
        r1 = tk.Frame(b3, bg=theme.CARD)
        r1.pack(fill="x", pady=2)
        tk.Label(r1, text="名前", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=6, anchor="w").pack(side="left")
        theme.soft_entry(r1, textvariable=self.name_var).pack(
            side="left", fill="x", expand=True)
        r2 = tk.Frame(b3, bg=theme.CARD)
        r2.pack(fill="x", pady=2)
        tk.Label(r2, text="メモ", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=6, anchor="w").pack(side="left")
        theme.soft_entry(r2, textvariable=self.notes_var).pack(
            side="left", fill="x", expand=True)

        box = tk.Frame(self, bg=theme.BG)
        box.pack(pady=(6, 14))
        theme.RoundButton(box, "保存して閉じる", self._save, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

    def _save(self):
        self.st.library.update_fields(self.creature.uid,
                                      name=self.name_var.get().strip(),
                                      notes=self.notes_var.get().strip())
        self.destroy()
        if self.on_changed:
            self.on_changed()
