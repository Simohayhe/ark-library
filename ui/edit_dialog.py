# -*- coding: utf-8 -*-
"""個体の手直し。

取り込みで読み違えたとき、Export Gun が無くてレベルの内訳が決まらなかったとき、
ゲーム内で色を塗り替えたときなどに、手で直せるようにしておく。

ステータスは **レベルの内訳** を直す。表示値はそこから計算し直すので、
サーバー倍率を変えても矛盾しない。
"""
import tkinter as tk
from tkinter import messagebox

from arklib import ark, colors as arkcolors, stats
from arklib.creature import FEMALE, GENDERLESS, MALE, UNKNOWN_SEX

from . import theme
from .colorpick import ColorButton, ColorDialog

SHORT = {ark.HEALTH: "体力", ark.STAMINA: "スタミナ", ark.OXYGEN: "酸素",
         ark.FOOD: "食料", ark.WEIGHT: "重量", ark.MELEE: "近接",
         ark.SPEED: "速度", ark.CRAFTING_SPEED: "作成",
         ark.TEMPERATURE_FORTITUDE: "温耐"}


class StatEditDialog(tk.Toplevel):
    """ステータス (レベルの内訳)・名前・性別・刷り込みを直す。"""

    def __init__(self, parent, app, creature, on_done=None):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.c = creature
        self.on_done = on_done
        self.sp = self.st.species_db.by_bp(creature.species_bp)
        self.title("ステータスを編集 - %s" % creature.display_name)
        self.transient(parent)
        self.resizable(False, False)

        self.stat_list = ([s for s in self.sp.displayed_stat_indices()
                           if s != ark.TORPIDITY] if self.sp is not None
                          else [s for s in range(ark.STATS_COUNT)
                                if s != ark.TORPIDITY])

        tk.Label(self, text="%s %s" % (creature.species_name, creature.display_name),
                 bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="レベルの内訳を直します。ゲーム内の値はここから"
                            "計算し直すので、手で入れる必要はありません。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=20)

        # ---- 名前・性別 ----
        top = tk.Frame(self, bg=theme.BG)
        top.pack(fill="x", padx=20, pady=(12, 4))
        tk.Label(top, text="名前", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=5, anchor="w").pack(side="left")
        self.name_var = tk.StringVar(value=creature.name)
        theme.soft_entry(top, textvariable=self.name_var, width=20,
                         bg=theme.BG).pack(side="left", padx=(0, 16))
        tk.Label(top, text="性別", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(0, 4))
        self.sex_var = tk.StringVar(value=creature.sex)
        if self.sp is not None and self.sp.no_gender:
            choices = [(GENDERLESS, "U (性別なし)")]
        else:
            choices = [(MALE, "♂ オス"), (FEMALE, "♀ メス"), (UNKNOWN_SEX, "不明")]
        for key, label in choices:
            tk.Radiobutton(top, text=label, variable=self.sex_var, value=key,
                           bg=theme.BG, fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.BG, activeforeground=theme.INK,
                           font=theme.F.get("small"), bd=0,
                           highlightthickness=0).pack(side="left")

        # ---- レベルの表 ----
        grid = tk.Frame(self, bg=theme.CARD)
        grid.pack(fill="x", padx=20, pady=(8, 4))
        for i, h in enumerate(["ステータス", "野生", "変異", "強化", "継承", "ゲーム内"]):
            tk.Label(grid, text=h, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small")).grid(row=0, column=i, padx=6,
                                                     pady=(6, 2))
        self.wild = {}
        self.mut = {}
        self.dom = {}
        self.sum_labels = {}
        self.val_labels = {}
        for r, s in enumerate(self.stat_list, 1):
            tk.Label(grid, text=SHORT.get(s, ark.NAMES_JA[s]), bg=theme.CARD,
                     fg=theme.INK, font=theme.F.get("ui"), width=8,
                     anchor="w").grid(row=r, column=0, sticky="w", padx=6)
            for col, (store, src) in enumerate(
                    [(self.wild, creature.levels_wild),
                     (self.mut, creature.levels_mut),
                     (self.dom, creature.levels_dom)], 1):
                v = tk.StringVar(value=str(src[s]))
                store[s] = v
                e = theme.soft_entry(grid, textvariable=v, width=5, bg=theme.CARD)
                e.grid(row=r, column=col, padx=4, pady=1)
                e.bind("<KeyRelease>", lambda _e: self._preview())
            self.sum_labels[s] = tk.Label(grid, text="", bg=theme.CARD,
                                          fg=theme.PINK_DK,
                                          font=theme.F.get("ui_b"), width=5)
            self.sum_labels[s].grid(row=r, column=4, padx=4)
            self.val_labels[s] = tk.Label(grid, text="", bg=theme.CARD,
                                          fg=theme.INK_SUB,
                                          font=theme.F.get("small"), width=10,
                                          anchor="e")
            self.val_labels[s].grid(row=r, column=5, padx=6, sticky="e")
        tk.Frame(grid, bg=theme.CARD, height=6).grid(row=len(self.stat_list) + 1,
                                                     column=0)

        # ---- 刷り込み・変異カウンタ ----
        extra = tk.Frame(self, bg=theme.BG)
        extra.pack(fill="x", padx=20, pady=(4, 0))
        tk.Label(extra, text="刷り込み %", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.imp_var = tk.StringVar(value="%d" % round(creature.imprint * 100))
        e = theme.soft_entry(extra, textvariable=self.imp_var, width=5, bg=theme.BG)
        e.pack(side="left", padx=(4, 14))
        e.bind("<KeyRelease>", lambda _e: self._preview())
        tk.Label(extra, text="変異カウンタ 父側", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.mf_var = tk.StringVar(value=str(creature.mutations_father))
        theme.soft_entry(extra, textvariable=self.mf_var, width=5,
                         bg=theme.BG).pack(side="left", padx=(4, 8))
        tk.Label(extra, text="母側", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.mm_var = tk.StringVar(value=str(creature.mutations_mother))
        theme.soft_entry(extra, textvariable=self.mm_var, width=5,
                         bg=theme.BG).pack(side="left", padx=(4, 0))

        self.info = tk.Label(self, text="", bg=theme.FIELD, fg=theme.INK,
                             font=theme.F.get("ui"), padx=10, pady=6,
                             anchor="w", justify="left")
        self.info.pack(fill="x", padx=20, pady=(12, 0))

        box = tk.Frame(self, bg=theme.BG)
        box.pack(padx=20, pady=14)
        theme.RoundButton(box, "保存", self._save, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "キャンセル", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

        self._preview()
        self.grab_set()

    # ---- 計算 ----------------------------------------------------------

    def _num(self, var, default=0):
        try:
            return max(0, int((var.get() or "0").strip()))
        except ValueError:
            return default

    def _levels(self):
        lw = list(self.c.levels_wild)
        lm = list(self.c.levels_mut)
        ld = list(self.c.levels_dom)
        for s in self.stat_list:
            lw[s] = self._num(self.wild[s])
            lm[s] = self._num(self.mut[s])
            ld[s] = self._num(self.dom[s])
        return lw, lm, ld

    def _preview(self):
        lw, lm, ld = self._levels()
        imprint = self._num(self.imp_var) / 100.0
        wild_total = sum(lw[s] + lm[s] for s in range(ark.STATS_COUNT)
                         if s != ark.TORPIDITY)
        for s in self.stat_list:
            self.sum_labels[s].configure(text=str(lw[s] + lm[s]))
            text = "-"
            if self.sp is not None and self.sp.stats[s] is not None:
                v = stats.calc_value(
                    self.sp, s, lw[s], lm[s], ld[s], self.c.state != "wild",
                    taming_eff=(1.0 if self.c.taming_eff is None
                                else self.c.taming_eff),
                    imprinting_bonus=imprint)
                text = stats.format_value(s, v)
            self.val_labels[s].configure(text=text)
        self.info.configure(
            text="素Lv%d  強化 %d  → 表示レベル Lv%d"
                 % (1 + wild_total, sum(ld), 1 + wild_total + sum(ld)))

    # ---- 保存 ----------------------------------------------------------

    def _save(self):
        lw, lm, ld = self._levels()
        imprint = min(1.0, self._num(self.imp_var) / 100.0)
        wild_total = sum(lw[s] + lm[s] for s in range(ark.STATS_COUNT)
                         if s != ark.TORPIDITY)
        values = list(self.c.values)
        if self.sp is not None:
            for s in range(ark.STATS_COUNT):
                if self.sp.stats[s] is None:
                    values[s] = 0.0
                    continue
                lvl = wild_total if s == ark.TORPIDITY else lw[s]
                mm = 0 if s == ark.TORPIDITY else lm[s]
                dd = 0 if s == ark.TORPIDITY else ld[s]
                values[s] = stats.calc_value(
                    self.sp, s, lvl, mm, dd, self.c.state != "wild",
                    taming_eff=(1.0 if self.c.taming_eff is None
                                else self.c.taming_eff),
                    imprinting_bonus=imprint)
        self.st.library.update_fields(
            self.c.uid,
            name=self.name_var.get().strip(),
            sex=self.sex_var.get(),
            levels_wild=_json(lw), levels_mut=_json(lm), levels_dom=_json(ld),
            values=_json(values),
            level=1 + wild_total + sum(ld),
            imprint=imprint,
            mutations_father=self._num(self.mf_var),
            mutations_mother=self._num(self.mm_var),
            # 手で直したのだから「内訳が決まらなかった」印は外す
            ambiguous=0)
        self.destroy()
        if self.on_done:
            self.on_done()


class ColorEditDialog(tk.Toplevel):
    """個体の色を直す (塗り替えたとき・取り込みで近い色を拾い損ねたとき)。"""

    def __init__(self, parent, app, creature, on_done=None):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.c = creature
        self.on_done = on_done
        self.title("色を編集 - %s" % creature.display_name)
        self.transient(parent)
        self.resizable(False, False)

        self.colors = list(creature.colors) + [0] * (6 - len(creature.colors))
        regions = (arkcolors.used_regions(creature.species_bp)
                   if arkcolors.available() else [])
        if not regions:
            regions = list(range(arkcolors.REGION_COUNT))

        tk.Label(self, text="%s の色" % creature.display_name, bg=theme.BG,
                 fg=theme.INK, font=theme.F.get("cute_b")).pack(
            anchor="w", padx=20, pady=(16, 2))
        tk.Label(self, text="領域ごとに色を選びます。交配では領域ごとに"
                            "どちらかの親の色をそのまま受け継ぎます。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=20)

        box = tk.Frame(self, bg=theme.BG)
        box.pack(anchor="w", padx=20, pady=(10, 0))
        self.buttons = {}
        for n, i in enumerate(regions):
            row = tk.Frame(box, bg=theme.BG)
            row.grid(row=n, column=0, sticky="w", pady=2)
            tk.Label(row, text=arkcolors.region_name(creature.species_bp, i),
                     bg=theme.BG, fg=theme.INK, font=theme.F.get("ui"),
                     width=14, anchor="w").pack(side="left")
            b = ColorButton(row, self.colors[i], lambda r=i: self._pick(r),
                            bg=theme.BG)
            b.pack(side="left")
            self.buttons[i] = b

        btns = tk.Frame(self, bg=theme.BG)
        btns.pack(padx=20, pady=16)
        theme.RoundButton(btns, "保存", self._save, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(btns, "キャンセル", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)
        self.grab_set()

    def _pick(self, region):
        ColorDialog(self, self.c.species_bp, region, self.colors[region],
                    lambda cid, r=region: self._set(r, cid))

    def _set(self, region, color_id):
        self.colors[region] = color_id
        self.buttons[region].set_color(color_id)

    def _save(self):
        self.st.library.update_fields(self.c.uid, colors=_json(self.colors))
        self.destroy()
        if self.on_done:
            self.on_done()


def _json(v):
    import json
    return json.dumps(v)
