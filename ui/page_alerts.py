# -*- coding: utf-8 -*-
"""「取り込んだ瞬間」の設定。

    自動取り込み … エクスポートした瞬間にライブラリへ入れる
    名前         … M H47 S24 W37 M26 を組み立ててクリップボードへ
    オーバーレイ … 画面に数秒だけ出す
    音           … 成功 / 失敗 / 自己ベスト更新 / 最高と同じ の 4 種類
"""
import tkinter as tk
from tkinter import filedialog, ttk

from arklib import ark, naming, sounds
from arklib.creature import FEMALE, MALE, Creature

from . import theme
from .overlay import POSITIONS

# 名前に入れられるステータス (この順に並ぶ)
NAMING_ORDER = [ark.HEALTH, ark.STAMINA, ark.OXYGEN, ark.FOOD, ark.WEIGHT,
                ark.MELEE, ark.SPEED]

STAT_LABEL = {ark.HEALTH: "体力", ark.STAMINA: "スタミナ", ark.OXYGEN: "酸素",
              ark.FOOD: "食料", ark.WEIGHT: "重量", ark.MELEE: "近接",
              ark.SPEED: "速度"}

SECONDS_CHOICES = ["2", "3", "5", "8", "10", "15"]

# 見張る間隔 (秒)。既定は 0.4 秒
INTERVAL_CHOICES = ["0.2", "0.3", "0.4", "0.5", "1", "2", "3"]


class AlertsPage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.auto = app.autoimport
        self._loading = True
        self._build()
        self._load()
        self._loading = False

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        tk.Label(self, text="取り込んだ瞬間", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(self, text="ゲーム内でエクスポートしたときに、何をするか。",
                 bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=16)

        cols = tk.Frame(self, bg=theme.BG)
        cols.pack(fill="both", expand=True, padx=16, pady=(8, 14))
        left = tk.Frame(cols, bg=theme.BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(cols, bg=theme.BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # ---- 自動取り込み ----
        card = theme.Card(left, bg=theme.BG)
        card.pack(fill="x")
        b = card.body
        _head(b, "自動取り込み")
        self.auto_on = tk.BooleanVar()
        _check(b, "エクスポートした瞬間にライブラリへ入れる", self.auto_on,
               self._save_auto)
        row = tk.Frame(b, bg=theme.CARD)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="見に行く間隔", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.interval = tk.StringVar()
        box = ttk.Combobox(row, textvariable=self.interval, width=6,
                           state="readonly", style="Cute.TCombobox",
                           values=INTERVAL_CHOICES)
        box.pack(side="left", padx=6)
        box.bind("<<ComboboxSelected>>", lambda _e: self._save_auto())
        tk.Label(row, text="秒  (短いほど名前が早くコピーされます)",
                 bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.folder_label = tk.Label(b, text="", bg=theme.CARD, fg=theme.INK_SUB,
                                     font=theme.F.get("small"), anchor="w",
                                     justify="left", wraplength=420)
        self.folder_label.pack(fill="x", pady=(6, 0))

        # ---- 名前 ----
        card2 = theme.Card(left, bg=theme.BG)
        card2.pack(fill="x", pady=(8, 0))
        b2 = card2.body
        _head(b2, "名前 (ゲームに貼り付ける用)")

        mrow0 = tk.Frame(b2, bg=theme.CARD)
        mrow0.pack(fill="x", pady=(0, 4))
        tk.Label(mrow0, text="作り方", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(0, 6))
        self.name_mode = tk.StringVar()
        self._mode_labels = [label for _k, label, _h in naming.MODES]
        self._mode_keys = [k for k, _l, _h in naming.MODES]
        cb = ttk.Combobox(mrow0, textvariable=self.name_mode, width=14,
                          state="readonly", style="Cute.TCombobox",
                          values=self._mode_labels)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _e: self._save_naming())
        self.mode_hint = tk.Label(mrow0, text="", bg=theme.CARD, fg=theme.INK_SUB,
                                  font=theme.F.get("small"))
        self.mode_hint.pack(side="left", padx=8)

        self.name_copy = tk.BooleanVar()
        _check(b2, "作った名前をクリップボードにコピーする", self.name_copy,
               self._save_naming)
        self.name_sex = tk.BooleanVar()
        _check(b2, "先頭に性別 (M / F / U) を付ける", self.name_sex, self._save_naming)
        self.name_fill = tk.BooleanVar()
        _check(b2, "ゲーム内で名前が付いていない個体は、この名前で登録する",
               self.name_fill, self._save_naming)

        tk.Label(b2, text="入れるステータス", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), anchor="w").pack(fill="x", pady=(6, 0))
        srow = tk.Frame(b2, bg=theme.CARD)
        srow.pack(fill="x")
        self.name_stats = {}
        for i, s in enumerate(NAMING_ORDER):
            v = tk.BooleanVar()
            self.name_stats[s] = v
            tk.Checkbutton(srow, text="%s(%s)" % (STAT_LABEL[s], naming.LETTERS[s]),
                           variable=v, command=self._save_naming, bg=theme.CARD,
                           fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.CARD, font=theme.F.get("small"),
                           bd=0, highlightthickness=0, anchor="w").grid(
                row=i // 4, column=i % 4, sticky="w", padx=(0, 10))

        mrow = tk.Frame(b2, bg=theme.CARD)
        mrow.pack(fill="x", pady=(4, 0))
        tk.Label(mrow, text="変異が乗ったステに付ける印", bg=theme.CARD,
                 fg=theme.INK_SUB, font=theme.F.get("small")).pack(side="left")
        self.name_mark = tk.StringVar()
        e = theme.soft_entry(mrow, textvariable=self.name_mark, width=4,
                             bg=theme.CARD)
        e.pack(side="left", padx=6)
        e.bind("<KeyRelease>", lambda _e: self._save_naming())
        tk.Label(mrow, text="(空なら付けない)", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")

        self.name_preview = tk.Label(b2, text="", bg=theme.FIELD, fg=theme.INK,
                                     font=theme.F.get("ui_b"), padx=10, pady=6,
                                     anchor="w")
        self.name_preview.pack(fill="x", pady=(8, 0))

        # ---- オーバーレイ ----
        card3 = theme.Card(right, bg=theme.BG)
        card3.pack(fill="x")
        b3 = card3.body
        _head(b3, "オーバーレイ")
        self.ov_on = tk.BooleanVar()
        _check(b3, "取り込んだ瞬間に画面へ出す", self.ov_on, self._save_overlay)
        row3 = tk.Frame(b3, bg=theme.CARD)
        row3.pack(fill="x", pady=(4, 0))
        tk.Label(row3, text="消えるまで", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.ov_sec = tk.StringVar()
        sbox = ttk.Combobox(row3, textvariable=self.ov_sec, width=5,
                            state="readonly", style="Cute.TCombobox",
                            values=SECONDS_CHOICES)
        sbox.pack(side="left", padx=6)
        sbox.bind("<<ComboboxSelected>>", lambda _e: self._save_overlay())
        tk.Label(row3, text="秒", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(0, 14))
        tk.Label(row3, text="出る場所", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.ov_pos = tk.StringVar()
        pbox = ttk.Combobox(row3, textvariable=self.ov_pos, width=12,
                            state="readonly", style="Cute.TCombobox",
                            values=[label for _k, label in POSITIONS])
        pbox.pack(side="left", padx=6)
        pbox.bind("<<ComboboxSelected>>", lambda _e: self._save_overlay())
        theme.RoundButton(b3, "出してみる", self._preview_overlay, kind="soft",
                          bg=theme.CARD).pack(anchor="w", pady=(8, 0))
        tk.Label(b3, text="ARK が「フルスクリーン(専用)」だと Windows の仕様で"
                         "上に出せません。「ウィンドウ(フルスクリーン)」にしてください。",
                 bg=theme.CARD, fg=theme.INK_SUB, font=theme.F.get("small"),
                 wraplength=420, justify="left", anchor="w").pack(fill="x",
                                                                  pady=(6, 0))

        # ---- 音 ----
        card4 = theme.Card(right, bg=theme.BG)
        card4.pack(fill="x", pady=(8, 0))
        b4 = card4.body
        _head(b4, "音")
        self.snd_on = tk.BooleanVar()
        _check(b4, "音を鳴らす", self.snd_on, self._save_sound)
        vrow = tk.Frame(b4, bg=theme.CARD)
        vrow.pack(fill="x", pady=(2, 6))
        tk.Label(vrow, text="音量", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left")
        self.volume = tk.DoubleVar(value=0.6)
        ttk.Scale(vrow, from_=0.0, to=1.0, variable=self.volume, length=160,
                  style="Cute.Horizontal.TScale",
                  command=lambda _v: self._save_sound()).pack(side="left", padx=8)
        self.vol_label = tk.Label(vrow, text="", bg=theme.CARD, fg=theme.INK_SUB,
                                  font=theme.F.get("small"))
        self.vol_label.pack(side="left")

        self.sound_vars = {}
        choices = sounds.builtin_choices()
        self._sound_labels = [label for _spec, label in choices]
        self._sound_specs = [spec for spec, _label in choices]
        for key, label_text, _default in sounds.EVENTS:
            row = tk.Frame(b4, bg=theme.CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label_text, bg=theme.CARD, fg=theme.INK,
                     font=theme.F.get("small"), width=14, anchor="w").pack(side="left")
            var = tk.StringVar()
            self.sound_vars[key] = var
            cb = ttk.Combobox(row, textvariable=var, width=18, state="readonly",
                              style="Cute.TCombobox", values=self._sound_labels)
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>",
                    lambda _e, k=key: self._save_sound_spec(k))
            theme.RoundButton(row, "試聴", lambda k=key: self.auto.preview(k),
                              kind="ghost", bg=theme.CARD).pack(side="left", padx=2)
            theme.RoundButton(row, "ファイル", lambda k=key: self._pick_file(k),
                              kind="ghost", bg=theme.CARD).pack(side="left")

        tk.Label(b4, text="「自己ベスト更新」は、これまでライブラリに入れた同じ種族の"
                         "どれよりも高いステータスが出たとき。"
                         "「最高と同じ」は今の最高値に並んだとき。",
                 bg=theme.CARD, fg=theme.INK_SUB, font=theme.F.get("small"),
                 wraplength=420, justify="left", anchor="w").pack(fill="x",
                                                                  pady=(8, 0))

    # ---- 読み書き ------------------------------------------------------

    def on_show(self):
        self._load()

    def reload(self):
        self._load()

    def _load(self):
        self._loading = True
        a = self.auto
        self.auto_on.set(bool(a.get("auto_import")))
        ms = a.get("auto_import_interval") or 400
        self.interval.set(("%g" % (ms / 1000.0)))
        folder = a.folder()
        self.folder_label.configure(
            text=("見張っているフォルダ: " + folder) if folder
            else "フォルダが未設定です。「取り込み」画面で指定してください。")

        self.name_copy.set(bool(a.get("naming_copy")))
        self.name_sex.set(bool(a.get("naming_with_sex")))
        self.name_fill.set(bool(a.get("naming_fill_empty")))
        self.name_mark.set(a.get("naming_mutation_mark") or "")
        mode = a.get("naming_mode") or naming.MODE_ALL
        if mode in self._mode_keys:
            self.name_mode.set(self._mode_labels[self._mode_keys.index(mode)])
        chosen = a.naming_stats()
        for s, var in self.name_stats.items():
            var.set(s in chosen)

        self.ov_on.set(bool(a.get("overlay_enabled")))
        self.ov_sec.set(str(int(float(a.get("overlay_seconds") or 5))))
        pos = a.get("overlay_position") or "top"
        self.ov_pos.set(dict(POSITIONS).get(pos, POSITIONS[0][1]))

        self.snd_on.set(bool(a.get("sound_enabled")))
        self.volume.set(float(a.get("sound_volume") or 0.6))
        for key, _label, _default in sounds.EVENTS:
            spec = a.sound_spec(key)
            self.sound_vars[key].set(sounds.label_of(spec))
        self._loading = False
        self._refresh_preview()
        self.vol_label.configure(text="%d%%" % round(self.volume.get() * 100))

    def _save_auto(self):
        if self._loading:
            return
        self.auto.set("auto_import", bool(self.auto_on.get()))
        try:
            self.auto.set("auto_import_interval",
                          int(float(self.interval.get()) * 1000))
        except ValueError:
            pass
        self.auto.apply_setting()
        self.app.refresh_status()
        page = self.app._pages.get("import")
        if page is not None:
            page.watching.set(bool(self.auto_on.get()))

    def _save_naming(self):
        if self._loading:
            return
        a = self.auto
        a.set("naming_copy", bool(self.name_copy.get()))
        a.set("naming_with_sex", bool(self.name_sex.get()))
        a.set("naming_fill_empty", bool(self.name_fill.get()))
        a.set("naming_mutation_mark", self.name_mark.get()[:2])
        label = self.name_mode.get()
        if label in self._mode_labels:
            key = self._mode_keys[self._mode_labels.index(label)]
            a.set("naming_mode", key)
            self.mode_hint.configure(
                text=dict((k, h) for k, _l, h in naming.MODES).get(key, ""))
        a.set("naming_stats", [s for s in NAMING_ORDER
                               if self.name_stats[s].get()])
        self._refresh_preview()

    def _save_overlay(self):
        if self._loading:
            return
        a = self.auto
        a.set("overlay_enabled", bool(self.ov_on.get()))
        try:
            a.set("overlay_seconds", float(self.ov_sec.get()))
        except ValueError:
            pass
        label_to_key = {label: key for key, label in POSITIONS}
        a.set("overlay_position", label_to_key.get(self.ov_pos.get(), "top"))

    def _save_sound(self):
        if self._loading:
            return
        self.auto.set("sound_enabled", bool(self.snd_on.get()))
        self.auto.set("sound_volume", round(float(self.volume.get()), 2))
        self.vol_label.configure(text="%d%%" % round(self.volume.get() * 100))

    def _save_sound_spec(self, key):
        if self._loading:
            return
        label = self.sound_vars[key].get()
        if label in self._sound_labels:
            self.auto.set_sound_spec(key, self._sound_specs[
                self._sound_labels.index(label)])
            self.auto.preview(key)

    def _pick_file(self, key):
        f = filedialog.askopenfilename(
            parent=self, title="音のファイル",
            filetypes=[("音", "*.wav *.mp3 *.m4a *.ogg"), ("すべて", "*.*")])
        if not f:
            return
        self.auto.set_sound_spec(key, f)
        self.sound_vars[key].set(sounds.label_of(f))
        self.auto.preview(key)

    # ---- 見本 ----------------------------------------------------------

    def _refresh_preview(self):
        cr = _sample_creature()
        stat_list = [s for s in NAMING_ORDER if self.name_stats[s].get()]
        label = self.name_mode.get()
        mode = (self._mode_keys[self._mode_labels.index(label)]
                if label in self._mode_labels else naming.MODE_ALL)
        text = naming.make_name(cr, stat_list or naming.DEFAULT_STATS,
                                bool(self.name_sex.get()),
                                mutation_mark=self.name_mark.get()[:2],
                                mode=mode)
        self.name_preview.configure(text="こうなります:  " + (text or "(何も入れない)"))

    def _preview_overlay(self):
        self._save_overlay()
        from arklib import records
        cr = _sample_creature()
        sp = self.st.species_db.get("Rex")
        check = records.check(cr, [], [ark.HEALTH, ark.STAMINA, ark.WEIGHT,
                                       ark.MELEE])
        check.per_stat[ark.MELEE] = records.NEW
        check.per_stat[ark.HEALTH] = records.TIE
        check.first_of_species = False
        name_text = naming.make_name(
            cr, [s for s in NAMING_ORDER if self.name_stats[s].get()]
            or naming.DEFAULT_STATS, bool(self.name_sex.get()))
        self.auto.overlay.position = self.auto.get("overlay_position")
        self.auto.overlay.seconds = float(self.auto.get("overlay_seconds") or 5)
        self.auto.overlay.show_creature(cr, sp, check, name_text, copied=True)


def _sample_creature():
    """見本の個体。ゼロ狙いと OF の見え方も分かるように、酸素と食料は 0。"""
    cr = Creature(species_name="Rex", sex=MALE, state="bred", level=302)
    for s, lv in ((ark.HEALTH, 47), (ark.STAMINA, 24), (ark.OXYGEN, 0),
                  (ark.FOOD, 0), (ark.WEIGHT, 37), (ark.MELEE, 26)):
        cr.levels_wild[s] = lv
    cr.levels_mut[ark.MELEE] = 4
    cr.mutations_father = 20
    cr.mutations_mother = 3
    return cr


def _head(parent, text):
    tk.Label(parent, text=text, bg=theme.CARD, fg=theme.INK,
             font=theme.F.get("cute_b")).pack(anchor="w", pady=(0, 4))


def _check(parent, text, var, command):
    tk.Checkbutton(parent, text=text, variable=var, command=command,
                   bg=theme.CARD, fg=theme.INK, selectcolor=theme.FIELD,
                   activebackground=theme.CARD, activeforeground=theme.INK,
                   font=theme.F.get("small"), bd=0, highlightthickness=0,
                   anchor="w").pack(fill="x")
