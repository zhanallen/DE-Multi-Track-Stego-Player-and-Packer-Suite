"""分析分塊音軌在切點的取樣數與時間對齊：量測 chunk0 / chunk1 / 合併檔多出的取樣、切點前後相對原始音軌的延遲，以及切點附近的靜音缺口。

用法：python src/test/verify/verify_chunk_boundary.py <data_dir> [--lang de-DE] [--initial-sec 3.0] [--prefix audio_] > <data_dir>/boundary_log.txt
需先執行 verify_audio.py 產生 <data_dir>/extracted/。
"""
import io
import os
import sys
import argparse
import tempfile
import contextlib
import subprocess

import numpy as np

from _common import FF, sha256, print_header
import audio_chunker

SR = 44100


def pcm(path):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.int16).reshape(-1, 2).astype(np.float64)


def lag(ref, sig, ref_start, win, max_lag):
    """回傳 sig 相對 ref 的延遲（取樣數，正值代表 sig 較晚）與正規化相關係數。"""
    a = ref[ref_start:ref_start + win].mean(axis=1)
    b = sig[ref_start - max_lag:ref_start + win + max_lag].mean(axis=1)
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)[:2 * max_lag + 1]
    k = int(np.argmax(c))
    seg = b[k:k + win]
    r = float(np.dot(a, seg) / (np.linalg.norm(a) * np.linalg.norm(seg) + 1e-12))
    return k - max_lag, r


def silent_runs(x, start, stop, thr=8.0, min_len=64):
    """回傳 [start, stop) 內 |x| < thr 且長度 >= min_len 的連續區段 (起點, 長度)。"""
    m = np.abs(x[start:stop]).max(axis=1) < thr
    runs, i = [], 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if j - i >= min_len:
                runs.append((start + i, j - i))
            i = j
        else:
            i += 1
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--lang", default="de-DE")
    ap.add_argument("--initial-sec", type=float, default=3.0)
    ap.add_argument("--prefix", default="audio_")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    cut = int(round(a.initial_sec * SR))
    orig_p = os.path.join(a.data_dir, f"{a.prefix}{a.lang}.mp3")
    ex = os.path.join(a.data_dir, "extracted")
    ex_c0, ex_c1, ex_full = (os.path.join(ex, f"{a.lang}{s}.mp3") for s in ("_chunk0", "_chunk1", ""))
    for p in (orig_p, ex_c0, ex_c1, ex_full):
        print(f"# sha256 {os.path.relpath(p, a.data_dir)} = {sha256(p)}")

    tmp = tempfile.mkdtemp()
    with contextlib.redirect_stdout(io.StringIO()):
        lc0, lc1 = audio_chunker.split_audio_into_chunks(orig_p, initial_sec=a.initial_sec, output_dir=tmp)
    O, C0, C1, F, L1 = (pcm(p) for p in (orig_p, ex_c0, ex_c1, ex_full, lc1))

    print(f"[G] decoded sample counts (stereo frames @ {SR} Hz), cut = {cut}:")
    print(f"    original           = {len(O)}")
    print(f"    extracted chunk0   = {len(C0)}  (vs cut: {len(C0) - cut:+d})")
    print(f"    extracted chunk1   = {len(C1)}  (vs original-cut: {len(C1) - (len(O) - cut):+d})")
    print(f"    local chunk1       = {len(L1)}  (vs original-cut: {len(L1) - (len(O) - cut):+d})")
    print(f"    extracted full     = {len(F)}  (vs original: {len(F) - len(O):+d}; vs chunk0+chunk1: {len(F) - len(C0) - len(C1):+d})")

    win, ml = SR // 2, 4000
    print("[H] alignment of extracted full vs original (positive lag = extracted is later):")
    for t in (0.5, 1.5, 2.4, 3.6, 5.0, 10.0, 20.0, 28.0):
        s = int(t * SR)
        if s + win + ml < min(len(O), len(F)):
            d, r = lag(O, F, s, win, ml)
            print(f"    t={t:5.1f}s lag={d:+5d} samples ({d / SR * 1000:+7.2f} ms) corr={r:.4f}")
    print("[H] extracted chunk1 vs original[cut:] and vs local chunk1:")
    O1 = O[cut:]
    for t in (0.2, 1.0, 5.0):
        s = int(t * SR)
        d1, r1 = lag(O1, C1, s, win, ml)
        d2, r2 = lag(L1, C1, s, win, ml)
        print(f"    t={t:4.1f}s  vs original: lag={d1:+5d} corr={r1:.4f}   vs local: lag={d2:+5d} corr={r2:.4f}")

    print("[I] near-silent runs (|x|<8, >=64 samples) within ±0.2 s of the join in extracted full:")
    j = len(C0)
    for st, ln in silent_runs(F, max(0, j - SR // 5), j + SR // 5):
        print(f"    at {st} ({(st - j) / SR * 1000:+.2f} ms from join) length={ln} ({ln / SR * 1000:.2f} ms)")
    print("[I] same window in original around the cut (reference):")
    for st, ln in silent_runs(O, max(0, cut - SR // 5), cut + SR // 5):
        print(f"    at {st} ({(st - cut) / SR * 1000:+.2f} ms from cut) length={ln} ({ln / SR * 1000:.2f} ms)")


if __name__ == "__main__":
    main()
