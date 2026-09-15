# -*- coding: utf-8 -*-
"""ゲーム内で付ける名前を組み立てる。

    M H47 S24 W37 M26
    ^ 性別          ^ 近接攻撃力のレベル

先頭が性別 (M / F)、あとは「ステータスの頭文字 + 野生レベル」を並べたもの。
先頭の M (Male) と近接の M (Melee) はかぶるが、位置で読めるのでこのまま。

レベルは **野生 + 変異** を使う。交配で子に渡るのがこの値なので、名前を見れば
そのまま交配の材料として使えるため。自分で振った強化レベルは入れない。
"""
from . import ark
from .creature import FEMALE, GENDERLESS, MALE

# ステータス → 名前に使う頭文字
LETTERS = {
    ark.HEALTH: "H",
    ark.STAMINA: "S",
    ark.OXYGEN: "O",
    ark.FOOD: "F",
    ark.WEIGHT: "W",
    ark.MELEE: "M",
    ark.SPEED: "D",           # Speed の S はスタミナと衝突するので D (Dash)
    ark.CRAFTING_SPEED: "C",
    ark.TEMPERATURE_FORTITUDE: "T",
}

# 既定で名前に入れるステータス
DEFAULT_STATS = [ark.HEALTH, ark.STAMINA, ark.WEIGHT, ark.MELEE]

# 性別なしの種族は U。名前を見たときに「オスでもメスでもない」と分かるように
SEX_LETTER = {MALE: "M", FEMALE: "F", GENDERLESS: "U"}


# ライブラリに登録するときの名前の決め方
APPLY_EMPTY = "empty"    # ゲーム内で名前が無いときだけ、作った名前を入れる
APPLY_ALWAYS = "always"  # いつも作った名前で登録する（ゲーム内の名前は使わない）
APPLY_NEVER = "never"    # 入れない。ゲーム内の名前のまま
APPLIES = (
    (APPLY_EMPTY, "名前が無い個体だけ、作った名前で登録する"),
    (APPLY_ALWAYS, "いつも、作った名前で登録する"),
    (APPLY_NEVER, "入れない（ゲーム内の名前のまま）"),
)


def apply_label(key):
    for k, lbl in APPLIES:
        if k == key:
            return lbl
    return APPLIES[0][1]


# 名前の作り方
MODE_ALL = "all"        # 選んだステータスを全部並べる   M H47 S24 W37 M26
MODE_ZEROS = "zeros"    # 0 のステータスだけ並べる        M O0 F0
MODE_MUTATIONS = "of"   # 変異数と性別だけ (オーバーフロー用)  M 23

MODES = [
    (MODE_ALL, "ぜんぶ", "選んだステータスを並べる"),
    (MODE_ZEROS, "ゼロだけ", "0 になっているステータスだけ並べる"),
    (MODE_MUTATIONS, "OF (変異数)", "性別と変異カウンタだけ"),
]

NO_ZERO_TEXT = "0なし"


def make_name(creature, stat_list=None, with_sex=True, separator=" ",
              mutation_mark="", mode=MODE_ALL):
    """個体から名前を作る。

    creature      : Creature
    stat_list     : 入れるステータス (省略時は 体力/スタミナ/重量/近接)
    with_sex      : 先頭に M / F を付ける
    mutation_mark : 変異が乗っているステータスに付ける印 (例 "*")
    mode          : MODE_ALL / MODE_ZEROS / MODE_MUTATIONS
    """
    stat_list = list(stat_list or DEFAULT_STATS)
    parts = []
    if with_sex:
        letter = SEX_LETTER.get(creature.sex)
        if letter:
            parts.append(letter)

    if mode == MODE_MUTATIONS:
        # オーバーフロー系統は「何代目か」だけ分かればよい。
        # 父側・母側の内訳も出す (どちらが 20 未満かで次に掛ける相手が決まる)
        parts.append("%d" % creature.mutations_total)
        if creature.mutations_father and creature.mutations_mother:
            parts.append("(%d/%d)" % (creature.mutations_father,
                                      creature.mutations_mother))
        return separator.join(parts)

    if mode == MODE_ZEROS:
        zeros = ["%s0" % LETTERS[s] for s in stat_list
                 if s in LETTERS and creature.bl(s) == 0]
        parts.extend(zeros if zeros else [NO_ZERO_TEXT])
        return separator.join(parts)

    for s in stat_list:
        letter = LETTERS.get(s)
        if letter is None:
            continue
        mark = mutation_mark if (mutation_mark and creature.levels_mut[s]) else ""
        parts.append("%s%d%s" % (letter, creature.bl(s), mark))
    return separator.join(parts)


def describe_format(stat_list=None, with_sex=True):
    """設定画面に出す「こうなります」の見本。"""
    stat_list = list(stat_list or DEFAULT_STATS)
    parts = (["M"] if with_sex else []) + [
        "%s%d" % (LETTERS[s], 10 + i * 7)
        for i, s in enumerate(stat_list) if s in LETTERS]
    return " ".join(parts)


def available_stats(species):
    """その種族で名前に入れられるステータス。"""
    return [s for s in species.displayed_stat_indices()
            if s != ark.TORPIDITY and s in LETTERS]
