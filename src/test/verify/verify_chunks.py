"""以 audio_chunker 在本機重新切割原始 mp3，與 verify_audio.py 擷取出的 chunk0/chunk1/合併檔逐位元比對。

用法：python src/test/verify/verify_chunks.py <data_dir> [--initial-sec 3.0] [--prefix audio_] > <data_dir>/chunk_log_3s.txt
需先執行 verify_audio.py 產生 <data_dir>/extracted/。
"""
import io
import os
import sys
import glob
import shutil
import argparse
import tempfile
import contextlib

from _common import sha256, print_header
import audio_chunker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--initial-sec", type=float, default=3.0)
    ap.add_argument("--prefix", default="audio_")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    srcs = sorted(glob.glob(os.path.join(a.data_dir, f"{a.prefix}*.mp3")))

    print("[F] original mp3 sha256 (dedup check):")
    groups = {}
    for p in srcs:
        groups.setdefault(sha256(p), []).append(os.path.basename(p)[len(a.prefix):-4])
    for h, langs in groups.items():
        print(f"    {h[:16]}… x{len(langs)}: {langs}")

    print(f"[F] re-split originals locally with audio_chunker (initial_sec={a.initial_sec}) "
          f"and compare to extracted chunks/full files:")
    ex = os.path.join(a.data_dir, "extracted")
    for p in srcs:
        lang = os.path.basename(p)[len(a.prefix):-4]
        tmp = tempfile.mkdtemp()
        with contextlib.redirect_stdout(io.StringIO()):
            c0, c1 = audio_chunker.split_audio_into_chunks(p, initial_sec=a.initial_sec, output_dir=tmp)
            full = os.path.join(tmp, "full.mp3")
            audio_chunker.concatenate_chunks([c0, c1], full)
        eq = [sha256(x) == sha256(os.path.join(ex, y)) for x, y in
              ((c0, f"{lang}_chunk0.mp3"), (c1, f"{lang}_chunk1.mp3"), (full, f"{lang}.mp3"))]
        print(f"    {lang:6s} chunk0_equal={eq[0]} chunk1_equal={eq[1]} concat_equal={eq[2]}")
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
