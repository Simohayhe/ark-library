# -*- coding: utf-8 -*-
"""ARK ライブラリ - 起動口。

    python ark_library.py                既定の場所の DB を開く
    python ark_library.py path\to.db      DB を指定して開く
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.app import main

if __name__ == "__main__":
    sys.exit(main())
