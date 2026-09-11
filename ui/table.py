# -*- coding: utf-8 -*-
"""一覧表の部品。

ttk.Treeview だと**セル単位の色付けができない**。このアプリでは
「この列の最高値はこの個体」が一目で分かることが肝なので、Canvas に
自前で描いている。行数が増えても重くならないよう、見えている範囲の
行だけ描き直す。

    cols = [Col("name", "名前", 140), Col("hp", "体力", 60, align="e")]
    t = Table(parent, cols, on_select=..., cell_style=...)
    t.set_rows([{"name": "ノワール", "hp": 45, "_obj": creature}, ...])

cell_style(row, col_key) で (背景, 文字色, 太字) を返すとそのセルだけ
色が変わる。None を返せば既定のまま。
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import theme

ROW_H = 26
HEADER_H = 30


class Col(object):
    def __init__(self, key, title, width=80, align="w", sortable=True,
                 tooltip="", sort_key=None, numeric=False):
        self.key = key
        self.title = title
        self.width = width
        self.align = align          # w / e / center
        self.sortable = sortable
        self.tooltip = tooltip
        self.sort_key = sort_key
        self.numeric = numeric


class Table(tk.Frame):
    def __init__(self, master, cols, on_select=None, on_activate=None,
                 cell_style=None, row_style=None, bg=None, min_rows=6,
                 on_header_menu=None):
        bg = theme.CARD if bg is None else bg
        tk.Frame.__init__(self, master, bg=bg)
        self.cols = list(cols)
        self.on_select = on_select
        self.on_activate = on_activate
        self.cell_style = cell_style
        self.row_style = row_style
        self.on_header_menu = on_header_menu
        self.bg = bg

        self.rows = []
        self.sort_key = None
        self.sort_desc = True
        self.selected = None        # 選択行のインデックス
        self.offset = 0             # 縦のスクロール量 (px)
        self.xoffset = 0            # 横のスクロール量 (px)

        self.font = theme.F.get("ui", ("Yu Gothic UI", 10))
        self.font_b = theme.F.get("ui_b", ("Yu Gothic UI", 10, "bold"))
        self.font_h = theme.F.get("small", ("Yu Gothic UI", 9))
        self._fm = tkfont.Font(font=self.font)

        self.head = tk.Canvas(self, height=HEADER_H, bg=theme.BG_SOFT,
                              highlightthickness=0, bd=0)
        self.head.pack(fill="x", side="top")

        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0,
                                height=ROW_H * min_rows)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb = ttk.Scrollbar(body, orient="vertical", style="Cute.Vertical.TScrollbar",
                                command=self._on_scrollbar)
        self.sb.pack(side="right", fill="y")

        self.hsb = ttk.Scrollbar(self, orient="horizontal",
                                 style="Cute.Horizontal.TScrollbar",
                                 command=self._on_hscrollbar)

        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_hwheel)
        self.head.bind("<Shift-MouseWheel>", self._on_hwheel)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.head.bind("<Button-1>", self._on_head_click)
        self.head.bind("<Button-3>", self._on_head_right)
        self.canvas.bind("<Button-3>", self._on_right_click)

    # ---- データ --------------------------------------------------------

    def set_rows(self, rows, keep_sort=True):
        self.rows = list(rows)
        if keep_sort and self.sort_key:
            self._apply_sort()
        self.offset = 0
        self.selected = None
        self._redraw()

    def set_cols(self, cols):
        self.cols = list(cols)
        self._redraw()

    def selected_row(self):
        if self.selected is None or not (0 <= self.selected < len(self.rows)):
            return None
        return self.rows[self.selected]

    def selected_obj(self):
        r = self.selected_row()
        return r.get("_obj") if r else None

    def select_by(self, predicate):
        for i, r in enumerate(self.rows):
            if predicate(r):
                self.selected = i
                self._ensure_visible(i)
                self._redraw()
                if self.on_select:
                    self.on_select(r)
                return True
        return False

    def sort_by(self, key, desc=True):
        self.sort_key = key
        self.sort_desc = desc
        self._apply_sort()
        self._redraw()

    def _apply_sort(self):
        col = next((c for c in self.cols if c.key == self.sort_key), None)
        if col is None:
            return
        getter = col.sort_key or (lambda r: r.get(col.key))

        def key(r):
            v = getter(r)
            if v is None:
                return (1, 0, "")
            if isinstance(v, bool):
                return (0, int(v), "")
            if isinstance(v, (int, float)):
                return (0, v, "")
            return (0, 0, str(v))

        self.rows.sort(key=key, reverse=self.sort_desc)

    # ---- 描画 ----------------------------------------------------------

    def _total_width(self):
        return sum(c.width for c in self.cols)

    def _redraw(self):
        self._draw_header()
        self._draw_rows()
        self._sync_scrollbar()

    def _draw_header(self):
        cv = self.head
        cv.delete("all")
        w = max(cv.winfo_width(), self._total_width())
        cv.create_rectangle(0, 0, w, HEADER_H, fill=theme.BG_SOFT, outline="")
        x = -self.xoffset
        for c in self.cols:
            title = c.title
            if self.sort_key == c.key:
                title += " ▼" if self.sort_desc else " ▲"
            anchor = {"w": "w", "e": "e", "center": "center"}[c.align]
            tx = x + 8 if c.align == "w" else (x + c.width - 8 if c.align == "e"
                                              else x + c.width / 2)
            cv.create_text(tx, HEADER_H / 2, text=title, anchor=anchor,
                           fill=theme.INK_SUB if self.sort_key != c.key else theme.INK,
                           font=self.font_h)
            x += c.width
        cv.create_line(0, HEADER_H - 1, w, HEADER_H - 1, fill=theme.LINE)

    def _draw_rows(self):
        cv = self.canvas
        cv.delete("all")
        h = cv.winfo_height()
        if h <= 1:
            return
        if not self.rows:
            cv.create_text(16, 18, text="データがありません", anchor="w",
                           fill=theme.INK_SUB, font=self.font)
            return

        first = max(0, int(self.offset // ROW_H))
        last = min(len(self.rows), first + int(h // ROW_H) + 2)
        w = max(cv.winfo_width(), self._total_width())

        for i in range(first, last):
            row = self.rows[i]
            y = i * ROW_H - self.offset
            rbg = self.bg
            if i % 2 == 1:
                rbg = theme.BG_SOFT if not theme.dark() else theme._shade(self.bg, 1.12)
            custom = self.row_style(row) if self.row_style else None
            if custom:
                rbg = custom.get("bg", rbg)
            if i == self.selected:
                rbg = theme.HOVER_SOFT
            cv.create_rectangle(0, y, w, y + ROW_H, fill=rbg, outline="")

            x = -self.xoffset
            for c in self.cols:
                if x + c.width < 0 or x > w:
                    x += c.width
                    continue
                val = row.get(c.key)
                text = "" if val is None else (val if isinstance(val, str) else _fmt(val))
                fg = theme.INK
                font = self.font
                style = self.cell_style(row, c.key) if self.cell_style else None
                if style:
                    cbg, cfg, bold = style
                    if cbg:
                        cv.create_rectangle(x + 2, y + 2, x + c.width - 2, y + ROW_H - 2,
                                            fill=cbg, outline="")
                    if cfg:
                        fg = cfg
                    if bold:
                        font = self.font_b
                if custom and custom.get("fg"):
                    fg = custom["fg"]
                anchor = {"w": "w", "e": "e", "center": "center"}[c.align]
                tx = x + 8 if c.align == "w" else (x + c.width - 8 if c.align == "e"
                                                   else x + c.width / 2)
                text = self._clip(text, c.width - 12)
                cv.create_text(tx, y + ROW_H / 2, text=text, anchor=anchor,
                               fill=fg, font=font)
                x += c.width
            cv.create_line(0, y + ROW_H - 1, w, y + ROW_H - 1, fill=theme.LINE)

    def _clip(self, text, px):
        if self._fm.measure(text) <= px:
            return text
        out = text
        while out and self._fm.measure(out + "…") > px:
            out = out[:-1]
        return out + "…"

    # ---- スクロール ----------------------------------------------------

    def _content_h(self):
        return max(1, len(self.rows) * ROW_H)

    def _sync_scrollbar(self):
        self._sync_hscrollbar()
        h = max(1, self.canvas.winfo_height())
        total = self._content_h()
        if total <= h:
            self.offset = 0
            self.sb.set(0, 1)
            return
        self.offset = max(0, min(self.offset, total - h))
        self.sb.set(self.offset / total, (self.offset + h) / total)

    def _sync_hscrollbar(self):
        w = max(1, self.canvas.winfo_width())
        total = self._total_width()
        if total <= w:
            if self.xoffset:
                self.xoffset = 0
            if self.hsb.winfo_ismapped():
                self.hsb.pack_forget()
            return
        if not self.hsb.winfo_ismapped():
            self.hsb.pack(fill="x", side="bottom")
        self.xoffset = max(0, min(self.xoffset, total - w))
        self.hsb.set(self.xoffset / total, (self.xoffset + w) / total)

    def _on_hscrollbar(self, *args):
        w = max(1, self.canvas.winfo_width())
        total = self._total_width()
        if args[0] == "moveto":
            self.xoffset = float(args[1]) * total
        elif args[0] == "scroll":
            step = 40 if args[2] == "units" else w
            self.xoffset += int(args[1]) * step
        self.xoffset = max(0, min(self.xoffset, max(0, total - w)))
        self._draw_header()
        self._draw_rows()
        self._sync_hscrollbar()

    def _on_hwheel(self, e):
        w = max(1, self.canvas.winfo_width())
        total = self._total_width()
        if total <= w:
            return
        self.xoffset -= (e.delta / 120.0) * 60
        self.xoffset = max(0, min(self.xoffset, total - w))
        self._draw_header()
        self._draw_rows()
        self._sync_hscrollbar()

    def _on_scrollbar(self, *args):
        h = max(1, self.canvas.winfo_height())
        total = self._content_h()
        if args[0] == "moveto":
            self.offset = float(args[1]) * total
        elif args[0] == "scroll":
            amount = int(args[1])
            if args[2] == "units":
                self.offset += amount * ROW_H
            else:
                self.offset += amount * h
        self.offset = max(0, min(self.offset, max(0, total - h)))
        self._draw_rows()
        self._sync_scrollbar()

    def _on_wheel(self, e):
        total = self._content_h()
        h = max(1, self.canvas.winfo_height())
        if total <= h:
            return
        self.offset -= (e.delta / 120.0) * ROW_H * 3
        self.offset = max(0, min(self.offset, total - h))
        self._draw_rows()
        self._sync_scrollbar()

    def _ensure_visible(self, index):
        h = max(1, self.canvas.winfo_height())
        top = index * ROW_H
        if top < self.offset:
            self.offset = top
        elif top + ROW_H > self.offset + h:
            self.offset = top + ROW_H - h

    # ---- 操作 ----------------------------------------------------------

    def _row_at(self, y):
        i = int((y + self.offset) // ROW_H)
        return i if 0 <= i < len(self.rows) else None

    def _on_click(self, e):
        i = self._row_at(e.y)
        if i is None:
            return
        self.selected = i
        self._draw_rows()
        if self.on_select:
            self.on_select(self.rows[i])

    def _on_double(self, e):
        i = self._row_at(e.y)
        if i is None:
            return
        self.selected = i
        self._draw_rows()
        if self.on_activate:
            self.on_activate(self.rows[i])

    def _on_right_click(self, e):
        i = self._row_at(e.y)
        if i is not None:
            self.selected = i
            self._draw_rows()
            if self.on_select:
                self.on_select(self.rows[i])

    def _col_at(self, x):
        x += self.xoffset
        acc = 0
        for c in self.cols:
            if acc <= x < acc + c.width:
                return c
            acc += c.width
        return None

    def _on_head_click(self, e):
        c = self._col_at(e.x)
        if c is None or not c.sortable:
            return
        if self.sort_key == c.key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key = c.key
            self.sort_desc = True
        self._apply_sort()
        self.selected = None
        self.offset = 0
        self._redraw()

    def _on_head_right(self, e):
        if self.on_header_menu:
            self.on_header_menu(self._col_at(e.x), e)


def _fmt(v):
    if isinstance(v, float):
        return ("%.1f" % v).rstrip("0").rstrip(".") if abs(v) < 1000 else "%.0f" % v
    return str(v)
