"""驗證：payload 跨越「容量為 0 的幀」（全黑／全白）時，封裝→擷取是否仍正確（RSK-01）。

coltuc_embed_frame 遇到容量不足的幀會直接略過、不寫標頭；decode_video_multi 則在擷取完成前對每一幀呼叫
coltuc_decode_frame。本腳本以合成影片組出「shapes ×2 → black ×2 → shapes ×N」的載體，
用 encode_video_multi 封裝一軌 mp3，再以 decode_video_multi 擷取並比對 SHA-256。

用法：python src/test/verify/verify_zero_capacity_frames.py <synthetic_dir> <audio.mp3> <out_dir> > <log>
"""
import io
import os
import sys
import glob
import shutil
import argparse
import contextlib
import traceback

import numpy as np

from _common import sha256, print_header
import pee_stego


def read_y4m(path):
    with open(path, "rb") as f:
        header = f.readline()
        w = int(header.split(b" W")[1].split(b" ")[0])
        h = int(header.split(b" H")[1].split(b" ")[0])
        fs = w * h * 3 // 2
        frames = []
        while f.readline().startswith(b"FRAME"):
            frames.append(f.read(fs))
    return header, frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("synthetic_dir")
    ap.add_argument("audio")
    ap.add_argument("out_dir")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    os.makedirs(a.out_dir, exist_ok=True)
    shapes = glob.glob(os.path.join(a.synthetic_dir, "synthetic_shapes_*.y4m"))[0]
    black = glob.glob(os.path.join(a.synthetic_dir, "synthetic_black_*.y4m"))[0]
    header, fs = read_y4m(shapes)
    _, fb = read_y4m(black)
    seq = fs[:2] + fb[:2] + fs[2:]
    carrier = os.path.join(a.out_dir, "shapes2_black2_shapes.y4m")
    with open(carrier, "wb") as f:
        f.write(header)
        for fr in seq:
            f.write(b"FRAME\n" + fr)
    print(f"# carrier: frames 0-1 shapes, 2-3 black, 4-{len(seq) - 1} shapes; sha256={sha256(carrier)}")

    track = os.path.join(a.out_dir, "clip_audio_xx.mp3")
    shutil.copyfile(a.audio, track)
    print(f"# audio: {a.audio} sha256={sha256(track)} size={os.path.getsize(track)}")
    stego = os.path.join(a.out_dir, "zero_cap_stego.mp4")
    out = os.path.join(a.out_dir, "extracted")
    shutil.rmtree(out, ignore_errors=True)
    for chunked in (False, True):
        label = "chunked" if chunked else "monolithic"
        log = io.StringIO()
        try:
            with contextlib.redirect_stdout(log):
                pee_stego.encode_video_multi(carrier, [track], stego, chunked=chunked, initial_sec=3.0)
                tracks = pee_stego.decode_video_multi(stego, out)
            got = tracks.get("xx") if isinstance(tracks, dict) else (tracks[0] if tracks else None)
            ok = bool(got) and os.path.exists(got) and sha256(got) == sha256(track)
            print(f"[{label}] decode returned {tracks!r}")
            print(f"[{label}] RESULT {'PASS' if ok else 'FAIL'}  extracted_sha_equal={ok}")
        except Exception as e:
            print(f"[{label}] RESULT FAIL  exception: {type(e).__name__}: {e}")
            print("    " + traceback.format_exc().strip().replace("\n", "\n    "))
        print(f"[{label}] pipeline log tail:")
        for line in [l for l in log.getvalue().splitlines() if "已寫入" not in l and "已掃描" not in l][-6:]:
            print("    " + line)
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    main()
