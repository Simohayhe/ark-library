# -*- coding: utf-8 -*-
"""サーバー倍率。

ARKStatsExtractor/ARKBreedingStats/values/ServerMultipliers.cs に対応する。

statMultipliers[statIndex][i] の i は
    0: TamingAdd   … PerLevelStatsMultiplier_DinoTamed_Add
    1: TamingMult  … PerLevelStatsMultiplier_DinoTamed_Affinity
    2: LevelDom    … PerLevelStatsMultiplier_DinoTamed
    3: LevelWild   … PerLevelStatsMultiplier_DinoWild
"""
import io
import json
import os
import re

from . import ark

IDX_TAMING_ADD = 0
IDX_TAMING_MULT = 1
IDX_LEVEL_DOM = 2
IDX_LEVEL_WILD = 3
IDX_NAMES = ("TamingAdd", "TamingMult", "LevelDom", "LevelWild")

# ini のキー名 → statMultipliers の第2添字
INI_STAT_KEYS = {
    "perlevelstatsmultiplier_dinotamed_add": IDX_TAMING_ADD,
    "perlevelstatsmultiplier_dinotamed_affinity": IDX_TAMING_MULT,
    "perlevelstatsmultiplier_dinotamed": IDX_LEVEL_DOM,
    "perlevelstatsmultiplier_dinowild": IDX_LEVEL_WILD,
}

# ini のキー名 → 属性名 (交配・テイム系)
INI_SCALAR_KEYS = {
    "tamingspeedmultiplier": "taming_speed",
    "matingintervalmultiplier": "mating_interval",
    "egghatchspeedmultiplier": "egg_hatch_speed",
    "babymaturespeedmultiplier": "baby_mature_speed",
    "babycuddleintervalmultiplier": "baby_cuddle_interval",
    "babyimprintingstatscalemultiplier": "imprint_stat_scale",
    "babyimprintamountmultiplier": "imprint_amount",
}

INI_BOOL_KEYS = {
    "allowflyerspeedleveling": "allow_flyer_speed_leveling",
    "ballowflyerspeedleveling": "allow_flyer_speed_leveling",
    "busesingleplayersettings": "single_player_settings",
}

_INI_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\s*(\d+)\s*\])?\s*=\s*(.+?)\s*$")


class ServerMultipliers(object):
    """サーバーの倍率一式。既定はバニラ (全部 1)。"""

    def __init__(self):
        # [12][4] すべて 1.0
        self.stat = [[1.0, 1.0, 1.0, 1.0] for _ in range(ark.STATS_COUNT)]

        self.taming_speed = 1.0
        self.mating_interval = 1.0
        self.egg_hatch_speed = 1.0
        self.baby_mature_speed = 1.0
        self.baby_cuddle_interval = 1.0
        self.imprint_stat_scale = 1.0   # BabyImprintingStatScaleMultiplier
        self.imprint_amount = 1.0       # BabyImprintAmountMultiplier (刷り込み%の付き方)

        self.allow_speed_leveling = False       # ASA 既定では移動速度は強化不可
        self.allow_flyer_speed_leveling = False
        self.single_player_settings = False

    # ---- 生成 ----------------------------------------------------------

    def copy(self):
        m = ServerMultipliers()
        m.stat = [list(row) for row in self.stat]
        for k, v in self.__dict__.items():
            if k != "stat":
                setattr(m, k, v)
        return m

    @classmethod
    def official(cls, game="asa"):
        """公式サーバーの既定値。バニラ(全部1)ではないので注意。

        体力と近接攻撃力だけ TamingAdd / TamingMult / LevelDom が下げられている。
        (ARKStatsExtractor/json/serverMultipliers.json の "official" プリセット)
        """
        m = cls()
        m.stat[ark.HEALTH] = [0.14, 0.44, 0.2, 1.0]
        m.stat[ark.MELEE] = [0.14, 0.44, 0.17, 1.0]
        if game == "asa":
            m.allow_speed_leveling = False
        else:
            m.allow_speed_leveling = True
            m.allow_flyer_speed_leveling = False
        return m

    @classmethod
    def single_player_preset(cls):
        """シングルプレイヤー設定 (bUseSingleplayerSettings) の補正。

        これは単体で使うものではなく、他の倍率に「掛ける」ためのもの。
        """
        m = cls()
        m.stat[ark.HEALTH] = [3.57142857, 2.27272727, 2.125, 1.0]
        m.stat[ark.MELEE] = [3.57142857, 2.27272727, 2.35294118, 1.0]
        m.taming_speed = 2.5
        m.mating_interval = 0.125
        m.egg_hatch_speed = 10.0
        m.baby_mature_speed = 36.799
        m.baby_cuddle_interval = 0.167
        return m

    def with_single_player_applied(self):
        """single_player_settings が立っていれば SP 補正を掛けた新しい倍率を返す。

        Values.cs ApplyMultipliers() と同じ扱い (既存の倍率に乗算する)。
        """
        if not self.single_player_settings:
            return self
        sp = ServerMultipliers.single_player_preset()
        m = self.copy()
        for s in range(ark.STATS_COUNT):
            for i in range(4):
                m.stat[s][i] *= sp.stat[s][i]
        m.taming_speed *= sp.taming_speed
        m.mating_interval *= sp.mating_interval
        m.egg_hatch_speed *= sp.egg_hatch_speed
        m.baby_mature_speed *= sp.baby_mature_speed
        m.baby_cuddle_interval *= sp.baby_cuddle_interval
        m.single_player_settings = False  # 適用済み
        return m

    # ---- 入出力 --------------------------------------------------------

    @classmethod
    def from_ini(cls, *paths):
        """Game.ini / GameUserSettings.ini から読み取る。

        セクションは見ずにキー名だけで拾う。どちらのファイルに書かれていても、
        また ASA / ASE のどちらの流儀でも取れるようにするため。
        引数は 1 つでも複数でもよい (後のファイルが優先)。
        """
        m = cls()
        found = []
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            with io.open(path, encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    if not line.strip() or line.lstrip().startswith((";", "#", "[")):
                        continue
                    mo = _INI_LINE.match(line)
                    if not mo:
                        continue
                    key, index, value = mo.group(1).lower(), mo.group(2), mo.group(3)

                    if key in INI_STAT_KEYS and index is not None:
                        s = int(index)
                        if 0 <= s < ark.STATS_COUNT:
                            try:
                                m.stat[s][INI_STAT_KEYS[key]] = float(value)
                                found.append("%s[%d]" % (key, s))
                            except ValueError:
                                pass
                    elif key in INI_SCALAR_KEYS:
                        try:
                            setattr(m, INI_SCALAR_KEYS[key], float(value))
                            found.append(key)
                        except ValueError:
                            pass
                    elif key in INI_BOOL_KEYS:
                        setattr(m, INI_BOOL_KEYS[key], value.strip().lower() in ("true", "1"))
                        found.append(key)
        m.loaded_keys = found
        return m

    def to_dict(self):
        d = {"statMultipliers": [list(r) for r in self.stat]}
        for k, v in sorted(self.__dict__.items()):
            if k not in ("stat", "loaded_keys"):
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d):
        m = cls()
        sm = d.get("statMultipliers")
        if sm:
            for s in range(min(len(sm), ark.STATS_COUNT)):
                if sm[s]:
                    m.stat[s] = [float(x) for x in sm[s]]
        for k, v in d.items():
            if k != "statMultipliers" and hasattr(m, k):
                setattr(m, k, v)
        return m

    def save(self, path):
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, path):
        with io.open(path, encoding="utf-8-sig") as f:
            return cls.from_dict(json.load(f))

    # ---- 表示 ----------------------------------------------------------

    def describe(self):
        lines = []
        head = "%-14s %9s %9s %9s %9s" % ("ステータス", "TameAdd", "TameAff", "Tamed", "Wild")
        lines.append(head)
        for s in ark.DISPLAY_ORDER:
            row = self.stat[s]
            if row == [1.0, 1.0, 1.0, 1.0]:
                continue
            lines.append("%-14s %9g %9g %9g %9g" % (ark.NAMES_JA[s], row[0], row[1], row[2], row[3]))
        if len(lines) == 1:
            lines.append("  (ステータス倍率はすべて 1)")
        lines.append("")
        lines.append("刷り込みステータス倍率 : %g" % self.imprint_stat_scale)
        lines.append("孵化速度 / 成長速度    : %g / %g" % (self.egg_hatch_speed, self.baby_mature_speed))
        lines.append("刷り込み間隔 / 交配CD  : %g / %g" % (self.baby_cuddle_interval, self.mating_interval))
        lines.append("テイム速度             : %g" % self.taming_speed)
        lines.append("飛行生物の速度強化     : %s" % ("可" if self.allow_flyer_speed_leveling else "不可"))
        if self.single_player_settings:
            lines.append("※ シングルプレイヤー設定 ON")
        return "\n".join(lines)

    def __repr__(self):
        return "<ServerMultipliers wild=%s dom=%s ibm=%g>" % (
            self.stat[ark.HEALTH][IDX_LEVEL_WILD],
            self.stat[ark.HEALTH][IDX_LEVEL_DOM],
            self.imprint_stat_scale)
