# -*- coding: utf-8 -*-
"""個体ライブラリの永続化 (SQLite)。

DB は既定で %LOCALAPPDATA%\\ArkLibrary\\library.db に置く。アプリを
exe で置き換えてもデータが消えないようにするため、アプリ本体と同じ
フォルダには置かない。

同一個体の判定
--------------
ARK の DinoID (DinoID1/DinoID2 の組) が取れていればそれが最優先。
手入力などで ID がない場合は「サーバー + 種族 + 名前 + レベル」で
同じものとみなす。取り込みのたびに行が増えるのを防ぐための措置。
"""
import json
import os
import sqlite3
import time

from . import ark
from .creature import Creature, STATUS_DEAD

APP_DIR_NAME = "ArkLibrary"

CREATURE_COLUMNS = [
    "uid", "ark_id", "species_bp", "species_name", "name", "sex", "state",
    "level", "levels_wild", "levels_mut", "levels_dom", "values", "imprint",
    "taming_eff", "mutations_father", "mutations_mother", "mother_ark_id",
    "father_ark_id", "mother_name", "father_name", "colors", "owner", "tribe",
    "imprinter", "server", "status", "neutered", "baby_age",
    "mating_cooldown_until", "tags", "notes", "source", "source_file",
    "added_at", "updated_at", "ambiguous",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS creatures (
    uid                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ark_id                INTEGER NOT NULL DEFAULT 0,
    species_bp            TEXT NOT NULL,
    species_name          TEXT NOT NULL,
    name                  TEXT NOT NULL DEFAULT '',
    sex                   TEXT NOT NULL DEFAULT '-',
    state                 TEXT NOT NULL DEFAULT 'bred',
    level                 INTEGER NOT NULL DEFAULT 0,
    levels_wild           TEXT NOT NULL,
    levels_mut            TEXT NOT NULL,
    levels_dom            TEXT NOT NULL,
    "values"              TEXT NOT NULL,
    imprint               REAL NOT NULL DEFAULT 0,
    taming_eff            REAL,
    mutations_father      INTEGER NOT NULL DEFAULT 0,
    mutations_mother      INTEGER NOT NULL DEFAULT 0,
    mother_ark_id         INTEGER NOT NULL DEFAULT 0,
    father_ark_id         INTEGER NOT NULL DEFAULT 0,
    mother_name           TEXT NOT NULL DEFAULT '',
    father_name           TEXT NOT NULL DEFAULT '',
    colors                TEXT NOT NULL DEFAULT '[]',
    owner                 TEXT NOT NULL DEFAULT '',
    tribe                 TEXT NOT NULL DEFAULT '',
    imprinter             TEXT NOT NULL DEFAULT '',
    server                TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'alive',
    neutered              INTEGER NOT NULL DEFAULT 0,
    baby_age              REAL,
    mating_cooldown_until REAL,
    tags                  TEXT NOT NULL DEFAULT '[]',
    notes                 TEXT NOT NULL DEFAULT '',
    source                TEXT NOT NULL DEFAULT 'manual',
    source_file           TEXT NOT NULL DEFAULT '',
    added_at              REAL NOT NULL,
    updated_at            REAL NOT NULL,
    ambiguous             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_creatures_species ON creatures (species_bp);
CREATE INDEX IF NOT EXISTS idx_creatures_arkid ON creatures (ark_id);

CREATE TABLE IF NOT EXISTS servers (
    name        TEXT PRIMARY KEY,
    multipliers TEXT NOT NULL,
    ini_paths   TEXT NOT NULL DEFAULT '[]',
    is_default  INTEGER NOT NULL DEFAULT 0,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS imported_files (
    path       TEXT PRIMARY KEY,
    mtime      REAL NOT NULL,
    uid        INTEGER,
    result     TEXT NOT NULL DEFAULT '',
    imported_at REAL NOT NULL
);
"""


def default_db_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME, "library.db")


class Library(object):
    def __init__(self, path=None):
        self.path = path or default_db_path()
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def fix_genderless(self, species_db):
        """性別が無い種族の個体を U 表記に直す (古いデータの手当て)。

        以前は「性別不明 (-)」として入れていたので、交配の相手から外れていた。
        """
        rows = self.db.execute(
            "SELECT uid, species_bp FROM creatures WHERE sex = '-'").fetchall()
        fixed = 0
        for row in rows:
            sp = species_db.by_bp(row["species_bp"])
            if sp is not None and sp.no_gender:
                self.db.execute("UPDATE creatures SET sex = 'U' WHERE uid = ?",
                                (row["uid"],))
                fixed += 1
        if fixed:
            self.db.commit()
        return fixed

    def close(self):
        try:
            self.db.close()
        except sqlite3.Error:
            pass

    # ---- 個体の追加 / 更新 ---------------------------------------------

    def find_duplicate(self, cr):
        """同一個体がすでに居ればその行を返す。"""
        if cr.ark_id:
            row = self.db.execute(
                "SELECT * FROM creatures WHERE ark_id = ?", (cr.ark_id,)).fetchone()
            if row:
                return row
        row = self.db.execute(
            "SELECT * FROM creatures WHERE ark_id = 0 AND species_bp = ? "
            "AND name = ? AND level = ? AND server = ?",
            (cr.species_bp, cr.name, cr.level, cr.server)).fetchone()
        return row

    def save(self, cr):
        """新規なら挿入、既存なら更新する。戻り値は (uid, 'added'|'updated')。"""
        row = self.find_duplicate(cr) if cr.uid is None else None
        if row is not None:
            cr.uid = row["uid"]
            cr.added_at = row["added_at"]
            # 手で付けたメモ・タグ・状態は取り込みで消さない
            if not cr.notes:
                cr.notes = row["notes"]
            if not cr.tags:
                try:
                    cr.tags = json.loads(row["tags"])
                except (ValueError, TypeError):
                    pass
            if row["status"] == STATUS_DEAD and cr.status != STATUS_DEAD:
                # 死亡扱いにしたものが取り込みで生き返らないようにする
                # (同じ ID で再取得できたなら生きているので、新しい方を採る)
                pass

        cr.updated_at = time.time()
        d = cr.to_row()
        if cr.uid is None:
            cols = [c for c in CREATURE_COLUMNS if c != "uid"]
            sql = ('INSERT INTO creatures (%s) VALUES (%s)'
                   % (", ".join('"%s"' % c for c in cols),
                      ", ".join("?" for _ in cols)))
            cur = self.db.execute(sql, [d[c] for c in cols])
            cr.uid = cur.lastrowid
            action = "added"
        else:
            cols = [c for c in CREATURE_COLUMNS if c != "uid"]
            sql = ('UPDATE creatures SET %s WHERE uid = ?'
                   % ", ".join('"%s" = ?' % c for c in cols))
            self.db.execute(sql, [d[c] for c in cols] + [cr.uid])
            action = "updated"
        self.db.commit()
        return cr.uid, action

    def delete(self, uid):
        self.db.execute("DELETE FROM creatures WHERE uid = ?", (uid,))
        self.db.commit()

    def update_fields(self, uid, **fields):
        """メモ・名前・状態などの部分更新。"""
        if not fields:
            return
        for k in ("tags",):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k], ensure_ascii=False)
        fields["updated_at"] = time.time()
        sql = ("UPDATE creatures SET %s WHERE uid = ?"
               % ", ".join('"%s" = ?' % k for k in fields))
        self.db.execute(sql, list(fields.values()) + [uid])
        self.db.commit()

    # ---- 取得 ----------------------------------------------------------

    def get(self, uid):
        row = self.db.execute("SELECT * FROM creatures WHERE uid = ?", (uid,)).fetchone()
        return Creature.from_row(row) if row else None

    def by_ark_id(self, ark_id):
        if not ark_id:
            return None
        row = self.db.execute("SELECT * FROM creatures WHERE ark_id = ?",
                              (ark_id,)).fetchone()
        return Creature.from_row(row) if row else None

    def all_creatures(self, include_dead=True):
        sql = "SELECT * FROM creatures"
        if not include_dead:
            sql += " WHERE status != 'dead'"
        return [Creature.from_row(r) for r in self.db.execute(sql)]

    def by_species(self, species_bp, server=None, include_dead=True):
        sql = "SELECT * FROM creatures WHERE species_bp = ?"
        args = [species_bp]
        if server:
            sql += " AND server = ?"
            args.append(server)
        if not include_dead:
            sql += " AND status != 'dead'"
        return [Creature.from_row(r) for r in self.db.execute(sql, args)]

    def species_summary(self, server=None):
        """種族ごとの頭数。ライブラリ画面の左側リスト用。"""
        sql = ("SELECT species_bp, species_name, COUNT(*) AS n, "
               "SUM(CASE WHEN sex = 'M' THEN 1 ELSE 0 END) AS males, "
               "SUM(CASE WHEN sex = 'F' THEN 1 ELSE 0 END) AS females, "
               "SUM(CASE WHEN sex = 'U' THEN 1 ELSE 0 END) AS genderless, "
               "SUM(CASE WHEN status = 'dead' THEN 1 ELSE 0 END) AS dead "
               "FROM creatures")
        args = []
        if server:
            sql += " WHERE server = ?"
            args.append(server)
        sql += " GROUP BY species_bp ORDER BY species_name"
        return [dict(r) for r in self.db.execute(sql, args)]

    def servers_in_use(self):
        rows = self.db.execute(
            "SELECT DISTINCT server FROM creatures ORDER BY server")
        return [r["server"] for r in rows]

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM creatures").fetchone()[0]

    # ---- 最高ステータス ------------------------------------------------

    def top_levels(self, species_bp, server=None, include_dead=False,
                   breeding_only=True):
        """ステータスごとのライブラリ内最高レベルと、その個体。

        戻り値: {statIndex: (level, [Creature, ...])}
        """
        pool = [c for c in self.by_species(species_bp, server, include_dead)
                if not breeding_only or c.can_breed() or not breeding_only]
        if not include_dead:
            pool = [c for c in pool if c.status != STATUS_DEAD]
        out = {}
        for s in range(ark.STATS_COUNT):
            if s == ark.TORPIDITY:
                continue
            best = -1
            holders = []
            for c in pool:
                lv = c.bl(s)
                if lv > best:
                    best, holders = lv, [c]
                elif lv == best:
                    holders.append(c)
            if best >= 0:
                out[s] = (best, holders)
        return out

    # ---- サーバー設定 --------------------------------------------------

    def save_server(self, name, multipliers_dict, ini_paths=None, is_default=False):
        if is_default:
            self.db.execute("UPDATE servers SET is_default = 0")
        self.db.execute(
            "INSERT INTO servers (name, multipliers, ini_paths, is_default, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
            "multipliers = excluded.multipliers, ini_paths = excluded.ini_paths, "
            "is_default = excluded.is_default, updated_at = excluded.updated_at",
            (name, json.dumps(multipliers_dict), json.dumps(list(ini_paths or [])),
             1 if is_default else 0, time.time()))
        self.db.commit()

    def servers(self):
        out = []
        for r in self.db.execute("SELECT * FROM servers ORDER BY name"):
            d = dict(r)
            d["multipliers"] = json.loads(d["multipliers"])
            d["ini_paths"] = json.loads(d["ini_paths"])
            out.append(d)
        return out

    def default_server(self):
        row = self.db.execute(
            "SELECT * FROM servers WHERE is_default = 1").fetchone()
        if row is None:
            row = self.db.execute("SELECT * FROM servers ORDER BY name").fetchone()
        if row is None:
            return None
        d = dict(row)
        d["multipliers"] = json.loads(d["multipliers"])
        d["ini_paths"] = json.loads(d["ini_paths"])
        return d

    def delete_server(self, name):
        self.db.execute("DELETE FROM servers WHERE name = ?", (name,))
        self.db.commit()

    def rename_server(self, old, new):
        self.db.execute("UPDATE servers SET name = ? WHERE name = ?", (new, old))
        self.db.execute("UPDATE creatures SET server = ? WHERE server = ?", (new, old))
        self.db.commit()

    # ---- 設定 ----------------------------------------------------------

    def set_setting(self, key, value):
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def get_setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key = ?",
                              (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    # ---- 取り込み履歴 --------------------------------------------------

    def mark_imported(self, path, mtime, uid=None, result=""):
        self.db.execute(
            "INSERT INTO imported_files (path, mtime, uid, result, imported_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET "
            "mtime = excluded.mtime, uid = excluded.uid, result = excluded.result, "
            "imported_at = excluded.imported_at",
            (os.path.abspath(path), mtime, uid, result, time.time()))
        self.db.commit()

    def was_imported(self, path, mtime):
        row = self.db.execute(
            "SELECT mtime FROM imported_files WHERE path = ?",
            (os.path.abspath(path),)).fetchone()
        return row is not None and abs(row["mtime"] - mtime) < 1.0

    def forget_imported(self, path=None):
        if path is None:
            self.db.execute("DELETE FROM imported_files")
        else:
            self.db.execute("DELETE FROM imported_files WHERE path = ?",
                            (os.path.abspath(path),))
        self.db.commit()
