# -*- coding: utf-8 -*-
"""エクスポートファイルの取り込み。

ファイル 1 個 → Creature 1 体。途中で
    種族の解決 → (必要なら) ステータス逆算 → 変異レベルの推定
をやる。

    ARK 標準エクスポート (.ini)  : 表示値しか入っていないので逆算する
    Export Gun (.sav / .json)    : レベルの内訳が入っているので逆算しない
"""
import os
import re

from .. import ark, breeding, colors
from ..creature import (STATE_BRED, STATE_TAMED, STATE_WILD, UNKNOWN_SEX,
                        Creature)
from . import dino_export_ini, export_gun

SOURCE_INI = "export_ini"
SOURCE_GUN = "export_gun"

_BP_WRAPPER = re.compile(r"^[A-Za-z]*'?(?P<path>/Game/[^']+?)'?$")


class ImportResult(object):
    def __init__(self, path=""):
        self.path = path
        self.creature = None
        self.ok = False
        self.action = ""            # added / updated / skipped
        self.problems = []
        self.notes = []
        self.ambiguous = False
        self.species = None
        self.solutions = []
        self.guesses = []
        self.unknown_blueprint = ""
        self.unknown_tag = ""

    @property
    def label(self):
        if self.creature is not None:
            return self.creature.display_name
        return os.path.basename(self.path)

    def __repr__(self):
        return "<ImportResult %s %s>" % (self.label, "ok" if self.ok else "NG")


def normalize_blueprint(bp):
    """エクスポートに入っているブループリントパスを species.json の形に揃える。

        Blueprint'/Game/PrimalEarth/Dinos/Rex/Rex_Character_BP.Rex_Character_BP_C'
        → /Game/PrimalEarth/Dinos/Rex/Rex_Character_BP.Rex_Character_BP
    """
    if not bp:
        return ""
    s = bp.strip()
    m = _BP_WRAPPER.match(s)
    if m:
        s = m.group("path")
    s = s.strip("'\"")
    if s.endswith("_C"):
        s = s[:-2]
    return s


def resolve_species(species_db, blueprint, fallback_name=""):
    """ブループリントパスから Species を引く。見つからなければ名前で探す。"""
    bp = normalize_blueprint(blueprint)
    sp = species_db.by_bp(bp)
    if sp is not None:
        return sp, bp

    # パスの末尾 (クラス名) だけで照合する。Mod でパスが違うだけの同一種に効く
    if bp:
        cls = bp.split("/")[-1].split(".")[0].lower()
        for cand in species_db.all:
            if cand.bp.split("/")[-1].split(".")[0].lower() == cls:
                return cand, bp

    if fallback_name:
        sp = species_db.get(fallback_name)
        if sp is not None:
            return sp, bp
    return None, bp


# ---- ファイル 1 個の取り込み -------------------------------------------


def detect_kind(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ini":
        return SOURCE_INI
    if ext in (".sav", ".json"):
        return SOURCE_GUN
    return None


def import_file(path, species_db, server_multipliers, library=None, server="",
                game="asa", parent_lookup=None, budget=None):
    """エクスポートファイルを 1 個読んで Creature を作る。

    library を渡すと保存もする (同一個体なら更新)。
    parent_lookup は ark_id → Creature を返す関数。省略時は library から引く。
    """
    res = ImportResult(path)
    kind = detect_kind(path)
    if kind is None:
        res.problems.append("対応していない拡張子です (.ini / .sav / .json)")
        return res

    try:
        if kind == SOURCE_INI:
            ec = dino_export_ini.parse_file(path)
        else:
            ec = export_gun.parse_file(path)
    except Exception as e:                      # 壊れたファイルで落ちないように
        res.problems.append("読み取りに失敗しました: %s" % e)
        return res

    if ec is None:
        res.problems.append("生物のエクスポートファイルではありません")
        return res

    return _build(res, ec, kind, species_db, server_multipliers, library,
                  server, game, parent_lookup, budget)


def _build(res, ec, kind, species_db, sm, library, server, game, parent_lookup,
           budget=None):
    sp, bp = resolve_species(species_db, ec.blueprint, ec.species_tag)
    if sp is None:
        res.problems.append("種族が分かりません: %s"
                            % (ec.species_tag or bp or "?"))
        res.unknown_blueprint = bp
        res.unknown_tag = ec.species_tag
        # 計算式が合う既存種族を探しておく (Mod の生物は使い回しが多い)
        try:
            from .. import guess
            values = {i: v for i, v in enumerate(ec.values)
                      if getattr(ec, "has_value", [True] * 12)[i]}
            res.guesses = guess.guess_species(species_db, ec.level, values, sm,
                                              state=ec.state, imprint=ec.imprint,
                                              game=game, limit=6)
            if res.guesses:
                res.problems.append(guess.describe(res.guesses))
        except Exception:
            pass
        return res
    res.species = sp
    sp.apply(sm, game)

    cr = Creature(
        ark_id=ec.ark_id,
        species_bp=sp.bp,
        species_name=sp.display_name,
        name=ec.name,
        sex=UNKNOWN_SEX if sp.no_gender else ec.sex,
        state=ec.state,
        level=ec.level,
        imprint=ec.imprint,
        mutations_father=ec.mutations_father,
        mutations_mother=ec.mutations_mother,
        mother_ark_id=ec.mother_ark_id,
        father_ark_id=ec.father_ark_id,
        mother_name=ec.mother_name,
        father_name=ec.father_name,
        owner=getattr(ec, "owner", "") or getattr(ec, "tamer", ""),
        tribe=getattr(ec, "tribe", "") or "",
        imprinter=ec.imprinter,
        neutered=ec.neutered,
        baby_age=ec.baby_age,
        server=server,
        source=SOURCE_INI if kind == SOURCE_INI else SOURCE_GUN,
        source_file=ec.path or "",
        values=list(ec.values),
    )

    if kind == SOURCE_GUN:
        cr.levels_wild = list(ec.levels_wild)
        cr.levels_mut = list(ec.levels_mut)
        cr.levels_dom = list(ec.levels_dom)
        cr.taming_eff = ec.taming_eff
        cr.colors = list(ec.colors) + [0] * (6 - len(ec.colors))
        res.notes.append("Export Gun のファイルなのでレベルの内訳をそのまま使いました")
    else:
        from .. import extraction
        values = {s: v for s, v in enumerate(ec.values) if ec.has_value[s]}

        # 同じ個体を前に取り込んでいれば、そのときのテイム効率を使い回す。
        # 効率はテイムしたときに決まって以降変わらないので、これで
        # 「強化レベルを振ったら読めなくなる」を避けられる (しかも速い)
        known_wild = None
        if ec.state == STATE_TAMED and ec.ark_id:
            lookup = parent_lookup
            if lookup is None and library is not None:
                lookup = library.by_ark_id
            if lookup is not None:
                prior = lookup(ec.ark_id)
                if prior is not None and any(prior.levels_wild):
                    known_wild = list(prior.breeding_levels())

        ex = extraction.extract_levels(
            sp, ec.level, values, sm, state=ec.state, imprint=ec.imprint,
            taming_eff=(1.0 if ec.state != STATE_TAMED else None), game=game,
            known_wild=known_wild, budget=budget)
        if not ex.ok and known_wild is not None:
            # 前回の野生レベルと噛み合わない (取り違え等)。総当たりでやり直す
            ex = extraction.extract_levels(
                sp, ec.level, values, sm, state=ec.state, imprint=ec.imprint,
                taming_eff=None, game=game, budget=budget)
        elif known_wild is not None and ex.ok:
            res.notes.append("前に取り込んだときの野生レベルを手がかりにしました")
        res.notes.extend(ex.notes)
        if not ex.ok:
            res.problems.extend(ex.problems)
            res.creature = cr
            return res
        cr.levels_wild = list(ex.levels_wild)
        cr.levels_dom = list(ex.levels_dom)
        cr.taming_eff = ex.taming_eff
        cr.ambiguous = ex.ambiguous
        res.ambiguous = ex.ambiguous
        res.solutions = ex.solutions
        # ini には色そのものが入っているので、いちばん近い定義色の ID に直す
        cr.colors = colors.ids_from_rgba_map(getattr(ec, "color_rgba", None))

    # --- 変異レベルの振り分け (親が居るときだけ) ------------------------
    if cr.is_bred and (cr.mother_ark_id or cr.father_ark_id):
        lookup = parent_lookup
        if lookup is None and library is not None:
            lookup = library.by_ark_id
        if lookup is not None:
            mother = lookup(cr.mother_ark_id)
            father = lookup(cr.father_ark_id)
            if mother is not None or father is not None:
                lw, lm, notes = breeding.infer_mutations(
                    cr.breeding_levels(), mother, father)
                if any(lm):
                    cr.levels_wild = lw
                    cr.levels_mut = lm
                res.notes.extend(notes)

    res.creature = cr
    res.ok = True

    if library is not None:
        _uid, action = library.save(cr)
        res.action = action
        if ec.path:
            library.mark_imported(ec.path, ec.mtime or 0, cr.uid,
                                  "ok" if res.ok else "ng")
    return res


# ---- フォルダまるごと --------------------------------------------------


def import_folder(folder, species_db, server_multipliers, library=None,
                  server="", game="asa", skip_known=True, progress=None):
    """フォルダ内のエクスポートをまとめて取り込む。

    skip_known=True なら、前回と同じ内容のファイルは読み飛ばす。
    progress(done, total, result) を渡すと 1 件ごとに呼ぶ。
    """
    files = []
    try:
        names = sorted(os.listdir(folder))
    except OSError as e:
        return [], "フォルダを開けません: %s" % e
    for n in names:
        if detect_kind(n) is not None:
            files.append(os.path.join(folder, n))

    # 親を先に取り込みたいので古い順に処理する
    files.sort(key=lambda p: _mtime(p))

    results = []
    total = len(files)
    for i, p in enumerate(files, 1):
        if skip_known and library is not None and library.was_imported(p, _mtime(p)):
            continue
        r = import_file(p, species_db, server_multipliers, library, server, game)
        results.append(r)
        if progress is not None:
            progress(i, total, r)
    return results, None


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
