# -*- coding: utf-8 -*-
"""ARK のインストール先・エクスポート先・設定ファイルの自動検出。

エクスポートの保存先 (Steam 版)
    ASA : <インストール>\\ShooterGame\\Saved\\DinoExports\\*.ini
    ASE : <インストール>\\ShooterGame\\Saved\\DinoExports\\<SteamID>\\*.ini
    Export Gun Mod : 上記 DinoExports の下の ASB\\ フォルダ

インストール先は Steam のレジストリ → libraryfolders.vdf の順にたどる。
見つからなければ決め打ちの候補を当たる。
"""
import os
import re

APPID_ASA = "2399830"
APPID_ASE = "346110"

ASA_FOLDER_NAMES = ("ARK Survival Ascended", "ARKSurvivalAscended")
ASE_FOLDER_NAMES = ("ARK", "ARK Survival Evolved")

# ホストが自分でサーバーを建てている場合に見に行く場所
SERVER_ROOT_CANDIDATES = (
    r"C:\ArkServers",
    r"C:\ArkCluster",
    r"C:\ASAServers",
    r"D:\ArkServers",
)

SERVER_CONFIG_RELATIVE = os.path.join("ShooterGame", "Saved", "Config", "WindowsServer")


def steam_path():
    """Steam のインストール先。"""
    try:
        import winreg
    except ImportError:
        return None
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
                      (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                for name in ("InstallPath", "SteamPath"):
                    try:
                        p = winreg.QueryValueEx(k, name)[0]
                        if p and os.path.isdir(p):
                            return p
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def steam_library_folders():
    """Steam のライブラリフォルダ一覧 (steamapps までのパス)。"""
    sp = steam_path()
    out = []
    if not sp:
        return out
    main = os.path.join(sp, "steamapps")
    if os.path.isdir(main):
        out.append(main)

    vdf = os.path.join(main, "libraryfolders.vdf")
    if os.path.isfile(vdf):
        try:
            with open(vdf, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        for m in re.finditer(r'"path"\s*"([^"]+)"', text):
            p = os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps")
            if os.path.isdir(p) and p not in out:
                out.append(p)
    return out


def ark_install_dirs():
    """見つかった ARK のインストール先。[(path, 'asa'|'ase'), ...]"""
    found = []
    for lib in steam_library_folders():
        common = os.path.join(lib, "common")
        if not os.path.isdir(common):
            continue
        for name in ASA_FOLDER_NAMES:
            p = os.path.join(common, name)
            if os.path.isdir(p):
                found.append((p, "asa"))
        for name in ASE_FOLDER_NAMES:
            p = os.path.join(common, name)
            if os.path.isdir(p) and os.path.isdir(os.path.join(p, "ShooterGame")):
                found.append((p, "ase"))

    if not found:
        for base in (r"C:\Program Files (x86)\Steam\steamapps\common",
                     r"C:\Program Files\Steam\steamapps\common"):
            for name in ASA_FOLDER_NAMES:
                p = os.path.join(base, name)
                if os.path.isdir(p):
                    found.append((p, "asa"))

    # 重複を除く
    seen = set()
    out = []
    for p, g in found:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            out.append((os.path.abspath(p), g))
    return out


def dino_export_dirs():
    """エクスポートされた ini が置かれるフォルダの候補。

    [(path, ラベル, exists), ...] を返す。ASA は SteamID のサブフォルダを
    使わないが、ASE は使うので中のフォルダも候補に入れる。
    """
    out = []
    for install, game in ark_install_dirs():
        base = os.path.join(install, "ShooterGame", "Saved", "DinoExports")
        label = "ASA" if game == "asa" else "ASE"
        out.append((base, "%s 標準エクスポート" % label, os.path.isdir(base)))
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                sub = os.path.join(base, name)
                if not os.path.isdir(sub):
                    continue
                if name.upper() == "ASB":
                    out.append((sub, "%s Export Gun" % label, True))
                else:
                    out.append((sub, "%s %s" % (label, name), True))
    return out


def first_existing_export_dir():
    for path, _label, exists in dino_export_dirs():
        if exists:
            return path
    for path, _label, _exists in dino_export_dirs():
        return path
    return None


def local_server_configs():
    """このPCで動かしているサーバーの設定フォルダ。[(名前, Game.ini, GameUserSettings.ini)]"""
    out = []
    for root in SERVER_ROOT_CANDIDATES:
        if not os.path.isdir(root):
            continue
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for name in names:
            cfg = os.path.join(root, name, SERVER_CONFIG_RELATIVE)
            game_ini = os.path.join(cfg, "Game.ini")
            gus_ini = os.path.join(cfg, "GameUserSettings.ini")
            if os.path.isfile(game_ini) or os.path.isfile(gus_ini):
                out.append((name,
                            game_ini if os.path.isfile(game_ini) else None,
                            gus_ini if os.path.isfile(gus_ini) else None))
    return out


def client_config_dirs():
    """クライアント側の設定 (シングルプレイ / 非公式の自分の設定)。"""
    out = []
    for install, game in ark_install_dirs():
        sub = "Windows" if game == "asa" else "WindowsNoEditor"
        cfg = os.path.join(install, "ShooterGame", "Saved", "Config", sub)
        if os.path.isdir(cfg):
            out.append((game, cfg))
    return out
