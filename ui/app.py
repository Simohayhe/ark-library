# -*- coding: utf-8 -*-
"""アプリ本体 (ウィンドウと画面切り替え)。"""
import os
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import paths
from arklib.library import Library
from arklib.multipliers import ServerMultipliers
from arklib.species import SpeciesDB

from . import theme

APP_TITLE = "ARK ライブラリ"
DEFAULT_THEME = "modern"

NAV = [
    ("library", "ライブラリ", "🦖"),
    ("plan", "交配プラン", "💞"),
    ("import", "取り込み", "📥"),
    ("alerts", "取り込み通知", "🔔"),
    ("settings", "設定", "⚙"),
]


class AppState(object):
    """画面をまたいで使うもの。"""

    def __init__(self, db_path=None):
        self.library = Library(db_path)
        self.species_db = SpeciesDB()
        self.server = self.library.get_setting("current_server", "") or ""
        self.multipliers = ServerMultipliers.official("asa")
        self.game = "asa"
        self._load_server()

    def _load_server(self):
        prof = None
        if self.server:
            prof = next((p for p in self.library.servers() if p["name"] == self.server),
                        None)
        if prof is None:
            prof = self.library.default_server()
        if prof is not None:
            self.server = prof["name"]
            try:
                self.multipliers = ServerMultipliers.from_dict(prof["multipliers"])
            except Exception:
                self.multipliers = ServerMultipliers.official("asa")
        self.apply_multipliers()

    def apply_multipliers(self):
        self.species_db.apply_multipliers(
            self.multipliers.with_single_player_applied(), self.game)

    def use_server(self, name):
        self.server = name or ""
        self.library.set_setting("current_server", self.server)
        self._load_server()

    def server_names(self):
        names = [p["name"] for p in self.library.servers()]
        for n in self.library.servers_in_use():
            if n and n not in names:
                names.append(n)
        return names

    def creatures(self, species_bp=None, include_dead=True):
        if species_bp:
            return self.library.by_species(species_bp, None, include_dead)
        return self.library.all_creatures(include_dead)


class App(tk.Tk):
    def __init__(self, db_path=None):
        tk.Tk.__init__(self)
        self.withdraw()
        self.state_obj = AppState(db_path)
        name = self.state_obj.library.get_setting("theme", DEFAULT_THEME)
        theme.use(name if name in theme.PALETTES else DEFAULT_THEME)
        theme.init(self)

        self.title(APP_TITLE)
        self.configure(bg=theme.BG)
        self.geometry(self.state_obj.library.get_setting("geometry", "1180x740"))
        self.minsize(980, 600)
        try:
            from .appicon import make_icon
            self._icon = make_icon(64)      # 参照を持っておかないと消える
            self.iconphoto(True, self._icon)
        except Exception:
            pass

        self._pages = {}
        self._current = None
        self._build()

        # エクスポートの見張り。取り込み画面を開いていなくても動く
        from .autoimport import AutoImport
        self.autoimport = AutoImport(self)
        self.autoimport.apply_setting()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.deiconify()
        self.show("library")

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        outer = tk.Frame(self, bg=theme.BG)
        outer.pack(fill="both", expand=True)

        # 左のナビ
        nav = tk.Frame(outer, bg=theme.BG_SOFT, width=158)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)

        tk.Label(nav, text="🦖  ARK\nライブラリ", bg=theme.BG_SOFT, fg=theme.INK,
                 font=theme.F.get("head"), justify="left").pack(
            anchor="w", padx=16, pady=(18, 14))

        self._nav_buttons = {}
        for key, label_text, icon in NAV:
            b = _NavButton(nav, "%s  %s" % (icon, label_text),
                           lambda k=key: self.show(k))
            b.pack(fill="x", padx=10, pady=2)
            self._nav_buttons[key] = b

        self.status = tk.Label(nav, text="", bg=theme.BG_SOFT, fg=theme.INK_SUB,
                               font=theme.F.get("small"), justify="left",
                               wraplength=132)
        self.status.pack(side="bottom", anchor="w", padx=14, pady=12)

        # 右の本体
        self.container = tk.Frame(outer, bg=theme.BG)
        self.container.pack(side="left", fill="both", expand=True)
        self.refresh_status()

    def refresh_status(self):
        st = self.state_obj
        self.status.configure(
            text="%d 体 / %d 種\nサーバー: %s"
            % (st.library.count(), len(st.library.species_summary()),
               st.server or "(未設定)"))

    # ---- 画面切り替え --------------------------------------------------

    def show(self, key):
        if key not in self._pages:
            self._pages[key] = self._make_page(key)
        for k, b in self._nav_buttons.items():
            b.set_active(k == key)
        if self._current is not None:
            self._current.pack_forget()
        page = self._pages[key]
        page.pack(fill="both", expand=True)
        self._current = page
        if hasattr(page, "on_show"):
            page.on_show()

    def _make_page(self, key):
        if key == "library":
            from .page_library import LibraryPage
            return LibraryPage(self.container, self)
        if key == "import":
            from .page_import import ImportPage
            return ImportPage(self.container, self)
        if key == "plan":
            from .page_plan import PlanPage
            return PlanPage(self.container, self)
        if key == "alerts":
            from .page_alerts import AlertsPage
            return AlertsPage(self.container, self)
        if key == "settings":
            from .page_settings import SettingsPage
            return SettingsPage(self.container, self)
        raise KeyError(key)

    def reload_pages(self, except_key=None):
        """データが変わったので開いている画面を作り直す。"""
        for k, p in list(self._pages.items()):
            if k == except_key:
                continue
            if hasattr(p, "reload"):
                p.reload()
        self.refresh_status()

    def set_theme(self, name):
        self.state_obj.library.set_setting("theme", name)
        messagebox.showinfo(APP_TITLE,
                            "テーマは次に起動したときから変わります。", parent=self)

    # ---- 終了 ----------------------------------------------------------

    def _on_close(self):
        try:
            self.autoimport.stop()
            self.autoimport.overlay.hide()
        except Exception:
            pass
        try:
            self.state_obj.library.set_setting("geometry", self.winfo_geometry())
            self.state_obj.library.close()
        except Exception:
            pass
        self.destroy()


class _NavButton(tk.Canvas):
    """左ナビの項目。選択中は色が付く。"""

    H = 36

    def __init__(self, master, text, command):
        tk.Canvas.__init__(self, master, height=self.H, bg=theme.BG_SOFT,
                           highlightthickness=0, bd=0)
        self.command = command
        self.text = text
        self.active = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw())
        self.bind("<ButtonRelease-1>", lambda e: command())
        self.configure(cursor="hand2")

    def set_active(self, on):
        self.active = on
        self._draw()

    def _draw(self, hover=False):
        self.delete("all")
        w = max(self.winfo_width(), 1)
        fill = theme.PINK if self.active else (theme.HOVER_SOFT if hover else theme.BG_SOFT)
        fg = theme.ON_ACCENT if self.active else theme.INK
        theme.round_rect(self, 0, 2, w, self.H - 2, min(10, theme.RADIUS),
                         fill=fill, outline="")
        self.create_text(14, self.H / 2, text=self.text, anchor="w", fill=fg,
                         font=theme.F.get("cute"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    page = "library"
    if "--page" in argv:
        i = argv.index("--page")
        if i + 1 < len(argv):
            page = argv[i + 1]
        del argv[i:i + 2]
    db_path = argv[0] if argv else None
    app = App(db_path)
    if page != "library":
        app.show(page)
    app.mainloop()
    return 0
