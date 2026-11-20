"""StegoPacker 邊界案例：TC-PK-04（容量估計與容量不足）、TC-PK-05（非標準 MP3 分塊）。

TC-PK-04
  a. estimate_capacity()（GUI 用的估計值，只取中段 15 幀）vs 實際容量（逐幀以 coltuc_embed_frame 飽和嵌入加總）
  b. 以 API 封裝超過容量的 payload：是否拋出例外、拋出前是否已寫出輸出檔
TC-PK-05
  以 audio_chunker 分塊下列 MP3，檢查不拋例外、走哪條路徑（位元組切割或 ffmpeg 重新編碼）、輸出可解碼：
  MPEG-2 Layer III（22.05 kHz）、中段插入 100 個隨機位元組、WAV 改副檔名為 .mp3、在 frame 中間截斷、檔尾附 ID3v1

用法：python src/test/verify/verify_packer_edges.py --carriers <video> [...] --mp3 <ref.mp3> --tracks <mp3> [...] --work <dir> > <log>
"""
import io
import os
import sys
import shutil
import argparse
import contextlib
import subprocess

import numpy as np

from _common import FF, sha256, print_header
import pee_stego
import audio_chunker


def frames(path):
    import re
    info = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr
    w, h = map(int, re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", info).groups())
    p = subprocess.Popen([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                         stdout=subprocess.PIPE)
    fs = w * h * 3 // 2
    while True:
        raw = p.stdout.read(fs)
        if len(raw) < fs:
            break
        yield np.frombuffer(raw, np.uint8).copy(), w, h
    p.kill()


def actual_capacity_bytes(path):
    total, n, zero = 0, 0, 0
    big = None
    for f, w, h in frames(path):
        if big is None:
            big = np.zeros(w * h, np.uint8)
        pos, used = pee_stego.coltuc_embed_frame(f, w * h, h, w, big, 0)
        total += pos
        n += 1
        zero += not used
    return total // 8, n, zero


def pk04(carriers, tracks, work):
    print("[PK-04a] estimate_capacity() vs actual (bytes)")
    for c in carriers:
        est = pee_stego.estimate_capacity(c)
        act, n, zero = actual_capacity_bytes(c)
        err = (est - act) / act * 100 if act else float("inf") if est else 0.0
        print(f"    {os.path.basename(c):40s} frames={n:4d} zero-capacity frames={zero:4d}  "
              f"estimate={est:>11,}  actual={act:>11,}  estimate error={err:+.1f}%")
    c = carriers[0]
    payload = pee_stego.get_payload_size(tracks)
    act, _, _ = actual_capacity_bytes(c)
    out = os.path.join(work, "overflow_stego.mp4")
    if os.path.exists(out):
        os.remove(out)
    print(f"[PK-04b] API overflow: carrier={os.path.basename(c)} actual capacity={act:,} B, payload≈{payload:,} B "
          f"({len(tracks)} tracks)")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pee_stego.encode_video_multi(c, tracks, out, chunked=True, initial_sec=3.0)
        print("    no exception raised  -> FAIL")
    except Exception as e:
        print(f"    exception: {type(e).__name__}: {e}")
    left = os.path.exists(out)
    print(f"    output file left behind after failure: {left}" + (f" ({os.path.getsize(out):,} bytes)" if left else ""))


def pk05(ref, work):
    d = os.path.join(work, "mp3_edge")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    data = open(ref, "rb").read()
    cases = {}
    p = os.path.join(d, "mpeg2_22k.mp3")
    subprocess.run([FF, "-v", "error", "-y", "-i", ref, "-ar", "22050", "-c:a", "libmp3lame", "-b:a", "64k", p], check=True)
    cases["MPEG-2 Layer III 22.05 kHz"] = p
    rng = np.random.default_rng(20261027)
    mid = len(data) // 2
    p = os.path.join(d, "corrupt_mid.mp3")
    open(p, "wb").write(data[:mid] + rng.integers(0, 256, 100, dtype=np.uint8).tobytes() + data[mid:])
    cases["100 random bytes inserted mid-file"] = p
    early = len(data) // 20                       # 5%：位於 3 秒切點之前，迫使解析失敗而退回 ffmpeg
    p = os.path.join(d, "corrupt_early.mp3")
    open(p, "wb").write(data[:early] + rng.integers(0, 256, 100, dtype=np.uint8).tobytes() + data[early:])
    cases["100 random bytes inserted at 5%"] = p
    p = os.path.join(d, "wav_renamed.mp3")
    subprocess.run([FF, "-v", "error", "-y", "-i", ref, "-f", "wav", p], check=True)
    cases["WAV renamed to .mp3"] = p
    p = os.path.join(d, "truncated.mp3")
    open(p, "wb").write(data[:int(len(data) * 0.6) + 7])
    cases["truncated mid-frame at 60%"] = p
    p = os.path.join(d, "id3v1.mp3")
    open(p, "wb").write(data + b"TAG" + b"\x00" * 125)
    cases["ID3v1 tag appended"] = p

    print("[PK-05] case | exception | path | chunk0/chunk1 bytes | concat decodable (samples) | chunk0 samples")
    for label, path in cases.items():
        cd = os.path.join(d, os.path.splitext(os.path.basename(path))[0])
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                c0, c1 = audio_chunker.split_audio_into_chunks(path, initial_sec=3.0, output_dir=cd)
                full = audio_chunker.concatenate_chunks([c0, c1], os.path.join(cd, "full.mp3"))
            orig = open(path, "rb").read()
            route = "byte-split" if open(c0, "rb").read() + open(c1, "rb").read() == orig else "ffmpeg re-encode"
            pcm = lambda q: len(subprocess.run([FF, "-v", "error", "-i", q, "-f", "s16le", "-ac", "2", "-ar", "44100", "-"],
                                               capture_output=True).stdout) // 4
            print(f"    {label:36s} | none | {route:16s} | {os.path.getsize(c0)}/{os.path.getsize(c1)} | "
                  f"{pcm(full)} | {pcm(c0)}")
        except Exception as e:
            print(f"    {label:36s} | {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carriers", nargs="+", required=True)
    ap.add_argument("--mp3", required=True)
    ap.add_argument("--tracks", nargs="+", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    os.makedirs(a.work, exist_ok=True)
    for c in a.carriers:
        print(f"# sha256 {c} = {sha256(c)}")
    pk04(a.carriers, a.tracks, a.work)
    pk05(a.mp3, a.work)


if __name__ == "__main__":
    main()
