# -*- coding: utf-8 -*-
"""共有 (同期) の面倒を見る係。

設定の出し入れと、サーバー / クライアントの起動停止をまとめる。
**別スレッドから Tk を触らない**のがここの肝。同期スレッドは自分の DB に
書くだけで、画面の作り直しはメインスレッドの見張り (``_pump``) がやる。
"""
import queue
import time

from arklib import sync

MODE_OFF = "off"
MODE_SERVER = "server"
MODE_CLIENT = "client"

PUMP_MS = 700


class Share(object):
    def __init__(self, app):
        self.app = app
        self.st = app.state_obj
        lib = self.st.library
        self.mode = lib.get_setting("share_mode", MODE_OFF) or MODE_OFF
        self.port = int(lib.get_setting("share_port", sync.DEFAULT_PORT)
                        or sync.DEFAULT_PORT)
        self.token = lib.get_setting("share_token", "") or ""
        self.url = lib.get_setting("share_url", "") or ""
        self.interval = float(lib.get_setting("share_interval",
                                              sync.DEFAULT_INTERVAL)
                              or sync.DEFAULT_INTERVAL)
        self.server = None
        self.client = None
        self.last_error = ""
        self.last_sync = None
        self._events = queue.Queue()
        self._pumping = False

    # ---- 設定 ----------------------------------------------------------

    def configure(self, mode=None, port=None, token=None, url=None,
                  interval=None):
        lib = self.st.library
        if mode is not None:
            self.mode = mode
            lib.set_setting("share_mode", mode)
        if port is not None:
            self.port = int(port)
            lib.set_setting("share_port", self.port)
        if token is not None:
            self.token = token
            lib.set_setting("share_token", token)
        if url is not None:
            self.url = url
            lib.set_setting("share_url", url)
        if interval is not None:
            self.interval = float(interval)
            lib.set_setting("share_interval", self.interval)

    # ---- 起動 / 停止 ---------------------------------------------------

    def start(self):
        """設定どおりに動かす。戻り値は (うまくいったか, ひとこと)。"""
        self.stop()
        if self.mode == MODE_SERVER:
            if not self.token:
                self.configure(token=sync.make_token())
            self.server = sync.SyncServer(
                self.st.library.path, self.token, self.port,
                on_change=lambda counts: self._events.put(("server", counts)))
            if not self.server.start():
                msg = self.server.error or "共有元にできませんでした"
                self.last_error = msg
                self.server = None
                return False, msg
            self._start_pump()
            return True, "共有元として動いています"
        if self.mode == MODE_CLIENT:
            if not self.url:
                return False, "共有元のアドレスを入れてください"
            self.client = sync.SyncClient(
                self.st.library.path, self.url, self.token, self.interval,
                on_change=lambda a, b: self._events.put(("client", (a, b))))
            self.client.start()
            self._start_pump()
            return True, "共有元につなぎに行きます"
        return True, "共有していません"

    def restart(self):
        return self.start()

    def stop(self):
        if self.server is not None:
            self.server.stop()
            self.server = None
        if self.client is not None:
            self.client.stop()
            self.client = None

    # ---- いますぐ 1 回 --------------------------------------------------

    def sync_now(self):
        """手で 1 回だけやり取りする。失敗したら文字列を返す。"""
        if self.mode != MODE_CLIENT:
            return "「共有元につなぎに行く」のときだけ使えます。"
        if not self.url:
            return "共有元のアドレスを入れてください。"
        client = self.client or sync.SyncClient(self.st.library.path, self.url,
                                                self.token, self.interval)
        try:
            got = client.sync_once()
        except Exception as e:
            return "やり取りできませんでした。\n\n%s" % e
        self.last_sync = time.time()
        return got

    # ---- 画面の作り直し ------------------------------------------------

    def _start_pump(self):
        if self._pumping:
            return
        self._pumping = True
        self.app.after(PUMP_MS, self._pump)

    def _pump(self):
        """同期スレッドからの知らせをメインスレッドで受ける。"""
        changed = False
        try:
            while True:
                kind, _payload = self._events.get_nowait()
                changed = True
        except queue.Empty:
            pass
        if self.client is not None:
            self.last_error = self.client.error
            self.last_sync = self.client.last_ok
        if changed:
            try:
                self.app.reload_pages()
            except Exception:
                pass
        if self.server is None and self.client is None:
            self._pumping = False
            return
        self.app.after(PUMP_MS, self._pump)

    # ---- 表示 ----------------------------------------------------------

    def describe(self):
        if self.mode == MODE_OFF:
            return "共有していません"
        if self.mode == MODE_SERVER:
            if self.server is None or not self.server.running:
                return "共有元にできていません  %s" % (self.last_error or "")
            last = ("  最後のやり取り %s" % _hhmm(self.server.last_at)
                    if self.server.last_at else "  まだ誰も来ていません")
            return "共有元として動いています (ポート %d)%s" % (self.port, last)
        if self.client is None or not self.client.running:
            return "つないでいません  %s" % (self.last_error or "")
        if self.client.error:
            return "つながりません: %s" % self.client.error
        if self.client.last_ok:
            return ("つながっています  最後のやり取り %s  "
                    "(受け取り %d / 送り出し %d)"
                    % (_hhmm(self.client.last_ok), self.client.pulled,
                       self.client.pushed))
        return "つなぎに行っています…"


def _hhmm(t):
    return time.strftime("%H:%M:%S", time.localtime(t)) if t else "-"
