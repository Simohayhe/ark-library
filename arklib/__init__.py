# -*- coding: utf-8 -*-
"""ARK: Survival Ascended 生物ライブラリ。

ゲーム内の「恐竜のエクスポート」を取り込んで、ステータスのレベル内訳を
割り出し、交配で最高ステータスを作るための組み合わせを提案する。

ステータス計算と逆算の考え方は ARKStatsExtractor (MIT License,
(c) 2015 cadon) の実装を Python に移植したもの。種族データも同プロジェクトの
values.json / ASA-values.json から生成している。
"""

__version__ = "1.12.1"
__all__ = ["ark", "stats", "species", "multipliers", "extractor", "extraction",
           "creature", "library", "breeding", "importers", "paths", "naming",
           "records", "colors", "sounds", "updater"]
