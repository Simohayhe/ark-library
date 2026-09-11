# -*- coding: utf-8 -*-
"""交配プラン。「最高ステータスを作るには何と何を合わせればいいか」を出す。

ARK の交配ルール (ARKStatsExtractor/Ark.cs の定数に合わせてある)
---------------------------------------------------------------
* ステータスごとに独立して、**高い方の親の値を 55%**、低い方を 45% で継承する。
  (両親が同じ値ならその値で確定)
* 継承されるのは「野生レベル + 変異レベル」。自分で振った強化レベルは渡らない。
* 変異は 1 回の交配で最大 3 ロール、各ロール 2.5%。少なくとも 1 回起きる確率は
  1-(1-0.025)^3 = 約 7.3%。変異カウンタが 20 以上の親側からは出にくくなる。
* 変異が起きるとランダムな 1 ステータスに **+2 レベル**。

プランの考え方
--------------
1. ライブラリからステータスごとの最高レベル (= 目標) を出す。
2. その最高値を持っている個体を拾い、**最小の組み合わせで全ステータスを
   カバーできる集合**を選ぶ (貪欲法の集合被覆)。ここに選ばれた個体が
   「合わせるべき個体」。
3. 選んだ個体をトーナメント式に 2 匹ずつ掛け合わせていく。各ペアについて
   「必要な形が出る確率」= 0.55^(食い違っているステータス数) を出す。
   世代数は ceil(log2(必要個体数)) が下限になる。

確率は 1 個の卵あたりの値。平均して何匹孵せばいいかは 1/確率 で出す。
"""
import math

from . import ark
from .creature import (BREEDING_STATS, FEMALE, MALE, MUTATION_LIMIT,
                       STATUS_DEAD, Creature)

# 高い方の親の値を継承する確率 (Ark.cs ProbabilityInheritHigherLevel)
P_HIGHER = 0.55
P_LOWER = 1.0 - P_HIGHER
# 変異 1 ロールの確率と、1 回の交配でのロール数
P_MUTATION = 0.025
MUTATION_ROLLS = 3
LEVELS_PER_MUTATION = 2

# 両親とも変異カウンタ 20 未満のときに、少なくとも 1 回変異が起きる確率
P_ONE_MUTATION = 1.0 - (1.0 - P_MUTATION) ** MUTATION_ROLLS
# 片方だけ 20 未満のとき (片親からしか出ないので確率は半分として計算する)
P_ONE_MUTATION_ONE_PARENT = 1.0 - (1.0 - P_MUTATION / 2.0) ** MUTATION_ROLLS


def mutation_probability(a, b):
    """このペアで少なくとも 1 回変異が起きる確率。"""
    sides = 0
    for p in (a, b):
        if p.mutations_total < MUTATION_LIMIT:
            sides += 1
    if sides == 2:
        return P_ONE_MUTATION
    if sides == 1:
        return P_ONE_MUTATION_ONE_PARENT
    return 0.0


# ---- 目標ステータス ----------------------------------------------------


def top_levels(creatures, stat_list=None, include_dead=False):
    """ステータスごとの最高レベル。戻り値 {stat: level}"""
    stat_list = stat_list or BREEDING_STATS
    pool = [c for c in creatures if include_dead or c.status != STATUS_DEAD]
    out = {}
    for s in stat_list:
        levels = [c.bl(s) for c in pool]
        if levels:
            out[s] = max(levels)
    return out


def holders(creatures, tops, include_dead=False):
    """最高レベルを持っている個体。戻り値 {stat: [Creature, ...]}"""
    pool = [c for c in creatures if include_dead or c.status != STATUS_DEAD]
    return {s: [c for c in pool if c.bl(s) == lv] for s, lv in tops.items()}


def covered_stats(creature, tops):
    """この個体が持っている最高ステータスの集合。"""
    return frozenset(s for s, lv in tops.items() if creature.bl(s) >= lv)


def minimal_cover(creatures, tops, breedable_only=True):
    """全ての最高ステータスを網羅する、なるべく少ない個体の組み合わせ。

    貪欲法。同じカバー数なら、レベル合計が高く・変異が少ない個体を優先する。
    """
    pool = [c for c in creatures
            if (not breedable_only or c.can_breed()) and c.status != STATUS_DEAD]
    need = set(tops)
    chosen = []
    while need:
        best = None
        best_key = None
        for c in pool:
            if c in chosen:
                continue
            gain = covered_stats(c, tops) & need
            if not gain:
                continue
            key = (len(gain),
                   sum(c.bl(s) for s in tops),
                   -c.mutations_total)
            if best_key is None or key > best_key:
                best, best_key = c, key
        if best is None:
            break                       # 届かないステータスが残っている
        chosen.append(best)
        need -= covered_stats(best, tops)
    return chosen, need


# ---- ペアの評価 --------------------------------------------------------


class PairPlan(object):
    """1 組のペアの評価結果。"""

    def __init__(self, male, female, tops, stat_list=None):
        self.male = male
        self.female = female
        self.tops = dict(tops or {})
        self.stat_list = list(stat_list or BREEDING_STATS)

        self.best_child = {}      # stat: 最良の場合に子が持つレベル
        self.expected = {}        # stat: 期待レベル
        self.differing = []       # 両親で値が違うステータス
        for s in self.stat_list:
            hi = max(male.bl(s), female.bl(s))
            lo = min(male.bl(s), female.bl(s))
            self.best_child[s] = hi
            self.expected[s] = P_HIGHER * hi + P_LOWER * lo
            if hi != lo:
                self.differing.append(s)

        # 最良の子になるために「高い方の親から貰わないといけない」ステータス。
        # 両親の値が同じステータスは放っておいても確定するので数えない。
        self.needed = list(self.differing)
        # そのうち、ライブラリの最高値に届くもの (表示の補足に使う)
        self.needed_for_top = [s for s in self.differing
                               if self.tops.get(s) is not None
                               and self.best_child[s] >= self.tops[s]]

        self.mutation_probability = mutation_probability(male, female)

    # ---- 確率 ----------------------------------------------------------

    @property
    def probability(self):
        """最良の子 (食い違うステータスを全部高い方から貰う) が出る確率。

        ステータスごとに独立なので 0.55 の n 乗。両親が同じ値しか持って
        いなければ何を引いても同じなので 1.0。
        """
        return P_HIGHER ** len(self.needed) if self.needed else 1.0

    @property
    def eggs_needed(self):
        """平均して何匹孵せばその形が出るか。"""
        p = self.probability
        return 1.0 / p if p > 0 else float("inf")

    @property
    def top_probability(self):
        """**最高値だけ**を高い方の親から貰える確率。

        プランの途中では、最高値に届かないステータスがどちらから来ようと
        あとの世代で上書きされる。そこを数えないぶん現実的な数字になる。
        """
        return P_HIGHER ** len(self.needed_for_top) if self.needed_for_top else 1.0

    @property
    def top_eggs_needed(self):
        p = self.top_probability
        return 1.0 / p if p > 0 else float("inf")

    @property
    def top_count(self):
        """最良の場合に子が持つ「ライブラリ最高値」の数。"""
        return sum(1 for s, lv in self.tops.items()
                   if self.best_child.get(s, 0) >= lv)

    @property
    def best_child_level(self):
        """最良の場合の子の素レベル (1 + 全ステータスのレベル合計)。"""
        return 1 + sum(self.best_child.values())

    @property
    def expected_level(self):
        return 1 + sum(self.expected.values())

    def score(self, weights=None):
        """並べ替え用の点数。最高ステを何個集められるかを最優先にする。"""
        w = weights or {}
        weighted = sum(self.expected[s] * w.get(s, 1.0) for s in self.stat_list)
        return (self.top_count, weighted, self.probability)

    def describe(self, species=None):
        name = (lambda s: species.stat_name(s)) if species else (lambda s: ark.NAMES_JA[s])
        parts = ["%s ♂ × %s ♀" % (self.male.display_name, self.female.display_name)]
        parts.append("  最高ステ %d/%d、最良の子 Lv%d (期待 Lv%.1f)"
                     % (self.top_count, len(self.tops), self.best_child_level,
                        self.expected_level))
        if self.needed:
            parts.append("  狙い通り出る確率 %.1f%% (平均 %.1f 匹) / 分かれ目: %s"
                         % (self.probability * 100, self.eggs_needed,
                            "・".join(name(s) for s in self.needed)))
        else:
            parts.append("  両親の差がないため確実にその形が出る")
        parts.append("  変異の可能性 %.1f%%" % (self.mutation_probability * 100))
        return "\n".join(parts)

    def __repr__(self):
        return "<PairPlan %s x %s top=%d>" % (
            self.male.display_name, self.female.display_name, self.top_count)


def can_mate(a, b, species_db=None):
    """交配できる組み合わせか。"""
    if a is b or not a.can_breed() or not b.can_breed():
        return False
    if {a.sex, b.sex} != {MALE, FEMALE}:
        return False
    if a.species_bp == b.species_bp:
        return True
    # 変種同士など、交配可能な相手が定義されている場合
    if species_db is not None:
        sp = species_db.by_bp(a.species_bp)
        if sp is not None and sp.mates_with:
            return b.species_bp in sp.mates_with
    return False


def rank_pairs(creatures, stat_list=None, weights=None, tops=None,
               species_db=None, limit=30, require_top=0):
    """全ペアを評価して良い順に返す。"""
    stat_list = list(stat_list or BREEDING_STATS)
    pool = [c for c in creatures if c.can_breed() and c.status != STATUS_DEAD]
    tops = tops if tops is not None else top_levels(pool, stat_list)

    males = [c for c in pool if c.sex == MALE]
    females = [c for c in pool if c.sex == FEMALE]
    plans = []
    for m in males:
        for f in females:
            if not can_mate(m, f, species_db):
                continue
            p = PairPlan(m, f, tops, stat_list)
            if p.top_count < require_top:
                continue
            plans.append(p)
    plans.sort(key=lambda p: p.score(weights), reverse=True)
    return plans[:limit] if limit else plans


# ---- 世代プラン --------------------------------------------------------


class PlanStep(object):
    """プラン 1 手。2 匹を掛け合わせて次の個体を作る。"""

    def __init__(self, generation, a, b, pair, result_stats, result_label):
        self.generation = generation
        self.a = a
        self.b = b
        self.pair = pair
        self.result_stats = dict(result_stats)
        self.result_label = result_label

    @property
    def probability(self):
        """この手で「必要な最高値が全部そろった子」が出る確率。"""
        return self.pair.top_probability if self.pair else 1.0

    @property
    def eggs_needed(self):
        return self.pair.top_eggs_needed if self.pair else 1.0

    @property
    def needed_stats(self):
        return self.pair.needed_for_top if self.pair else []


class _Virtual(Creature):
    """プラン上の「これから作る子」。実在しないので性別は未定。"""

    def __init__(self, species_bp, species_name, label, levels, sex="-"):
        Creature.__init__(self, species_bp=species_bp, species_name=species_name,
                          name=label, sex=sex, state="bred")
        for s, lv in levels.items():
            self.levels_wild[s] = lv
        self.virtual = True

    def can_breed(self):
        return True


def plan_to_best(creatures, stat_list=None, species_db=None, max_generations=8,
                 breedable_only=True):
    """最高ステータスを 1 匹に集めるまでの手順を組む。

    戻り値 dict:
        tops        {stat: level}   目標
        cover       [Creature]      合わせるべき個体
        missing     set             ライブラリに持ち主が居ないステータス
        steps       [PlanStep]      手順 (世代順)
        generations int             必要な世代数
        total_eggs  float           各手の平均必要数の合計 (目安)
        final       Creature        最終的に出来る個体 (仮想)
    """
    stat_list = list(stat_list or BREEDING_STATS)
    pool = [c for c in creatures if c.status != STATUS_DEAD]
    if breedable_only:
        pool = [c for c in pool if c.can_breed()]
    tops = top_levels(pool, stat_list)
    cover, missing = minimal_cover(pool, tops, breedable_only)

    species_bp = cover[0].species_bp if cover else ""
    species_name = cover[0].species_name if cover else ""

    steps = []
    # 現世代の持ち駒。実個体と仮想個体が混ざる
    current = list(cover)
    generation = 0
    while len(current) > 1 and generation < max_generations:
        generation += 1
        nxt = []
        used = [False] * len(current)
        # カバー範囲が補い合うペアから順に組む
        order = _pairing_order(current, tops, stat_list, species_db)
        for i, j in order:
            if used[i] or used[j]:
                continue
            a, b = current[i], current[j]
            m, f = _as_male_female(a, b)
            pair = PairPlan(m, f, tops, stat_list)
            child_levels = dict(pair.best_child)
            label = "第%d世代の子%d" % (generation, len(nxt) + 1)
            child = _Virtual(a.species_bp or species_bp,
                             a.species_name or species_name, label, child_levels)
            steps.append(PlanStep(generation, a, b, pair, child_levels, label))
            nxt.append(child)
            used[i] = used[j] = True
        # 余った個体はそのまま次の世代へ持ち越す
        for k, c in enumerate(current):
            if not used[k]:
                nxt.append(c)
        if len(nxt) >= len(current):
            break                       # これ以上まとめられない
        current = nxt

    final = current[0] if current else None
    total_eggs = sum(st.eggs_needed for st in steps if st.eggs_needed < 1e6)
    return {
        "tops": tops,
        "cover": cover,
        "missing": missing,
        "steps": steps,
        "generations": generation,
        "total_eggs": total_eggs,
        "final": final,
        "species_bp": species_bp,
        "species_name": species_name,
    }


def _pairing_order(pool, tops, stat_list, species_db):
    """組む順番。お互いの足りないところを埋め合うペアを先に。"""
    scored = []
    n = len(pool)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = pool[i], pool[j]
            ca = covered_stats(a, tops)
            cb = covered_stats(b, tops)
            union = ca | cb
            overlap = len(ca & cb)
            diff = sum(1 for s in stat_list if a.bl(s) != b.bl(s))
            # カバー数が多く、無駄な重複が少なく、食い違いが少ない順
            scored.append(((len(union), -overlap, -diff), i, j))
    scored.sort(reverse=True)
    return [(i, j) for _k, i, j in scored]


def _as_male_female(a, b):
    if a.sex == MALE or b.sex == FEMALE:
        return a, b
    return b, a


# ---- 変異狙い ----------------------------------------------------------


def mutation_pairs(creatures, stat_list=None, tops=None, species_db=None, limit=10):
    """変異を狙うのに向いたペア。

    理想は「片方が完成個体 (最高ステを全部持っている)」かつ「両親の変異
    カウンタが 20 未満」。完成個体同士なら食い違いがないので、生まれた子が
    親より高ければそれが変異と分かる。
    """
    stat_list = list(stat_list or BREEDING_STATS)
    pool = [c for c in creatures if c.can_breed() and c.status != STATUS_DEAD]
    tops = tops if tops is not None else top_levels(pool, stat_list)
    out = []
    for m in [c for c in pool if c.sex == MALE]:
        for f in [c for c in pool if c.sex == FEMALE]:
            if not can_mate(m, f, species_db):
                continue
            p = PairPlan(m, f, tops, stat_list)
            if p.mutation_probability <= 0:
                continue
            out.append(p)
    # 変異確率 → 完成度 → 食い違いの少なさ の順
    out.sort(key=lambda p: (p.mutation_probability, p.top_count, -len(p.differing)),
             reverse=True)
    return out[:limit] if limit else out


# ---- 変異レベルの推定 --------------------------------------------------


def infer_mutations(child_breeding_levels, mother, father, stat_list=None):
    """子のレベルと両親から、どのステータスが変異したかを推定する。

    交配産の子は各ステータスをどちらかの親から貰うので、親の値と一致しない
    ぶんは変異 (+2 レベル) と考えられる。

    戻り値 (levels_wild, levels_mut, notes)
    """
    stat_list = list(stat_list or range(ark.STATS_COUNT))
    lw = [0] * ark.STATS_COUNT
    lm = [0] * ark.STATS_COUNT
    notes = []
    for s in stat_list:
        if s == ark.TORPIDITY:
            continue
        child = child_breeding_levels[s]
        exact = []
        mutated = []
        for p in (mother, father):
            if p is None:
                continue
            if p.bl(s) == child:
                exact.append(p)
            else:
                d = child - p.bl(s)
                if d > 0 and d % LEVELS_PER_MUTATION == 0:
                    mutated.append((p, d // LEVELS_PER_MUTATION))
        if exact:
            p = exact[0]
            lw[s] = p.levels_wild[s]
            lm[s] = p.levels_mut[s]
        elif mutated:
            p, count = min(mutated, key=lambda t: t[1])
            lw[s] = p.levels_wild[s]
            lm[s] = p.levels_mut[s] + count * LEVELS_PER_MUTATION
            notes.append("%s に変異 %d 回 (+%d レベル)"
                         % (ark.NAMES_JA[s], count, count * LEVELS_PER_MUTATION))
        else:
            # 親の情報と噛み合わない。全部野生レベル扱いにしておく
            lw[s] = child
            if mother is not None or father is not None:
                notes.append("%s は両親の値と噛み合いません (親が古い可能性)"
                             % ark.NAMES_JA[s])
    return lw, lm, notes


# ---- サマリ ------------------------------------------------------------


def library_summary(creatures, stat_list=None):
    """種族ごとの到達状況。ライブラリ画面の見出し用。"""
    stat_list = list(stat_list or BREEDING_STATS)
    pool = [c for c in creatures if c.status != STATUS_DEAD]
    tops = top_levels(pool, stat_list)
    best_possible = 1 + sum(tops.values())
    have_all = [c for c in pool
                if all(c.bl(s) >= lv for s, lv in tops.items())]
    return {
        "count": len(pool),
        "males": sum(1 for c in pool if c.sex == MALE),
        "females": sum(1 for c in pool if c.sex == FEMALE),
        "tops": tops,
        "best_possible_level": best_possible,
        "complete": have_all,
        "max_mutations": max([c.mutations_total for c in pool] or [0]),
    }


def generations_needed(holder_count):
    """必要個体数から最短世代数。"""
    if holder_count <= 1:
        return 0
    return int(math.ceil(math.log(holder_count, 2)))
