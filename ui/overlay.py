# -*- coding: utf-8 -*-
"""取り込んだ瞬間に出す、短時間のオーバーレイ。

ゲームの上に重ねて出すので、**絶対にフォーカスを奪ってはいけない**
(奪うと ARK がアクティブでなくなって操作が飛ぶ)。WS_EX_NOACTIVATE と
WS_EX_TRANSPARENT を立てて「見えるだけ・触れない窓」にしている。

    表示 → 既定 5 秒で自動的に消える
    次の取り込みが来たら、前のは即座に消して差し替える

ARK が「フルスクリーン (専用)」だと Windows の仕様上どんな窓も上に出せない。
その場合はゲーム側の表示設定を「ウィンドウ(フルスクリーン)」にしてもらう。
"""
import ctypes
import tkinter as tk

from arklib import ark, records

from . import theme
from .page_library import SHORT_JA

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

# 画面のどこに出すか
POSITIONS = [
    ("top", "上ちゅうおう"),
    ("top-left", "左上"),
    ("top-right", "右上"),
    ("bottom", "下ちゅうおう"),
    ("bottom-left", "左下"),
    ("bottom-right", "右下"),
]

MARGIN = 40


def no_focus(win):
    """浮かべた窓を「見えるだけ」にする。押しても反応せず、焦点も取らない。"""
    try:
        win.update_idletasks()
        u = ctypes.windll.user32
        hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
        get = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
        put = getattr(u, "SetWindowLongPtrW", u.SetWindowLongW)
        put(hwnd, GWL_EXSTYLE,
            get(hwnd, GWL_EXSTYLE) | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    except Exception:
        pass            # Windows 以外なら、ただの窓のままでかまわない


class StatOverlay(object):
    """1 つだけ浮かぶオーバーレイ。show() を呼ぶたびに中身が入れ替わる。"""

    def __init__(self, master, position="top", seconds=5.0, alpha=0.94):
        self.master = master
        self.position = position
        self.seconds = seconds
        self.alpha = alpha
        self.win = None
        self._job = None

    # ---- 出す --------------------------------------------------------

    def show_creature(self, creature, species, record=None, name_text="",
                      copied=False, action=""):
        """取り込めたときの表示。"""
        tone = _tone_for(record)
        win, box = self._open(tone)
        if win is None:
            return

        head = tk.Frame(box, bg=theme.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        title = "%s %s  Lv%d" % (creature.species_name, creature.sex_ja,
                                 creature.level)
        tk.Label(head, text=title, bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("head")).pack(side="left")
        badge = record.label() if record is not None else ""
        if action == "updated":
            badge = badge or "取り込み直しました"
        if badge:
            tk.Label(head, text=badge, bg=theme.CARD, fg=tone,
                     font=theme.F.get("cute_b")).pack(side="left", padx=(14, 0))

        # ステータス。最高記録は色と印で目立たせる
        row = tk.Frame(box, bg=theme.CARD)
        row.pack(fill="x", padx=18, pady=(6, 4))
        stat_list = [s for s in species.displayed_stat_indices()
                     if s != ark.TORPIDITY] if species is not None else []
        for s in stat_list:
            mark = ""
            fg = theme.INK_SUB
            level_fg = theme.INK
            if record is not None:
                state = record.per_stat.get(s, "")
                if state == records.NEW:
                    # 絵文字は環境によって豆腐になるので記号で示す
                    mark, fg, level_fg = "▲", theme.PINK_DK, theme.PINK_DK
                elif state == records.TIE:
                    mark, fg, level_fg = "★", theme.LAV, theme.LAV
            cell = tk.Frame(row, bg=theme.CARD)
            cell.pack(side="left", padx=(0, 16))
            tk.Label(cell, text=SHORT_JA.get(s, ark.NAMES_JA[s]) + mark,
                     bg=theme.CARD, fg=fg,
                     font=theme.F.get("small")).pack(anchor="w")
            text = "%d" % creature.bl(s)
            if creature.levels_mut[s]:
                text += " (変異%d)" % (creature.levels_mut[s] // 2)
            tk.Label(cell, text=text, bg=theme.CARD, fg=level_fg,
                     font=theme.F.get("num_s")).pack(anchor="w")

        # 名前 (コピーしたもの)
        if name_text:
            foot = tk.Frame(box, bg=theme.CARD)
            foot.pack(fill="x", padx=18, pady=(2, 12))
            tk.Label(foot, text=name_text, bg=theme.FIELD, fg=theme.INK,
                     font=theme.F.get("ui_b"), padx=10, pady=4).pack(side="left")
            if copied:
                tk.Label(foot, text="コピー済み  Ctrl+V で貼れます", bg=theme.CARD,
                         fg=theme.INK_SUB,
                         font=theme.F.get("small")).pack(side="left", padx=10)
        else:
            tk.Frame(box, bg=theme.CARD, height=10).pack()

        self._place(win)

    def show_loading(self, filename):
        """取り込み中の仮表示。中身が出来たらそのまま差し替わる。

        逆算に時間がかかることがある (強化レベルを振ったテイム個体など) ので、
        まず「読んでいる」ことだけ先に出す。
        """
        win, box = self._open(theme.LAV)
        if win is None:
            return
        row = tk.Frame(box, bg=theme.CARD)
        row.pack(fill="x", padx=18, pady=(12, 12))
        tk.Label(row, text="読み込み中…", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("head")).pack(side="left")
        tk.Label(row, text=filename, bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=12)
        # 自動で消さない。結果が出たら差し替わる
        self._place(win, auto_hide=False)

    def show_error(self, filename, problems):
        """取り込めなかったときの表示。"""
        win, box = self._open(theme.RED)
        if win is None:
            return
        tk.Label(box, text="取り込めませんでした", bg=theme.CARD, fg=theme.RED,
                 font=theme.F.get("head")).pack(anchor="w", padx=18, pady=(12, 0))
        tk.Label(box, text=filename, bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=18)
        for p in (problems or [])[:3]:
            tk.Label(box, text="・" + p, bg=theme.CARD, fg=theme.INK,
                     font=theme.F.get("ui"), wraplength=560, justify="left").pack(
                anchor="w", padx=18, pady=(4, 0))
        tk.Frame(box, bg=theme.CARD, height=10).pack()
        self._place(win)

    def show_text(self, title, detail="", tone=None):
        """設定画面の「試してみる」用。"""
        win, box = self._open(tone or theme.PINK)
        if win is None:
            return
        tk.Label(box, text=title, bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=18, pady=(12, 0))
        if detail:
            tk.Label(box, text=detail, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("ui")).pack(anchor="w", padx=18)
        tk.Frame(box, bg=theme.CARD, height=12).pack()
        self._place(win)

    # ---- 消す --------------------------------------------------------

    def hide(self):
        if self._job is not None:
            try:
                self.master.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    # ---- 内部 --------------------------------------------------------

    def _open(self, border):
        """前のを消して、空の窓を作る。"""
        self.hide()
        try:
            win = tk.Toplevel(self.master)
            win.withdraw()
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            try:
                win.attributes("-alpha", self.alpha)
            except tk.TclError:
                pass
            box = tk.Frame(win, bg=theme.CARD, highlightthickness=3,
                           highlightbackground=border, highlightcolor=border)
            box.pack(fill="both", expand=True)
            self.win = win
            return win, box
        except tk.TclError:
            self.win = None
            return None, None

    def _place(self, win, auto_hide=True):
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        pos = self.position
        if pos.endswith("left"):
            x = MARGIN
        elif pos.endswith("right"):
            x = sw - w - MARGIN
        else:
            x = max(0, (sw - w) // 2)
        y = (sh - h - MARGIN * 2) if pos.startswith("bottom") else MARGIN
        win.geometry("+%d+%d" % (int(x), int(y)))
        win.deiconify()
        no_focus(win)
        if auto_hide and self.seconds > 0:
            self._job = self.master.after(int(self.seconds * 1000), self.hide)


def _tone_for(record):
    if record is None:
        return theme.LINE
    if record.overall == records.NEW:
        return theme.PINK
    if record.overall == records.TIE:
        return theme.LAV
    if record.first_of_species:
        return theme.MINT
    return theme.LINE
