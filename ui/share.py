# -*- coding: utf-8 -*-
"""共有 (同期) の面倒を見る係。

設定の出し入れと、サーバー / クライアント / 外に出す道具の起動停止をまとめる。
**別スレッドから Tk を触らない**のがここの肝。同期スレッドは自分の DB に
書くだけで、画面の作り直しはメインスレッドの見張り (``_pump``) がやる。
"""
import queue
import time

from arklib import sync, tunnel

MODE_OFF = "off"
MODE_SERVER = "server"
MODE_CLIENT = "client"

# 外からどう届かせるか
OPEN_LAN = "lan"              # 家の中だけ
OPEN_CLOUDFLARE = "cf"        # Cloudflare トンネル (ルーターをいじらない)
OPEN_UPNP = "upnp"            # ルーターに自動で穴を開けてもらう

OPEN_JA = {
    OPEN_LAN: "家の中だけ",
    OPEN_CLOUDFLARE: "Cloudflare トンネル",
    OPEN_UPNP: "UPnP でポートを開ける",
}

PUMP_MS = 700


class Share(object):
    def __init__(self, app):
        self.app = app
        self.st = app.state_obj
        lib = self.st.library
        self.mode = lib.get_setting("share_mode", MODE_OFF) or MODE_OFF
        self.port = int(lib.get_setting("share_port", sync.DEFAULT_PORT)
                        or sync.DEFAULT_PORT)
        self.url = lib.get_setting("share_url", "") or ""
        self.interval = float(lib.get_setting("share_interval",
                                              sync.DEFAULT_INTERVAL)
                              or sync.DEFAULT_INTERVAL)
        self.opening = lib.get_setting("share_open", OPEN_LAN) or OPEN_LAN
        self.tokens = self._load_tokens()
        # つなぎに行くときに使う合言葉 (相手から貰ったもの)
        self.token = lib.get_setting("share_token", "") or ""

        self.server = None
        self.client = None
        self.tunnel = None
        self.upnp = None
        self.public_url = ""
        self.open_error = ""
        self.last_error = ""
        self.last_sync = None
        self._events = queue.Queue()
        self._pumping = False

    # ---- 合言葉 --------------------------------------------------------

    def _load_tokens(self):
        got = self.st.library.get_setting("share_tokens", None)
        if got:
            return list(got)
        # 昔の「合言葉ひとつ」からの引き継ぎ
        old = self.st.library.get_setting("share_token", "") or ""
        if old:
            entry = {"token": old, "role": sync.ROLE_ADMIN, "name": "自分のPC",
                     "created_at": time.time()}
            self.st.library.set_setting("share_tokens", [entry])
            return [entry]
        return []

    def save_tokens(self):
        self.st.library.set_setting("share_tokens", self.tokens)

    def issue(self, role=sync.ROLE_ADMIN, name=""):
        entry = sync.new_entry(role, name or ("管理者" if role == sync.ROLE_ADMIN
                                              else "メンバー"))
        self.tokens.append(entry)
        self.save_tokens()
        return entry

    def revoke(self, token):
        self.tokens = [t for t in self.tokens if t.get("token") != token]
        self.save_tokens()

    def admin_token(self):
        for t in self.tokens:
            if t.get("role") == sync.ROLE_ADMIN:
                return t.get("token", "")
        return ""

    # ---- 設定 ----------------------------------------------------------

    def configure(self, mode=None, port=None, token=None, url=None,
                  interval=None, opening=None):
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
        if opening is not None:
            self.opening = opening
            lib.set_setting("share_open", opening)

    # ---- 起動 / 停止 ---------------------------------------------------

    def start(self):
        """設定どおりに動かす。戻り値は (うまくいったか, ひとこと)。"""
        self.stop()
        if self.mode == MODE_SERVER:
            if not self.tokens:
                self.issue(sync.ROLE_ADMIN, "自分のPC")
            self.server = sync.SyncServer(
                self.st.library.path, port=self.port, tokens=self.tokens,
                on_change=lambda counts: self._events.put(("server", counts)))
            if not self.server.start():
                msg = self.server.error or "共有元にできませんでした"
                self.last_error = msg
                self.server = None
                return False, msg
            ok, note = self._open_outside()
            self._start_pump()
            return ok, note
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

    def _open_outside(self):
        """外から届くようにする。"""
        self.public_url = ""
        self.open_error = ""
        if self.opening == OPEN_CLOUDFLARE:
            self.tunnel = tunnel.CloudflareTunnel(
                self.port,
                on_url=lambda u: self._events.put(("tunnel", u)))
            if not self.tunnel.start():
                self.open_error = self.tunnel.error
                self.tunnel = None
                return False, "トンネルを開けませんでした"
            return True, "トンネルを開いています… (URL が出るまで少し待ちます)"
        if self.opening == OPEN_UPNP:
            self.upnp = tunnel.UpnpMapping(self.port, "ARK Library")
            if not self.upnp.start():
                self.open_error = self.upnp.error
                self.upnp = None
                return False, "ルーターに穴を開けられませんでした"
            self.public_url = self.upnp.url
            return True, "ルーターに穴を開けました"
        return True, "家の中だけに配っています"

    def restart(self):
        return self.start()

    def stop(self):
        if self.server is not None:
            self.server.stop()
            self.server = None
        if self.client is not None:
            self.client.stop()
            self.client = None
        if self.tunnel is not None:
            self.tunnel.stop()
            self.tunnel = None
        if self.upnp is not None:
            self.upnp.stop()
            self.upnp = None
        self.public_url = ""

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

    # ---- 配る先 --------------------------------------------------------

    def addresses(self):
        """友達 / もう 1 台に教えるアドレス。"""
        out = []
        if self.public_url:
            out.append(self.public_url)
        if self.tunnel is not None and self.tunnel.url:
            out.append(self.tunnel.url)
        for a in sync.local_addresses():
            out.append("http://%s:%d" % (a, self.port))
        seen, uniq = set(), []
        for a in out:
            if a not in seen:
                seen.add(a)
                uniq.append(a)
        return uniq

    # ---- 画面の作り直し ------------------------------------------------

    def _start_pump(self):
        if self._pumping:
            return
        self._pumping = True
        self.app.after(PUMP_MS, self._pump)

    def _pump(self):
        """よそのスレッドからの知らせをメインスレッドで受ける。"""
        changed = False
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "tunnel":
                    self.public_url = payload
                    self._refresh_page()
                else:
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

    def _refresh_page(self):
        page = self.app._pages.get("share")
        if page is not None:
            try:
                page.reload()
            except Exception:
                pass

    # ---- 表示 ----------------------------------------------------------

    def describe(self):
        if self.mode == MODE_OFF:
            return "共有していません"
        if self.mode == MODE_SERVER:
            if self.server is None or not self.server.running:
                return "共有元にできていません  %s" % (self.last_error or "")
            parts = ["共有元として動いています (ポート %d)" % self.port]
            if self.opening == OPEN_CLOUDFLARE:
                if self.tunnel is not None and self.tunnel.url:
                    parts.append("トンネル OK")
                elif self.open_error:
                    parts.append("トンネル失敗: %s" % self.open_error.splitlines()[0])
                else:
                    parts.append("トンネルを開いています…")
            elif self.opening == OPEN_UPNP:
                parts.append("ルーターに穴あり" if self.upnp is not None
                             else "ルーター失敗: %s" % (self.open_error or ""))
            if self.server.last_at:
                parts.append("最後のやり取り %s%s"
                             % (_hhmm(self.server.last_at),
                                " (%s)" % self.server.last_who
                                if self.server.last_who else ""))
            else:
                parts.append("まだ誰も来ていません")
            return "  ".join(parts)
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
