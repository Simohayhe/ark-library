# -*- coding: utf-8 -*-
"""ARK 標準の「恐竜のエクスポート」が書き出す ini ファイルを読む。

保存先 (ASA / Steam)
    <ARKインストール>\\ShooterGame\\Saved\\DinoExports\\*.ini
ASE は上記の下に SteamID のサブフォルダが付く。

ファイルの形
------------
ふつうの ini だが 2 点くせがある。

1. ステータス値は `[Max Character Status Values]` セクションに **並び順だけで**
   入っている。キー名はゲームの言語で変わる (日本語クライアントなら日本語) ので
   名前では引けない。順番は内部のステータス番号そのままで

       体力, スタミナ, 気絶値, 酸素, 食料, 水分, 温度, 重量,
       近接攻撃力, 移動速度, 温度耐性, 作成速度

2. 近接攻撃力・移動速度・温度耐性・作成速度は「100% からの増分」で入っている。
   0.5 なら 150%。内部表現に直すときは 1 を足す。

ここではレベルの内訳は出さない (ファイルに入っていない)。表示値・レベル・
刷り込み率を拾って、逆算は arklib.extraction に任せる。
"""
import io
import os
import re

from .. import ark
from ..creature import (FEMALE, MALE, STATE_BRED, STATE_TAMED, STATE_WILD,
                        UNKNOWN_SEX, ark_id_from_parts)

STAT_SECTION = "max character status values"

# [Max Character Status Values] に並ぶ順番 = ステータス番号そのまま
STAT_ORDER = list(range(ark.STATS_COUNT))

# 100% からの増分で書かれているステータス
OFFSET_STATS = frozenset((ark.MELEE, ark.SPEED, ark.TEMPERATURE_FORTITUDE,
                          ark.CRAFTING_SPEED))

_ANCESTOR_RE = re.compile(
    r"MaleName=(?P<mname>[^;]*?)(?:\s*-\s*Lvl\s*(?P<mlvl>\d+))?;"
    r"MaleDinoID1=(?P<mid1>[^;]*);MaleDinoID2=(?P<mid2>[^;]*);"
    r"FemaleName=(?P<fname>[^;]*?)(?:\s*-\s*Lvl\s*(?P<flvl>\d+))?;"
    r"FemaleDinoID1=(?P<fid1>[^;]*);FemaleDinoID2=(?P<fid2>[^;]*)")

_COLOR_RE = re.compile(
    r"R=(-?[\d.]+),G=(-?[\d.]+),B=(-?[\d.]+),A=(-?[\d.]+)")


# ロストコロニーのスキルツリーが付ける刷り込み。この3段階しかない
SKILL_IMPRINTS = (0.10, 0.20, 0.30)


class ExportedCreature(object):
    """ini から読めた生の情報。種族の解決と逆算はまだしていない。"""

    def __init__(self):
        self.blueprint = ""
        self.species_tag = ""
        self.name = ""
        self.tamer = ""
        self.tribe = ""
        self.imprinter = ""
        self.owner = ""
        self.sex = UNKNOWN_SEX
        self.neutered = False
        self.level = 0
        self.imprint = 0.0
        self.baby_age = None
        self.mutations_father = 0
        self.mutations_mother = 0
        self.ark_id = 0
        self.mother_ark_id = 0
        self.father_ark_id = 0
        self.mother_name = ""
        self.father_name = ""
        self.values = [0.0] * ark.STATS_COUNT
        self.has_value = [False] * ark.STATS_COUNT
        self.colors = [0] * 6
        self.color_rgba = {}
        self.traits = []
        self.raw = {}
        self.path = ""
        self.mtime = None

    @property
    def state(self):
        """野生 / テイム / 交配産 の判定。

        BabyAge は**成体でも 1 が書かれる**ので、これだけでは交配産と判断できない
        (実機のテイム個体で BabyAge=1 を確認済み)。まだ育ち切っていない
        (1 未満) なら交配産とみなす。

        飼い主もテイマーも刷り込み者も居なければ野生。

        刷り込みが乗っていても、交配産とは限らない。ロストコロニーの
        スキルツリーは、野生をテイムしただけで 10/20/30% を付ける。
        """
        if self.skill_tree_imprint():
            return STATE_TAMED
        if (self.imprinter or self.imprint > 0
                or (self.baby_age is not None and self.baby_age < 1.0)
                or self.mother_ark_id or self.father_ark_id):
            return STATE_BRED
        if self.name or self.tamer or self.tribe or self.owner:
            return STATE_TAMED
        return STATE_WILD

    def skill_tree_imprint(self):
        """スキルツリーで付いた刷り込みか。

        ロストコロニーのスキルツリーには、テイムした相手に刷り込みを
        乗せるものがあり、10% / 20% / 30% の3段階。野生をテイムしただけ
        なので、親も刷り込み者も居らず、赤ちゃんでもない。
        交配で育てたものは、この3つにぴったり一致してもどれかが埋まる。
        """
        if self.imprinter or self.mother_ark_id or self.father_ark_id:
            return False
        if self.baby_age is not None and self.baby_age < 1.0:
            return False
        return any(abs(self.imprint - v) < 0.005 for v in SKILL_IMPRINTS)

    def __repr__(self):
        return ("<ExportedCreature %s Lv%d %s>"
                % (self.species_tag or self.blueprint, self.level, self.sex))


def _to_float(text):
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def parse_file(path):
    """ini を読んで ExportedCreature を返す。恐竜のエクスポートでなければ None。"""
    with io.open(path, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    ec = parse_text(text)
    if ec is not None:
        ec.path = os.path.abspath(path)
        try:
            ec.mtime = os.path.getmtime(path)
        except OSError:
            pass
    return ec


def parse_text(text):
    ec = ExportedCreature()
    id_parts = []
    ancestor_line = None
    found_any = False

    sections = _split_sections(text)
    stat_section = _pick_stat_section(sections)

    for section_name, entries in sections:
        if entries is stat_section:
            # --- ステータス欄 (キー名ではなく並び順で決まる) ------------
            for pos, (_key, value) in enumerate(entries[:len(STAT_ORDER)]):
                s = STAT_ORDER[pos]
                v = _to_float(value)
                if v is None:
                    continue
                ec.values[s] = v + 1.0 if s in OFFSET_STATS else v
                ec.has_value[s] = True
                found_any = True
            continue

        for key, value in entries:
            found_any = _read_entry(ec, key, value, id_parts) or found_any
            if "DinoAncestors" in key.split("[", 1)[0] and "MaleName=" in value:
                ancestor_line = value       # 最後の行が直接の親

    # --- ID ------------------------------------------------------------
    if len(id_parts) >= 2:
        d = dict(id_parts[:2])
        ec.ark_id = ark_id_from_parts(d.get("DinoID1"), d.get("DinoID2"))

    # --- 親 ------------------------------------------------------------
    if ancestor_line:
        m = _ANCESTOR_RE.search(ancestor_line)
        if m:
            ec.father_ark_id = ark_id_from_parts(m.group("mid1"), m.group("mid2"))
            ec.mother_ark_id = ark_id_from_parts(m.group("fid1"), m.group("fid2"))
            ec.father_name = (m.group("mname") or "").strip()
            ec.mother_name = (m.group("fname") or "").strip()

    if not found_any or not ec.blueprint:
        return None
    return ec


def _split_sections(text):
    """[セクション名] ごとに (名前, [(キー, 値), ...]) へ分ける。"""
    sections = [("", [])]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sections.append((line[1:-1].strip(), []))
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        sections[-1][1].append((key.strip(), value.strip()))
    return sections


def _pick_stat_section(sections):
    """ステータス欄はどれか。

    英語クライアントなら [Max Character Status Values] で当たる。ゲームの
    言語によってはセクション名まで翻訳されている可能性があるので、当たら
    なければ「数値ばかりが 12 個並んでいるセクション」を探す。
    """
    for name, entries in sections:
        if name.lower() == STAT_SECTION:
            return entries
    best = None
    for name, entries in sections:
        if not (8 <= len(entries) <= 14):
            continue
        numeric = sum(1 for _k, v in entries if _to_float(v) is not None)
        if numeric < len(entries) - 1:
            continue
        # 生物の素性が入っているセクションは除く
        if any(k.split("[", 1)[0] in _IDENTITY_KEYS for k, _v in entries):
            continue
        if best is None or abs(len(entries) - 12) < abs(len(best) - 12):
            best = entries
    return best


_IDENTITY_KEYS = frozenset((
    "DinoID1", "DinoID2", "DinoClass", "DinoNameTag", "bIsFemale", "bNeutered",
    "TamerString", "TamedName", "ImprinterName", "CharacterLevel", "ColorSet",
    "DinoImprintingQuality", "RandomMutationsMale", "RandomMutationsFemale"))


def _read_entry(ec, key, value, id_parts):
    """ステータス欄以外の 1 行を読む。種族かレベルが取れたら True。"""
    found_any = False
    ec.raw[key] = value
    base_key = key.split("[", 1)[0]

    if base_key in ("DinoID1", "DinoID2"):
        id_parts.append((base_key, value))
    elif base_key == "DinoClass":
        # 名前は DinoClass だが中身はブループリントパス
        ec.blueprint = value
        found_any = True
    elif base_key == "DinoNameTag":
        ec.species_tag = value
    elif base_key == "bIsFemale":
        ec.sex = FEMALE if value.lower().startswith("t") else MALE
    elif base_key == "bNeutered":
        ec.neutered = value.lower().startswith("t")
    elif base_key == "TamerString":
        # 部族に入っていれば部族名、ソロなら本人の名前が入る
        ec.tamer = value
    elif base_key in ("TamedName", "DinoName"):
        ec.name = value
    elif base_key == "ImprinterName":
        ec.imprinter = value
    elif base_key in ("OwningPlayerName", "TribeName"):
        ec.owner = value
    elif base_key == "RandomMutationsMale":
        ec.mutations_father = int(_to_float(value) or 0)
    elif base_key == "RandomMutationsFemale":
        ec.mutations_mother = int(_to_float(value) or 0)
    elif base_key == "BabyAge":
        ec.baby_age = _to_float(value)
    elif base_key == "CharacterLevel":
        ec.level = int(_to_float(value) or 0)
        found_any = True
    elif base_key == "DinoImprintingQuality":
        ec.imprint = _to_float(value) or 0.0
    elif base_key == "ColorSet":
        idx = _index_of(key)
        if idx is not None and 0 <= idx < 6:
            ec.color_rgba[idx] = _parse_color(value)
    elif base_key in ("DinoTraits", "Traits"):
        ec.traits = [t for t in re.split(r"[;,]", value) if t]
    return found_any


def _index_of(key):
    m = re.search(r"\[(\d+)\]", key)
    return int(m.group(1)) if m else None


def _parse_color(text):
    """ColorSet の値 (R=..,G=..,B=..,A=..) を RGBA のタプルにする。"""
    m = _COLOR_RE.search(text)
    if not m:
        return None
    return tuple(float(m.group(i)) for i in range(1, 5))


def list_export_files(folder):
    """DinoExports フォルダの ini を新しい順に返す。"""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for n in names:
        if not n.lower().endswith(".ini"):
            continue
        p = os.path.join(folder, n)
        try:
            out.append((p, os.path.getmtime(p)))
        except OSError:
            continue
    out.sort(key=lambda t: t[1], reverse=True)
    return [p for p, _ in out]
