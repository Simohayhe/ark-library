# -*- coding: utf-8 -*-
"""設定画面。サーバーごとの倍率プロファイルを作る。

逆算は倍率が合っていないと必ず外れる。倍率の入れ方は 4 つ。
    1. Game.ini / GameUserSettings.ini を読む (自分のサーバーならこれが確実)
    2. Export Gun のサーバー倍率ファイルを読む
    3. 公式サーバー相当のプリセットから始める
    4. **表を直接書き換える** (他所のサーバーで ini が貰えないとき)

4 が要るのは、たとえば「公式相当だけど重量のテイムLvだけ 2 倍」のような
サーバーがよくあるため。ここが 1 つずれるだけで逆算は解なしになる。
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import arklib
from arklib import ark, paths
from arklib.importers import export_gun
from arklib.multipliers import (IDX_LEVEL_DOM, IDX_LEVEL_WILD, IDX_TAMING_ADD,
                                IDX_TAMING_MULT, ServerMultipliers)

from . import theme

SHOW_STATS = [ark.HEALTH, ark.STAMINA, ark.OXYGEN, ark.FOOD, ark.WEIGHT,
              ark.MELEE, ark.SPEED]

# 表の列 (見出し, statMultipliers の添字)
MULT_COLUMNS = [
    ("野生Lv", IDX_LEVEL_WILD),
    ("テイムLv", IDX_LEVEL_DOM),
    ("テイム加算", IDX_TAMING_ADD),
    ("テイム乗算", IDX_TAMING_MULT),
]

# 添字 → 列見出し (MULT_COLUMNS の並びとは別物なので引き直す)
COLUMN_TITLE = {idx: title for title, idx in MULT_COLUMNS}

SHORT_JA = {ark.HEALTH: "体力", ark.STAMINA: "スタミナ", ark.OXYGEN: "酸素量",
            ark.FOOD: "食料", ark.WEIGHT: "重量", ark.MELEE: "近接攻撃力",
            ark.SPEED: "移動速度"}


class SettingsPage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.current = None          # 編集中のプロファイル名
        self.sm = ServerMultipliers.official("asa")
        self.cells = {}              # (stat, idx) -> StringVar
        self.scalars = {}            # 属性名 -> StringVar
        self._build()
        self.reload()

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        tk.Label(self, text="設定", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(self, text="サーバーごとの倍率を登録します。"
                            "ここが合っていないとステータスの逆算がずれます。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small")).pack(
            anchor="w", padx=16)

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=(10, 14))

        # 左: プロファイル一覧
        left = tk.Frame(body, bg=theme.CARD, width=200)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="サーバー", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=12, pady=(10, 4))
        self.listbox = tk.Listbox(left, bg=theme.CARD, fg=theme.INK, bd=0,
                                  highlightthickness=0, activestyle="none",
                                  selectbackground=theme.PINK,
                                  selectforeground=theme.ON_ACCENT,
                                  font=theme.F.get("ui"))
        self.listbox.pack(fill="both", expand=True, padx=8)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_select())
        btns = tk.Frame(left, bg=theme.CARD)
        btns.pack(fill="x", padx=8, pady=8)
        theme.RoundButton(btns, "新規", self._new, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=2)
        theme.RoundButton(btns, "使う", self._use, kind="primary",
                          bg=theme.CARD).pack(side="left", padx=2)
        theme.RoundButton(btns, "削除", self._delete, kind="danger",
                          bg=theme.CARD).pack(side="left", padx=2)

        # 右
        right = tk.Frame(body, bg=theme.BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        src = theme.Card(right, bg=theme.BG)
        src.pack(fill="x")
        sb = src.body
        tk.Label(sb, text="倍率の取り込み", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w")
        r1 = tk.Frame(sb, bg=theme.CARD)
        r1.pack(fill="x", pady=(6, 2))
        theme.RoundButton(r1, "自サーバーから読み込む", self._from_local,
                          kind="primary", bg=theme.CARD).pack(side="left", padx=(0, 4))
        theme.RoundButton(r1, "ini ファイルを読み込む", self._from_ini, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)
        theme.RoundButton(r1, "Export Gun の倍率ファイル", self._from_gun,
                          kind="soft", bg=theme.CARD).pack(side="left", padx=4)
        theme.RoundButton(r1, "公式サーバー相当", self._official, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)
        theme.RoundButton(r1, "すべて 1.0 倍", self._vanilla, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)

        cur = theme.Card(right, bg=theme.BG)
        cur.pack(fill="both", expand=True, pady=(8, 0))
        cb = cur.body
        headrow = tk.Frame(cb, bg=theme.CARD)
        headrow.pack(fill="x")
        self.title_label = tk.Label(headrow, text="", bg=theme.CARD, fg=theme.INK,
                                    font=theme.F.get("cute_b"))
        self.title_label.pack(side="left")
        theme.RoundButton(headrow, "保存", self._save, kind="primary",
                          bg=theme.CARD).pack(side="right")
        tk.Label(headrow, text="値は直接書き換えられます", bg=theme.CARD,
                 fg=theme.INK_SUB, font=theme.F.get("small")).pack(side="right",
                                                                   padx=8)

        # --- 倍率の表 (書き換え可) ---
        grid = tk.Frame(cb, bg=theme.CARD)
        grid.pack(fill="x", pady=(8, 4))
        tk.Label(grid, text="ステータスごとの倍率", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        for col, (title, _idx) in enumerate(MULT_COLUMNS, 1):
            tk.Label(grid, text=title, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small")).grid(row=0, column=col, padx=4)
        for row, s in enumerate(SHOW_STATS, 1):
            tk.Label(grid, text=SHORT_JA.get(s, ark.NAMES_JA[s]), bg=theme.CARD,
                     fg=theme.INK, font=theme.F.get("ui"), width=10,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=1)
            for col, (_title, idx) in enumerate(MULT_COLUMNS, 1):
                var = tk.StringVar()
                self.cells[(s, idx)] = var
                e = tk.Entry(grid, textvariable=var, width=8, relief="flat", bd=0,
                             bg=theme.FIELD, fg=theme.INK, justify="right",
                             insertbackground=theme.PINK_DK,
                             font=theme.F.get("ui"), highlightthickness=1,
                             highlightbackground=theme.LINE,
                             highlightcolor=theme.PINK)
                e.grid(row=row, column=col, padx=4, pady=1, ipady=2)

        tk.Label(cb, text="逆算に効くのは上の表だけ。下は交配の速さ (参考)。",
                 bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", pady=(6, 2))

        misc_grid = tk.Frame(cb, bg=theme.CARD)
        misc_grid.pack(fill="x")
        scalar_fields = [
            ("imprint_stat_scale", "刷り込みステータス倍率"),
            ("imprint_amount", "刷り込み量倍率"),
            ("egg_hatch_speed", "孵化速度"),
            ("baby_mature_speed", "成長速度"),
        ]
        for i, (attr, label_text) in enumerate(scalar_fields):
            tk.Label(misc_grid, text=label_text, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small"), anchor="w").grid(
                row=i // 2, column=(i % 2) * 2, sticky="w", padx=(0, 6), pady=1)
            var = tk.StringVar()
            self.scalars[attr] = var
            tk.Entry(misc_grid, textvariable=var, width=8, relief="flat", bd=0,
                     bg=theme.FIELD, fg=theme.INK, justify="right",
                     insertbackground=theme.PINK_DK, font=theme.F.get("ui"),
                     highlightthickness=1, highlightbackground=theme.LINE,
                     highlightcolor=theme.PINK).grid(
                row=i // 2, column=(i % 2) * 2 + 1, padx=(0, 18), pady=1, ipady=2)

        flags = tk.Frame(cb, bg=theme.CARD)
        flags.pack(fill="x", pady=(6, 0))
        self.single = tk.BooleanVar(value=False)
        self.speed_level = tk.BooleanVar(value=False)
        for text, var in (("シングルプレイ設定 (bUseSingleplayerSettings)", self.single),
                          ("移動速度を強化できる", self.speed_level)):
            tk.Checkbutton(flags, text=text, variable=var, bg=theme.CARD,
                           fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.CARD, font=theme.F.get("small"),
                           bd=0, highlightthickness=0).pack(side="left", padx=(0, 12))

        self.source_label = tk.Label(cb, text="", bg=theme.CARD, fg=theme.INK_SUB,
                                     font=theme.F.get("small"), anchor="w",
                                     justify="left", wraplength=640)
        self.source_label.pack(fill="x", pady=(6, 0))

        misc = theme.Card(right, bg=theme.BG)
        misc.pack(fill="x", pady=(8, 0))
        mb = misc.body
        row = tk.Frame(mb, bg=theme.CARD)
        row.pack(fill="x")
        tk.Label(row, text="見た目", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(0, 8))
        self.theme_var = tk.StringVar(
            value=self.st.library.get_setting("theme", "modern"))
        for key in ("modern", "cute", "cool"):
            pal = theme.PALETTES.get(key) or {}
            tk.Radiobutton(row, text=pal.get("NAME", key), variable=self.theme_var,
                           value=key, command=self._set_theme, bg=theme.CARD,
                           fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.CARD, font=theme.F.get("small"),
                           bd=0, highlightthickness=0).pack(side="left")
        self.paths_label = tk.Label(mb, text="", bg=theme.CARD, fg=theme.INK_SUB,
                                    font=theme.F.get("small"), justify="left",
                                    anchor="w", wraplength=660)
        self.paths_label.pack(fill="x", pady=(6, 0))

        about = theme.Card(right, bg=theme.BG)
        about.pack(fill="x", pady=(8, 0))
        ab = about.body
        arow = tk.Frame(ab, bg=theme.CARD)
        arow.pack(fill="x")
        tk.Label(arow, text="ARK ライブラリ  v%s" % arklib.__version__,
                 bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(side="left")
        theme.RoundButton(arow, "更新を確認", self._check_update, kind="primary",
                          bg=theme.CARD).pack(side="right")
        theme.RoundButton(arow, "GitHub", self._open_github, kind="soft",
                          bg=theme.CARD).pack(side="right", padx=6)
        theme.RoundButton(arow, "Mod 生物を追加", self._open_mods, kind="soft",
                          bg=theme.CARD).pack(side="right", padx=6)
        tk.Label(ab, text="ステータス計算と種族データは ARKStatsExtractor "
                         "(MIT, (c) 2015 cadon) を元にしています。",
                 bg=theme.CARD, fg=theme.INK_SUB, font=theme.F.get("small"),
                 anchor="w", justify="left", wraplength=660).pack(fill="x",
                                                                  pady=(4, 0))

    # ---- 一覧 ----------------------------------------------------------

    def on_show(self):
        self.reload()

    def reload(self):
        profs = self.st.library.servers()
        self._profiles = profs
        self.listbox.delete(0, "end")
        for p in profs:
            mark = "★ " if p["name"] == self.st.server else "   "
            self.listbox.insert("end", mark + p["name"])
        src = self.st.species_db.source
        asa = sum(1 for x in self.st.species_db.all if x.in_asa)
        self.paths_label.configure(
            text="DB: %s\n種族データ: ASA %d種 (全 %d種) / values %s + ASA %s"
            % (self.st.library.path, asa, len(self.st.species_db),
               src.get("ase_values_version", "?"),
               src.get("asa_values_version", "?")))
        if profs:
            names = [p["name"] for p in profs]
            idx = names.index(self.current) if self.current in names else 0
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)
            self._load_profile(profs[idx])
        else:
            self.current = None
            self.title_label.configure(
                text="サーバーが未登録です → 「新規」から作ってください")
            self._render()

    def _on_select(self):
        sel = self.listbox.curselection()
        if sel:
            self._load_profile(self._profiles[sel[0]])

    def _load_profile(self, prof):
        self.current = prof["name"]
        try:
            self.sm = ServerMultipliers.from_dict(prof["multipliers"])
        except Exception:
            self.sm = ServerMultipliers.official("asa")
        self.title_label.configure(
            text="%s%s" % (prof["name"],
                           "  (いま使っています)" if prof["name"] == self.st.server else ""))
        self._render(prof.get("ini_paths"))

    # ---- 表の中身 ------------------------------------------------------

    def _render(self, ini_paths=None):
        """self.sm の内容を入力欄に流し込む。"""
        for (s, idx), var in self.cells.items():
            var.set(_fmt(self.sm.stat[s][idx]))
        for attr, var in self.scalars.items():
            var.set(_fmt(getattr(self.sm, attr, 1.0)))
        self.single.set(bool(self.sm.single_player_settings))
        self.speed_level.set(bool(self.sm.allow_speed_leveling))
        if ini_paths:
            self.source_label.configure(text="読み込み元: " + " / ".join(ini_paths))
        else:
            self.source_label.configure(text="")

    def _collect(self):
        """入力欄の内容を self.sm に取り込む。おかしい値があれば知らせる。"""
        bad = []
        for (s, idx), var in self.cells.items():
            try:
                self.sm.stat[s][idx] = float(var.get())
            except ValueError:
                bad.append("%s の %s" % (SHORT_JA.get(s, ark.NAMES_JA[s]),
                                        COLUMN_TITLE.get(idx, "?")))
        for attr, var in self.scalars.items():
            try:
                setattr(self.sm, attr, float(var.get()))
            except ValueError:
                bad.append(attr)
        self.sm.single_player_settings = bool(self.single.get())
        self.sm.allow_speed_leveling = bool(self.speed_level.get())
        return bad

    # ---- 倍率の取り込み ------------------------------------------------

    def _from_local(self):
        found = paths.local_server_configs()
        if not found:
            messagebox.showinfo(
                "ARK ライブラリ",
                "このPCのサーバー設定が見つかりませんでした。\n"
                "「ini ファイルを選ぶ」から指定するか、表を直接書き換えてください。",
                parent=self)
            return
        _LocalServerDialog(self, found, self._apply_ini)

    def _apply_ini(self, name, ini_files):
        files = [f for f in ini_files if f]
        try:
            sm = ServerMultipliers.from_ini(*files)
        except Exception as e:
            messagebox.showerror("ARK ライブラリ", "読み込みに失敗しました: %s" % e,
                                 parent=self)
            return
        self.sm = sm
        self.current = name or self.current
        self.title_label.configure(text="%s (未保存)" % (self.current or "新しい設定"))
        self._render(files)

    def _from_ini(self):
        files = filedialog.askopenfilenames(
            parent=self, title="Game.ini / GameUserSettings.ini",
            filetypes=[("ini", "*.ini"), ("すべて", "*.*")])
        if files:
            self._apply_ini(None, list(files))

    def _from_gun(self):
        f = filedialog.askopenfilename(
            parent=self, title="Export Gun のサーバー倍率ファイル",
            filetypes=[("Export Gun", "*.sav *.json"), ("すべて", "*.*")])
        if not f:
            return
        try:
            sm, session = export_gun.server_multipliers_from_file(f)
        except Exception as e:
            messagebox.showerror("ARK ライブラリ", "読み込みに失敗しました: %s" % e,
                                 parent=self)
            return
        if sm is None:
            messagebox.showwarning("ARK ライブラリ",
                                   "サーバー倍率のファイルではないようです。", parent=self)
            return
        self.sm = sm
        if session and not self.current:
            self.current = session
        self.title_label.configure(
            text="%s (未保存)" % (self.current or session or "新しい設定"))
        self._render([f])

    def _official(self):
        self.sm = ServerMultipliers.official("asa")
        self._render()

    def _vanilla(self):
        self.sm = ServerMultipliers()
        self._render()

    # ---- 保存 ----------------------------------------------------------

    def _new(self):
        name = simpledialog.askstring("新しいサーバー", "名前を入れてください:",
                                      parent=self)
        if not name:
            return
        self.current = name.strip()
        self.sm = ServerMultipliers.official("asa")
        self.st.library.save_server(self.current, self.sm.to_dict(), [],
                                    is_default=not self._profiles)
        self.reload()

    def _save(self):
        if not self.current:
            self._new()
            return
        bad = self._collect()
        if bad:
            messagebox.showwarning("ARK ライブラリ",
                                   "数字として読めない欄があります:\n" + "\n".join(bad),
                                   parent=self)
            return
        self.st.library.save_server(self.current, self.sm.to_dict(), [])
        if self.st.server == self.current:
            self.st.use_server(self.current)
        self.reload()
        self.app.reload_pages()
        messagebox.showinfo("ARK ライブラリ", "保存しました。", parent=self)

    def _use(self):
        if not self.current:
            return
        if self._collect():
            messagebox.showwarning("ARK ライブラリ",
                                   "数字として読めない欄があります。", parent=self)
            return
        self.st.library.save_server(self.current, self.sm.to_dict(), [],
                                    is_default=True)
        self.st.use_server(self.current)
        self.reload()
        self.app.reload_pages()
        self.app.refresh_status()

    def _delete(self):
        if not self.current:
            return
        if not messagebox.askyesno("削除の確認",
                                   "%s を削除しますか？" % self.current, parent=self):
            return
        self.st.library.delete_server(self.current)
        self.current = None
        self.reload()

    def _set_theme(self):
        self.app.set_theme(self.theme_var.get())

    # ---- 更新 ----------------------------------------------------------

    def _check_update(self):
        from .update_dialog import check_and_offer
        check_and_offer(self, arklib.__version__)

    def _open_mods(self):
        from .mods_dialog import ModsDialog
        ModsDialog(self, self.app)

    def _open_github(self):
        import webbrowser

        from arklib import updater
        webbrowser.open("https://github.com/" + updater.REPO)


def _fmt(v):
    """1.0 は "1"、0.44 は "0.44" のように短く見せる。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "1"
    if f == int(f):
        return str(int(f))
    return ("%.6f" % f).rstrip("0").rstrip(".")


class _LocalServerDialog(tk.Toplevel):
    """このPCで動いているサーバーから選ぶ。"""

    def __init__(self, master, found, on_pick):
        tk.Toplevel.__init__(self, master, bg=theme.BG)
        self.title("このPCのサーバー")
        self.transient(master)
        self.found = found
        self.on_pick = on_pick
        tk.Label(self, text="設定を読み込むサーバーを選んでください",
                 bg=theme.BG, fg=theme.INK, font=theme.F.get("cute_b")).pack(
            padx=18, pady=(14, 8))
        self.lb = tk.Listbox(self, bg=theme.CARD, fg=theme.INK, bd=0,
                             highlightthickness=0, width=46,
                             height=min(12, len(found)),
                             selectbackground=theme.PINK,
                             selectforeground=theme.ON_ACCENT,
                             font=theme.F.get("ui"))
        self.lb.pack(padx=18, fill="both", expand=True)
        for name, game_ini, gus in found:
            marks = []
            if game_ini:
                marks.append("Game.ini")
            if gus:
                marks.append("GameUserSettings.ini")
            self.lb.insert("end", " %s  (%s)" % (name, " + ".join(marks)))
        self.lb.selection_set(0)
        box = tk.Frame(self, bg=theme.BG)
        box.pack(pady=12)
        theme.RoundButton(box, "読み込む", self._ok, kind="primary",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "キャンセル", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)
        self.grab_set()

    def _ok(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name, game_ini, gus = self.found[sel[0]]
        self.destroy()
        self.on_pick(name, [game_ini, gus])
