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
