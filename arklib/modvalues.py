# -*- coding: utf-8 -*-
"""Mod の生物を足す。

ARK Smart Breeding (ARKStatsExtractor) は、Mod ごとの種族データを
**Obelisk** というリポジトリで配っている。ここではそれを落としてきて、
このアプリの形に直し、ユーザーのデータフォルダに置く。

    一覧      : ARKStatsExtractor の _manifest.json (どの Mod のデータがあるか)
    中身      : https://raw.githubusercontent.com/arkutils/Obelisk/master/data/asb/<file>
    置き場所  : %LOCALAPPDATA%\\ArkLibrary\\mods\\<ファイル名>

種族データの作り方は tools/build_species_db.py と同じ (Species.cs 準拠)。

公開データが無い Mod の生物は、これでは足せない。その場合は
arklib.guess で「既存のどの種族と同じ計算式か」を当てにいく。
"""
import io
import json
import os
import re
import urllib.request

from . import ark

MANIFEST_URL = ("https://raw.githubusercontent.com/cadon/ARKStatsExtractor/"
                "master/ARKBreedingStats/json/values/_manifest.json")
VALUES_URL = "https://raw.githubusercontent.com/arkutils/Obelisk/master/data/asb/"
UA = "ArkLibrary-ModValues"

# Species.cs の既定値
IMPRINT_DEFAULT = [0.2, 0, 0.2, 0, 0.2, 0.2, 0, 0.2, 0.2, 0.2, 0, 0]
MUTATION_DEFAULT = [1.0] * ark.STATS_COUNT
DISPLAYED_DEFAULT = 927

SKIP_BP_PARTS = ("/Missions/", "TekCave", "/Gauntlet", "/Boss/")
SKIP_NAME_PARTS = ("VR ", "Ghost", "Corrupted", "Malfunctioned", "Dinotar")


# ---- 置き場所 ----------------------------------------------------------


def mods_dir(library_path=None):
    """Mod データの置き場所。ライブラリ DB と同じフォルダの mods/。"""
    if library_path:
        base = os.path.dirname(os.path.abspath(library_path))
    else:
        base = os.path.join(os.environ.get("LOCALAPPDATA")
                            or os.path.expanduser("~"), "ArkLibrary")
    path = os.path.join(base, "mods")
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            pass
    return path


def installed(library_path=None):
    """入れてある Mod データ。[{file, mod, count}] を返す。"""
    out = []
    folder = mods_dir(library_path)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for n in names:
        if not n.lower().endswith(".json"):
            continue
        try:
            with io.open(os.path.join(folder, n), encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        out.append({"file": n, "mod": d.get("mod") or {},
                    "count": len(d.get("species") or []),
                    "path": os.path.join(folder, n)})
    return out


def remove(file_name, library_path=None):
    path = os.path.join(mods_dir(library_path), file_name)
    try:
        os.remove(path)
        return True
    except OSError:
        return False


# ---- 一覧と取得 --------------------------------------------------------


def fetch_catalog(asa_only=True, timeout=20):
    """配布されている Mod データの一覧。[{file, id, tag, title, author, asa}]"""
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    out = []
    for file_name, info in (data.get("files") or {}).items():
        mod = info.get("mod")
        if not mod:
            continue
        if asa_only and not mod.get("ASA"):
            continue
        out.append({
            "file": file_name,
            "id": mod.get("id") or "",
            "tag": mod.get("tag") or "",
            "title": mod.get("title") or file_name,
            "author": mod.get("author") or "",
            "asa": bool(mod.get("ASA")),
        })
    out.sort(key=lambda m: m["title"].lower())
    return out


def download(file_name, timeout=30):
    """Mod の値ファイルを落として dict で返す。"""
    req = urllib.request.Request(VALUES_URL + file_name,
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def install(file_name, library_path=None, timeout=30):
    """落として、このアプリの形に直して保存する。(保存先, 種族数) を返す。"""
    raw = download(file_name, timeout)
    return install_from_dict(raw, file_name, library_path)


def install_from_file(path, library_path=None):
    """手元の値ファイル (ASB 形式) を取り込む。"""
    with io.open(path, encoding="utf-8-sig") as f:
        raw = json.load(f)
    return install_from_dict(raw, os.path.basename(path), library_path)


def install_from_dict(raw, file_name, library_path=None):
    converted = convert(raw)
    if not converted["species"]:
        raise ValueError("種族データが入っていません")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", file_name)
    if not name.lower().endswith(".json"):
        name += ".json"
    path = os.path.join(mods_dir(library_path), name)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=1)
    return path, len(converted["species"])


# ---- 変換 --------------------------------------------------------------


def convert(raw):
    """ASB の値ファイルを、このアプリの species.json と同じ形にする。"""
    species = []
    for s in raw.get("species") or []:
        rec = build_record(s, in_asa=bool((raw.get("mod") or {}).get("ASA")))
        if rec is not None:
            species.append(rec)
    return {
        "source": {
            "from": "ASB mod values",
            "version": raw.get("version"),
            "format": raw.get("format"),
        },
        "mod": raw.get("mod") or {},
        "species": species,
    }


def _int_key_dict(d):
    if not d:
        return None
    return {int(k): v for k, v in d.items()}


def normalize_stats_raw(raw):
    """fullStatsRaw を 12 x 5 に整える。使わないステータスは None のまま。"""
    if not raw:
        return None
    out = []
    for s in range(ark.STATS_COUNT):
        entry = raw[s] if s < len(raw) else None
        if entry is None:
            out.append(None)
            continue
        vals = [float(entry[i]) if i < len(entry) and entry[i] is not None else 0.0
                for i in range(5)]
        if vals[4] < 0:                 # 乗算テイムボーナスが負のものは 0 扱い
            vals[4] = 0.0
        out.append(vals)
    return out


def build_record(s, in_asa=True):
    """ASB の species 1 件を、このアプリの 1 レコードにする。"""
    name = s.get("name")
    bp = s.get("blueprintPath") or ""
    stats_raw = normalize_stats_raw(s.get("fullStatsRaw"))
    if not name or not stats_raw:
        return None
    if any(p in bp for p in SKIP_BP_PARTS) or any(p in name for p in SKIP_NAME_PARTS):
        return None

    used = 0
    for i, e in enumerate(stats_raw):
        if e is not None:
            used |= 1 << i

    displayed = s.get("displayedStats")
    if displayed is None or displayed == -1:
        displayed = used if used else DISPLAYED_DEFAULT

    skip_wild = int(s.get("skipWildLevelStats") or 0)
    skip_wild |= (~used) & ((1 << ark.STATS_COUNT) - 1)

    rec = {
        "name": name,
        "bp": bp,
        "asa": bool(in_asa),
        "statsRaw": stats_raw,
        "imprint": [float(x) for x in (s.get("statImprintMult") or IMPRINT_DEFAULT)],
        "mutationMult": [float(x) for x in (s.get("mutationMult") or MUTATION_DEFAULT)],
        "tbhm": (float(s["TamedBaseHealthMultiplier"])
                 if s.get("TamedBaseHealthMultiplier") else 1.0),
        "displayedStats": displayed,
        "usedStats": used,
        "skipWildLevelStats": skip_wild,
    }
    if s.get("variants"):
        rec["variants"] = list(s["variants"])
    if s.get("isFlyer"):
        rec["isFlyer"] = True
    if s.get("noGender"):
        rec["noGender"] = True
    if s.get("statNames"):
        rec["statNames"] = s["statNames"]
    for key, dst in (("statCaps", "statCaps"),
                     ("statLevelUpsAdditive", "additive"),
                     ("altBaseStats", "altBase")):
        d = _int_key_dict(s.get(key))
        if d:
            rec[dst] = {str(k): v for k, v in sorted(d.items())}

    br = s.get("breeding")
    if br:
        mat = float(br.get("maturationTime") or 0)
        if mat > 0:
            rec["breeding"] = {
                "incubation": round(float(br.get("incubationTime") or 0), 3),
                "gestation": round(float(br.get("gestationTime") or 0), 3),
                "maturation": round(mat, 3),
                "cdMin": float(br.get("matingCooldownMin") or 0),
                "cdMax": float(br.get("matingCooldownMax") or 0),
            }
    if s.get("matesWith"):
        rec["matesWith"] = [b[:-2] if b.endswith("_C") else b
                            for b in s["matesWith"]]
    return rec


# ---- 読み込み ----------------------------------------------------------


def load_extra_species(library_path=None):
    """入れてある Mod データの species レコードを全部返す。"""
    out = []
    for got in installed(library_path):
        try:
            with io.open(got["path"], encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        mod = d.get("mod") or {}
        for rec in d.get("species") or []:
            rec = dict(rec)
            rec["mod"] = mod.get("title") or mod.get("tag") or ""
            out.append(rec)
    return out
