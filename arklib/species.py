# -*- coding: utf-8 -*-
"""種族データと、サーバー倍率を適用した実効ステータス値。

ARKStatsExtractor/ARKBreedingStats/species/Species.cs と
values/Values.cs の ApplyMultipliers() に対応する。
"""
import io
import json
import os
import sys

from . import ark
from .multipliers import (IDX_LEVEL_DOM, IDX_LEVEL_WILD, IDX_TAMING_ADD,
                          IDX_TAMING_MULT, ServerMultipliers)

def _find_data(name):
    """種族データの置き場所。exe に固めたときは展開先から読む。"""
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [os.path.dirname(here)]                 # ふつうに動かしたとき
    base = getattr(sys, "_MEIPASS", None)           # PyInstaller の展開先
    if base:
        roots.insert(0, base)
    roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    for root in roots:
        path = os.path.join(root, "data", name)
        if os.path.isfile(path):
            return path
    return os.path.join(roots[0], "data", name)


DATA_PATH = _find_data("species.json")

INF = float("inf")


class SpeciesStat(object):
    """倍率適用後の 1 ステータス分の係数。"""

    __slots__ = ("base", "inc_wild", "inc_mut", "inc_dom", "add_tamed",
                 "mult_affinity", "as_percentage", "cap")

    def __init__(self):
        self.base = 0.0
        self.inc_wild = 0.0
        self.inc_mut = 0.0
        self.inc_dom = 0.0
        self.add_tamed = 0.0
        self.mult_affinity = 0.0
        self.as_percentage = True
        self.cap = INF

    def __repr__(self):
        return ("<Stat B=%g Iw=%g Im=%g Id=%g Ta=%g Tm=%g>"
                % (self.base, self.inc_wild, self.inc_mut, self.inc_dom,
                   self.add_tamed, self.mult_affinity))


class Species(object):
    def __init__(self, rec):
        self.name = rec["name"]
        self.mod = rec.get("mod") or ""
        self.display_name = rec.get("displayName") or rec["name"]
        self.bp = rec["bp"]
        self.in_asa = bool(rec.get("asa"))
        self.variants = rec.get("variants") or []
        self.is_flyer = bool(rec.get("isFlyer"))
        self.no_gender = bool(rec.get("noGender"))
        self.stats_raw = rec["statsRaw"]
        self.imprint_raw = rec["imprint"]
        self.mutation_mult = rec["mutationMult"]
        self.tbhm = rec.get("tbhm", 1.0)
        self.used_stats = rec.get("usedStats", 0)
        self.breeding = rec.get("breeding")
        self.mates_with = rec.get("matesWith")
        self._stat_names = rec.get("statNames")

        self._caps = {int(k): float(v) for k, v in (rec.get("statCaps") or {}).items()}
        self._additive = {int(k): bool(v) for k, v in (rec.get("additive") or {}).items()}
        self._alt_base = {int(k): float(v) for k, v in (rec.get("altBase") or {}).items()}

        self._displayed_base = rec.get("displayedStats", 0)
        self._skip_wild_base = rec.get("skipWildLevelStats", 0)

        # apply() 後に埋まる
        self.stats = [None] * ark.STATS_COUNT
        self.imprint = list(self.imprint_raw)
        self.displayed_stats = self._displayed_base
        self.skip_wild_level_stats = self._skip_wild_base

    # ---- 表示ヘルパ ----------------------------------------------------

    def stat_name(self, s, lang="ja"):
        """発光生物などステータス名が違う種族に対応した名前。"""
        if self._stat_names:
            custom = self._stat_names.get(str(s)) if isinstance(self._stat_names, dict) else None
            if custom:
                return custom
        return ark.NAMES_JA[s] if lang == "ja" else ark.NAMES_EN[s]

    def uses_stat(self, s):
        return bool(self.used_stats & (1 << s))

    def displays_stat(self, s):
        return bool(self.displayed_stats & (1 << s))

    def can_have_wild_levels(self, s):
        return not (self.skip_wild_level_stats & (1 << s))

    def displayed_stat_indices(self):
        """ゲーム内の並び順で、表示されるステータスの index を返す。"""
        return [s for s in ark.DISPLAY_ORDER if self.displays_stat(s)]

    def is_breedable(self):
        return self.breeding is not None

    # ---- 倍率の適用 ----------------------------------------------------

    def apply(self, sm, game="asa"):
        """サーバー倍率を適用して self.stats を作る。Values.cs ApplyMultipliers 相当。

        sm: ServerMultipliers。single_player_settings が立っていれば先に展開する。
        """
        sm = sm.with_single_player_applied()

        # ASA では移動速度の強化は既定で不可。飛行生物はさらに別フラグ。
        allow_speed = sm.allow_speed_leveling or game != "asa"
        speed_levelable = allow_speed and (sm.allow_flyer_speed_leveling or not self.is_flyer)
        # Values.cs 557 は速度の Id を潰す判定に飛行フラグだけを見る
        use_speed_levelup = sm.allow_flyer_speed_leveling or not self.is_flyer

        for s in range(ark.STATS_COUNT):
            raw = self.stats_raw[s]
            if raw is None:
                self.stats[s] = None
                continue
            mult = sm.stat[s]
            st = SpeciesStat()
            st.base = raw[0]

            # 加算テイムボーナスが負の種族 (ギガノト等) には倍率を掛けない
            add = raw[3]
            st.add_tamed = add * (mult[IDX_TAMING_ADD] if add > 0 else 1.0)
            # 乗算テイムボーナスも同様 (アベレーション変種等)
            aff = raw[4]
            st.mult_affinity = aff * (mult[IDX_TAMING_MULT] if aff > 0 else 1.0)

            if use_speed_levelup or s != ark.SPEED:
                st.inc_dom = raw[2] * mult[IDX_LEVEL_DOM]
            else:
                st.inc_dom = 0.0

            st.inc_wild = raw[1] * mult[IDX_LEVEL_WILD]
            st.inc_mut = st.inc_wild * self.mutation_mult[s]

            st.as_percentage = not self._additive.get(s, False)
            st.cap = self._caps.get(s, INF)
            self.stats[s] = st

        # 速度強化の可否で表示 / 刷り込み / 野生レベルの扱いが変わる
        self.imprint = list(self.imprint_raw)
        self.displayed_stats = self._displayed_base
        self.skip_wild_level_stats = self._skip_wild_base
        bit = 1 << ark.SPEED
        if speed_levelable:
            self.displayed_stats |= bit
            self.skip_wild_level_stats &= ~bit
        else:
            self.displayed_stats &= ~bit
            self.imprint[ark.SPEED] = 0.0
            self.skip_wild_level_stats |= bit

        return self

    def __repr__(self):
        return "<Species %s>" % self.display_name


class SpeciesDB(object):
    def __init__(self, path=DATA_PATH, library_path=None, with_mods=True):
        with io.open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        self.source = data.get("source", {})
        records = list(data["species"])
        self.extra_count = 0
        self.mod_count = 0

        # ARKStatsExtractor のデータにまだ載っていない生物 (同梱)
        extra_path = _find_data("extra_species.json")
        if os.path.isfile(extra_path):
            try:
                with io.open(extra_path, encoding="utf-8-sig") as f:
                    extra = json.load(f).get("species") or []
            except (OSError, ValueError):
                extra = []
            records.extend(extra)
            self.extra_count = len(extra)
        if with_mods:
            # Mod の生物 (%LOCALAPPDATA%\ArkLibrary\mods) を足す。
            # 同じブループリントパスなら Mod 側で上書きする
            from . import modvalues
            extra = modvalues.load_extra_species(library_path)
            if extra:
                by_bp = {r.get("bp"): i for i, r in enumerate(records)}
                for rec in extra:
                    i = by_bp.get(rec.get("bp"))
                    if i is None:
                        records.append(rec)
                    else:
                        records[i] = rec
                self.mod_count = len(extra)
        self.all = [Species(r) for r in records]
        self._by_bp = {sp.bp: sp for sp in self.all}
        self._applied_for = None
        # 未適用の Species を外に出さない。apply() 前に stats を参照すると
        # 全部 None になり、呼び出し側が静かに空振りするため。
        self.apply_multipliers(ServerMultipliers())

    def apply_multipliers(self, sm, game="asa"):
        """全種族に倍率を適用する。倍率を変えたら毎回呼ぶこと。"""
        for sp in self.all:
            sp.apply(sm, game)
        self._applied_for = (sm, game)
        return self

    def by_bp(self, bp):
        return self._by_bp.get(bp)

    def search(self, query, asa_only=True, breedable_only=False, limit=25):
        """名前の部分一致検索。完全一致 → 前方一致 → 部分一致 の順に返す。"""
        q = (query or "").strip().lower()
        pool = [sp for sp in self.all
                if (not asa_only or sp.in_asa)
                and (not breedable_only or sp.is_breedable())]
        if not q:
            return pool[:limit]

        exact, prefix, part = [], [], []
        for sp in pool:
            n = sp.name.lower()
            d = sp.display_name.lower()
            if n == q:
                exact.append(sp)
            elif n.startswith(q) or d.startswith(q):
                prefix.append(sp)
            elif q in n or q in d:
                part.append(sp)
        return (exact + prefix + part)[:limit]

    def get(self, name, asa_only=True):
        """名前でひとつだけ取る。変種なしの本体を優先する。"""
        hits = self.search(name, asa_only=asa_only, limit=200)
        if not hits:
            return None
        for sp in hits:
            if sp.name.lower() == (name or "").lower() and not sp.variants:
                return sp
        return hits[0]

    def __len__(self):
        return len(self.all)
