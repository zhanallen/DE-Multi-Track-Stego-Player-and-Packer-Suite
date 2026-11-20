"""驗證 stego 影片相對原始載體：無損編碼證據、逐幀 PSNR（舊算法 vs MSE-first）、Coltuc 可逆還原。

用法：python src/test/verify/verify_jimmy.py <data_dir> [--cover cover.webm] [--stego chunked_stego.mp4] > <data_dir>/verify_log.txt
"""
import os
import re
import sys
import math
import argparse
import subprocess

import numpy as np

from _common import FF, sha256, print_header
import pee_stego
import numba
import cv2


def psnr(mse):
    return float("inf") if mse == 0 else 10 * math.log10(255 ** 2 / mse)


def frame_size(path):
    info = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr
    w, h = map(int, re.search(r"Video: .*?, (\d{3,5})x(\d{3,5})", info).groups())
    return w, h


def yuv_pipe(path):
    return subprocess.Popen([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                            stdout=subprocess.PIPE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--cover", default="cover.webm")
    ap.add_argument("--stego", default="chunked_stego.mp4")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    print(f"# libs    : numba={numba.__version__} cv2={cv2.__version__}")
    cover, stego = os.path.join(a.data_dir, a.cover), os.path.join(a.data_dir, a.stego)
    for p in (cover, stego):
        print(f"# sha256 {os.path.basename(p)} = {sha256(p)}  size={os.path.getsize(p)}")

    # A. x265 編碼參數 SEI：確認 lossless 旗標
    with open(stego, "rb") as f:
        m = re.search(rb"x265 \(build[\x20-\x7e]{0,4000}", f.read())
    sei = m.group(0).decode() if m else ""
    print("[A] x265 SEI:", "present" if sei else "absent")
    for tok in ("lossless", "no-lossless", "cu-lossless"):
        hits = re.findall(r"(?<![\w-])" + re.escape(tok) + r"(?:=\S+)?", sei)
        if hits:
            print(f"    {tok}: {sorted(set(hits))}")
    print("    SEI head:", sei[:300])

    # B. 逐幀比對 + 依 decode_video_multi 的停止條件做還原
    w, h = frame_size(stego)
    ys, fs = w * h, w * h * 3 // 2
    pc, ps = yuv_pipe(cover), yuv_pipe(stego)
    rows, payload = [], []
    got = target = used = 0
    extracting = True
    chroma_bad = restore_bad = unmod_bad = 0
    while True:
        rc, rs = pc.stdout.read(fs), ps.stdout.read(fs)
        if len(rc) < fs or len(rs) < fs:
            print(f"[B] end: cover_bytes_left={len(rc)} stego_bytes_left={len(rs)}")
            break
        C = np.frombuffer(rc, np.uint8)
        S = np.frombuffer(rs, np.uint8).copy()
        if not np.array_equal(C[ys:], S[ys:]):
            chroma_bad += 1
        df = S[:ys].astype(np.int32) - C[:ys].astype(np.int32)
        mse = float(np.mean(df * df))
        rest = "-"
        if extracting:
            R = S.copy()
            chunk = pee_stego.coltuc_decode_frame(R, ys, h, w)
            payload.append(chunk)
            got += len(chunk)
            used += 1
            ok = np.array_equal(R, C)
            rest = "OK" if ok else "FAIL"
            restore_bad += not ok
            if target == 0 and got >= 32:
                head = np.concatenate(payload)[:32]
                target = 32 + int("".join(map(str, head)), 2) * 8
            if target and got >= target:
                extracting = False
        elif mse != 0:
            unmod_bad += 1
        rows.append((len(rows), mse, int(np.abs(df).max()), float(np.mean(df != 0)), rest))
    pc.kill()
    ps.kill()
    n = len(rows)
    print(f"[B] {w}x{h} frames={n} payload_frames={used} target_bits={target} extracted_bits={got} "
          f"chroma_mismatch_frames={chroma_bad} restore_fail_frames={restore_bad} nonpayload_frames_with_diff={unmod_bad}")

    print("[C] per-frame: idx mse maxabs frac_changed PSNR(dB) restore")
    for i, mse, mx, fr, rest in rows:
        p = "inf" if mse == 0 else f"{psnr(mse):.4f}"
        print(f"    {i:4d} {mse:.6f} {mx} {fr:.4f} {p} {rest}")

    # D. 四種 PSNR 彙總（同一份資料並列）
    mses = [r[1] for r in rows]
    capped = [100.0 if m == 0 else psnr(m) for m in mses]
    step = max(1, n // 5)
    q = list(range(0, n, step))[:5]
    pl = [r for r in rows if r[4] != "-"]
    print(f"[D] payload frames: PSNR min={min(psnr(r[1]) for r in pl):.4f} max={max(psnr(r[1]) for r in pl):.4f} maxabs={max(r[2] for r in pl)}")
    print(f"[D] old stego_bench method (5 frames {q}, MSE=0->100, mean of dB) = {np.mean([capped[i] for i in q]):.4f} dB")
    print(f"[D] mean of dB over all {n} frames (MSE=0->100)            = {np.mean(capped):.4f} dB")
    print(f"[D] MSE-first over all {n} frames                           = {psnr(np.mean(mses)):.4f} dB")
    print(f"[D] MSE-first over payload frames only ({used})            = {psnr(np.mean(mses[:used])):.4f} dB")
    print(f"[D] bpp over payload frames = {target / (used * ys):.4f}; bpp over whole video = {target / (n * ys):.4f}")


if __name__ == "__main__":
    main()
