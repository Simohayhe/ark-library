# 使わせてもらっているもの

## ARKStatsExtractor (ARK Smart Breeding)

https://github.com/cadon/ARKStatsExtractor — MIT License, Copyright (c) 2015 cadon

このアプリの以下は同プロジェクトを元にしています。

- ステータス値の計算式 (`arklib/stats.py` … `Stats.cs` の移植)
- 表示値からレベルを割り出す逆算 (`arklib/extractor.py` … `Extraction.cs` の移植)
- サーバー倍率の扱い (`arklib/multipliers.py` … `values/ServerMultipliers.cs`)
- 交配の確率などの定数 (`arklib/breeding.py` … `Ark.cs`)
- エクスポートファイルの読み取り (`arklib/importers/` … `importExported/`, `importExportGun/`)
- 種族データ `data/species.json` (同プロジェクトの `values.json` と
  ASA 用 values をマージして生成したもの)

```
MIT License

Copyright (c) 2015 cadon

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

ARK: Survival Ascended / Survival Evolved は Studio Wildcard の商標です。
このアプリは非公式のファンツールで、Studio Wildcard とは関係ありません。
