# -*- coding: utf-8 -*-
"""exe をビルドする。

    python tools/build.py            # onefile / onedir(zip) / setup.exe の全部
    python tools/build.py onefile    # 1 つの exe だけ
    python tools/build.py onedir     # フォルダ版 (zip) だけ
    python tools/build.py setup      # インストーラだけ (onedir を先に作る)

Windows Defender の誤検知 (Trojan:Win32/Wacatac.*!ml) 対策として、
このスクリプトは次を必ず行う。ふわふわタイマーで実際に踏んだ対策。

  * UPX を使わない        … 圧縮された exe は問答無用で疑われる
  * バージョン情報を埋める … 会社名・製品名・著作権が空の exe は疑われる
  * onedir 版も一緒に作る  … onefile は %TEMP% に自己展開するので
                             機械学習判定に引っかかりやすい。
                             フォルダ版はその挙動が無く、かなり通りやすい

最後に Defender でスキャンして結果を出す。
"""
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)

NAME = "ArkLibrary"
PRODUCT = "ARK Library"
ENTRY = "ark_library.py"
REPO_URL = "https://github.com/Simohayhe/ark-library"
VERSION_FILE = os.path.join(PROJ, "build_version_info.txt")


def app_version():
    """arklib/__init__.py の __version__ を読む (import せずに)。"""
    path = os.path.join(PROJ, "arklib", "__init__.py")
    with open(path, encoding="utf-8") as f:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
    return m.group(1) if m else "0.0.0"


def write_version_info(ver):
    """exe のプロパティに出る情報。空だと Defender の心証が悪い。"""
    parts = [int(x) for x in ver.split(".")]
    while len(parts) < 4:
        parts.append(0)
    quad = tuple(parts[:4])
    text = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=%(q)s, prodvers=%(q)s,
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041104b0', [
      StringStruct('CompanyName', 'Simohaya'),
      StringStruct('FileDescription', 'ARK Library - creature library and breeding planner'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', '%(n)s'),
      StringStruct('LegalCopyright',
                   'Copyright (c) 2026 Simohaya. MIT License.'),
      StringStruct('OriginalFilename', '%(n)s.exe'),
      StringStruct('ProductName', '%(p)s'),
      StringStruct('ProductVersion', '%(v)s'),
      StringStruct('Comments',
                   'Open source. %(u)s')])]),
    VarFileInfo([VarStruct('Translation', [1041, 1200])])
  ]
)
""" % {"q": quad, "v": ver, "n": NAME, "p": PRODUCT, "u": REPO_URL}
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    return VERSION_FILE


SPEC_NOTE = """# -*- mode: python ; coding: utf-8 -*-
#
# このファイルは tools/build.py が自動生成する。直接編集しても次のビルドで消える。
#
# upx は必ず False のままにすること。
# True にすると Windows Defender に Trojan:Win32/Wacatac.C!ml として
# 誤検知され、ダウンロードした瞬間に消される。
# version-file (会社名・製品名・著作権) を入れておくのも誤検知対策。
#
"""


def keep_spec_note(spec_name):
    path = os.path.join(PROJ, spec_name)
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        body = f.read()
    body = body.split("\n", 1)[1] if body.startswith("# -*- mode: python") else body
    with open(path, "w", encoding="utf-8") as f:
        f.write(SPEC_NOTE + body.lstrip("\n"))


def run(args):
    print("$ " + " ".join(args))
    r = subprocess.run(args, cwd=PROJ)
    if r.returncode != 0:
        sys.exit("ビルドに失敗しました (exit %d)" % r.returncode)


def common_args(ver):
    return [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--noconsole", "--noupx",
        "--icon", os.path.join("assets", "icon.ico"),
        "--version-file", write_version_info(ver),
        "--add-data", "data%sspecies.json%sdata" % (os.sep, os.pathsep),
        "--add-data", "data%scolors.json%sdata" % (os.sep, os.pathsep),
        ENTRY,
    ]


def build_onefile(ver):
    args = common_args(ver)
    args[args.index(ENTRY):] = ["--onefile", "--name", NAME, ENTRY]
    run(args)
    keep_spec_note(NAME + ".spec")
    return os.path.join(PROJ, "dist", NAME + ".exe")


def build_onedir(ver):
    dirname = NAME + "-dir"
    args = common_args(ver)
    args[args.index(ENTRY):] = ["--onedir", "--name", dirname, ENTRY]
    run(args)
    keep_spec_note(dirname + ".spec")
    src = os.path.join(PROJ, "dist", dirname)
    # PyInstaller は出力名で exe を作るので "-dir" が付く。正しい名前に直す
    # (_internal は相対で読むので、exe の名前を変えても動く)
    made = os.path.join(src, dirname + ".exe")
    want = os.path.join(src, NAME + ".exe")
    if os.path.exists(made):
        if os.path.exists(want):
            os.remove(want)
        os.rename(made, want)
    zip_path = os.path.join(PROJ, "dist", "%s-%s-win64.zip" % (NAME, ver))
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(src):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src)
                if rel.lower() == dirname.lower() + ".exe":
                    rel = NAME + ".exe"
                z.write(full, os.path.join(NAME, rel))
    return zip_path


ISCC_CANDIDATES = (
    r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe",
    r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe",
    r"%ProgramFiles%\Inno Setup 6\ISCC.exe",
)


def find_iscc():
    for p in ISCC_CANDIDATES:
        p = os.path.expandvars(p)
        if os.path.exists(p):
            return p
    return shutil.which("ISCC") or shutil.which("iscc")


def build_setup(ver):
    """Inno Setup で setup.exe を作る。onedir の中身をそのまま詰める。"""
    iscc = find_iscc()
    if not iscc:
        print("  ! Inno Setup が見つからないので setup.exe は作りません")
        print("    winget install JRSoftware.InnoSetup で入ります")
        return None
    src = os.path.join(PROJ, "dist", NAME + "-dir")
    if not os.path.isdir(src):
        print("  ! %s が無いので、先に onedir を作ってください" % src)
        return None
    iss = os.path.join(PROJ, "installer", NAME + ".iss")
    run([iscc, "/DMyVersion=" + ver, iss])
    return os.path.join(PROJ, "dist", "%s-%s-setup.exe" % (NAME, ver))


def defender_scan(path):
    mp = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                      "Windows Defender", "MpCmdRun.exe")
    if not os.path.exists(path):
        return "(消えています。Defender に隔離された可能性)"
    if not os.path.exists(mp):
        return "(MpCmdRun.exe が見つからないのでスキャン省略)"
    r = subprocess.run([mp, "-Scan", "-ScanType", "3", "-File", path],
                       capture_output=True, text=True, errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    if "found no threats" in out or "見つかりませんでした" in out:
        return "OK (検出なし)"
    return "⚠ 何か出ました:\n" + out.strip()


def main():
    what = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    ver = app_version()
    print("=== %s v%s をビルドします ===" % (NAME, ver))
    made = []
    if what in ("all", "onefile"):
        made.append(build_onefile(ver))
    if what in ("all", "onedir", "setup"):
        made.append(build_onedir(ver))
    if what in ("all", "setup"):
        # setup.exe は onedir の中身をそのまま使うので、消す前に作る
        setup = build_setup(ver)
        if setup:
            made.append(setup)

    stray = os.path.join(PROJ, "dist", NAME + "-dir")
    if os.path.isdir(stray):
        shutil.rmtree(stray, ignore_errors=True)

    print("\n=== できあがり ===")
    for p in made:
        size = os.path.getsize(p) / 1024 / 1024 if os.path.exists(p) else 0
        print("  %-46s %6.2f MB" % (os.path.basename(p), size))
        print("      Defender: %s" % defender_scan(p))


if __name__ == "__main__":
    main()
