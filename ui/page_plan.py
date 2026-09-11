# -*- coding: utf-8 -*-
"""交配プラン画面。

やることは 3 つ。
    おすすめペア … 今すぐ掛けるならどの組み合わせが良いか
    仕上げの手順 … 最高ステを 1 匹に集めるまでの世代ごとの段取り
    変異狙い     … 完成個体を崩さずに変異を足せるペア
"""
import tkinter as tk
from tkinter import ttk

from arklib import ark, breeding
from arklib.creature import MUTATION_LIMIT

from . import theme
from .page_library import SHORT_JA, stat_columns
from .table import Col, Table

TABS = [("pairs", "おすすめペア"), ("plan", "仕上げの手順"),
        ("mutation", "変異狙い")]


class PlanPage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.species_bp = None
        self.species = None
        self.tab = "pairs"
        self.stat_vars = {}
        self.species_var = tk.StringVar()
        self.include_tamed = tk.BooleanVar(value=True)

        self._build()
        self.reload()

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text="交配プラン", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(side="left")
        self.species_box = ttk.Combobox(head, textvariable=self.species_var,
                                        width=26, state="readonly",
                                        style="Cute.TCombobox")
        self.species_box.pack(side="left", padx=12)
        self.species_box.bind("<<ComboboxSelected>>", lambda _e: self._on_species())
        theme.RoundButton(head, "計算し直す", self.recalc, kind="primary",
                          bg=theme.BG).pack(side="right")

        # 対象ステータスの選択
        self.stat_bar = tk.Frame(self, bg=theme.BG)
        self.stat_bar.pack(fill="x", padx=16, pady=(0, 4))

        self.goal = tk.Label(self, text="", bg=theme.BG, fg=theme.INK_SUB,
                             font=theme.F.get("small"), justify="left", anchor="w")
        self.goal.pack(fill="x", padx=16, pady=(0, 6))

        # タブ
        tabs = tk.Frame(self, bg=theme.BG)
        tabs.pack(fill="x", padx=16)
        self._tab_buttons = {}
        for key, label_text in TABS:
            b = _Tab(tabs, label_text, lambda k=key: self._set_tab(k))
            b.pack(side="left", padx=(0, 6))
            self._tab_buttons[key] = b

        self.content = tk.Frame(self, bg=theme.BG)
        self.content.pack(fill="both", expand=True, padx=16, pady=(8, 14))

        self.pair_holder = tk.Frame(self.content, bg=theme.CARD)
        self.pair_table = None
        self.plan_holder = tk.Frame(self.content, bg=theme.BG)
        self.mut_holder = tk.Frame(self.content, bg=theme.CARD)
        self.mut_table = None

        self.plan_text = tk.Text(self.plan_holder, bg=theme.CARD, fg=theme.INK,
                                 bd=0, highlightthickness=0, wrap="word",
                                 font=theme.F.get("ui"), padx=16, pady=12)
        self.plan_text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(self.plan_holder, orient="vertical",
                           style="Cute.Vertical.TScrollbar",
                           command=self.plan_text.yview)
        sb.pack(side="right", fill="y")
        self.plan_text.configure(yscrollcommand=sb.set, state="disabled")
        self.plan_text.tag_configure("h", font=theme.F.get("cute_b"),
                                     foreground=theme.INK)
        self.plan_text.tag_configure("step", font=theme.F.get("ui_b"),
                                     foreground=theme.PINK_DK)
        self.plan_text.tag_configure("sub", foreground=theme.INK_SUB)
        self.plan_text.tag_configure("warn", foreground=theme.RED)
        self.plan_text.tag_configure("good", foreground=theme.MINT)

        self._set_tab("pairs")

    def _set_tab(self, key):
        self.tab = key
        for k, b in self._tab_buttons.items():
            b.set_active(k == key)
        for f in (self.pair_holder, self.plan_holder, self.mut_holder):
            f.pack_forget()
        {"pairs": self.pair_holder, "plan": self.plan_holder,
         "mutation": self.mut_holder}[key].pack(fill="both", expand=True)

    # ---- データ --------------------------------------------------------

    def on_show(self):
        self.reload()

    def reload(self):
        summary = self.st.library.species_summary()
        self._summary = summary
        names = ["%s (%d体)" % (r["species_name"], r["n"]) for r in summary]
        self._bps = [r["species_bp"] for r in summary]
        self.species_box.configure(values=names)
        if not summary:
            self.goal.configure(text="ライブラリが空です。まず取り込んでください。")
            self._clear()
            return
        idx = 0
        if self.species_bp in self._bps:
            idx = self._bps.index(self.species_bp)
        self.species_var.set(names[idx])
        self._select(self._bps[idx])

    def select_species(self, bp):
        if bp in getattr(self, "_bps", []):
            self.species_var.set(self.species_box.cget("values")[self._bps.index(bp)])
            self._select(bp)

    def _on_species(self):
        names = list(self.species_box.cget("values"))
        if self.species_var.get() in names:
            self._select(self._bps[names.index(self.species_var.get())])

    def _select(self, bp):
        self.species_bp = bp
        self.species = self.st.species_db.by_bp(bp)
        self.creatures = [c for c in self.st.library.by_species(bp, None, False)]
        self._build_stat_bar()
        self.recalc()

    def _build_stat_bar(self):
        for w in self.stat_bar.winfo_children():
            w.destroy()
        tk.Label(self.stat_bar, text="狙うステータス", bg=theme.BG,
                 fg=theme.INK_SUB, font=theme.F.get("small")).pack(side="left",
                                                                   padx=(0, 8))
        if self.species is None:
            return
        all_stats = stat_columns(self.species)
        # 既定は体力 / スタミナ / 重量 / 近接。酸素・食料は交配で重視しないことが多い
        default_on = {ark.HEALTH, ark.STAMINA, ark.WEIGHT, ark.MELEE}
        saved = self.st.library.get_setting("plan_stats_%s" % self.species_bp, None)
        self.stat_vars = {}
        for s in all_stats:
            on = (s in saved) if saved is not None else (s in default_on)
            v = tk.BooleanVar(value=bool(on))
            self.stat_vars[s] = v
            tk.Checkbutton(self.stat_bar, text=SHORT_JA.get(s, ark.NAMES_JA[s]),
                           variable=v, command=self._save_stats,
                           bg=theme.BG, fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.BG, activeforeground=theme.INK,
                           font=theme.F.get("small"), bd=0,
                           highlightthickness=0).pack(side="left")

    def _save_stats(self):
        self.st.library.set_setting("plan_stats_%s" % self.species_bp,
                                    [s for s, v in self.stat_vars.items() if v.get()])
        self.recalc()

    def _stat_list(self):
        out = [s for s, v in self.stat_vars.items() if v.get()]
        return out or list(self.stat_vars.keys())

    def _clear(self):
        for w in self.pair_holder.winfo_children():
            w.destroy()
        for w in self.mut_holder.winfo_children():
            w.destroy()
        self._write_plan([])

    # ---- 計算 ----------------------------------------------------------

    def recalc(self):
        if self.species is None or not getattr(self, "creatures", None):
            self._clear()
            return
        stat_list = self._stat_list()
        pool = [c for c in self.creatures if c.can_breed()]
        tops = breeding.top_levels(pool, stat_list)
        self.tops = tops

        info = breeding.library_summary(pool, stat_list)
        tops_text = " ".join("%s%d" % (SHORT_JA.get(s, ark.NAMES_JA[s]), lv)
                             for s, lv in sorted(tops.items()))
        done = info["complete"]
        goal = ("目標 (ライブラリの最高値): %s → 全部そろえば 素Lv%d"
                % (tops_text, info["best_possible_level"]))
        if done:
            goal += "   ★もう揃っている個体: " + "、".join(
                c.display_name for c in done[:3])
        self.goal.configure(text=goal)

        self._fill_pairs(pool, stat_list, tops)
        self._fill_plan(pool, stat_list, tops, done)
        self._fill_mutation(pool, stat_list, tops)

    # ---- おすすめペア --------------------------------------------------

    def _fill_pairs(self, pool, stat_list, tops):
        if self.pair_table is None:
            cols = [Col("male", "♂ オス", 150),
                    Col("female", "♀ メス", 150),
                    Col("tops", "最高ステ", 70, align="e", numeric=True),
                    Col("best", "最良の子", 72, align="e", numeric=True),
                    Col("exp", "期待Lv", 66, align="e", numeric=True),
                    Col("prob", "当たり率", 70, align="e",
                        sort_key=lambda r: r.get("_prob", 0)),
                    Col("eggs", "平均何匹", 72, align="e",
                        sort_key=lambda r: -r.get("_eggs", 0)),
                    Col("mut", "変異率", 60, align="e",
                        sort_key=lambda r: r.get("_mut", 0)),
                    Col("diff", "分かれ目", 190)]
            self.pair_table = Table(self.pair_holder, cols, bg=theme.CARD,
                                    min_rows=10, cell_style=self._pair_cell)
            self.pair_table.pack(fill="both", expand=True)

        plans = breeding.rank_pairs(pool, stat_list, tops=tops,
                                    species_db=self.st.species_db, limit=60)
        rows = []
        for p in plans:
            rows.append({
                "_obj": p,
                "male": p.male.display_name,
                "female": p.female.display_name,
                "tops": "%d/%d" % (p.top_count, len(tops)),
                "best": p.best_child_level,
                "exp": round(p.expected_level, 1),
                "prob": "%.1f%%" % (p.probability * 100),
                "eggs": "%.0f 匹" % p.eggs_needed if p.eggs_needed < 1e6 else "-",
                "mut": "%.1f%%" % (p.mutation_probability * 100),
                "diff": "・".join(SHORT_JA.get(s, ark.NAMES_JA[s])
                                  for s in p.needed) or "両親とも同じ",
                "_prob": p.probability,
                "_eggs": p.eggs_needed,
                "_mut": p.mutation_probability,
                "_tops": p.top_count,
            })
        self.pair_table.set_rows(rows, keep_sort=False)
        self.pair_table.sort_by("best", desc=True)

    def _pair_cell(self, row, key):
        p = row.get("_obj")
        if p is None:
            return None
        if key == "tops" and p.top_count >= len(self.tops):
            return (theme.PINK, theme.ON_ACCENT, True)
        if key == "prob" and p.probability >= 0.25:
            return (None, theme.MINT, True)
        return None

    # ---- 仕上げの手順 --------------------------------------------------

    def _fill_plan(self, pool, stat_list, tops, complete):
        lines = []
        name = lambda s: SHORT_JA.get(s, ark.NAMES_JA[s])

        if complete:
            lines.append(("h", "もう完成しています"))
            for c in complete:
                lines.append(("good", "  ★ %s (素Lv%d) が狙ったステータスを全部持っています"
                              % (c.display_name, c.base_level())))
            lines.append(("sub", "  ここから伸ばすには変異を足すことになります。"
                                 "「変異狙い」を見てください。"))
            lines.append(("", ""))

        plan = breeding.plan_to_best(pool, stat_list,
                                     species_db=self.st.species_db)
        cover = plan["cover"]
        missing = plan["missing"]

        lines.append(("h", "合わせるべき個体 (%d 体)" % len(cover)))
        for c in cover:
            have = [name(s) for s, lv in tops.items() if c.bl(s) >= lv]
            lines.append(("step", "  %s %s  素Lv%d"
                          % (c.sex_ja, c.display_name, c.base_level())))
            lines.append(("sub", "      最高値を持っているステータス: %s"
                          % ("、".join(have) or "なし")))
        if missing:
            lines.append(("warn", "  ※ %s は最高値の持ち主が交配に使えません "
                                  "(去勢・死亡・性別不明)"
                          % "、".join(name(s) for s in missing)))
        lines.append(("", ""))

        steps = plan["steps"]
        if not steps:
            lines.append(("sub", "掛け合わせる相手がいません。"
                                 "オスとメスが揃っているか確認してください。"))
        else:
            lines.append(("h", "手順 (%d 世代)" % plan["generations"]))
            for i, stp in enumerate(steps, 1):
                lines.append(("step", "  %d. 第%d世代  %s × %s"
                              % (i, stp.generation, _who(stp.a), _who(stp.b))))
                got = [name(s) for s in stp.needed_stats]
                lines.append(("sub", "      欲しい子: 素Lv%d。"
                                     "必要な最高値が全部そろう確率 %.1f%% (平均 %.0f 匹)"
                              % (1 + sum(stp.result_stats.values()),
                                 stp.probability * 100, stp.eggs_needed)))
                if got:
                    lines.append(("sub", "      ここで引き当てたいステータス: %s"
                                  % "、".join(got)))
                else:
                    lines.append(("sub", "      両親の値が同じなので確実にそろいます"))
                if stp.generation < plan["generations"]:
                    lines.append(("sub", "      → この子を次の世代に使います "
                                         "(必要な性別が出るまで粘る必要があります)"))
            fin = plan["final"]
            if fin is not None:
                lines.append(("", ""))
                lines.append(("h", "ゴール"))
                lines.append(("good", "  素Lv%d (%s)"
                              % (fin.base_level(),
                                 " ".join("%s%d" % (name(s), fin.bl(s))
                                          for s in stat_list))))
                lines.append(("sub", "  卵の数はのべ %.0f 個くらいが目安 "
                                     "(運が平均的な場合)" % plan["total_eggs"]))
        lines.append(("", ""))
        lines.append(("sub", "※ ARK の継承は「高い方の親の値を 55%、低い方を 45%」。"
                             "ステータスごとに独立して決まります。"))
        self._write_plan(lines)

    def _write_plan(self, lines):
        self.plan_text.configure(state="normal")
        self.plan_text.delete("1.0", "end")
        for tag, text in lines:
            self.plan_text.insert("end", text + "\n", tag)
        self.plan_text.configure(state="disabled")

    # ---- 変異狙い ------------------------------------------------------

    def _fill_mutation(self, pool, stat_list, tops):
        if self.mut_table is None:
            cols = [Col("male", "♂ オス", 160),
                    Col("female", "♀ メス", 160),
                    Col("mut", "変異率", 70, align="e",
                        sort_key=lambda r: r.get("_mut", 0)),
                    Col("counters", "変異カウンタ", 120, align="center"),
                    Col("tops", "最高ステ", 70, align="e"),
                    Col("note", "ひとこと", 300)]
            self.mut_table = Table(self.mut_holder, cols, bg=theme.CARD,
                                   min_rows=10)
            self.mut_table.pack(fill="both", expand=True)

        plans = breeding.mutation_pairs(pool, stat_list, tops=tops,
                                       species_db=self.st.species_db, limit=40)
        rows = []
        for p in plans:
            note = []
            if p.top_count >= len(tops):
                note.append("この子は最高ステを保ったまま変異を狙える")
            elif p.needed:
                note.append("先にステータスを揃えた方が早い")
            over = [x.display_name for x in (p.male, p.female)
                    if x.mutations_total >= MUTATION_LIMIT]
            if over:
                note.append("%s はカウンタ 20 以上で変異が出にくい" % "・".join(over))
            rows.append({
                "_obj": p,
                "male": p.male.display_name,
                "female": p.female.display_name,
                "mut": "%.1f%%" % (p.mutation_probability * 100),
                "counters": "♂%d / ♀%d" % (p.male.mutations_total,
                                           p.female.mutations_total),
                "tops": "%d/%d" % (p.top_count, len(tops)),
                "note": "。".join(note),
                "_mut": p.mutation_probability,
            })
        self.mut_table.set_rows(rows, keep_sort=False)
        self.mut_table.sort_by("mut", desc=True)


def _who(c):
    """プラン上の表示名。これから作る子は性別が決まらないので印を変える。"""
    if getattr(c, "virtual", False):
        # 絵文字は tk.Text のフォントで豆腐になるので記号で代用する
        return "◇ %s" % c.display_name
    return "%s %s" % (c.sex_ja, c.display_name)


class _Tab(tk.Canvas):
    H = 30

    def __init__(self, master, text, command):
        import tkinter.font as tkfont
        font = theme.F.get("cute")
        fo = tkfont.Font(font=font)
        w = fo.measure(text) + 28
        tk.Canvas.__init__(self, master, width=w, height=self.H, bg=theme.BG,
                           highlightthickness=0, bd=0)
        self.text = text
        self.font = font
        self.active = False
        self.command = command
        self.bind("<ButtonRelease-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw())
        self.configure(cursor="hand2")
        self._draw()

    def set_active(self, on):
        self.active = on
        self._draw()

    def _draw(self, hover=False):
        self.delete("all")
        w = int(self["width"])
        fill = theme.PINK if self.active else (theme.HOVER_SOFT if hover
                                              else theme.BG_SOFT)
        fg = theme.ON_ACCENT if self.active else theme.INK_SUB
        theme.round_rect(self, 1, 2, w - 1, self.H - 2, min(10, theme.RADIUS),
                         fill=fill, outline="")
        self.create_text(w / 2, self.H / 2, text=self.text, fill=fg, font=self.font)
