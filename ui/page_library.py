# -*- coding: utf-8 -*-
"""ライブラリ画面。種族ごとに個体を並べ、列ごとの最高値を色で示す。"""
import tkinter as tk
from tkinter import messagebox, ttk

from arklib import ark, breeding, stats
from arklib.creature import (FEMALE, MALE, STATUS_ALIVE, STATUS_CRYO,
                             STATUS_DEAD, STATUS_JA, STATUS_OBELISK)

from . import theme
from .table import Col, Table

# 一覧に出すステータス (気絶値は出さない)
def stat_columns(species):
    out = [s for s in species.displayed_stat_indices() if s != ark.TORPIDITY]
    return out


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
        theme.RoundButton(right, "交配プランへ", self._to_plan, kind="primary",
                          bg=theme.BG).pack(side="right", padx=3)

        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill="x", padx=16, pady=(0, 8))

        tk.Label(bar, text="検索", bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        e = theme.soft_entry(bar, textvariable=self.query, width=18, bg=theme.BG)
        e.pack(side="left", padx=(6, 12))
        e.bind("<KeyRelease>", lambda _e: self._fill_table())

        tk.Checkbutton(bar, text="レベルではなく実数値で見る",
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
                "end", " %s  %d体 (♂%d ♀%d)"
                % (row["species_name"], row["n"], row["males"], row["females"]))
        if not summary:
            self.species_bp = None
            self.species = None
            self.sub.configure(text="まだ 1 体も入っていません。"
                                    "「取り込み」からエクスポートを読み込んでください")
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
        self.species = self.st.species_db.by_bp(bp)
        self.creatures = self.st.library.by_species(
            bp, None, self.include_dead.get())
        if self.species is None:
            self.sub.configure(text="種族データが見つかりません (%s)" % bp)
            self._build_table([])
            self._fill_table()
            return
        self.stat_list = stat_columns(self.species)
        self.tops = breeding.top_levels(self.creatures, self.stat_list,
                                        include_dead=self.include_dead.get())
        self._build_table(self.stat_list)
        self._fill_table()
        self._update_header()

    def _update_header(self):
        info = breeding.library_summary(self.creatures, self.stat_list)
        self.sub.configure(
            text="%s: %d体 (♂%d ♀%d) / 最高ステを全部集めると Lv%d"
            % (self.species.display_name, info["count"], info["males"],
               info["females"], info["best_possible_level"]))
        tops_text = " ".join(
            "%s%d" % (SHORT_JA.get(s, ark.NAMES_JA[s]), lv)
            for s, lv in sorted(self.tops.items()))
        done = len(info["complete"])
        self.tops_label.configure(
            text="最高値: %s%s" % (tops_text,
                                 ("  ★完成個体 %d体" % done) if done else ""))

    # ---- 表 ------------------------------------------------------------

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
        cols += [Col("mut", "変異", 42, align="e", numeric=True),
                 Col("imp", "刷込", 46, align="e"),
                 Col("state", "種別", 52, align="center"),
                 Col("status", "状態", 58, align="center"),
                 Col("server", "サーバー", 80),
                 Col("note", "メモ", 150)]
        self.table = Table(self.table_holder, cols, on_select=self._on_row,
                           on_activate=lambda r: self._open_detail(),
                           cell_style=self._cell_style, row_style=self._row_style,
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
        parts = []
        if c.ambiguous:
            parts.append("⚠ 表示値だけではレベルの内訳が一つに決まらなかった個体")
        vals = []
        for s in getattr(self, "stat_list", []):
            if c.values[s]:
                vals.append("%s %s (野生%d+変異%d / 強化%d)"
                            % (SHORT_JA.get(s, ark.NAMES_JA[s]),
                               stats.format_value(s, c.values[s]),
                               c.levels_wild[s], c.levels_mut[s], c.levels_dom[s]))
        if vals:
            parts.append("  ".join(vals))
        lineage = []
        if c.father_name or c.mother_name:
            lineage.append("父 %s / 母 %s" % (c.father_name or "?", c.mother_name or "?"))
        if c.mutations_total:
            lineage.append("変異カウンタ 父側%d・母側%d"
                           % (c.mutations_father, c.mutations_mother))
        if lineage:
            parts.append("  ".join(lineage))
        self.detail.configure(text="\n".join(parts))

    def _selected(self):
        if self.table is None:
            return None
        c = self.table.selected_obj()
        if c is None:
            messagebox.showinfo("ARK ライブラリ", "個体を選んでください。", parent=self)
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
                "(ゲーム内の生物には何も起きません)" % c.display_name, parent=self):
            return
        self.st.library.delete(c.uid)
        self.reload()
        self.app.refresh_status()

    def _change_status(self):
        c = self._selected()
        if c is None:
            return
        _StatusDialog(self, self.st.library, c, self._after_change)

    def _to_plan(self):
        self.app.show("plan")
        page = self.app._pages.get("plan")
        if page is not None and self.species_bp:
            page.select_species(self.species_bp)


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
        theme.RoundButton(box, "やめる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)
        self.grab_set()

    def _ok(self):
        self.library.update_fields(self.creature.uid, status=self.var.get())
        self.destroy()
        if self.on_done:
            self.on_done()
