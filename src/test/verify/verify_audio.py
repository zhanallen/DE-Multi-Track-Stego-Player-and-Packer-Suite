"""以 pee_stego.decode_video_multi 擷取音軌，並與原始 mp3 比對檔案雜湊與解碼後 PCM。

用法：python src/test/verify/verify_audio.py <data_dir> [--stego chunked_stego.mp4] [--prefix audio_] > <data_dir>/audio_log.txt
原始音軌需命名為 <prefix><lang>.mp3；擷取結果寫到 <data_dir>/extracted/。
"""
import io
import os
import sys
import shutil
import argparse
import contextlib
import subprocess

from _common import FF, sha256, print_header
import pee_stego


def pcm(path):
    return subprocess.run([FF, "-v", "error", "-i", path, "-f", "s16le", "-ac", "2", "-ar", "44100", "-"],
                          capture_output=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--stego", default="chunked_stego.mp4")
    ap.add_argument("--prefix", default="audio_")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    stego = os.path.join(a.data_dir, a.stego)
    print(f"# sha256 {a.stego} = {sha256(stego)}")

    out = os.path.join(a.data_dir, "extracted")
    shutil.rmtree(out, ignore_errors=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tracks = pee_stego.decode_video_multi(stego, out)
    print("[E] decoder log:")
    for line in buf.getvalue().splitlines():
        if "已掃描" not in line:
            print("    " + line)

    print("[E] lang | orig_size extr_size | file_sha_equal | pcm_equal (orig_samples vs extr_samples) | first_diff_byte")
    for lang in sorted(tracks):
        o, e = os.path.join(a.data_dir, f"{a.prefix}{lang}.mp3"), tracks[lang]
        if not os.path.exists(o):
            print(f"    {lang}: no original")
            continue
        x, y = pcm(o), pcm(e)
        fd = next((i for i in range(min(len(x), len(y))) if x[i] != y[i]), None) if x != y else None
        print(f"    {lang:6s} | {os.path.getsize(o)} {os.path.getsize(e)} | {sha256(o) == sha256(e)} | "
              f"{x == y} ({len(x) // 4} vs {len(y) // 4}) | {fd}")


if __name__ == "__main__":
    main()
