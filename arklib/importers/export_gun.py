# -*- coding: utf-8 -*-
"""Export Gun (ワンクリックで生物をエクスポートする便利 Mod) のファイルを読む。

標準の「恐竜のエクスポート」との違いは **レベルの内訳がそのまま入っている**
こと。野生 / 強化 / 変異レベルが整数で書かれているので逆算が要らず、
解が複数出てしまう問題も起きない。取り込めるならこちらが確実。

ファイル形式
------------
- `.json` … そのまま JSON。
- `.sav`  … UE の GVAS セーブに JSON 文字列を 1 個詰めたもの。
            ASA: GVAS ヘッダ → "DinoExportGunSave_C" → "StrProperty" → 9 バイト飛ばす
                 → int32 の長さ → UTF-8 (長さが負なら UTF-16)
            ASE: ヘッダが GVAS でない。"StrProperty" の後の並びが少し違う。

サーバー倍率ファイル (DinoExportGunServerSave_C) も同じ入れ物で来るので、
`parse_server_file()` で読める。こちらは Game.ini を触らずに倍率を揃えられる。

実装は ARKStatsExtractor/importExportGun (MIT, (c) 2015 cadon) の
ReadExportFile.cs / ExportGunCreatureFile.cs を参考にした。
"""
import io
import json
import os
import struct

from .. import ark
from ..creature import (FEMALE, MALE, STATE_BRED, STATE_TAMED, STATE_WILD,
                        UNKNOWN_SEX, ark_id_from_parts)

CREATURE_CLASS = b"DinoExportGunSave_C\x00"
SERVER_CLASS = b"DinoExportGunServerSave_C\x00"
STR_PROPERTY = b"StrProperty\x00"

# ステータスは Stats 配列の添字がステータス番号そのまま
OFFSET_STATS = frozenset((ark.MELEE, ark.SPEED, ark.TEMPERATURE_FORTITUDE,
                          ark.CRAFTING_SPEED))


class ExportGunCreature(object):
    """Export Gun の JSON から読めた情報。"""

    def __init__(self, d):
        self.raw = d
        self.blueprint = d.get("BlueprintPath") or ""
        self.species_tag = d.get("SpeciesName") or ""
        self.name = d.get("DinoName") or ""
        self.tribe = d.get("TribeName") or ""
        self.tamer = d.get("TamerString") or ""
        self.owner = d.get("OwningPlayerName") or ""
        self.imprinter = d.get("ImprinterName") or ""
        self.level = int(d.get("BaseCharacterLevel") or 0)
        self.imprint = float(d.get("DinoImprintingQuality") or 0.0)
        self.taming_eff = float(d.get("TameEffectiveness") or 0.0)
        self.sex = FEMALE if d.get("IsFemale") else MALE
        self.neutered = bool(d.get("Neutered"))
        self.mutations_father = int(d.get("RandomMutationsMale") or 0)
        self.mutations_mother = int(d.get("RandomMutationsFemale") or 0)
        self.baby_age = d.get("BabyAge")
        self.next_mating = d.get("NextAllowedMatingTimeDuration")
        self.mutagen = bool(d.get("MutagenApplied"))
        self.traits = list(d.get("Traits") or [])
        self.server_hash = d.get("ServerMultipliersHash") or ""
        self.colors = [int(c) for c in (d.get("ColorSetIndices") or [])][:6]
        self.ark_id = ark_id_from_parts(d.get("DinoID1"), d.get("DinoID2"))

        anc = d.get("Ancestry") or {}
        self.father_name = anc.get("MaleName") or ""
        self.mother_name = anc.get("FemaleName") or ""
        self.father_ark_id = ark_id_from_parts(anc.get("MaleDinoId1") or anc.get("MaleDinoID1"),
                                              anc.get("MaleDinoId2") or anc.get("MaleDinoID2"))
        self.mother_ark_id = ark_id_from_parts(anc.get("FemaleDinoId1") or anc.get("FemaleDinoID1"),
                                              anc.get("FemaleDinoId2") or anc.get("FemaleDinoID2"))

        self.levels_wild = [0] * ark.STATS_COUNT
        self.levels_mut = [0] * ark.STATS_COUNT
        self.levels_dom = [0] * ark.STATS_COUNT
        self.values = [0.0] * ark.STATS_COUNT
        for s, st in enumerate((d.get("Stats") or [])[:ark.STATS_COUNT]):
            if not isinstance(st, dict):
                continue
            self.levels_wild[s] = int(st.get("Wild") or 0)
            self.levels_dom[s] = int(st.get("Tamed") or 0)
            self.levels_mut[s] = int(st.get("Mutated") or 0)
            v = float(st.get("Value") or 0.0)
            # %表示のステータスは 100% からの増分で入っている
            self.values[s] = v + 1.0 if s in OFFSET_STATS else v

        self.path = ""
        self.mtime = None

    @property
    def state(self):
        if self.imprinter or (self.imprint > 0 and self.taming_eff > 0.9999):
            return STATE_BRED
        if not (self.name or self.tribe or self.owner or self.imprinter):
            return STATE_WILD
        return STATE_TAMED

    def __repr__(self):
        return ("<ExportGunCreature %s Lv%d>"
                % (self.species_tag or self.blueprint, self.level))


def read_gvas_json(path):
    """.sav (GVAS もしくは ASE 形式) に埋まっている JSON 文字列を取り出す。

    戻り値は (json_text, game) で game は 'asa' / 'ase'。
    読めないときは (None, エラー文) ではなく例外を投げる。
    """
    with io.open(path, "rb") as f:
        data = f.read()

    if data[:4] == b"GVAS":
        pos = _find_after(data, CREATURE_CLASS, 0)
        if pos is None:
            pos = _find_after(data, SERVER_CLASS, 0)
        if pos is None:
            raise ValueError("DinoExportGunSave_C が見つかりません (Export Gun のファイルではない)")
        sp = _find_after(data, STR_PROPERTY, pos)
        if sp is None:
            raise ValueError("StrProperty が見つかりません")
        p = sp + 9
        (length,) = struct.unpack_from("<i", data, p)
        p += 4
        if length >= 0:
            text = data[p:p + length].decode("utf-8", "replace")
        else:
            text = data[p:p + (-length) * 2].decode("utf-16-le", "replace")
        return text.rstrip("\x00"), "asa"

    # ASE 形式
    sp = _find_after(data, STR_PROPERTY, 0)
    if sp is None:
        raise ValueError("StrProperty が見つかりません")
    p = sp
    (byte_len,) = struct.unpack_from("<i", data, p)
    byte_len -= 4
    p += 4 + 4                      # 長さの後ろの \0 4 バイトを飛ばす
    (char_len,) = struct.unpack_from("<i", data, p)
    p += 4
    if char_len <= 0 and char_len * -2 == byte_len:
        text = data[p:p + byte_len].decode("utf-16-le", "replace")
    else:
        text = data[p:p + byte_len].decode("utf-8", "replace")
    return text.rstrip("\x00"), "ase"


def _find_after(data, pattern, start):
    i = data.find(pattern, start)
    return None if i < 0 else i + len(pattern)


def parse_file(path):
    """Export Gun の生物ファイル (.sav / .json) を読む。生物でなければ None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with io.open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    else:
        text, _game = read_gvas_json(path)

    d = json.loads(text)
    if not isinstance(d, dict) or not d.get("BlueprintPath"):
        return None                 # 倍率ファイルなど
    ec = ExportGunCreature(d)
    ec.path = os.path.abspath(path)
    try:
        ec.mtime = os.path.getmtime(path)
    except OSError:
        pass
    return ec


def parse_server_file(path):
    """Export Gun のサーバー倍率ファイルを読んで dict を返す。生物なら None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with io.open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    else:
        text, _game = read_gvas_json(path)
    d = json.loads(text)
    if not isinstance(d, dict) or d.get("BlueprintPath"):
        return None
    if "WildLevel" not in d and "TameLevel" not in d:
        return None
    return d


def server_multipliers_from_file(path):
    """Export Gun のサーバー倍率ファイルを ServerMultipliers にする。"""
    from ..multipliers import (IDX_LEVEL_DOM, IDX_LEVEL_WILD, IDX_TAMING_ADD,
                               IDX_TAMING_MULT, ServerMultipliers)
    d = parse_server_file(path)
    if d is None:
        return None, None
    sm = ServerMultipliers()
    for key, idx in (("TameAdd", IDX_TAMING_ADD), ("TameAff", IDX_TAMING_MULT),
                     ("TameLevel", IDX_LEVEL_DOM), ("WildLevel", IDX_LEVEL_WILD)):
        arr = d.get(key) or []
        for s, v in enumerate(arr[:ark.STATS_COUNT]):
            try:
                sm.stat[s][idx] = float(v)
            except (TypeError, ValueError):
                continue
    for key, attr in (("TamingSpeedMultiplier", "taming_speed"),
                      ("MatingIntervalMultiplier", "mating_interval"),
                      ("EggHatchSpeedMultiplier", "egg_hatch_speed"),
                      ("BabyMatureSpeedMultiplier", "baby_mature_speed"),
                      ("BabyCuddleIntervalMultiplier", "baby_cuddle_interval"),
                      ("BabyImprintingStatScaleMultiplier", "imprint_stat_scale"),
                      ("BabyImprintAmountMultiplier", "imprint_amount")):
        if key in d:
            try:
                setattr(sm, attr, float(d[key]))
            except (TypeError, ValueError):
                pass
    sm.allow_speed_leveling = bool(d.get("AllowSpeedLeveling"))
    sm.allow_flyer_speed_leveling = bool(d.get("AllowFlyerSpeedLeveling"))
    sm.single_player_settings = bool(d.get("UseSingleplayerSettings"))
    return sm, (d.get("SessionName") or "")
