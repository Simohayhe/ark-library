# -*- coding: utf-8 -*-
"""見た目の確認用。指定の画面・タブを開いた状態でアプリを起動する。

    python tools/gui_shot.py <db> <page> [tab]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.app import App

db = sys.argv[1]
page = sys.argv[2] if len(sys.argv) > 2 else "library"
tab = sys.argv[3] if len(sys.argv) > 3 else None

app = App(db)
app.show(page)
if tab and hasattr(app._pages[page], "_set_tab"):
    app._pages[page]._set_tab(tab)
app.update()
app.mainloop()
