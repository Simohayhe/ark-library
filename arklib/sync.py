# -*- coding: utf-8 -*-
"""PC どうしでライブラリを共有する。

ゲーム用 PC で取り込んだ個体を、サーバー用 PC からも同じように見たい。
そのために **1 台を共有元 (サーバー) にして、ほかは数秒おきに読み書きする**。

    ゲームPC ──┐
               ├─→ 共有元の PC ←→ ひとつのライブラリ
    サーバPC ──┘

各 PC は**自分のローカル DB を持ったまま**動く。つながらないときも
いつも通り使えて、つながったら差分だけをやり取りする。SQLite のファイルを
ネットワーク越しに直接開くと壊れることがあるので、そうはしない。

突き合わせ方
------------
個体は ``library.sync_key`` (ゲーム内の DinoID) で同じものとみなし、
``updated_at`` が新しい方を採る。個体のデータはほぼ動かない事実なので、
これでまず困らない。消した個体は「消した記録」を配って、向こうから
戻ってこないようにする。

設定は全部は配らない。取り込みフォルダや画面の色はその PC のものなので、
**種族ごとの狙い・名前の付け方・理想個体**だけを共有する。
"""
import hmac
import json
import threading
import time

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse
    from urllib.request import Request, urlopen
    from urllib.error import URLError
except ImportError:                      # Python 2 は想定しない
    raise

from .creature import Creature
from .library import CREATURE_COLUMNS, Library, sync_key

DEFAULT_PORT = 8787
DEFAULT_INTERVAL = 5.0
TOKEN_HEADER = "X-Ark-Token"
PROTOCOL = 1

# 合言葉の種類
ROLE_ADMIN = "admin"      # 読み書きできる (自分の PC・任せる相手)
ROLE_MEMBER = "member"    # 読むだけ (友達に配る用)
ROLE_JA = {ROLE_ADMIN: "管理者 (読み書き可)", ROLE_MEMBER: "メンバー (閲覧のみ)"}

# 共有する設定のあたま。これ以外 (取り込みフォルダ・テーマ・音量など) は
# その PC のものなので配らない
SHARED_SETTING_PREFIXES = ("naming_stats_", "naming_rule_",
                           "plan_goals_", "ideal_")


def shared_setting(key):
    return any(key.startswith(p) for p in SHARED_SETTING_PREFIXES)


# ---- 受け取ったものの覚え書き ------------------------------------------
#
# よそから受け取った行をそのまま送り返すと、2 台で延々とやり取りし続ける。
# 「この行はこの時刻の状態で向こうから貰った」と覚えておいて、こちらで
# 触っていなければ送らない。時計がずれていても効くように、時刻の大小では
# なく**一致**で見る。


def _remember(db, kind, key, at):
    db.execute("INSERT INTO sync_state (kind, key, at) VALUES (?, ?, ?) "
               "ON CONFLICT(kind, key) DO UPDATE SET at = excluded.at",
               (kind, key, float(at or 0)))


def _from_peer(db, kind, key, at):
    row = db.execute("SELECT at FROM sync_state WHERE kind = ? AND key = ?",
                     (kind, key)).fetchone()
    return row is not None and abs(row["at"] - float(at or 0)) < 1e-9


# ---- 差分の取り出しと取り込み ------------------------------------------


def changes_since(library, since=0.0, limit=2000, mine_only=False):
    """since より後に変わったものを集める。

    mine_only=True なら、よそから貰ったまま触っていない行は外す
    (送り返さないため)。共有元が配るときは外してはいけない。3 台目に
    届かなくなるため。
    """
    since = float(since or 0.0)
    db = library.db
    skip = _from_peer if mine_only else (lambda *_a: False)

    creatures = []
    for row in db.execute(
            "SELECT * FROM creatures WHERE updated_at > ? "
            "ORDER BY updated_at LIMIT ?", (since, limit)):
        if skip(db, "creature", sync_key(row), row["updated_at"]):
            continue
        d = dict(row)
        d.pop("uid", None)               # uid は PC ごとに別物
        creatures.append(d)

    settings = []
    for r in db.execute(
            "SELECT key, value, updated_at FROM settings WHERE updated_at > ?",
            (since,)):
        if not shared_setting(r["key"]):
            continue
        if skip(db, "setting", r["key"], r["updated_at"]):
            continue
        settings.append(dict(r))

    servers = []
    for r in db.execute(
            "SELECT name, multipliers, is_default, updated_at FROM servers "
            "WHERE updated_at > ?", (since,)):
        if skip(db, "server", r["name"], r["updated_at"]):
            continue
        servers.append(dict(r))

    deletions = []
    for k, key, t in library.deletions_since(since):
        if skip(db, "del", "%s/%s" % (k, key), t):
            continue
        deletions.append({"kind": k, "key": key, "deleted_at": t})

    return {"protocol": PROTOCOL, "now": time.time(), "creatures": creatures,
            "settings": settings, "servers": servers, "deletions": deletions}


def apply_changes(library, payload):
    """よそから来た差分を取り込む。新しい方を残す。"""
    db = library.db
    counts = {"creatures": 0, "settings": 0, "servers": 0, "deleted": 0}

    # 先に「消した記録」を反映する。あとから同じ個体が来ても弾けるように
    for d in payload.get("deletions") or []:
        kind, key = d.get("kind"), d.get("key")
        when = float(d.get("deleted_at") or 0)
        if not kind or not key:
            continue
        _remember(db, "del", "%s/%s" % (kind, key), when)
        if (library.deleted_at(kind, key) or 0) >= when:
            continue
        library.mark_deleted(kind, key, when)
        if kind == "creature":
            row = _find_by_key(db, key)
            if row is not None and row["updated_at"] <= when:
                db.execute("DELETE FROM creatures WHERE uid = ?", (row["uid"],))
                counts["deleted"] += 1

    for d in payload.get("creatures") or []:
        if _apply_creature(library, d):
            counts["creatures"] += 1

    for d in payload.get("settings") or []:
        key = d.get("key")
        if not key or not shared_setting(key):
            continue
        when = float(d.get("updated_at") or 0)
        _remember(db, "setting", key, when)
        row = db.execute("SELECT updated_at FROM settings WHERE key = ?",
                         (key,)).fetchone()
        if row is not None and (row["updated_at"] or 0) >= when:
            continue
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at", (key, d.get("value"), when))
        counts["settings"] += 1

    for d in payload.get("servers") or []:
        name = d.get("name")
        if not name:
            continue
        when = float(d.get("updated_at") or 0)
        _remember(db, "server", name, when)
        row = db.execute("SELECT updated_at FROM servers WHERE name = ?",
                         (name,)).fetchone()
        if row is not None and (row["updated_at"] or 0) >= when:
            continue
        db.execute(
            "INSERT INTO servers (name, multipliers, ini_paths, is_default, "
            "updated_at) VALUES (?, ?, '[]', ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET multipliers = excluded.multipliers, "
            "updated_at = excluded.updated_at",
            (name, d.get("multipliers"), int(d.get("is_default") or 0), when))
        counts["servers"] += 1

    db.commit()
    return counts


def _find_by_key(db, key):
    if key.startswith("id:"):
        try:
            ark_id = int(key[3:])
        except ValueError:
            return None
        return db.execute("SELECT * FROM creatures WHERE ark_id = ?",
                          (ark_id,)).fetchone()
    parts = key[3:].split("|")
    if len(parts) != 4:
        return None
    bp, name, level, server = parts
    return db.execute(
        "SELECT * FROM creatures WHERE ark_id = 0 AND species_bp = ? "
        "AND name = ? AND level = ? AND server = ?",
        (bp, name, level, server)).fetchone()


def _apply_creature(library, d):
    db = library.db
    key = sync_key(d)
    when = float(d.get("updated_at") or 0)
    _remember(db, "creature", key, when)
    # こちらで消した個体は戻さない
    if (library.deleted_at("creature", key) or 0) >= when:
        return False
    row = _find_by_key(db, key)
    if row is not None and (row["updated_at"] or 0) >= when:
        return False
    cols = [c for c in CREATURE_COLUMNS if c != "uid"]
    values = [d.get(c) for c in cols]
    if row is None:
        db.execute('INSERT INTO creatures (%s) VALUES (%s)'
                   % (", ".join('"%s"' % c for c in cols),
                      ", ".join("?" for _ in cols)), values)
    else:
        db.execute('UPDATE creatures SET %s WHERE uid = ?'
                   % ", ".join('"%s" = ?' % c for c in cols),
                   values + [row["uid"]])
    return True


# ---- 共有元 (サーバー) --------------------------------------------------


class SyncServer(object):
    """共有元。自分の DB を HTTP で配る。

    合言葉 (トークン) が合わないものは弾く。合言葉は 2 種類。

        管理者 (admin)   … 読みも書きもできる。自分のもう 1 台や、任せる相手
        メンバー (member) … 読むだけ。友達に配る用

    友達に配るときは外 (インターネット) に出ることになるので、合言葉なしでは
    動かさない。
    """

    def __init__(self, db_path, token=None, port=DEFAULT_PORT, host="0.0.0.0",
                 on_change=None, tokens=None):
        self.db_path = db_path
        # tokens = [{"token": .., "role": .., "name": ..}, ...]
        # 昔の「合言葉ひとつ」も管理者として通す
        self.tokens = list(tokens or [])
        if token:
            self.tokens.append({"token": token, "role": ROLE_ADMIN,
                                "name": "既定"})
        self.port = int(port or DEFAULT_PORT)
        self.host = host
        self.on_change = on_change
        self.httpd = None
        self.thread = None
        self.error = ""
        self.hits = 0
        self.last_at = None
        self.last_who = ""

    @property
    def token(self):
        """昔ながらの「合言葉ひとつ」として見たときの値。"""
        for t in self.tokens:
            if t.get("role", ROLE_ADMIN) == ROLE_ADMIN:
                return t.get("token") or ""
        return self.tokens[0].get("token") if self.tokens else ""

    def role_of(self, token):
        """合言葉から役割を引く。合わなければ None。"""
        if not self.tokens:
            return ROLE_ADMIN          # 合言葉を決めていなければ素通し
        for t in self.tokens:
            want = t.get("token") or ""
            if want and hmac.compare_digest(want, token or ""):
                return t.get("role", ROLE_ADMIN), t.get("name", "")
        return None

    def start(self):
        if self.httpd is not None:
            return True
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a):
                pass                      # 標準エラーに出さない

            def _role(self):
                got = owner.role_of(self.headers.get(TOKEN_HEADER, ""))
                if got is None:
                    return None, ""
                if isinstance(got, tuple):
                    return got
                return got, ""

            def _send(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlparse(self.path)
                role, who = self._role()
                if url.path == "/ping":
                    return self._send(200, {"app": "ark-library",
                                            "protocol": PROTOCOL,
                                            "needs_token": bool(owner.tokens),
                                            "role": role})
                if role is None:
                    return self._send(403, {"error": "認証に失敗しました"})
                if url.path == "/pull":
                    q = parse_qs(url.query)
                    since = float((q.get("since") or ["0"])[0])
                    lib = Library(owner.db_path)
                    try:
                        out = changes_since(lib, since)
                    finally:
                        lib.close()
                    owner._touch(who or role)
                    return self._send(200, out)
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                role, who = self._role()
                if role is None:
                    return self._send(403, {"error": "認証に失敗しました"})
                if role != ROLE_ADMIN:
                    return self._send(
                        403, {"error": "このキーでは書き込めません "
                                       "(メンバーは閲覧のみ)"})
                if urlparse(self.path).path != "/push":
                    return self._send(404, {"error": "not found"})
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    payload = json.loads(self.rfile.read(n).decode("utf-8"))
                except ValueError:
                    return self._send(400, {"error": "不正なデータです"})
                lib = Library(owner.db_path)
                try:
                    counts = apply_changes(lib, payload)
                finally:
                    lib.close()
                owner._touch(who or role)
                if owner.on_change and any(counts.values()):
                    try:
                        owner.on_change(counts)
                    except Exception:
                        pass
                return self._send(200, {"applied": counts, "now": time.time()})

        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as e:
            self.error = "ポート %d を使えません (%s)" % (self.port, e)
            self.httpd = None
            return False
        self.httpd.daemon_threads = True
        self.error = ""
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.3},
                                       daemon=True)
        self.thread.start()
        return True

    def _touch(self, who=""):
        self.hits += 1
        self.last_at = time.time()
        if who:
            self.last_who = who

    def stop(self):
        if self.httpd is None:
            return
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None
        self.thread = None

    @property
    def running(self):
        return self.httpd is not None


# ---- つなぎに行く側 (クライアント) --------------------------------------


class SyncClient(object):
    """共有元と数秒おきにやり取りする。

    **Tk には一切触らない。** 別スレッドで自分の DB 接続を開いて書き込み、
    変わったことだけを on_change で知らせる (画面の作り直しは呼び出し側が
    メインスレッドでやる)。
    """

    def __init__(self, db_path, url, token="", interval=DEFAULT_INTERVAL,
                 on_change=None, on_status=None):
        self.db_path = db_path
        self.url = (url or "").rstrip("/")
        self.token = token or ""
        self.interval = float(interval or DEFAULT_INTERVAL)
        self.on_change = on_change
        self.on_status = on_status
        self._stop = threading.Event()
        self.thread = None
        self.status = "停止中"
        self.error = ""
        self.last_ok = None
        self.pulled = 0
        self.pushed = 0

    # ---- 出入り口 ------------------------------------------------------

    def start(self):
        if self.thread is not None:
            return
        self._stop.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()
        self.thread = None
        self.status = "停止中"

    @property
    def running(self):
        return self.thread is not None and not self._stop.is_set()

    def sync_once(self, lib=None):
        """1 回ぶんのやり取り。戻り値は (取り込んだ数, 送った数)。

        聞く位置と送る位置は別々に覚える。相手の時計とこちらの時計は
        別物なので、混ぜると取りこぼしたり延々と送り直したりする。
        """
        own = lib is None
        lib = lib or Library(self.db_path)
        try:
            pull_at = float(lib.get_setting("sync_pull_at", 0) or 0)
            push_at = float(lib.get_setting("sync_push_at", 0) or 0)
            here = time.time()

            got = self._get("/pull?since=%r" % pull_at)
            counts = apply_changes(lib, got)
            pulled = sum(counts.values())

            mine = changes_since(lib, push_at, mine_only=True)
            pushed = (len(mine["creatures"]) + len(mine["settings"])
                      + len(mine["servers"]) + len(mine["deletions"]))
            if pushed:
                self._post("/push", mine)

            # 少し戻しておく (書き込みとの行き違いで取りこぼさないように)
            lib.set_setting("sync_pull_at",
                            max(0.0, float(got.get("now") or here) - 1.0))
            lib.set_setting("sync_push_at", max(0.0, here - 1.0))
            self.pulled += pulled
            self.pushed += pushed
            return pulled, pushed
        finally:
            if own:
                lib.close()

    # ---- 中身 ----------------------------------------------------------

    def _loop(self):
        lib = Library(self.db_path)
        try:
            while not self._stop.is_set():
                try:
                    pulled, pushed = self.sync_once(lib)
                    self.error = ""
                    self.last_ok = time.time()
                    self.status = "接続中"
                    if (pulled or pushed) and self.on_change:
                        self.on_change(pulled, pushed)
                except Exception as e:
                    self.error = _friendly(e)
                    self.status = "接続失敗"
                if self.on_status:
                    try:
                        self.on_status(self.status, self.error)
                    except Exception:
                        pass
                self._stop.wait(self.interval)
        finally:
            lib.close()

    def _headers(self):
        h = {"Content-Type": "application/json; charset=utf-8"}
        if self.token:
            h[TOKEN_HEADER] = self.token
        return h

    def _get(self, path):
        req = Request(self.url + path, headers=self._headers())
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(self.url + path, data=body, headers=self._headers())
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))


def ping(url, token=""):
    """つながるかどうかだけ見る。"""
    headers = {}
    if token:
        headers[TOKEN_HEADER] = token
    req = Request((url or "").rstrip("/") + "/ping", headers=headers)
    with urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def _friendly(e):
    if isinstance(e, URLError):
        return "接続できません (%s)" % getattr(e, "reason", e)
    return "%s" % e


def local_addresses():
    """この PC の LAN アドレス。相手に教える用。"""
    import socket
    out = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ":" in ip or ip.startswith("127."):
                continue
            if ip not in out:
                out.append(ip)
    except OSError:
        pass
    return out


def make_token(length=14):
    """合言葉を適当に作る。

    外 (インターネット) に出すことがあるので、当てずっぽうで通らない長さに
    しておく。36 文字種 × 14 桁 ≒ 72 ビット。
    """
    import secrets
    import string
    pool = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(pool) for _ in range(length))


def new_entry(role=ROLE_ADMIN, name=""):
    return {"token": make_token(), "role": role, "name": name,
            "created_at": time.time()}
