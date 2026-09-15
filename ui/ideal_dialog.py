# -*- coding: utf-8 -*-
"""理想個体 (目標) を決める画面。

「この種族はこういう個体が欲しい」を 1 つ決めておくと、一覧に「理想まで何 %」
が出る。ステータスは足りないぶんだけ % が下がり、色は合っているかどうかだけ。
"""
import tkinter as tk

from arklib import ark, colors as arkcolors, ideal as arkideal

from . import theme
from .colorpick import ColorButton, ColorDialog

SHORT = {ark.HEALTH: "体力", ark.STAMINA: "スタミナ", ark.OXYGEN: "酸素",
         ark.FOOD: "食料", ark.WEIGHT: "重量", ark.MELEE: "近接",
         ark.SPEED: "速度", ark.CRAFTING_SPEED: "作成",
         ark.TEMPERATURE_FORTITUDE: "温耐"}


class IdealDialog(tk.Toplevel):
    def __init__(self, parent, app, species_bp, species_name, stat_list,
                 creatures=None, selected=None, on_done=None):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.species_bp = species_bp
        self.stat_list = list(stat_list or [])
        self.creatures = list(creatures or [])
        self.selected = selected
        self.on_done = on_done
        self.title("理想個体 - %s" % species_name)
        self.transient(parent)
        self.resizable(False, False)

        cur = arkideal.load(self.st.library, species_bp)

        tk.Label(self, text="%s の理想個体" % species_name, bg=theme.BG,
                 fg=theme.INK, font=theme.F.get("cute_b")).pack(
            anchor="w", padx=20, pady=(16, 2))
        tk.Label(self,
                 text="目標のステータスと色を設定すると、一覧に到達率が表示されます。\n"
                      "ステータスは目標から離れるほど % が下がります "
                      "(0 を指定するとゼロ狙い)。\n"
                      "色は一致・不一致のみで判定します (近似色の概念なし)。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=20)

        # ---- ステータス ----
        tk.Label(self, text="ステータス (野生+変異レベル)", bg=theme.BG,
                 fg=theme.INK_SUB, font=theme.F.get("small")).pack(
            anchor="w", padx=20, pady=(12, 2))
        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(anchor="w", padx=20)
        self.use = {}
        self.level = {}
        for i, s in enumerate(self.stat_list):
            row, col = i // 3, (i % 3) * 2
            v = tk.BooleanVar(value=s in cur.stats)
            self.use[s] = v
            tk.Checkbutton(grid, text=SHORT.get(s, ark.NAMES_JA[s]), variable=v,
                           command=self._preview, bg=theme.BG, fg=theme.INK,
                           selectcolor=theme.FIELD, activebackground=theme.BG,
                           activeforeground=theme.INK, font=theme.F.get("ui"),
                           bd=0, highlightthickness=0, anchor="w", width=8).grid(
                row=row, column=col, sticky="w")
            sv = tk.StringVar(value=str(cur.stats.get(s, "")))
            self.level[s] = sv
            e = theme.soft_entry(grid, textvariable=sv, width=5, bg=theme.BG)
            e.grid(row=row, column=col + 1, sticky="w", padx=(2, 14), pady=2)
            e.bind("<KeyRelease>", lambda _e: self._preview())

        fill = tk.Frame(self, bg=theme.BG)
        fill.pack(anchor="w", padx=20, pady=(8, 0))
        theme.RoundButton(fill, "最高値を反映", self._from_tops,
                          kind="soft", bg=theme.BG).pack(side="left", padx=(0, 6))
        if selected is not None:
            theme.RoundButton(fill, "選択中の個体から", self._from_selected,
                              kind="soft", bg=theme.BG).pack(side="left",
                                                             padx=(0, 6))
        theme.RoundButton(fill, "すべてクリア", self._clear_stats, kind="ghost",
                          bg=theme.BG).pack(side="left")

        # ---- 色 ----
        self.colors = dict(cur.colors)
        regions = arkcolors.used_regions(species_bp) if arkcolors.available() else []
        self.color_buttons = {}
        if regions:
            tk.Label(self, text="色 (対象外の領域は「色を指定しない」のまま)",
                     bg=theme.BG, fg=theme.INK_SUB,
                     font=theme.F.get("small")).pack(anchor="w", padx=20,
                                                     pady=(14, 2))
            cbox = tk.Frame(self, bg=theme.BG)
            cbox.pack(anchor="w", padx=20)
            for n, i in enumerate(regions):
                box = tk.Frame(cbox, bg=theme.BG)
                box.grid(row=n // 2, column=n % 2, sticky="w", padx=(0, 16),
                         pady=2)
                tk.Label(box, text=arkcolors.region_name(species_bp, i),
                         bg=theme.BG, fg=theme.INK, font=theme.F.get("small"),
                         width=12, anchor="w").pack(side="left")
                b = ColorButton(box, self.colors.get(i, 0),
                                lambda r=i: self._pick_color(r), bg=theme.BG)
                b.pack(side="left")
                self.color_buttons[i] = b

        self.preview = tk.Label(self, text="", bg=theme.FIELD, fg=theme.INK,
                                font=theme.F.get("ui"), padx=10, pady=6,
                                anchor="w", justify="left")
        self.preview.pack(fill="x", padx=20, pady=(14, 0))

        box = tk.Frame(self, bg=theme.BG)
        box.pack(padx=20, pady=14)
        theme.RoundButton(box, "決定", self._save, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "目標を解除", self._delete, kind="soft",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

        self._preview()
        self.grab_set()

    # ---- 中身 ----------------------------------------------------------

    def _build(self):
        """いまの入力から Ideal を作る。"""
        stats = {}
        for s in self.stat_list:
            if not self.use[s].get():
                continue
            try:
                stats[s] = max(0, int((self.level[s].get() or "0").strip()))
            except ValueError:
                stats[s] = 0
        return arkideal.Ideal(stats, self.colors)

    def _preview(self):
        idl = self._build()
        if idl.empty:
            self.preview.configure(text="未設定")
            return
        lines = ["目標: %s  (素Lv%d)" % (idl.describe(self.species_bp),
                                         idl.base_level())]
        refs = arkideal.refs_from(self.creatures)
        ranked = arkideal.rank(self.creatures, idl, refs, self.species_bp)
        if ranked:
            sc, c = ranked[0]
            lines.append("最も近い個体: %s  %.0f%%"
                         % (c.display_name, sc.percent))
            if sc.short:
                lines.append("  未達: " + "、".join(i.text for i in sc.short))
        self.preview.configure(text="\n".join(lines))

    def _pick_color(self, region):
        ColorDialog(self, self.species_bp, region, self.colors.get(region, 0),
                    lambda cid, r=region: self._set_color(r, cid))

    def _set_color(self, region, color_id):
        if color_id:
            self.colors[region] = color_id
        else:
            self.colors.pop(region, None)
        self.color_buttons[region].set_color(color_id)
        self._preview()

    # ---- 埋めるボタン ---------------------------------------------------

    def _from_tops(self):
        tops = {}
        for c in self.creatures:
            for s in self.stat_list:
                if c.bl(s) > tops.get(s, 0):
                    tops[s] = c.bl(s)
        for s in self.stat_list:
            self.use[s].set(True)
            self.level[s].set(str(tops.get(s, 0)))
        self._preview()

    def _from_selected(self):
        c = self.selected
        if c is None:
            return
        for s in self.stat_list:
            self.use[s].set(True)
            self.level[s].set(str(c.bl(s)))
        for i, b in self.color_buttons.items():
            cid = c.colors[i] if i < len(c.colors) else 0
            self._set_color(i, cid)
        self._preview()

    def _clear_stats(self):
        for s in self.stat_list:
            self.use[s].set(False)
            self.level[s].set("")
        self._preview()

    # ---- 保存 ----------------------------------------------------------

    def _save(self):
        arkideal.save(self.st.library, self.species_bp, self._build())
        self.destroy()
        if self.on_done:
            self.on_done()

    def _delete(self):
        arkideal.save(self.st.library, self.species_bp, None)
        self.destroy()
        if self.on_done:
            self.on_done()
