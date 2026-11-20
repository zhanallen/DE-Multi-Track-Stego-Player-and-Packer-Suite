"""驗證 Coltuc 2x2 PEE 的離散失真模型（P3-7、P3-8）。

以 pee_stego.coltuc_embed_frame 把隨機位元嵌滿一幀，再只用「原圖 Y」與「嵌入後 Y'」逐區塊反推：
  d  = (X−x) − (N−n) − (W−w) + (NW−nw)，u = 四個像素的修改量
  P3-7：每個處理區塊 u == (⌊d/4⌋, ⌊(d+1)/4⌋, ⌊(d+2)/4⌋, ⌊(d+3)/4⌋) 且 Σu² == |d|，max|Δ| ≤ 1
  P3-8：可擴張區塊（|p|≤1）中 q0、q+、q− 的比例；每 bit 失真
        D_exp(一般式) = 0.5·q0 + 1.5·q+ + 0.5·q−，對稱近似 D_exp = 1 − 0.5·q0（需 q+ ≈ q−）
  另驗證 SSE_實測 == Σ|d| + 保留列 LSB 旁通道的變動數（逐位元相等）。

用法：python src/test/verify/verify_distortion_model.py --video <cover> --frames 0 144 288 432 576 --image src/image/cat.jpg ... > <log>
"""
import os
import re
import sys
import math
import struct
import argparse
import subprocess

import numpy as np

from _common import FF, sha256, print_header
import pee_stego
import cv2

SEED = 20261027


def video_frames(path, wanted):
    info = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr
    w, h = map(int, re.search(r"Video: .*?, (\d{3,5})x(\d{3,5})", info).groups())
    p = subprocess.Popen([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                         stdout=subprocess.PIPE)
    fs, i, out, last = w * h * 3 // 2, 0, {}, max(wanted)
    while i <= last:
        raw = p.stdout.read(fs)
        if len(raw) < fs:
            break
        if i in wanted:
            out[i] = np.frombuffer(raw, np.uint8)[:w * h].reshape(h, w).copy()
        i += 1
    p.kill()
    return out


def image_y(path):
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0].copy()


def analyse(name, Y):
    h, w = Y.shape
    ys = h * w
    frame = np.concatenate([Y.ravel(), np.full(ys // 2, 128, np.uint8)])
    bits = np.random.default_rng(SEED).integers(0, 2, ys, dtype=np.uint8)   # 足以嵌滿整幀
    gpos, used = pee_stego.coltuc_embed_frame(frame, ys, h, w, bits, 0)
    Ys = frame[:ys].reshape(h, w)
    resv_rows = struct.unpack(">H", np.packbits(Ys.ravel()[:16] & 1).tobytes())[0]

    o = Y.astype(np.int32)
    s = Ys.astype(np.int32)
    delta = s - o
    maxabs = int(np.abs(delta).max())
    sse = int((delta * delta).sum())
    sse_resv = int((delta[:resv_rows] ** 2).sum())

    # 處理區（resv_rows 之後）的 2x2 不相交區塊
    hb = (h - resv_rows) // 2 * 2
    wb = (w - 1) // 2 * 2 if w % 2 else w
    blk = lambda a, dr, dc: a[resv_rows + dr:resv_rows + hb:2, dc:wb:2]
    nw, n, ww, x = (blk(o, 0, 0), blk(o, 0, 1), blk(o, 1, 0), blk(o, 1, 1))
    NW, N, W, X = (blk(s, 0, 0), blk(s, 0, 1), blk(s, 1, 0), blk(s, 1, 1))
    ux, un, uw, unw = X - x, n - N, ww - W, NW - nw
    d = ux + un + uw + unw
    inband = ((nw >= 2) & (nw <= 253) & (n >= 2) & (n <= 253) & (ww >= 2) & (ww <= 253) & (x >= 2) & (x <= 253))
    p = x - (n + ww - nw)
    pattern_ok = ((ux == d // 4) & (uw == (d + 1) // 4) & (unw == (d + 2) // 4) & (un == (d + 3) // 4))
    sumsq = ux * ux + un * un + uw * uw + unw * unw
    proc = inband
    mism_pattern = int((proc & ~pattern_ok).sum())
    mism_sumsq = int((proc & (sumsq != np.abs(d))).sum())
    skip_changed = int((~proc & (d != 0)).sum())
    sse_blocks = int(sumsq[proc].sum())
    sse_other = sse - sse_resv - sse_blocks          # 處理區內、但不屬任何 2x2 區塊的像素（奇數邊）

    exp = proc & (np.abs(p) <= 1)
    n0, npos, nneg = int((exp & (p == 0)).sum()), int((exp & (p == 1)).sum()), int((exp & (p == -1)).sum())
    nexp = n0 + npos + nneg
    nshift = int((proc & (np.abs(p) > 1)).sum())
    q0, qp, qn = n0 / nexp, npos / nexp, nneg / nexp
    absd = np.abs(d)
    mean_d = lambda m: float(absd[m].mean()) if m.any() else float("nan")
    d_meas = float(absd[exp].sum()) / nexp
    d_gen = 0.5 * q0 + 1.5 * qp + 0.5 * qn
    d_sym = 1 - 0.5 * q0
    sym_gap = abs(qp - qn) / (qp + qn)
    mse = sse / ys
    mse_gen = (nexp * d_gen + 2 * nshift + sse_resv + sse_other) / ys
    mse_sym = (nexp * d_sym + 2 * nshift + sse_resv + sse_other) / ys
    psnr = lambda m: 10 * math.log10(255 ** 2 / m)

    print(f"== {name}  {w}x{h}  resv_rows={resv_rows}  embedded_bits={gpos}  (incl. side-channel LSBs)")
    print(f"   [P3-7] blocks processed={int(proc.sum())}  u-pattern mismatches={mism_pattern}  "
          f"sum(u^2)!=|d| mismatches={mism_sumsq}  skipped-but-changed={skip_changed}  max|delta|={maxabs}")
    print(f"   [SSE ] measured={sse}  = blocks {sse_blocks} + reserved-rows {sse_resv} + other {sse_other}  "
          f"(identity {'OK' if sse == sse_blocks + sse_resv + sse_other and sse_other == 0 else 'CHECK'})")
    print(f"   [P3-8] expandable={nexp}  q0={q0:.4f} q+={qp:.4f} q-={qn:.4f}  symmetry gap |q+-q-|/(q+ + q-)={sym_gap * 100:.3f}%  "
          f"shift={nshift}")
    print(f"          mean|d|: p=0 {mean_d(exp & (p == 0)):.4f} (exp 0.5)  p=+1 {mean_d(exp & (p == 1)):.4f} (exp 1.5)  "
          f"p=-1 {mean_d(exp & (p == -1)):.4f} (exp 0.5)  shift {mean_d(proc & (np.abs(p) > 1)):.4f} (exp 2)")
    print(f"          D_exp measured={d_meas:.5f}  general={d_gen:.5f} (err {100 * (d_gen - d_meas) / d_meas:+.3f}%)  "
          f"1-0.5q0={d_sym:.5f} (err {100 * (d_sym - d_meas) / d_meas:+.3f}%)")
    print(f"   [PSNR] measured={psnr(mse):.4f} dB  model(general)={psnr(mse_gen):.4f} ({psnr(mse_gen) - psnr(mse):+.4f})  "
          f"model(1-0.5q0)={psnr(mse_sym):.4f} ({psnr(mse_sym) - psnr(mse):+.4f})  bpp={(gpos) / ys:.4f}")
    return mism_pattern + mism_sumsq + skip_changed + (maxabs > 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--frames", type=int, nargs="*", default=[])
    ap.add_argument("--image", nargs="*", default=[])
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    print(f"# random payload: numpy default_rng(seed={SEED}).integers(0, 2)")
    fails = 0
    if a.video:
        print(f"# sha256 {a.video} = {sha256(a.video)}")
        for i, Y in sorted(video_frames(a.video, set(a.frames)).items()):
            fails += analyse(f"{os.path.basename(a.video)} frame {i}", Y)
    for path in a.image:
        print(f"# sha256 {path} = {sha256(path)}")
        fails += analyse(os.path.basename(path), image_y(path))
    print(f"[RESULT] P3-7 {'PASS' if fails == 0 else f'FAIL ({fails})'}")


if __name__ == "__main__":
    main()
