# -*- coding: utf-8 -*-
"""アプリのアイコン。

ふわふわタイマーは「子午線」、こちらは **ステータスの棒グラフ**。
右肩上がりの 3 本の棒を丸で囲んだだけの形にしてある。16px まで小さくしても
「丸の中に階段」と分かるので、タスクバーで見分けが付く。

外部ライブラリは使わない (Tk の PhotoImage に 1 ピクセルずつ置く)。
"""
import tkinter as tk

from . import theme


def make_icon(size=64):
    img = tk.PhotoImage(width=size, height=size)
    c = (size - 1) / 2.0
    r = c - 0.5

    base = theme.PINK
    light = theme.ON_ACCENT

    # 棒グラフ: 3 本、右へ行くほど高い
    bar_w = size * 0.16
    gap = size * 0.08
    total = bar_w * 3 + gap * 2
    left = c - total / 2.0
    bottom = size * 0.76
    heights = (size * 0.26, size * 0.40, size * 0.54)

    rows, holes = [], []
    for y in range(size):
        row = []
        for x in range(size):
            dx, dy = x - c, y - c
            if (dx * dx + dy * dy) ** 0.5 > r:
                row.append(theme.BG)
                holes.append((x, y))
                continue
            color = base
            for i, h in enumerate(heights):
                x0 = left + i * (bar_w + gap)
                if x0 <= x < x0 + bar_w and bottom - h <= y <= bottom:
                    color = light
                    break
            row.append(color)
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    for x, y in holes:
        img.transparency_set(x, y, True)
    return img
