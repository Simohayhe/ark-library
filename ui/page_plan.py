# -*- coding: utf-8 -*-
"""交配プラン画面。

やることは 3 つ。
    おすすめペア … 今すぐ掛けるならどの組み合わせが良いか
    仕上げの手順 … 狙ったステータスを 1 匹に集めるまでの世代ごとの段取り
    変異狙い     … 完成個体を崩さずに変異を足せるペア
"""
import tkinter as tk
from tkinter import ttk

from arklib import ark, breeding
from arklib import colors as arkcolors
from arklib.creature import MUTATION_LIMIT

from . import theme
from .page_library import SHORT_JA, stat_columns
from .table import Col, Table

TABS = [("pairs", "おすすめペア"), ("plan", "仕上げの手順"),
        ("mutation", "変異狙い"), ("color", "色")]

# 狙い方のプリセット。ステータスごとに 最高(MAX) / ゼロ(MIN) / 無視(None)
PRESETS = [
    ("最高ステ狙い", "all_max"),
    ("実用型 (酸素・食料をゼロ)", "practical"),
    ("Lv1個体 (全ステゼロ)", "level1"),
]


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
        self.color_holder = tk.Frame(self.content, bg=theme.BG)
        self.color_table = None
        self.color_targets = {}      # 領域番号 -> 狙う色 ID

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
        for f in (self.color_holder,):
            f.pack_forget()
        {"pairs": self.pair_holder, "plan": self.plan_holder,
         "mutation": self.mut_holder,
         "color": self.color_holder}[key].pack(fill="both", expand=True)

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
        tk.Label(self.stat_bar, text="狙い", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(0, 6))
        if self.species is None:
            return

        self.goal_chips = {}
        for s in stat_columns(self.species):
            chip = _GoalChip(self.stat_bar, SHORT_JA.get(s, ark.NAMES_JA[s]),
                             lambda _s=s: self._on_goal_changed())
            chip.pack(side="left", padx=(0, 4))
            self.goal_chips[s] = chip

        tk.Label(self.stat_bar, text="まとめて:", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(12, 4))
        self.preset_var = tk.StringVar()
        box = ttk.Combobox(self.stat_bar, textvariable=self.preset_var, width=22,
                           state="readonly", style="Cute.TCombobox",
                           values=[label for label, _k in PRESETS])
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self._apply_preset())

        self._load_goals()

    # ---- 狙い方の読み書き ----------------------------------------------

    def _load_goals(self):
        """保存してある狙い方を chips に流し込む。古い設定からも拾う。"""
        saved = self.st.library.get_setting("plan_goals_%s" % self.species_bp, None)
        if saved is None:
            # 昔の「入れるステータスのチェック」からの引き継ぎ
            old_list = self.st.library.get_setting(
                "plan_stats_%s" % self.species_bp, None)
            if old_list is None:
                old_list = [ark.HEALTH, ark.STAMINA, ark.WEIGHT, ark.MELEE]
            saved = {str(s): breeding.MAX for s in old_list}
        for s, chip in self.goal_chips.items():
            chip.set_goal(saved.get(str(s)) or saved.get(s) or "")

    def _save_goals(self):
        self.st.library.set_setting(
            "plan_goals_%s" % self.species_bp,
            {str(s): c.goal for s, c in self.goal_chips.items() if c.goal})

    def _on_goal_changed(self):
        self.preset_var.set("")
        self._save_goals()
        self.recalc()

    def _apply_preset(self):
        label = self.preset_var.get()
        key = dict((l, k) for l, k in PRESETS).get(label)
        if not key:
            return
        for s, chip in self.goal_chips.items():
            if key == "all_max":
                chip.set_goal(breeding.MAX)
            elif key == "level1":
                chip.set_goal(breeding.MIN)
            else:       # practical
                chip.set_goal(breeding.MIN if s in (ark.OXYGEN, ark.FOOD)
                              else breeding.MAX)
        self._save_goals()
        self.recalc()

    def _goals(self):
        got = {s: c.goal for s, c in self.goal_chips.items() if c.goal}
        if not got:
            got = {s: breeding.MAX for s in self.goal_chips}
        return got

    def _stat_list(self):
        return list(self._goals())

    def _clear(self):
        for w in self.pair_holder.winfo_children():
            w.destroy()
        for w in self.mut_holder.winfo_children():
            w.destroy()
        for w in self.color_holder.winfo_children():
            w.destroy()
        self._write_plan([])

    # ---- 計算 ----------------------------------------------------------

    def recalc(self):
        if self.species is None or not getattr(self, "creatures", None):
            self._clear()
            return
        goals = self._goals()
        self.goals = goals
        stat_list = list(goals)
        pool = [c for c in self.creatures if c.can_breed()]
        tops = breeding.target_levels(pool, goals)
        self.tops = tops

        info = breeding.library_summary(pool, goals=goals)
        tops_text = " ".join(
            "%s%d%s" % (SHORT_JA.get(s, ark.NAMES_JA[s]), lv,
                        "↓" if goals.get(s) == breeding.MIN else "")
            for s, lv in sorted(tops.items()))
        done = info["complete"]
        zero_mode = all(g == breeding.MIN for g in goals.values())
        goal = ("目標 (いまライブラリにある一番いい値): %s → 全部そろえば 素Lv%d"
                % (tops_text, info["best_possible_level"]))
        if zero_mode:
            # 交配では「両親より低い値」は出ない。0 を持つ個体が居ないステータスは
            # そこで頭打ちになるので、何が足りないのかを書く
            missing_zero = [SHORT_JA.get(s, ark.NAMES_JA[s])
                            for s, lv in sorted(tops.items()) if lv > 0]
            if missing_zero:
                goal += ("\n  いまの群れではここが下限です。"
                         "0 を持つ個体が居ないステ: %s"
                         "  ← 低い個体を捕まえて入れると、そのぶん下がります"
                         % "・".join(missing_zero))
            else:
                goal += "  ← 素レベル 1 まで行けます"
        if done:
            goal += "   ★もう揃っている個体: " + "、".join(
                c.display_name for c in done[:3])
        self.goal.configure(text=goal)

        self._fill_pairs(pool, stat_list, tops)
        self._fill_plan(pool, stat_list, tops, done)
        self._fill_mutation(pool, stat_list, tops)
        self._fill_color()

    # ---- おすすめペア --------------------------------------------------

    def _fill_pairs(self, pool, stat_list, tops):
        if self.pair_table is None:
            cols = [Col("male", "♂ オス", 150),
                    Col("female", "♀ メス", 150),
                    Col("tops", "目標達成", 70, align="e",
                        sort_key=lambda r: r.get("_tops", 0)),
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

        plans = breeding.rank_pairs(pool, tops=tops, goals=self.goals,
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
        # 「目標をいくつ満たせるか」で並べる。ゼロ狙いだとレベルの高い順に
        # 並べても意味がないので、ここは狙い方に関係なく達成数を先に見る
        self.pair_table.sort_by("tops", desc=True)

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

        plan = breeding.plan_to_best(pool, goals=self.goals,
                                     species_db=self.st.species_db)
        cover = plan["cover"]
        missing = plan["missing"]

        lines.append(("h", "合わせるべき個体 (%d 体)" % len(cover)))
        for c in cover:
            have = [name(s) for s in breeding.covered_stats(c, tops, self.goals)]
            lines.append(("step", "  %s %s  素Lv%d"
                          % (c.sex_ja, c.display_name, c.base_level())))
            lines.append(("sub", "      目標に届いているステータス: %s"
                          % ("、".join(have) or "なし")))
        if missing:
            lines.append(("warn", "  ※ %s は目標値の持ち主が交配に使えません "
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
                                     "必要な値が全部そろう確率 %.1f%% (平均 %.0f 匹)"
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
        if any(g == breeding.MIN for g in self.goals.values()):
            lines.append(("sub", "　 ゼロ狙い (↓) のステータスは低い方が欲しいので、"
                                 "当たる確率は 45% になります。"))
            lines.append(("sub", "　 両親より低い値は出ません。下限を下げたいときは、"
                                 "そのステータスが低い個体を捕まえて入れてください。"))
        self._write_plan(lines)

    def _write_plan(self, lines):
        self.plan_text.configure(state="normal")
        self.plan_text.delete("1.0", "end")
        for tag, text in lines:
            self.plan_text.insert("end", text + "\n", tag)
        self.plan_text.configure(state="disabled")

    # ---- 色 ------------------------------------------------------------

    def _fill_color(self):
        for w in self.color_holder.winfo_children():
            w.destroy()
        if self.species is None:
            return
        bp = self.species_bp
        regions = arkcolors.used_regions(bp) if arkcolors.available() else []
        if not regions:
            tk.Label(self.color_holder,
                     text="この種族の色データがありません。",
                     bg=theme.BG, fg=theme.INK_SUB,
                     font=theme.F.get("ui")).pack(anchor="w", padx=16, pady=12)
            return

        pool = [c for c in self.creatures if c.can_breed()]
        inv = breeding.color_inventory(pool, regions)

        head = tk.Frame(self.color_holder, bg=theme.BG)
        head.pack(fill="x")
        tk.Label(head, text="狙う色を選ぶ (領域ごと)", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(side="left")
        tk.Label(head, text="色は領域ごとに、どちらかの親のものをそのまま受け継ぐ "
                           "(半々)。混ざらない。",
                 bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=10)
        theme.RoundButton(head, "選び直す", self._clear_color_targets, kind="ghost",
                          bg=theme.BG).pack(side="right")

        picker = tk.Frame(self.color_holder, bg=theme.BG)
        picker.pack(fill="x", pady=(6, 8))
        for n, i in enumerate(regions):
            # 領域は最大 6 つ。横一列だと入りきらないので 3 つずつ折り返す
            box = tk.Frame(picker, bg=theme.CARD)
            box.grid(row=n // 3, column=n % 3, padx=(0, 10), pady=2, sticky="nw")
            tk.Label(box, text=arkcolors.region_name(bp, i), bg=theme.CARD,
                     fg=theme.INK_SUB, font=theme.F.get("small")).pack(anchor="w",
                                                                       padx=8,
                                                                       pady=(6, 2))
            have = inv.get(i) or {}
            if not have:
                tk.Label(box, text="(この領域の色を持つ個体がいない)", bg=theme.CARD,
                         fg=theme.INK_SUB,
                         font=theme.F.get("small")).pack(anchor="w", padx=8,
                                                          pady=(0, 6))
                continue
            row = tk.Frame(box, bg=theme.CARD)
            row.pack(anchor="w", padx=6, pady=(0, 6))
            # 色見本も 4 つずつ折り返す (横に長い種族があるため)
            for n, (cid, owners) in enumerate(
                    sorted(have.items(), key=lambda kv: -len(kv[1]))[:12]):
                sw = _ColorSwatch(row, cid, len(owners),
                                  selected=self.color_targets.get(i) == cid,
                                  command=lambda r=i, c=cid: self._pick_color(r, c))
                sw.grid(row=n // 4, column=n % 4, padx=2, pady=2)

        if self.color_table is None or not self.color_table.winfo_exists():
            cols = [Col("male", "♂ オス", 150), Col("female", "♀ メス", 150),
                    Col("prob", "出る確率", 78, align="e",
                        sort_key=lambda r: r.get("_prob", 0)),
                    Col("eggs", "平均何匹", 78, align="e",
                        sort_key=lambda r: -r.get("_eggs", 0)),
                    Col("sure", "確定している領域", 170),
                    Col("risky", "五分五分の領域", 170)]
            self.color_table = Table(self.color_holder, cols, bg=theme.CARD,
                                     min_rows=8)
        self.color_table.pack(fill="both", expand=True)

        targets = {i: c for i, c in self.color_targets.items() if c}
        if not targets:
            self.color_table.set_rows([{
                "male": "↑ 上の色見本を押して、狙う色を選んでください",
                "female": "", "prob": "", "eggs": "", "sure": "", "risky": "",
            }], keep_sort=False)
            return
        pairs = breeding.rank_color_pairs(pool, targets,
                                          species_db=self.st.species_db, limit=40)
        rows = []
        for cp in pairs:
            rows.append({
                "_obj": cp,
                "male": cp.male.display_name,
                "female": cp.female.display_name,
                "prob": "%.0f%%" % (cp.probability * 100),
                "eggs": "%.0f 匹" % cp.eggs_needed if cp.eggs_needed < 1e6 else "-",
                "sure": "・".join(arkcolors.region_name(bp, i)
                                  for i in cp.sure_regions) or "-",
                "risky": "・".join(arkcolors.region_name(bp, i)
                                   for i in cp.risky_regions) or "-",
                "_prob": cp.probability,
                "_eggs": cp.eggs_needed,
            })
        self.color_table.set_rows(rows, keep_sort=False)
        self.color_table.sort_by("prob", desc=True)

    def _pick_color(self, region, color_id):
        if self.color_targets.get(region) == color_id:
            self.color_targets.pop(region, None)
        else:
            self.color_targets[region] = color_id
        self._fill_color()

    def _clear_color_targets(self):
        self.color_targets = {}
        self._fill_color()

    # ---- 変異狙い ------------------------------------------------------

    def _fill_mutation(self, pool, stat_list, tops):
        if self.mut_table is None:
            cols = [Col("male", "♂ オス", 160),
                    Col("female", "♀ メス", 160),
                    Col("mut", "変異率", 70, align="e",
                        sort_key=lambda r: r.get("_mut", 0)),
                    Col("counters", "変異カウンタ", 120, align="center"),
                    Col("tops", "目標達成", 70, align="e"),
                    Col("note", "ひとこと", 300)]
            self.mut_table = Table(self.mut_holder, cols, bg=theme.CARD,
                                   min_rows=10)
            self.mut_table.pack(fill="both", expand=True)

        plans = breeding.mutation_pairs(pool, tops=tops, goals=self.goals,
                                        species_db=self.st.species_db, limit=40)
        rows = []
        for p in plans:
            note = []
            if p.top_count >= len(tops):
                note.append("この子は狙ったステを保ったまま変異を狙える")
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


class _ColorSwatch(tk.Canvas):
    """色見本。押すと「狙う色」に選ばれる。"""

    W, H = 58, 34

    def __init__(self, master, color_id, count, selected, command):
        tk.Canvas.__init__(self, master, width=self.W, height=self.H,
                           bg=theme.CARD, highlightthickness=0, bd=0)
        self.color_id = color_id
        self.count = count
        self.selected = selected
        self.command = command
        self.bind("<ButtonRelease-1>", lambda e: command())
        self.configure(cursor="hand2")
        self._draw()

    def _draw(self):
        self.delete("all")
        fill = arkcolors.hex_of(self.color_id) or theme.BG_SOFT
        outline = theme.INK if self.selected else theme.LINE
        theme.round_rect(self, 1, 1, self.W - 1, self.H - 1, 6, fill=fill,
                         outline=outline, width=3 if self.selected else 1)
        ink = "#000000" if _bright(fill) else "#FFFFFF"
        self.create_text(self.W / 2, self.H / 2 - 5, text=str(self.color_id),
                         fill=ink, font=theme.F.get("small"))
        self.create_text(self.W / 2, self.H / 2 + 8, text="%d体" % self.count,
                         fill=ink, font=theme.F.get("small"))


def _bright(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (r * 299 + g * 587 + b * 114) / 1000.0 > 140


class _GoalChip(tk.Canvas):
    """ステータスの狙い方を 3 段階で切り替えるチップ。

        ↑ = 最高を狙う   ↓ = ゼロを狙う   — = 気にしない

    押すたびに ↑ → ↓ → — と回る。
    """

    H = 26
    ORDER = [breeding.MAX, breeding.MIN, ""]
    MARK = {breeding.MAX: "↑", breeding.MIN: "↓", "": "—"}

    def __init__(self, master, text, on_change):
        import tkinter.font as tkfont
        self.font = theme.F.get("small")
        fo = tkfont.Font(font=self.font)
        w = fo.measure(text + " ↑") + 20
        tk.Canvas.__init__(self, master, width=w, height=self.H, bg=theme.BG,
                           highlightthickness=0, bd=0)
        self.text = text
        self.goal = breeding.MAX
        self.on_change = on_change
        self.bind("<ButtonRelease-1>", self._click)
        self.configure(cursor="hand2")
        self._draw()

    def set_goal(self, goal):
        self.goal = goal if goal in self.ORDER else ""
        self._draw()

    def _click(self, _e=None):
        self.goal = self.ORDER[(self.ORDER.index(self.goal) + 1) % len(self.ORDER)]
        self._draw()
        if self.on_change:
            self.on_change()

    def _draw(self):
        self.delete("all")
        w = int(self["width"])
        fill = {breeding.MAX: theme.PINK, breeding.MIN: theme.SKY,
                "": theme.BG_SOFT}[self.goal]
        fg = theme.INK_SUB if not self.goal else theme.ON_ACCENT
        theme.round_rect(self, 1, 2, w - 1, self.H - 2, min(9, theme.RADIUS),
                         fill=fill, outline="")
        self.create_text(w / 2, self.H / 2,
                         text="%s %s" % (self.text, self.MARK[self.goal]),
                         fill=fg, font=self.font)


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
