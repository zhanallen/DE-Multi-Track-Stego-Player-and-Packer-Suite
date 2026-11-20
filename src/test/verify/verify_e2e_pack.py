"""端到端驗證（DEF-001）：以目前的 encode_video_multi 封裝多語音軌 → decode_video_multi 擷取 → 比對每軌 SHA-256 與原檔。

用法：python src/test/verify/verify_e2e_pack.py <data_dir> [--cover cover.webm] [--initial-sec 3.0] [--prefix audio_] > <data_dir>/e2e_log.txt
stego 輸出到 <data_dir>/e2e_stego.mp4，擷取結果到 <data_dir>/extracted_e2e/。
"""
import io
import os
import sys
import glob
import time
import shutil
import argparse
import tempfile
import contextlib

from _common import sha256, print_header
import pee_stego


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--cover", default="cover.webm")
    ap.add_argument("--initial-sec", type=float, default=3.0)
    ap.add_argument("--prefix", default="audio_")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    cover = os.path.join(a.data_dir, a.cover)
    print(f"# sha256 {a.cover} = {sha256(cover)}")

    # parse_track_lang 需要 *_audio_<lang>.mp3 命名
    staging = tempfile.mkdtemp(prefix="e2e_tracks_")
    originals = {}
    for p in sorted(glob.glob(os.path.join(a.data_dir, f"{a.prefix}*.mp3"))):
        lang = os.path.basename(p)[len(a.prefix):-4]
        dst = os.path.join(staging, f"track_audio_{lang}.mp3")
        shutil.copyfile(p, dst)
        originals[lang] = p

    stego = os.path.join(a.data_dir, "e2e_stego.mp4")
    out = os.path.join(a.data_dir, "extracted_e2e")
    shutil.rmtree(out, ignore_errors=True)
    log = io.StringIO()
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(log):
        pee_stego.encode_video_multi(cover, sorted(glob.glob(os.path.join(staging, "*.mp3"))), stego,
                                     chunked=True, initial_sec=a.initial_sec)
        t1 = time.perf_counter()
        tracks = pee_stego.decode_video_multi(stego, out)
    t2 = time.perf_counter()
    print("[L] pipeline log:")
    for line in log.getvalue().splitlines():
        if "已寫入" not in line and "已掃描" not in line:
            print("    " + line)
    print(f"[L] encode {t1 - t0:.1f}s, decode {t2 - t1:.1f}s, stego size={os.path.getsize(stego)} sha256={sha256(stego)}")

    fails = 0
    print("[M] lang | original_sha256 | extracted_sha256 | equal")
    for lang, orig in sorted(originals.items()):
        ext = tracks.get(lang)
        ho = sha256(orig)
        he = sha256(ext) if ext and os.path.exists(ext) else "MISSING"
        fails += ho != he
        print(f"    {lang:6s} | {ho[:16]}… | {he[:16]}… | {ho == he}")
    print(f"[RESULT] {'PASS' if fails == 0 and len(tracks) == len(originals) else f'FAIL ({fails} mismatches, {len(tracks)}/{len(originals)} tracks)'}")
    shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
