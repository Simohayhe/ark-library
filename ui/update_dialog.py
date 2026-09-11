# -*- coding: utf-8 -*-
"""「更新を確認」ボタンの中身。

GitHub のリリースを見に行って、新しければ更新内容を出し、押されたら
落として入れ替える。

通信は別スレッドでやるが、**tkinter を別スレッドから触ってはいけない**
(after() を呼ぶだけでも "main thread is not in main loop" で落ちることがある)。
そこでスレッドは結果を箱に置くだけにして、画面側が after() で定期的に
覗きに行く形にしている。
"""
import threading
import tkinter as tk
import webbrowser

from arklib import updater

from . import theme

POLL_MS = 120


def check_and_offer(parent, current_version):
    """更新を確認して、あればダイアログを出す。ボタンから呼ぶ。"""
    return _UpdateDialog(parent, current_version)


class _UpdateDialog(tk.Toplevel):
    def __init__(self, parent, current_version):
        tk.Toplevel.__init__(self, parent, bg=theme.BG)
        self.title("更新の確認")
        self.transient(parent)
        self.resizable(False, False)
        self.current = current_version
        self.info = None
        self.asset = None

        # スレッドとやりとりする箱。触るのは「置く側」と「取る側」だけ
        self._lock = threading.Lock()
        self._result = None          # ("checked", info) / ("downloaded", path) / ("error", text)
        self._progress = None        # (落とした量, 全体)
        self._alive = True

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
        self._page_btn = theme.RoundButton(box, "リリースページ", self._open_page,
                                           kind="soft", bg=theme.BG)
        self._page_btn.pack(side="left", padx=4)
        theme.RoundButton(box, "閉じる", self.destroy, kind="ghost",
                          bg=theme.BG).pack(side="left", padx=4)

        self.grab_set()
        self._start(self._check_worker)

    # ---- スレッドと箱 --------------------------------------------------

    def _start(self, worker):
        threading.Thread(target=worker, daemon=True).start()
        self.after(POLL_MS, self._poll)

    def _put(self, kind, value):
        with self._lock:
            self._result = (kind, value)

    def _take(self):
        with self._lock:
            got, self._result = self._result, None
        return got

    def _poll(self):
        if not self._alive:
            return
        with self._lock:
            prog = self._progress
        if prog:
            got, total = prog
            if total:
                self.progress.set(got / float(total))
        got = self._take()
        if got is None:
            self.after(POLL_MS, self._poll)
            return
        kind, value = got
        if kind == "error":
            self._say("うまくいきませんでした", value)
        elif kind == "checked":
            self._checked(value)
        elif kind == "downloaded":
            self._apply(value)

    # ---- 確認 ----------------------------------------------------------

    def _check_worker(self):
        try:
            self._put("checked", updater.check())
        except Exception as e:
            self._put("error", str(e))

    def _checked(self, info):
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
        # RoundButton は Canvas なので lift() は使えない (Canvas の lift と衝突する)。
        # before= で「リリースページ」の左に置く
        self.ok_btn.pack(side="left", padx=4, before=self._page_btn)

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
        self._start(self._download_worker)

    def _download_worker(self):
        try:
            path = updater.download(self.asset, on_progress=self._on_progress)
        except Exception as e:
            self._put("error", "落とせませんでした: %s" % e)
            return
        self._put("downloaded", path)

    def _on_progress(self, got, total):
        """別スレッドから呼ばれる。箱に置くだけ (画面は触らない)。"""
        with self._lock:
            self._progress = (got, total)

    def _apply(self, path):
        self.progress.set(1.0)
        self.head.configure(text="入れ替えています…")
        self.update_idletasks()
        ok, why = updater.apply(path)
        if not ok:
            self._say("入れ替えられませんでした", why)
            return
        # 入れ替え用のバッチがこのプロセスの終了を待っているので、素直に閉じる
        self.after(300, self._quit_app)

    def _quit_app(self):
        self._alive = False
        try:
            self.master.winfo_toplevel().destroy()
        except Exception:
            pass

    def _open_page(self):
        url = (self.info or {}).get("url") or updater.RELEASES_PAGE
        webbrowser.open(url)

    def destroy(self):
        self._alive = False
        tk.Toplevel.destroy(self)
