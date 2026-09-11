# -*- coding: utf-8 -*-
"""音まわり (ARK ブリーディングタイマーから流用)。

* 内蔵音は起動時に自前で合成して WAV を作る（音源ファイル同梱不要・音量を焼き込める）
* 自分の mp3 / wav / m4a なども指定できる（MCI 経由なので音量も効く）
* 追加ライブラリ不要

音の指定文字列 (spec):
    "builtin:bell"   内蔵音
    "C:\\path\\to\\my.mp3"  自分のファイル
    ""               既定音を使う
"""
from __future__ import annotations

import array
import math
import os
import struct
import threading
import wave

try:
    import winsound
except ImportError:
    winsound = None

SR = 22050

# ---------------------------------------------------------------- 内蔵音の定義
# (表示名, 音符リスト, 全体長)
#   音符 = (開始秒, 周波数, 音量, 音色)
BUILTIN = {
    "bell": ("ちりん（ベル）", [
        (0.00, 1318.5, 1.0, "bell"),
        (0.26, 1108.7, 0.8, "bell"),
    ], 1.8),
    "marimba": ("ぽろん（マリンバ）", [
        (0.00, 523.3, 1.0, "marimba"),
        (0.11, 659.3, 0.9, "marimba"),
        (0.22, 784.0, 0.9, "marimba"),
        (0.33, 1046.5, 0.8, "marimba"),
    ], 1.3),
    "chime": ("きらきら（チャイム）", [
        (0.00, 784.0, 0.9, "chime"),
        (0.13, 987.8, 0.9, "chime"),
        (0.26, 1174.7, 0.9, "chime"),
        (0.39, 1568.0, 1.0, "chime"),
    ], 2.2),
    "pico": ("ぴこぴこ（8bit）", [
        (0.00, 523.3, 0.8, "square"),
        (0.09, 659.3, 0.8, "square"),
        (0.18, 784.0, 0.8, "square"),
        (0.27, 1046.5, 0.9, "square"),
        (0.42, 784.0, 0.8, "square"),
        (0.51, 1046.5, 0.9, "square"),
    ], 1.1),
    "pon": ("ぽん（やわらか）", [
        (0.00, 440.0, 1.0, "soft"),
        (0.14, 659.3, 0.7, "soft"),
    ], 1.4),
    "alarm": ("アラーム（強め）", [
        (0.00, 880.0, 1.0, "square"),
        (0.18, 1174.7, 1.0, "square"),
        (0.36, 880.0, 1.0, "square"),
        (0.54, 1174.7, 1.0, "square"),
        (0.72, 880.0, 1.0, "square"),
        (0.90, 1174.7, 1.0, "square"),
    ], 1.5),
    # --- 取り込みイベント用 ---
    "ok": ("ぽん（取り込み成功）", [
        (0.00, 659.3, 0.85, "marimba"),
        (0.08, 987.8, 0.75, "marimba"),
    ], 0.9),
    "ng": ("ぶぶー（失敗）", [
        (0.00, 233.1, 1.0, "square"),
        (0.20, 185.0, 1.0, "square"),
    ], 1.0),
    "record": ("ファンファーレ（記録更新）", [
        (0.00, 784.0, 0.9, "chime"),
        (0.10, 1046.5, 0.9, "chime"),
        (0.20, 1318.5, 0.95, "chime"),
        (0.32, 1568.0, 1.0, "chime"),
        (0.52, 1568.0, 0.9, "bell"),
        (0.60, 2093.0, 0.8, "bell"),
    ], 2.4),
    "tie": ("ちりん（最高と同じ）", [
        (0.00, 1318.5, 0.85, "bell"),
    ], 1.4),
    "pipi": ("ピピピ（電子音）", [
        (0.00, 2093.0, 0.9, "beep"),
        (0.16, 2093.0, 0.9, "beep"),
        (0.32, 2093.0, 0.9, "beep"),
    ], 0.9),
}

# 音色 = (倍音[(比, 音量, 減衰倍率)], 減衰時定数, アタック秒, 波形)
VOICES = {
    "bell":    ([(1, 1.0, 1.0), (2.0, 0.55, 0.7), (2.76, 0.32, 0.5), (5.4, 0.12, 0.3)],
                1.10, 0.004, "sine"),
    "chime":   ([(1, 1.0, 1.0), (2.7, 0.35, 0.6), (4.9, 0.14, 0.4)],
                0.95, 0.004, "sine"),
    "marimba": ([(1, 1.0, 1.0), (4.0, 0.30, 0.35)], 0.30, 0.002, "sine"),
    "soft":    ([(1, 1.0, 1.0), (3.0, 0.10, 0.6)], 0.55, 0.025, "sine"),
    "square":  ([(1, 1.0, 1.0)], 0.13, 0.003, "square"),
    "beep":    ([(1, 1.0, 1.0)], 0.055, 0.002, "sine"),
}

DEFAULT_DONE = "builtin:bell"
DEFAULT_PREWARN = "builtin:pon"

# 取り込みのときに鳴らす 4 種類。設定で差し替えられる
EVENTS = [
    ("success", "取り込み成功", "builtin:ok"),
    ("fail", "取り込み失敗", "builtin:ng"),
    ("record", "自己ベスト更新", "builtin:record"),
    ("tie", "いまの最高と同じ", "builtin:tie"),
]

EVENT_DEFAULTS = {key: spec for key, _label, spec in EVENTS}


def builtin_choices():
    """[(spec, 表示名), ...]"""
    return [("builtin:%s" % k, v[0]) for k, v in BUILTIN.items()]


def label_of(spec):
    if not spec:
        return "既定の音"
    if spec.startswith("builtin:"):
        got = BUILTIN.get(spec.split(":", 1)[1])
        return got[0] if got else spec
    return os.path.basename(spec)


# ---------------------------------------------------------------- 合成
def _render(notes, total):
    """フルボリュームの波形を作る（重いので1音源につき一度だけ）。"""
    n = int(SR * total)
    buf = [0.0] * n
    sin = math.sin
    exp = math.exp
    two_pi = 2.0 * math.pi
    for t0, freq, amp, voice in notes:
        harm, tau, attack, wave_kind = VOICES[voice]
        start = int(t0 * SR)
        length = min(n - start, int(SR * tau * 8))
        for i in range(max(0, length)):
            t = i / SR
            base = exp(-t / tau)
            if base < 2e-4:
                break
            atk = min(1.0, t / attack) if attack > 0 else 1.0
            s = 0.0
            for ratio, ha, tscale in harm:
                w = two_pi * freq * ratio * t
                if wave_kind == "square":
                    v = 0.55 if sin(w) >= 0 else -0.55
                else:
                    v = sin(w)
                s += v * ha * exp(-t / (tau * tscale))
            buf[start + i] += s * amp * atk

    peak = max((abs(v) for v in buf), default=0.0)
    if peak <= 0:
        return buf
    gain = 0.92 / peak
    fade = max(1, int(SR * 0.02))
    for i in range(n):
        g = gain * (min(1.0, (n - i) / fade))
        buf[i] *= g
    return buf


def _write_wav(path, samples):
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(samples.tobytes())
    os.replace(tmp, path)


def _read_wav(path):
    with wave.open(path, "rb") as w:
        data = w.readframes(w.getnframes())
    a = array.array("h")
    a.frombytes(data)
    return a


def _master_path(name, cache_dir):
    return os.path.join(cache_dir, "%s_master.wav" % name)


def ensure_master(name, cache_dir):
    """フルボリュームの元音を返す（無ければ合成してキャッシュ）。"""
    os.makedirs(cache_dir, exist_ok=True)
    path = _master_path(name, cache_dir)
    if not os.path.exists(path):
        _label, notes, total = BUILTIN[name]
        buf = _render(notes, total)
        samples = array.array("h", (int(max(-1.0, min(1.0, v)) * 32767) for v in buf))
        _write_wav(path, samples)
    return path


def ensure_builtin(name, volume, cache_dir):
    """指定音量の内蔵音WAVのパスを返す。元音を読んで音量を掛けるだけなので速い。"""
    if name not in BUILTIN:
        name = "bell"
    vol_pct = int(round(max(0.0, min(1.0, volume)) * 100))
    master = ensure_master(name, cache_dir)
    if vol_pct >= 100:
        return master
    path = os.path.join(cache_dir, "%s_%03d.wav" % (name, vol_pct))
    if not os.path.exists(path):
        g = vol_pct / 100.0
        src = _read_wav(master)
        _write_wav(path, array.array("h", (int(v * g) for v in src)))
    return path


def prebuild(cache_dir):
    """全内蔵音の元音をまとめて用意する（起動時にバックグラウンドで呼ぶ）。"""
    for name in BUILTIN:
        try:
            ensure_master(name, cache_dir)
        except Exception:
            pass


# ---------------------------------------------------------------- 再生
_MCI_ALIAS = "arklib_sound"
_mci_lock = threading.Lock()


def _mci(cmd):
    import ctypes

    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, None)
    return err, buf.value


def _play_file(path, volume):
    """mp3等を MCI で再生（音量指定つき）。失敗したら False。"""
    ext = os.path.splitext(path)[1].lower()
    dev = "waveaudio" if ext == ".wav" else "mpegvideo"
    with _mci_lock:
        _mci("close %s" % _MCI_ALIAS)
        err, _ = _mci('open "%s" type %s alias %s' % (path, dev, _MCI_ALIAS))
        if err:
            err, _ = _mci('open "%s" alias %s' % (path, _MCI_ALIAS))
            if err:
                return False
        _mci("setaudio %s volume to %d" % (_MCI_ALIAS, int(max(0.0, min(1.0, volume)) * 1000)))
        err, _ = _mci("play %s" % _MCI_ALIAS)
        return err == 0


def stop():
    try:
        with _mci_lock:
            _mci("close %s" % _MCI_ALIAS)
    except Exception:
        pass
    if winsound is not None:
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


def play(spec, volume, cache_dir, fallback="builtin:bell"):
    """spec の音を非同期で鳴らす。呼び出しは即座に返る。"""
    if volume <= 0:
        return
    spec = spec or fallback
    try:
        if spec.startswith("builtin:"):
            path = ensure_builtin(spec.split(":", 1)[1], volume, cache_dir)
            if winsound is not None:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            _play_file(path, 1.0)
            return
        if os.path.isfile(spec):
            if _play_file(spec, volume):
                return
        # だめだったら内蔵音で鳴らす
        path = ensure_builtin(fallback.split(":", 1)[-1], volume, cache_dir)
        if winsound is not None:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        if winsound is not None:
            try:
                winsound.MessageBeep()
            except Exception:
                pass


def play_async(spec, volume, cache_dir, fallback="builtin:bell"):
    threading.Thread(target=play, args=(spec, volume, cache_dir, fallback),
                     daemon=True).start()
