# -*- coding: utf-8 -*-
"""ライブラリに入る個体 1 体分のデータ。

ステータスは「レベルの内訳」で持つ。表示値はサーバー倍率で変わるが、
レベルの内訳は個体に固定で紐づくため、こちらが個体の本質。

    levels_wild[s]  野生レベル (テイム時点の素の値。交配では親から継承される)
    levels_mut[s]   変異で乗ったレベル (伸び方は野生レベルと同じ)
    levels_dom[s]   テイム後に自分で振ったレベル (継承されない)

交配で子に渡るのは levels_wild + levels_mut なので、この合計を
`breeding_levels()` として扱う。ライブラリの並べ替えも基本これで行う。
"""
import json
import time

from . import ark

MALE = "M"
FEMALE = "F"
# 性別を持たない種族 (メイグアナ・アカティナなど)。ARK 側に雌雄の区別が無い。
# 「まだ分からない」ではなく「そもそも無い」なので、交配の相手からは外さない。
GENDERLESS = "U"
UNKNOWN_SEX = "-"

SEX_JA = {MALE: "♂", FEMALE: "♀", GENDERLESS: "U", UNKNOWN_SEX: "-"}

STATE_WILD = "wild"
STATE_TAMED = "tamed"
STATE_BRED = "bred"

STATE_JA = {STATE_WILD: "野生", STATE_TAMED: "テイム", STATE_BRED: "交配産"}

STATUS_ALIVE = "alive"
STATUS_CRYO = "cryo"
STATUS_DEAD = "dead"
STATUS_OBELISK = "obelisk"

STATUS_JA = {STATUS_ALIVE: "生存", STATUS_CRYO: "クライオ",
             STATUS_DEAD: "死亡", STATUS_OBELISK: "アップロード中"}

# 交配で効いてくるステータス (気絶値は継承の対象だが自分で選べない)
BREEDING_STATS = [ark.HEALTH, ark.STAMINA, ark.OXYGEN, ark.FOOD,
                  ark.WEIGHT, ark.MELEE, ark.SPEED]

# 変異カウンタがこの値以上だと、その親側からの新規変異が起きにくくなる
MUTATION_LIMIT = 20


def _zeros():
    return [0] * ark.STATS_COUNT


class Creature(object):
    __slots__ = (
        "uid", "ark_id", "species_bp", "species_name", "name", "sex", "state",
        "level", "levels_wild", "levels_mut", "levels_dom", "values",
        "imprint", "taming_eff", "mutations_father", "mutations_mother",
        "mother_ark_id", "father_ark_id", "mother_name", "father_name",
        "colors", "owner", "tribe", "imprinter", "server", "status",
        "neutered", "baby_age", "mating_cooldown_until", "tags", "notes",
        "source", "source_file", "added_at", "updated_at", "ambiguous",
    )

    def __init__(self, **kw):
        self.uid = kw.get("uid")
        self.ark_id = int(kw.get("ark_id") or 0)
        self.species_bp = kw.get("species_bp") or ""
        self.species_name = kw.get("species_name") or ""
        self.name = kw.get("name") or ""
        self.sex = kw.get("sex") or UNKNOWN_SEX
        self.state = kw.get("state") or STATE_BRED
        self.level = int(kw.get("level") or 0)
        self.levels_wild = list(kw.get("levels_wild") or _zeros())
        self.levels_mut = list(kw.get("levels_mut") or _zeros())
        self.levels_dom = list(kw.get("levels_dom") or _zeros())
        self.values = list(kw.get("values") or [0.0] * ark.STATS_COUNT)
        self.imprint = float(kw.get("imprint") or 0.0)
        self.taming_eff = kw.get("taming_eff")
        self.mutations_father = int(kw.get("mutations_father") or 0)
        self.mutations_mother = int(kw.get("mutations_mother") or 0)
        self.mother_ark_id = int(kw.get("mother_ark_id") or 0)
        self.father_ark_id = int(kw.get("father_ark_id") or 0)
        self.mother_name = kw.get("mother_name") or ""
        self.father_name = kw.get("father_name") or ""
        self.colors = list(kw.get("colors") or [0] * 6)
        self.owner = kw.get("owner") or ""
        self.tribe = kw.get("tribe") or ""
        self.imprinter = kw.get("imprinter") or ""
        self.server = kw.get("server") or ""
        self.status = kw.get("status") or STATUS_ALIVE
        self.neutered = bool(kw.get("neutered"))
        self.baby_age = kw.get("baby_age")
        self.mating_cooldown_until = kw.get("mating_cooldown_until")
        self.tags = list(kw.get("tags") or [])
        self.notes = kw.get("notes") or ""
        self.source = kw.get("source") or "manual"
        self.source_file = kw.get("source_file") or ""
        self.added_at = kw.get("added_at") or time.time()
        self.updated_at = kw.get("updated_at") or self.added_at
        # 逆算で解が一つに決まらなかった個体。表の値は候補のひとつ
        self.ambiguous = bool(kw.get("ambiguous"))

    # ---- 表示用 --------------------------------------------------------

    @property
    def display_name(self):
        return self.name or ("%s Lv%d" % (self.species_name, self.level))

    @property
    def sex_ja(self):
        return SEX_JA.get(self.sex, "-")

    @property
    def state_ja(self):
        return STATE_JA.get(self.state, self.state)

    @property
    def mutations_total(self):
        return self.mutations_father + self.mutations_mother

    @property
    def is_bred(self):
        return self.state == STATE_BRED

    @property
    def is_genderless(self):
        return self.sex == GENDERLESS

    def can_breed(self):
        """交配に使える個体か (去勢・死亡・性別不明を除く)。

        性別なし (U) の種族は雌雄が無いだけで交配はできるので通す。
        """
        if self.neutered or self.status == STATUS_DEAD:
            return False
        return self.sex in (MALE, FEMALE, GENDERLESS)

    # ---- レベル --------------------------------------------------------

    def breeding_levels(self):
        """子に継承されうるレベル (野生 + 変異)。"""
        return [self.levels_wild[s] + self.levels_mut[s]
                for s in range(ark.STATS_COUNT)]

    def bl(self, s):
        return self.levels_wild[s] + self.levels_mut[s]

    def wild_level_total(self):
        """気絶値を除いたレベル合計 (= 表示レベルの素の部分)。"""
        return sum(self.levels_wild[s] + self.levels_mut[s]
                   for s in range(ark.STATS_COUNT) if s != ark.TORPIDITY)

    def dom_level_total(self):
        return sum(self.levels_dom)

    def base_level(self):
        """孵化/テイム時のレベル (強化分を除く)。"""
        return 1 + self.wild_level_total()

    def mutation_room(self):
        """変異カウンタの余裕。(父側, 母側) それぞれ 20 未満なら変異を狙える。"""
        return (max(0, MUTATION_LIMIT - self.mutations_father),
                max(0, MUTATION_LIMIT - self.mutations_mother))

    # ---- 永続化 --------------------------------------------------------

    def to_row(self):
        return {
            "uid": self.uid,
            "ark_id": self.ark_id,
            "species_bp": self.species_bp,
            "species_name": self.species_name,
            "name": self.name,
            "sex": self.sex,
            "state": self.state,
            "level": self.level,
            "levels_wild": json.dumps(self.levels_wild),
            "levels_mut": json.dumps(self.levels_mut),
            "levels_dom": json.dumps(self.levels_dom),
            "values": json.dumps(self.values),
            "imprint": self.imprint,
            "taming_eff": self.taming_eff,
            "mutations_father": self.mutations_father,
            "mutations_mother": self.mutations_mother,
            "mother_ark_id": self.mother_ark_id,
            "father_ark_id": self.father_ark_id,
            "mother_name": self.mother_name,
            "father_name": self.father_name,
            "colors": json.dumps(self.colors),
            "owner": self.owner,
            "tribe": self.tribe,
            "imprinter": self.imprinter,
            "server": self.server,
            "status": self.status,
            "neutered": 1 if self.neutered else 0,
            "baby_age": self.baby_age,
            "mating_cooldown_until": self.mating_cooldown_until,
            "tags": json.dumps(self.tags, ensure_ascii=False),
            "notes": self.notes,
            "source": self.source,
            "source_file": self.source_file,
            "added_at": self.added_at,
            "updated_at": self.updated_at,
            "ambiguous": 1 if self.ambiguous else 0,
        }

    @classmethod
    def from_row(cls, row):
        d = dict(row)
        for k in ("levels_wild", "levels_mut", "levels_dom", "values", "colors", "tags"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except ValueError:
                    d[k] = None
        d["neutered"] = bool(d.get("neutered"))
        d["ambiguous"] = bool(d.get("ambiguous"))
        return cls(**d)

    def __repr__(self):
        return "<Creature %s %s Lv%d>" % (self.species_name, self.sex_ja, self.level)


def ark_id_from_parts(id1, id2):
    """ゲーム内の DinoID1 / DinoID2 を 64bit の一意な ID にまとめる。

    ARK は表示上この 2 つを文字列連結しているだけなので、表示 ID は
    一意にならない。ARKStatsExtractor と同じ並べ方にしておく。
    """
    try:
        a = int(id1) & 0xFFFFFFFF
        b = int(id2) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return 0
    return (a << 32) | b


def ark_id_display(ark_id):
    """ゲーム内に出る ID 表記 (DinoID1 と DinoID2 の連結) に戻す。"""
    if not ark_id:
        return ""
    return "%d%d" % ((ark_id >> 32) & 0xFFFFFFFF, ark_id & 0xFFFFFFFF)
