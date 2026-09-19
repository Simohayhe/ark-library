# -*- coding: utf-8 -*-
"""PC どうしの共有 (同期) のテスト。

同じプロセスの中に「共有元」と「つなぎに行く側」を 2 つ作って、
実際に HTTP でやり取りさせる。
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arklib import ark, sync
from arklib.creature import FEMALE, MALE, STATUS_DEAD, Creature
from arklib.library import Library

PASS, FAIL = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print("  OK   %-46s %s" % (name, got))
    else:
        FAIL.append(name)
        print("  NG   %-46s got=%s want=%s" % (name, got, want))


def mk(name, sex=MALE, hp=30, me=30, ark_id=0):
    c = Creature(species_bp="bp/Rex", species_name="Rex", name=name, sex=sex,
                 state="bred", ark_id=ark_id, server="GorillaArk")
    c.levels_wild[ark.HEALTH] = hp
    c.levels_wild[ark.MELEE] = me
    c.level = 1 + hp + me
    return c


def names(lib):
    return sorted(c.name for c in lib.all_creatures())


def main():
    tmp = tempfile.mkdtemp(prefix="arksync_")
    host_db = os.path.join(tmp, "host.db")
    game_db = os.path.join(tmp, "game.db")

    host = Library(host_db)
    game = Library(game_db)

    token = sync.make_token()
    print("合言葉: %s" % token)

    # ---- [1] サーバーを立てる --------------------------------------
    print("\n[1] 共有元を立てる")
    server = sync.SyncServer(host_db, token, port=0, host="127.0.0.1")
    check("1.1 起動できる", server.start(), True)
    port = server.httpd.server_address[1]
    url = "http://127.0.0.1:%d" % port
    print("       %s" % url)
    got = sync.ping(url)
    check("1.2 ping が返る", got.get("app"), "ark-library")
    check("1.3 合言葉が要ると言う", got.get("needs_token"), True)

    bad = sync.SyncClient(game_db, url, token="ちがう")
    try:
        bad.sync_once()
        check("1.4 合言葉が違うと弾かれる", False, True)
    except Exception:
        check("1.4 合言葉が違うと弾かれる", True, True)

    client = sync.SyncClient(game_db, url, token=token)

    # ---- [2] 向こうの個体がこっちに来る ----------------------------
    print("\n[2] 共有元 → こちら")
    host.save(mk("ホストの子", ark_id=1001))
    host.save(mk("ホストの子2", ark_id=1002))
    pulled, pushed = client.sync_once()
    check("2.1 2 体もらった", pulled, 2)
    check("2.2 送るものは無い", pushed, 0)
    check("2.3 名前が揃う", names(game), ["ホストの子", "ホストの子2"])

    # ---- [3] こっちの個体が向こうに行く ----------------------------
    print("\n[3] こちら → 共有元")
    game.save(mk("ゲームPCの子", sex=FEMALE, hp=45, ark_id=2001))
    pulled, pushed = client.sync_once()
    check("3.1 1 体送った", pushed, 1)
    check("3.2 共有元にも入った", "ゲームPCの子" in names(host), True)
    got = [c for c in host.all_creatures() if c.name == "ゲームPCの子"][0]
    check("3.3 レベルの内訳まで届く", got.bl(ark.HEALTH), 45)
    check("3.4 性別も届く", got.sex, FEMALE)

    # ---- [4] 同じ個体を両方で触ったとき ----------------------------
    print("\n[4] 新しい方が残る")
    c = [x for x in host.all_creatures() if x.ark_id == 1001][0]
    host.update_fields(c.uid, notes="ホストで書いたメモ")
    client.sync_once()
    mine = [x for x in game.all_creatures() if x.ark_id == 1001][0]
    check("4.1 メモが来た", mine.notes, "ホストで書いたメモ")

    time.sleep(0.01)
    game.update_fields(mine.uid, notes="ゲームPCで上書き")
    client.sync_once()
    theirs = [x for x in host.all_creatures() if x.ark_id == 1001][0]
    check("4.2 あとから書いた方が勝つ", theirs.notes, "ゲームPCで上書き")

    # ---- [5] 消したものは戻ってこない ------------------------------
    print("\n[5] 消したものは戻らない")
    doomed = [x for x in game.all_creatures() if x.ark_id == 1002][0]
    game.delete(doomed.uid)
    check("5.1 こちらから消えた", "ホストの子2" in names(game), False)
    client.sync_once()
    check("5.2 共有元からも消えた", "ホストの子2" in names(host), False)
    client.sync_once()
    check("5.3 もう一度回しても戻らない", "ホストの子2" in names(game), False)

    # ---- [6] 設定は選んだものだけ ----------------------------------
    print("\n[6] 配る設定・配らない設定")
    host.set_setting("ideal_bp/Rex", {"stats": {"0": 50}, "colors": {},
                                      "note": ""})
    host.set_setting("plan_goals_bp/Rex", {"0": "max"})
    host.set_setting("import_folder", r"D:\ホストのフォルダ")
    host.set_setting("theme", "dark")
    game.set_setting("import_folder", r"E:\ゲームPCのフォルダ")
    client.sync_once()
    check("6.1 理想個体は共有される",
          (game.get_setting("ideal_bp/Rex") or {}).get("stats"), {"0": 50})
    check("6.2 狙いも共有される", game.get_setting("plan_goals_bp/Rex"), {"0": "max"})
    check("6.3 取り込みフォルダは各自のまま",
          game.get_setting("import_folder"), r"E:\ゲームPCのフォルダ")
    check("6.4 テーマも配らない", game.get_setting("theme"), None)

    # ---- [7] 倍率プロファイル --------------------------------------
    print("\n[7] サーバー倍率のプロファイル")
    from arklib.multipliers import ServerMultipliers
    sm = ServerMultipliers.official("asa")
    sm.stat[ark.WEIGHT][2] = 2.0
    host.save_server("GorillaArk", sm.to_dict(), [], is_default=True)
    client.sync_once()
    names_here = [r["name"] for r in game.servers()]
    check("7.1 プロファイルが来た", "GorillaArk" in names_here, True)
    got = ServerMultipliers.from_dict(game.default_server()["multipliers"]) \
        if game.default_server() else None
    check("7.2 重量の強化倍率まで一致",
          got.stat[ark.WEIGHT][2] if got else None, 2.0)
    check("7.3 ini のパスは配らない (PC ごとに違う)",
          json_len(game, "GorillaArk"), 0)

    # ---- [8] 何も変わっていなければ何もしない ----------------------
    print("\n[8] 変わっていなければ静か")
    pulled, pushed = client.sync_once()
    check("8.1 やり取りなし", (pulled, pushed), (0, 0))

    # ---- [9] 見張りスレッド ----------------------------------------
    print("\n[9] 動かしっぱなしにする")
    seen = []
    client.on_change = lambda a, b: seen.append((a, b))
    client.interval = 0.2
    client.start()
    host.save(mk("あとから来た子", ark_id=3001))
    for _ in range(50):
        if "あとから来た子" in names(game):
            break
        time.sleep(0.1)
    client.stop()
    check("9.1 勝手に取り込まれる", "あとから来た子" in names(game), True)
    check("9.2 知らせが来る", bool(seen), True)

    # ---- [10] つながらないとき -------------------------------------
    print("\n[10] つながらないとき")
    server.stop()
    check("10.1 サーバーが止まった", server.running, False)
    lonely = sync.SyncClient(game_db, url, token=token, interval=0.1)
    lonely.start()
    # Windows は「つながらない」と分かるまで 2 秒ほどかかる
    for _ in range(80):
        if lonely.error:
            break
        time.sleep(0.1)
    lonely.stop()
    check("10.2 落ちずにエラーを持つ", bool(lonely.error), True)
    check("10.3 こちらのデータは無事", "あとから来た子" in names(game), True)

    # ---- [11] 合言葉の種類 (管理者 / メンバー) ---------------------
    print("\n[11] 管理者とメンバー")
    admin = sync.new_entry(sync.ROLE_ADMIN, "自分のPC")
    member = sync.new_entry(sync.ROLE_MEMBER, "ともだち")
    check("11.1 別の合言葉になる", admin["token"] != member["token"], True)
    check("11.2 十分な長さ", len(admin["token"]) >= 14, True)

    srv2 = sync.SyncServer(host_db, port=0, host="127.0.0.1",
                           tokens=[admin, member])
    check("11.3 起動できる", srv2.start(), True)
    url2 = "http://127.0.0.1:%d" % srv2.httpd.server_address[1]

    check("11.4 管理者だと分かる",
          sync.ping(url2, admin["token"]).get("role"), sync.ROLE_ADMIN)
    check("11.5 メンバーだと分かる",
          sync.ping(url2, member["token"]).get("role"), sync.ROLE_MEMBER)

    friend_db = os.path.join(tmp, "friend.db")
    friend = sync.SyncClient(friend_db, url2, token=member["token"])
    pulled, pushed = friend.sync_once()
    check("11.6 メンバーでも受け取れる", pulled > 0, True)

    fl = Library(friend_db)
    fl.save(mk("友達が作った子", ark_id=4001))
    fl.close()
    try:
        friend.sync_once()
        check("11.7 メンバーは書き込めない", False, True)
    except Exception as e:
        check("11.7 メンバーは書き込めない", "403" in str(e), True)
    check("11.8 共有元は汚れない", "友達が作った子" in names(host), False)

    boss = sync.SyncClient(os.path.join(tmp, "boss.db"), url2,
                           token=admin["token"])
    bl = Library(os.path.join(tmp, "boss.db"))
    bl.save(mk("管理者が作った子", ark_id=4002))
    bl.close()
    boss.sync_once()
    check("11.9 管理者は書き込める", "管理者が作った子" in names(host), True)

    nobody = sync.SyncClient(os.path.join(tmp, "x.db"), url2, token="でたらめ")
    try:
        nobody.sync_once()
        check("11.10 知らない合言葉は弾く", False, True)
    except Exception:
        check("11.10 知らない合言葉は弾く", True, True)

    check("11.11 誰が来たか分かる", bool(srv2.last_who), True)
    srv2.stop()

    # ---- [12] 外に出す道具 ------------------------------------------
    print("\n[12] 外に出す道具 (ポート開放なし)")
    from arklib import tunnel
    ip = tunnel.local_ip()
    check("12.1 自分のアドレスが引ける", ip.count(".") == 3, True)
    exe = tunnel.find_cloudflared()
    print("       cloudflared: %s" % (exe or "(未インストール)"))
    t = tunnel.CloudflareTunnel(9999, exe=exe)
    if exe is None:
        check("12.2 無ければ入れ方を案内する", t.start(), False)
        check("12.3 案内に winget が出る", "winget" in t.error, True)
    else:
        check("12.2 起動できる", t.start(), True)
        got = t.wait_for_url(30)
        check("12.3 URL を貰える", got.startswith("https://"), True)
        print("       %s" % got)
        t.stop()
    m = tunnel.UpnpMapping(9999)
    print("       UPnP: 探しています…")
    ok = m.start()
    print("       %s" % ("外から %s" % m.url if ok else m.error))
    check("12.4 UPnP は結果を持ち帰る", isinstance(ok, bool), True)
    if ok:
        m.stop()

    # ---- [13] 同期中でも読み取りが止まらないこと --------------------
    print("\n[13] 同期の書き込みが読み取りを止めない")
    check("13.1 WAL になっている",
          host.db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")

    import statistics
    import threading

    stop = threading.Event()

    def writer():
        # 共有サーバーがやること: リクエストごとに開いて書いて閉じる
        while not stop.is_set():
            lib = Library(host_db)
            try:
                lib.set_setting("sync_pull_at", time.time())
                lib.set_setting("sync_push_at", time.time())
            finally:
                lib.close()

    th = threading.Thread(target=writer, daemon=True)
    th.start()
    reader = Library(host_db)
    waits = []
    for _ in range(200):
        t0 = time.perf_counter()
        reader.get_setting("naming_mode", None)
        reader.all_creatures()
        waits.append((time.perf_counter() - t0) * 1000)
    stop.set()
    th.join(timeout=5)
    reader.close()
    worst = max(waits)
    print("       読み取り 中央値 %.2f ms / 最悪 %.2f ms"
          % (statistics.median(waits), worst))
    # 既定の journal だと書き込み中に 100ms 超えて待たされることがあった
    check("13.2 最悪でも 50ms 待たない (%.1f ms)" % worst, worst < 50, True)

    host.close()
    game.close()

    print("\n" + "=" * 66)
    print("%d 件成功 / %d 件失敗" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失敗: " + ", ".join(FAIL))
    return 1 if FAIL else 0


def json_len(lib, name):
    import json
    row = [r for r in lib.servers() if r["name"] == name]
    if not row:
        return -1
    paths = row[0]["ini_paths"]
    if isinstance(paths, str):
        try:
            paths = json.loads(paths)
        except ValueError:
            paths = []
    return len(paths or [])


if __name__ == "__main__":
    sys.exit(main())
