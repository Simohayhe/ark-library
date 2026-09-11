# -*- coding: utf-8 -*-
"""「更新を確認」ボタンの中身。

GitHub のリリースを見に行って、新しければ更新内容を出し、押されたら
落として入れ替える。通信と書き込みは別スレッドでやって、画面は
after() で触る (tkinter は別スレッドから触ると落ちるため)。
"""
import threading
import tkinter as tk
import webbrowser

from arklib import updater

from . import theme


def check_and_offer(parent, current_version, on_busy=None):
    """更新を確認して、あればダイアログを出す。ボタンから呼ぶ。"""
    dlg = _UpdateDialog(parent, current_version)
    return dlg


class _UpdateDialog(tk.Toplevel):
    def __init__(self, parent, current_version):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.title("更新の確認")
        self.transient(parent)
        self.resizable(False, False)
        self.current = current_version
        self.info = None
        self.asset = None
        self.downloaded = None
        self._closing = False

        self.head = tk.Label(self, text="確認しています…", bg=theme.BG,
                             fg=theme.INK, font=theme.F.get("cute_b"))
        self.head.pack(anchor="w", padx=20, pady=(16, 2))
        self.sub = tk.Label(self, text="いまのバージョン: v%s" % current_version,
                            bg=theme.BG, fg=theme.INK_SUB,
                            font=theme.F.get("small"))
        self.sub.pack(anchor="w", padx=20)

        self.notes = tk.Text(self, bg=theme.FIELD, fg=theme.INK, bd=0,
                             highlightthickness=0, wrap="word", width=54,
                             height=9, font=theme.F.get("ui"), padx=12, pady=10)
        self.notes.pack(padx=20, pady=(10, 4))
        self.notes.configure(state="disabled")

        self.progress = theme.RoundProgress(self, bg=theme.BG)
        self.progress.pack(fill="x", padx=20, pady=(0, 4))

        box = tk.Frame(self, bg=theme.BG)
        box.pack(padx=20, pady=(6, 16))
        self.ok_btn = theme.RoundButton(box, "更新する", self._do_update,
                                        kind="primary", bg=theme.BG)
        self.ok_btn.pack(side="left", padx=4)
        theme.RoundButton(box, "リリースページ", self._open_page, kind="soft",
                          bg=theme.BG).pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)
        self.ok_btn.pack_forget()

        self.grab_set()
        threading.Thread(target=self._check_worker, daemon=True).start()

    # ---- 確認 ----------------------------------------------------------

    def _check_worker(self):
        info = updater.check()
        self.after(0, lambda: self._checked(info))

    def _checked(self, info):
        if self._closing:
            return
        self.info = info
        if not info.get("ok"):
            self._say("確認できませんでした", info.get("why", ""))
            return
        tag = info.get("tag") or ""
        if not updater.is_newer(tag, self.current):
            self._say("いまのままで最新です",
                      "公開されている最新版: %s" % (tag or "(不明)"))
            return

        kind = updater.install_kind()
        self.asset = updater.pick_asset(info, kind)
        title = "新しい版があります: %s" % tag
        body = info.get("body") or "(更新内容の記載なし)"
        if kind == "source":
            self._say(title, body + "\n\n※ ソースから動いているので、"
                                    "git pull で更新してください")
            return
        if self.asset is None:
            self._say(title, body + "\n\n※ 入れ替えられるファイルが"
                                    "リリースに見当たりません")
            return
        self._say(title, body)
        self.ok_btn.pack(side="left", padx=4)

    def _say(self, head, body):
        self.head.configure(text=head)
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("end", body)
        self.notes.configure(state="disabled")

    # ---- 更新 ----------------------------------------------------------

    def _do_update(self):
        self.ok_btn.pack_forget()
        self.head.configure(text="落としています…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            path = updater.download(self.asset, on_progress=self._on_progress)
        except Exception as e:
            self.after(0, lambda: self._say("落とせませんでした", str(e)))
            return
        self.after(0, lambda: self._apply(path))

    def _on_progress(self, got, total):
        if total:
            self.after(0, lambda: self.progress.set(got / float(total)))

    def _apply(self, path):
        self.head.configure(text="入れ替えています…")
        ok, why = updater.apply(path)
        if not ok:
            self._say("入れ替えられませんでした", why)
            return
        # 入れ替え用のバッチがこのプロセスの終了を待っているので、素直に閉じる
        self.after(200, self._quit_app)

    def _quit_app(self):
        self._closing = True
        try:
            self.master.winfo_toplevel().destroy()
        except Exception:
            pass

    def _open_page(self):
        url = (self.info or {}).get("url") or updater.RELEASES_PAGE
        webbrowser.open(url)

    def destroy(self):
        self._closing = True
        tk.Toplevel.destroy(self)
