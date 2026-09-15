# -*- coding: utf-8 -*-
"""ライブラリ画面。種族ごとに個体を並べ、列ごとの最高値を色で示す。"""
import tkinter as tk
from tkinter import messagebox, ttk

from arklib import (ark, breeding, colors as arkcolors, ideal as arkideal,
                    naming, stats)
from arklib.creature import (FEMALE, MALE, STATUS_ALIVE, STATUS_CRYO,
                             STATUS_DEAD, STATUS_JA, STATUS_OBELISK)

from . import theme
from .table import Col, Table

# 一覧に出すステータス (気絶値は出さない)
def stat_columns(species):
    out = [s for s in species.displayed_stat_indices() if s != ark.TORPIDITY]
    return out


def _sex_text(row):
    """頭数の内訳。性別が無い種族は U でまとめる。"""
    u = row.get("genderless") or 0
    if u and not (row.get("males") or row.get("females")):
        return "U%d" % u
    text = "♂%d ♀%d" % (row.get("males") or 0, row.get("females") or 0)
    if u:
        text += " U%d" % u
    return text


def _ink_on(hex_color):
    """塗った色の上で読める文字色を選ぶ (明るい色なら黒、暗い色なら白)。"""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000.0 > 140 else "#FFFFFF"


SHORT_JA = {
    ark.HEALTH: "体力", ark.STAMINA: "スタミナ", ark.OXYGEN: "酸素",
    ark.FOOD: "食料", ark.WEIGHT: "重量", ark.MELEE: "近接",
    ark.SPEED: "速度", ark.CRAFTING_SPEED: "作成",
    ark.TEMPERATURE_FORTITUDE: "温耐",
}


class LibraryPage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.species_bp = None
        self.species = None
        self.show_values = tk.BooleanVar(value=False)
        self.include_dead = tk.BooleanVar(value=False)
        self.query = tk.StringVar()
        self.tops = {}

        self._build()
        self.reload()

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=16, pady=(14, 6))

        tk.Label(head, text="ライブラリ", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(side="left")

        self.sub = tk.Label(head, text="", bg=theme.BG, fg=theme.INK_SUB,
                            font=theme.F.get("small"))
        self.sub.pack(side="left", padx=(12, 0))

        right = tk.Frame(head, bg=theme.BG)
        right.pack(side="right")
        theme.RoundButton(right, "削除", self._delete, kind="danger",
                          bg=theme.BG).pack(side="right", padx=3)
        theme.RoundButton(right, "状態", self._change_status, kind="soft",
                          bg=theme.BG).pack(side="right", padx=3)
        theme.RoundButton(right, "詳細", self._open_detail, kind="soft",
                          bg=theme.BG).pack(side="right", padx=3)
        theme.RoundButton(right, "変異を推定", self._reassign_mutations,
                          kind="soft", bg=theme.BG).pack(side="right", padx=3)
        self.plan_btn = theme.RoundButton(right, "交配計画", self._toggle_plan,
                                          kind="primary", bg=theme.BG)
        self.plan_btn.pack(side="right", padx=3)
        theme.RoundButton(right, "命名規則", self._naming_dialog, kind="soft",
                          bg=theme.BG).pack(side="right", padx=3)
        theme.RoundButton(right, "理想個体", self._ideal_dialog, kind="soft",
                          bg=theme.BG).pack(side="right", padx=3)

        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill="x", padx=16, pady=(0, 8))

        tk.Label(bar, text="検索", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        e = theme.soft_entry(bar, textvariable=self.query, width=18, bg=theme.BG)
        e.pack(side="left", padx=(6, 12))
        e.bind("<KeyRelease>", lambda _e: self._fill_table())

        tk.Checkbutton(bar, text="実数値で表示",
                       variable=self.show_values, command=self._fill_table,
                       bg=theme.BG, fg=theme.INK, selectcolor=theme.FIELD,
                       activebackground=theme.BG, activeforeground=theme.INK,
                       font=theme.F.get("small"), bd=0,
                       highlightthickness=0).pack(side="left")
        tk.Checkbutton(bar, text="死亡も表示", variable=self.include_dead,
                       command=self.reload, bg=theme.BG, fg=theme.INK,
                       selectcolor=theme.FIELD, activebackground=theme.BG,
                       activeforeground=theme.INK, font=theme.F.get("small"),
                       bd=0, highlightthickness=0).pack(side="left", padx=(8, 0))

        self.tops_label = tk.Label(bar, text="", bg=theme.BG, fg=theme.INK_SUB,
                                   font=theme.F.get("small"))
        self.tops_label.pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # 左: 種族リスト
        left = tk.Frame(body, bg=theme.CARD, width=196)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="種族", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=12, pady=(10, 4))
        self.species_list = tk.Listbox(
            left, bg=theme.CARD, fg=theme.INK, bd=0, highlightthickness=0,
            selectbackground=theme.PINK, selectforeground=theme.ON_ACCENT,
            activestyle="none", font=theme.F.get("ui"))
        self.species_list.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.species_list.bind("<<ListboxSelect>>", self._on_species_select)

        # 右: 一覧と詳細
        right_box = tk.Frame(body, bg=theme.BG)
        right_box.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.table_holder = tk.Frame(right_box, bg=theme.CARD)
        self.table_holder.pack(fill="both", expand=True)
        self.table = None

        self.detail = tk.Label(right_box, text="", bg=theme.BG, fg=theme.INK_SUB,
                               font=theme.F.get("small"), justify="left",
                               anchor="w")
        self.detail.pack(fill="x", pady=(8, 0))

        # 交配計画。既定では畳んでおいて、ボタンで開く
        self.plan_holder = tk.Frame(right_box, bg=theme.BG)
        self.plan_page = None
        self.plan_open = False

    # ---- データ --------------------------------------------------------

    def on_show(self):
        self.reload()

    def reload(self):
        summary = self.st.library.species_summary()
        self._summary = summary
        sel = self.species_bp
        self.species_list.delete(0, "end")
        self._species_bps = []
        for row in summary:
            self._species_bps.append(row["species_bp"])
            self.species_list.insert(
                "end", " %s  %d体 (%s)"
                % (row["species_name"], row["n"], _sex_text(row)))
        if not summary:
            self.species_bp = None
            self.species = None
            self.sub.configure(text="個体が登録されていません。"
                                    "「インポート」から読み込んでください")
            self._build_table([])
            self._fill_table()
            return

        index = 0
        if sel in self._species_bps:
            index = self._species_bps.index(sel)
        self.species_list.selection_clear(0, "end")
        self.species_list.selection_set(index)
        self._select_species(self._species_bps[index])

    def _on_species_select(self, _e=None):
        sel = self.species_list.curselection()
        if not sel:
            return
        self._select_species(self._species_bps[sel[0]])

    def _select_species(self, bp):
        self.species_bp = bp
        # 外から種族を切り替えたときも左のリストの選択を合わせる
        bps = getattr(self, "_species_bps", [])
        if bp in bps:
            self.species_list.selection_clear(0, "end")
            self.species_list.selection_set(bps.index(bp))
        self.species = self.st.species_db.by_bp(bp)
        self.creatures = self.st.library.by_species(
            bp, None, self.include_dead.get())
        if self.species is None:
            self.sub.configure(text="種族データが見つかりません (%s)" % bp)
            self._build_table([])
            self._fill_table()
            return
        self.stat_list = stat_columns(self.species)
        # 理想個体 (狙っている姿)。決めてあれば「あと何 %」を出す
        self.ideal = arkideal.load(self.st.library, bp)
        self.ideal_refs = arkideal.refs_from(self.creatures, self.stat_list)
        # 交配プランで決めた狙い方 (ゼロ狙いなど) に合わせて光らせる
        self.goals = self._goals_for(self.stat_list)
        self.tops = breeding.target_levels(self.creatures, self.goals,
                                           include_dead=self.include_dead.get())
        self._build_table(self.stat_list)
        self._fill_table()
        self._update_header()
        self._sync_plan()

    def _goals_for(self, stat_list):
        """交配プラン画面で決めた狙い方。無ければ全部「最高狙い」。"""
        saved = self.st.library.get_setting("plan_goals_%s" % self.species_bp, None)
        goals = {s: breeding.MAX for s in stat_list}
        for key, goal in (saved or {}).items():
            try:
                s = int(key)
            except (TypeError, ValueError):
                continue
            if s in goals and goal in (breeding.MAX, breeding.MIN):
                goals[s] = goal
        return goals

    def _update_header(self):
        info = breeding.library_summary(self.creatures, goals=self.goals)
        has_min = any(g == breeding.MIN for g in self.goals.values())
        self.sub.configure(
            text="%s: %d体 (%s) / %sを全部集めると 素Lv%d"
            % (self.species.display_name, info["count"], _sex_text(info),
               "狙った値" if has_min else "最高ステ",
               info["best_possible_level"]))
        tops_text = " ".join(
            "%s%d%s" % (SHORT_JA.get(s, ark.NAMES_JA[s]), lv,
                        "↓" if self.goals.get(s) == breeding.MIN else "")
            for s, lv in sorted(self.tops.items()))
        done = len(info["complete"])
        text = "%s: %s%s" % ("目標" if has_min else "最高値", tops_text,
                             ("  ★完成個体 %d体" % done) if done else "")
        idl = getattr(self, "ideal", None)
        if idl is not None and not idl.empty:
            ranked = arkideal.rank(self.creatures, idl, self.ideal_refs,
                                   self.species_bp)
            if ranked:
                sc, c = ranked[0]
                text += "   理想に一番近い: %s %.0f%%" % (c.display_name,
                                                         sc.percent)
        self.tops_label.configure(text=text)

    # ---- 表 ------------------------------------------------------------

    def _color_regions(self):
        """この種族が使っている色領域。色データが無ければ空。"""
        if not self.species_bp or not arkcolors.available():
            return []
        return arkcolors.used_regions(self.species_bp)

    def _build_table(self, stat_list):
        for w in self.table_holder.winfo_children():
            w.destroy()
        cols = [Col("name", "名前", 116),
                Col("sex", "性", 34, align="center"),
                Col("level", "Lv", 42, align="e", numeric=True),
                Col("base", "素Lv", 46, align="e", numeric=True)]
        for s in stat_list:
            cols.append(Col("s%d" % s, SHORT_JA.get(s, ark.NAMES_JA[s]),
                            56, align="e", numeric=True))
        for i in self._color_regions():
            cols.append(Col("c%d" % i,
                            arkcolors.region_name(self.species_bp, i)[:4],
                            46, align="center",
                            sort_key=lambda r, k="c%d" % i: r.get("_" + k, 0)))
        if getattr(self, "ideal", None) is not None and not self.ideal.empty:
            cols.append(Col("ideal", "理想", 56, align="e",
                            sort_key=lambda r: r.get("_ideal", -1),
                            tooltip="理想個体にどれだけ近いか"))
        cols += [Col("mut", "変異", 42, align="e", numeric=True),
                 Col("imp", "刷込", 46, align="e"),
                 Col("state", "種別", 52, align="center"),
                 Col("status", "状態", 58, align="center"),
                 Col("server", "サーバー", 80),
                 Col("note", "メモ", 150)]
        self.table = Table(self.table_holder, cols, on_select=self._on_row,
                           on_activate=lambda r: self._open_detail(),
                           cell_style=self._cell_style, row_style=self._row_style,
                           on_row_menu=self._row_menu,
                           bg=theme.CARD, min_rows=10)
        self.table.pack(fill="both", expand=True)
        self.table.sort_key = "base"
        self.table.sort_desc = True

    def _fill_table(self):
        if self.table is None:
            return
        q = (self.query.get() or "").strip().lower()
        rows = []
        for c in getattr(self, "creatures", []):
            if q and q not in (c.name or "").lower() and q not in (c.notes or "").lower():
                continue
            row = {
                "_obj": c,
                "name": c.display_name,
                "sex": c.sex_ja,
                "level": c.level,
                "base": c.base_level(),
                "mut": c.mutations_total,
                "imp": "%d%%" % round(c.imprint * 100) if c.imprint else "",
                "state": c.state_ja,
                "status": STATUS_JA.get(c.status, c.status),
                "server": c.server,
                "note": c.notes,
            }
            for i in self._color_regions():
                cid = c.colors[i] if i < len(c.colors) else 0
                row["c%d" % i] = str(cid) if cid else ""
                row["_c%d" % i] = cid
            idl = getattr(self, "ideal", None)
            if idl is not None and not idl.empty:
                sc = idl.score(c, self.ideal_refs, self.species_bp)
                row["ideal"] = "%.0f%%" % sc.percent
                row["_ideal"] = sc.percent
                row["_score"] = sc
            for s in getattr(self, "stat_list", []):
                if self.show_values.get():
                    row["s%d" % s] = stats.format_value(s, c.values[s]) \
                        if c.values[s] else "-"
                else:
                    row["s%d" % s] = c.bl(s)
            rows.append(row)
        self.table.set_rows(rows)
        if self.table.sort_key:
            self.table._apply_sort()
            self.table._redraw()

    def _cell_style(self, row, key):
        if key == "ideal":
            sc = row.get("_score")
            if sc is None:
                return None
            if sc.reached:
                return (theme.MINT, theme.ON_ACCENT, True)
            if sc.percent >= 90:
                return (theme.FIELD, theme.MINT, True)
            return None
        if key.startswith("c") and key[1:].isdigit():
            cid = row.get("_" + key) or 0
            bg = arkcolors.hex_of(cid) if cid else None
            if not bg:
                return None
            return (bg, _ink_on(bg), False)
        if not key.startswith("s"):
            return None
        try:
            s = int(key[1:])
        except ValueError:
            return None
        c = row.get("_obj")
        if c is None or s not in self.tops:
            return None
        top = self.tops[s]
        lv = c.bl(s)
        goal = getattr(self, "goals", {}).get(s, breeding.MAX)
        if goal == breeding.MIN:
            # ゼロ狙いのステータスは「低いほど良い」ので低い方を光らせる
            if lv <= top:
                return (theme.SKY, theme.ON_ACCENT, True)
            if lv <= top + 2:
                return (theme.FIELD, theme.SKY, True)
            return None
        if top > 0 and lv >= top:
            return (theme.PINK, theme.ON_ACCENT, True)
        if top > 0 and lv >= top - 2:
            return (theme.FIELD, theme.PINK_DK, True)
        return None

    def _row_style(self, row):
        c = row.get("_obj")
        if c is None:
            return None
        if c.status == STATUS_DEAD:
            return {"fg": theme.INK_SUB}
        if c.ambiguous:
            return {"fg": theme.PEACH if not theme.dark() else theme.LEMON}
        return None

    # ---- 行の操作 ------------------------------------------------------

    def _on_row(self, row):
        c = row.get("_obj")
        if c is None:
            return
        if self.plan_open and self.plan_page is not None:
            self.plan_page.set_focus(c)
        parts = []
        if c.ambiguous:
            parts.append("⚠ 表示値だけではレベル内訳が一意に定まらなかった個体")
        vals = []
        for s in getattr(self, "stat_list", []):
            if c.values[s]:
                vals.append("%s %s (野生%d+変異%d / 強化%d)"
                            % (SHORT_JA.get(s, ark.NAMES_JA[s]),
                               stats.format_value(s, c.values[s]),
                               c.levels_wild[s], c.levels_mut[s], c.levels_dom[s]))
        if vals:
            parts.append("  ".join(vals))
        idl = getattr(self, "ideal", None)
        if idl is not None and not idl.empty:
            parts.append("理想個体: " + idl.score(
                c, self.ideal_refs, self.species_bp).summary())
        lineage = []
        if c.father_name or c.mother_name:
            lineage.append("父 %s / 母 %s" % (c.father_name or "?", c.mother_name or "?"))
        if c.mutations_total:
            lineage.append("変異カウンタ 父側%d・母側%d"
                           % (c.mutations_father, c.mutations_mother))
        if lineage:
            parts.append("  ".join(lineage))
        self.detail.configure(text="\n".join(parts))

    def _row_menu(self, row, event):
        """行を右クリックしたときの小さなメニュー。"""
        m = self._build_row_menu(row)
        if m is None:
            return
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _build_row_menu(self, row):
        c = row.get("_obj")
        if c is None:
            return None
        m = tk.Menu(self, tearoff=0, bg=theme.CARD, fg=theme.INK,
                    activebackground=theme.PINK,
                    activeforeground=theme.ON_ACCENT,
                    font=theme.F.get("ui"), bd=0)
        m.add_command(label="詳細", command=self._open_detail)
        m.add_separator()
        m.add_command(label="ステータスを編集…", command=self._edit_stats)
        m.add_command(label="色を編集…", command=self._edit_colors)
        m.add_command(label="状態を変更…", command=self._change_status)
        m.add_separator()
        m.add_command(label="理想個体に設定", command=self._set_as_ideal)
        m.add_command(label="名前をコピー", command=self._copy_name)
        m.add_separator()
        m.add_command(label="削除", command=self._delete)
        return m

    def _edit_stats(self):
        c = self._selected()
        if c is None:
            return
        from .edit_dialog import StatEditDialog
        StatEditDialog(self, self.app, c, on_done=self._after_change)

    def _edit_colors(self):
        c = self._selected()
        if c is None:
            return
        from .edit_dialog import ColorEditDialog
        ColorEditDialog(self, self.app, c, on_done=self._after_change)

    def _set_as_ideal(self):
        """選んだ個体をそのまま目標にする。"""
        c = self._selected()
        if c is None:
            return
        regions = self._color_regions()
        idl = arkideal.Ideal.from_creature(c, self.stat_list, regions)
        arkideal.save(self.st.library, self.species_bp, idl)
        self._after_change()
        messagebox.showinfo(
            "理想個体",
            "%s を理想個体に設定しました。\n\n%s"
            % (c.display_name, idl.describe(self.species_bp)), parent=self)

    def _copy_name(self):
        """ゲーム内に貼る名前をクリップボードへ。"""
        c = self._selected()
        if c is None:
            return
        rule = self.app.autoimport.naming_rule(self.species_bp)
        text = naming.make_name(c, rule["stats"], rule["with_sex"],
                                mutation_mark=rule["mark"], mode=rule["mode"])
        self.clipboard_clear()
        self.clipboard_append(text)
        self.detail.configure(text="クリップボードにコピーしました:  %s" % text)

    def _selected(self):
        if self.table is None:
            return None
        c = self.table.selected_obj()
        if c is None:
            messagebox.showinfo("ARK ライブラリ", "個体を選択してください。", parent=self)
        return c

    def _open_detail(self):
        c = self._selected()
        if c is None:
            return
        from .detail import CreatureDialog
        CreatureDialog(self, self.app, c, on_changed=self._after_change)

    def _after_change(self):
        self._select_species(self.species_bp)
        self.app.refresh_status()

    def _delete(self):
        c = self._selected()
        if c is None:
            return
        if not messagebox.askyesno(
                "削除の確認",
                "%s をライブラリから削除します。よろしいですか？\n"
                "(ゲーム内の生物には影響しません)" % c.display_name, parent=self):
            return
        self.st.library.delete(c.uid)
        self.reload()
        self.app.refresh_status()

    def _change_status(self):
        c = self._selected()
        if c is None:
            return
        _StatusDialog(self, self.st.library, c, self._after_change)

    def _reassign_mutations(self):
        """あとから親が揃った個体の変異を振り分け直す。"""
        fixed, looked, notes = breeding.reassign_mutations(self.st.library)
        lines = ["両親が見つかった個体: %d 体" % looked,
                 "変異を特定できた個体: %d 体" % fixed]
        for c, note in notes[:12]:
            lines.append("  %s … %s" % (c.display_name, note))
        if looked == 0:
            lines.append("")
            lines.append("両親の両方 (または片方) がライブラリに無いと判定できません。"
                         "両親もエクスポートしてインポートしてください。")
        messagebox.showinfo("変異の推定", "\n".join(lines), parent=self)
        self._after_change()

    # ---- 交配計画 ------------------------------------------------------

    def _toggle_plan(self):
        """同じ画面の下に交配計画を出す / しまう。"""
        if self.plan_open:
            self.plan_holder.pack_forget()
            self.plan_open = False
            self.plan_btn.set_text("交配計画")
            return
        if self.plan_page is None:
            from .page_plan import PlanPage
            self.plan_page = PlanPage(self.plan_holder, self.app, embedded=True)
            self.plan_page.pack(fill="both", expand=True)
        self.plan_holder.pack(fill="both", expand=True, pady=(8, 0))
        self.plan_open = True
        self.plan_btn.set_text("計画を閉じる")
        self._sync_plan()

    def _sync_plan(self):
        """いま選んでいる種族と個体を、下の交配計画に渡す。"""
        if not self.plan_open or self.plan_page is None:
            return
        if self.species_bp:
            self.plan_page.select_species(self.species_bp)
        self.plan_page.set_focus(self.table.selected_obj() if self.table else None)

    def _ideal_dialog(self):
        """狙っている個体の姿を決める。"""
        if self.species is None:
            messagebox.showinfo("ARK ライブラリ", "先に種族を選択してください。",
                                parent=self)
            return
        from .ideal_dialog import IdealDialog
        IdealDialog(self, self.app, self.species_bp,
                    self.species.display_name, self.stat_list,
                    creatures=self.creatures,
                    selected=self.table.selected_obj() if self.table else None,
                    on_done=self._after_change)

    def _naming_dialog(self):
        """この種族だけ、名前に入れるステータスを変える。"""
        if self.species is None:
            messagebox.showinfo("ARK ライブラリ", "先に種族を選択してください。",
                                parent=self)
            return
        from .naming_dialog import SpeciesNamingDialog
        SpeciesNamingDialog(self, self.app, self.species_bp,
                            self.species.display_name, self.stat_list)


class _StatusDialog(tk.Toplevel):
    """生存 / クライオ / アップロード / 死亡 の切り替え。"""

    CHOICES = [(STATUS_ALIVE, "生存"), (STATUS_CRYO, "クライオ"),
               (STATUS_OBELISK, "アップロード中"), (STATUS_DEAD, "死亡")]

    def __init__(self, master, library, creature, on_done):
        tk.Toplevel.__init__(self, master, bg=theme.BG)
        self.title("状態を変える")
        self.library = library
        self.creature = creature
        self.on_done = on_done
        self.transient(master)
        self.resizable(False, False)

        tk.Label(self, text=creature.display_name, bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(padx=20, pady=(16, 8))
        self.var = tk.StringVar(value=creature.status)
        for key, label_text in self.CHOICES:
            tk.Radiobutton(self, text=label_text, variable=self.var, value=key,
                           bg=theme.BG, fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.BG, font=theme.F.get("ui"),
                           bd=0, highlightthickness=0, anchor="w").pack(
                fill="x", padx=24)
        box = tk.Frame(self, bg=theme.BG)
        box.pack(padx=20, pady=14)
        theme.RoundButton(box, "決定", self._ok, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "キャンセル", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)
        self.grab_set()

    def _ok(self):
        self.library.update_fields(self.creature.uid, status=self.var.get())
        self.destroy()
        if self.on_done:
            self.on_done()
