# -*- coding: utf-8 -*-
"""色を選ぶ部品。

ARK の色は 100 種類くらいの「定義色」から選ばれる。領域ごとに野生で出うる
色が決まっている種族もあるので、分かるときはそれを先に出す。
"""
import tkinter as tk

from arklib import colors as arkcolors

from . import theme

CELL = 26


def ink_on(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000.0 > 140 else "#FFFFFF"


class ColorButton(tk.Canvas):
    """いまの色を見せるボタン。押すと ColorDialog が開く。"""

    W, H = 132, 28

    def __init__(self, master, color_id, command, bg=None):
        bg = theme.CARD if bg is None else bg
        tk.Canvas.__init__(self, master, width=self.W, height=self.H, bg=bg,
                           highlightthickness=0, bd=0)
        self.color_id = color_id
        self.command = command
        self.bind("<ButtonRelease-1>", lambda _e: command())
        self.configure(cursor="hand2")
        self._draw()

    def set_color(self, color_id):
        self.color_id = color_id
        self._draw()

    def _draw(self):
        self.delete("all")
        fill = arkcolors.hex_of(self.color_id) or theme.BG_SOFT
        theme.round_rect(self, 1, 1, self.W - 1, self.H - 1, 6, fill=fill,
                         outline=theme.LINE)
        text = arkcolors.label_of(self.color_id)
        fg = ink_on(fill) if self.color_id else theme.INK_SUB
        self.create_text(self.W / 2, self.H / 2, text=text, fill=fg,
                         font=theme.F.get("small"))


class ColorDialog(tk.Toplevel):
    """色を 1 つ選ぶ。選ぶと on_pick(色ID) が呼ばれて閉じる。"""

    def __init__(self, parent, species_bp, region, current, on_pick,
                 title=None):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.on_pick = on_pick
        self.title(title or "色を選ぶ")
        self.transient(parent)
        self.resizable(False, False)

        name = (arkcolors.region_name(species_bp, region)
                if species_bp is not None and region is not None else "色")
        tk.Label(self, text=name, bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w", padx=16,
                                                  pady=(14, 2))

        wild = []
        if species_bp is not None and region is not None:
            wild = [c for c in arkcolors.possible_ids(species_bp, region)
                    if arkcolors.hex_of(c)]
        if wild:
            self._section("この領域に野生で出る色", wild, current)
        rest = [c for c in arkcolors.creature_ids() if c not in wild]
        if rest:
            self._section("そのほかの生物色 (この領域には野生で出ない)", rest,
                          current)
        dyes = arkcolors.dye_ids()
        if dyes:
            self._section("染料色 (ID %d 以降・野生には出ない。変異や"
                          "イベントで付く)" % arkcolors.DYE_FIRST_ID,
                          dyes, current)

        box = tk.Frame(self, bg=theme.BG)
        box.pack(fill="x", padx=16, pady=(6, 14))
        theme.RoundButton(box, "色を指定しない", lambda: self._pick(0),
                          kind="soft", bg=theme.BG).pack(side="left", padx=(0, 6))
        theme.RoundButton(box, "キャンセル", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left")
        self.grab_set()

    def _section(self, title, ids, current):
        tk.Label(self, text=title, bg=theme.BG, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(anchor="w", padx=16, pady=(8, 2))
        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(anchor="w", padx=16)
        for n, cid in enumerate(ids):
            _Swatch(grid, cid, cid == current,
                    lambda c=cid: self._pick(c)).grid(row=n // 14, column=n % 14,
                                                      padx=1, pady=1)

    def _pick(self, color_id):
        self.destroy()
        if self.on_pick:
            self.on_pick(color_id)


class _Swatch(tk.Canvas):
    def __init__(self, master, color_id, selected, command):
        tk.Canvas.__init__(self, master, width=CELL, height=CELL, bg=theme.BG,
                           highlightthickness=0, bd=0)
        self.color_id = color_id
        self.selected = selected
        tip = arkcolors.label_of(color_id)
        self.bind("<ButtonRelease-1>", lambda _e: command())
        self.bind("<Enter>", lambda _e: _tip(self, tip))
        self.bind("<Leave>", lambda _e: _tip(self, None))
        self.configure(cursor="hand2")
        fill = arkcolors.hex_of(color_id) or theme.BG_SOFT
        theme.round_rect(self, 1, 1, CELL - 1, CELL - 1, 4, fill=fill,
                         outline=theme.INK if selected else theme.LINE,
                         width=2 if selected else 1)


_TIP = {}


def _tip(widget, text):
    """色の名前をそっと出す。"""
    win = _TIP.get("win")
    if win is not None:
        try:
            win.destroy()
        except tk.TclError:
            pass
        _TIP["win"] = None
    if not text:
        return
    win = tk.Toplevel(widget)
    win.wm_overrideredirect(True)
    win.configure(bg=theme.INK)
    tk.Label(win, text=text, bg=theme.INK, fg=theme.BG,
             font=theme.F.get("small"), padx=6, pady=2).pack()
    win.wm_geometry("+%d+%d" % (widget.winfo_rootx() + 10,
                                widget.winfo_rooty() - 26))
    _TIP["win"] = win
