"""驗證 audio_chunker 的 MP3 frame 邊界位元組切割（DEF-001）：
  1. chunk0 + chunk1 位元組 == 原檔；concatenate_chunks 輸出 SHA-256 == 原檔
  2. chunk1 以 frame sync 開頭；chunk0 可單獨解碼且長度 >= initial_sec，PCM 等於原檔前綴
  3. 舊版（重新編碼）chunk 仍走 ffmpeg concat，輸出與舊結果相同（向下相容）

用法：python src/test/verify/verify_mp3_split.py <data_dir> [--initial-sec 3.0 6.0] [--prefix audio_] > <data_dir>/mp3_split_log.txt
"""
import io
import os
import sys
import glob
import shutil
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
    return np.frombuffer(raw, np.int16).reshape(-1, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--initial-sec", type=float, nargs="+", default=[3.0, 6.0])
    ap.add_argument("--prefix", default="audio_")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    srcs = sorted(glob.glob(os.path.join(a.data_dir, f"{a.prefix}*.mp3")))
    fails = 0

    print("[J] lang | sec | cut_byte/size | bytes_equal concat_sha_equal | chunk1_sync | "
          "chunk0_samples (>=target) | chunk0_pcm_is_prefix | original_samples")
    for p in srcs:
        lang = os.path.basename(p)[len(a.prefix):-4]
        orig = open(p, "rb").read()
        O = pcm(p)
        for sec in a.initial_sec:
            tmp = tempfile.mkdtemp()
            c0, c1 = audio_chunker.split_audio_into_chunks(p, initial_sec=sec, output_dir=tmp)
            b0, b1 = open(c0, "rb").read(), open(c1, "rb").read()
            full = audio_chunker.concatenate_chunks([c0, c1], os.path.join(tmp, "full.mp3"))
            C0 = pcm(c0)
            target = int(sec * SR)
            checks = {
                "bytes": b0 + b1 == orig,
                "concat": sha256(full) == sha256(p),
                "sync": audio_chunker._is_mp3_continuation(c1),
                "len": len(C0) >= target,
                "prefix": bool(np.array_equal(C0, O[:len(C0)])),
            }
            fails += not all(checks.values())
            print(f"    {lang:6s} | {sec:3.1f} | {len(b0)}/{len(orig)} | {checks['bytes']} {checks['concat']} | "
                  f"{checks['sync']} | {len(C0)} ({checks['len']}) | {checks['prefix']} | {len(O)}")
            shutil.rmtree(tmp, ignore_errors=True)

    ex = os.path.join(a.data_dir, "extracted")
    legacy = sorted(glob.glob(os.path.join(ex, "*_chunk0.mp3")))
    print(f"[K] backward compatibility: legacy chunks in {os.path.relpath(ex, a.data_dir)}/ "
          f"(re-encoded, start with ID3) -> ffmpeg concat path, compare with previous full file:")
    for c0 in legacy:
        lang = os.path.basename(c0)[:-len("_chunk0.mp3")]
        c1, prev = os.path.join(ex, f"{lang}_chunk1.mp3"), os.path.join(ex, f"{lang}.mp3")
        if not (os.path.exists(c1) and os.path.exists(prev)):
            continue
        out = os.path.join(tempfile.mkdtemp(), "legacy.mp3")
        with contextlib.redirect_stdout(io.StringIO()):
            audio_chunker.concatenate_chunks([c0, c1], out)
        cont = audio_chunker._is_mp3_continuation(c1)
        same = sha256(out) == sha256(prev)
        fails += cont or not same
        print(f"    {lang:6s} chunk1_is_continuation={cont} (expect False) same_as_previous={same}")
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)

    print(f"[RESULT] {'PASS' if fails == 0 else f'FAIL ({fails} failing rows)'}")


if __name__ == "__main__":
    main()
