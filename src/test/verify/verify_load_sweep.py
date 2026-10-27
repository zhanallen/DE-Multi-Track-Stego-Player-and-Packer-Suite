"""負載掃描（P3-6、P3-9）與兩段式檔案膨脹（P3-10）：Coltuc vs Checkerboard。

每個方法先以飽和嵌入量出各幀容量 C_i，再對每個負載 α 產生 floor(α·ΣC_i) 個隨機位元，依幀序貪婪嵌入
（與 encode_video_multi 相同），並：
  - 逐幀計算 MSE，報告四種 PSNR（舊 stego_bench 算法、全片 dB 平均、全片 MSE-first、僅嵌入幀 MSE-first）
  - 逐幀還原並比對原幀與 payload（可逆性）
  - --encode：以與 pee_stego 相同的 x265 參數（ultrafast, lossless=1, yuv420p）編碼 stego 與未嵌入基準，
    報告「來源 → 無損基準」與「無損基準 → stego」兩段膨脹

注意：Checkerboard 採 src/test/stego_bench.py 實作（Q3-R2），其 skip map 由嵌入端直接交給解碼端、不存於影像內；
Coltuc 的 location map 存於影像保留列（佔容量、產生 LSB 失真）。兩者容量與檔案大小比較對 Checkerboard 較有利。

用法：python src/test/verify/verify_load_sweep.py <carrier> [--max-frames 120] [--loads 10 40 80 100]
                                                 [--payload-kib 256 512] [--methods coltuc checkerboard] [--encode] > <log>
  --loads 為「佔該方法容量的百分比」，兩方法容量不同（Checkerboard 約為 Coltuc 的 4 倍），跨方法比較請用 --payload-kib。
"""
import os
import re
import sys
import math
import argparse
import tempfile
import subprocess

import numpy as np

from _common import FF, REPO, sha256, print_header
import pee_stego

sys.path.insert(0, os.path.join(REPO, "src", "test"))
import stego_bench  # noqa: E402  Checkerboard 實作（Q3-R2）

SEED = 20261027
X265 = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "lossless=1", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]


def read_frames(path, max_frames):
    info = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace").stderr
    w, h = map(int, re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", info).groups())
    p = subprocess.Popen([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                         stdout=subprocess.PIPE)
    fs, frames = w * h * 3 // 2, []
    while max_frames is None or len(frames) < max_frames:
        raw = p.stdout.read(fs)
        if len(raw) < fs:
            break
        frames.append(np.frombuffer(raw, np.uint8).copy())
    p.kill()
    return frames, w, h


class Encoder:
    """以與 pee_stego 相同的 x265 參數串流編碼，結束時回傳檔案大小（不保留整批幀，節省記憶體）。"""

    def __init__(self, w, h):
        fd, self.out = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        self.p = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}",
                                   "-r", "24", "-i", "-", *X265, self.out], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def write(self, frame):
        self.p.stdin.write(frame.tobytes())

    def size(self):
        self.p.stdin.close()
        self.p.wait()
        n = os.path.getsize(self.out)
        os.remove(self.out)
        return n


def encoded_size(frames, w, h):
    enc = Encoder(w, h)
    for f in frames:
        enc.write(f)
    return enc.size()


# --- 方法介面：embed(frame_copy, bits, pos) -> (new_pos, meta)；restore(frame, meta, out_bits) ---
def coltuc_embed(frame, bits, pos, w, h):
    new_pos, used = pee_stego.coltuc_embed_frame(frame, w * h, h, w, bits, pos)
    return new_pos, (True if used else None)     # 容量不足的幀不寫標頭，視為未嵌入


def coltuc_restore(frame, meta, w, h):
    return pee_stego.coltuc_decode_frame(frame, w * h, h, w)


def cb_embed(frame, bits, pos, w, h):
    ys = w * h
    Y = frame[:ys].reshape(h, w).astype(np.int16)
    sm = np.zeros(ys, np.uint8)
    p2_end, p2_sm, p1_end, p1_sm = stego_bench.checkerboard_embed_frame_jit(Y, bits, len(bits), pos, sm, 0, h, w)
    frame[:ys] = Y.ravel().astype(np.uint8)
    return p2_end, dict(start=pos, p1_end=p1_end, p2_end=p2_end, p1_sm=p1_sm, sm=sm[:p2_sm].copy(), total=len(bits))


def cb_restore(frame, meta, w, h):
    # 解碼核心以全域位元索引寫入 stream_out；只配置本幀需要的長度，再把索引平移回 0（避免每幀配置 payload 全長）
    ys = w * h
    Y = frame[:ys].reshape(h, w).astype(np.int16)
    s0 = meta["start"]
    out = np.zeros(meta["p2_end"] - s0, np.uint8)
    stego_bench.checkerboard_decode_frame_jit(Y, out, meta["p2_end"] - s0, 0, meta["sm"], 0, h, w,
                                              meta["total"] - s0, meta["p1_end"] - s0, meta["p1_sm"])
    frame[:ys] = Y.ravel().astype(np.uint8)
    return out


METHODS = {"coltuc": (coltuc_embed, coltuc_restore), "checkerboard": (cb_embed, cb_restore)}


def psnr(m):
    return float("inf") if m == 0 else 10 * math.log10(255 ** 2 / m)


def run_method(name, frames, w, h, loads, payload_kib, do_encode, base_size):
    embed, restore = METHODS[name]
    ys, n = w * h, len(frames)
    big = np.random.default_rng(SEED).integers(0, 2, ys, dtype=np.uint8)
    caps = []
    for f in frames:
        pos, _ = embed(f.copy(), big, 0, w, h)
        caps.append(pos)
    C = int(sum(caps))
    print(f"[{name}] capacity: total={C} bits ({C / 8 / 1024:.1f} KiB)  per-frame min={min(caps)} max={max(caps)}  "
          f"bpp(avg)={C / (n * ys):.4f}")
    if C == 0:
        print(f"[{name}] zero capacity (every frame skipped) → no load cases")
        return
    # 相對負載（佔本方法容量 %）與絕對 payload（KiB，跨方法可比）
    cases = [(f"load={a:3d}%", int(C * a / 100), SEED + a) for a in loads]
    cases += [(f"payload={k}KiB", k * 8192, SEED + 100000 + k) for k in payload_kib]
    for label, nbits, seed in cases:
        if nbits > C:
            print(f"[{name}] {label}  bits={nbits} exceeds capacity {C} → skipped")
            continue
        bits = np.random.default_rng(seed).integers(0, 2, nbits, dtype=np.uint8)
        # 串流：逐幀嵌入 → 量 MSE → 送編碼器 → 立即還原並比對（只對有嵌入的幀解碼，模擬已知嵌入幀的理想解碼端）
        enc = Encoder(w, h) if do_encode else None
        pos, rpos, mses, emb_idx, restore_fail, payload_ok = 0, 0, [], [], 0, True
        for i, f in enumerate(frames):
            s = f.copy()
            meta = None
            if pos < nbits:
                pos, meta = embed(s, bits, pos, w, h)
            d = s[:ys].astype(np.int32) - f[:ys].astype(np.int32)
            mses.append(float(np.mean(d * d)))
            if enc:
                enc.write(s)
            if meta is not None:
                emb_idx.append(i)
                chunk = restore(s, meta, w, h)          # s 就地還原
                k = min(len(chunk), nbits - rpos)
                payload_ok &= bool(np.array_equal(chunk[:k], bits[rpos:rpos + k]))
                rpos += k
            if not np.array_equal(s, f):
                restore_fail += 1
        payload_ok &= rpos == nbits
        nused = len(emb_idx)
        capped = [100.0 if m == 0 else psnr(m) for m in mses]
        step = max(1, n // 5)
        q = list(range(0, n, step))[:5]
        pf = [psnr(mses[i]) for i in emb_idx if mses[i] > 0]
        line = (f"[{name}] {label}  bits={nbits} ({100 * nbits / C:.1f}% of capacity)  payload_frames={nused}/{n} (alpha_video={nused / n:.3f})  "
                f"bpp_payload={nbits / max(1, nused * ys):.4f}  restore_fail={restore_fail}  payload_ok={payload_ok}\n"
                f"          PSNR old(5f,100cap)={np.mean([capped[i] for i in q]):.4f}  meandB(all,100cap)={np.mean(capped):.4f}  "
                f"MSEfirst(all)={psnr(np.mean(mses)):.4f}  "
                f"MSEfirst(payload)={psnr(np.mean([mses[i] for i in emb_idx])) if emb_idx else float('nan'):.4f}  "
                f"per-frame[min,max]={'[' + f'{min(pf):.4f}, {max(pf):.4f}' + ']' if pf else 'n/a'}")
        if enc:
            ssz = enc.size()
            line += f"\n          size: stego={ssz}  vs lossless baseline {base_size}: {100 * (ssz - base_size) / base_size:+.2f}%"
        print(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("carrier")
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--loads", type=int, nargs="*", default=[10, 40, 80, 100])
    ap.add_argument("--payload-kib", type=int, nargs="*", default=[], help="absolute payload sizes, same for every method")
    ap.add_argument("--methods", nargs="+", default=["coltuc", "checkerboard"], choices=list(METHODS))
    ap.add_argument("--encode", action="store_true")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    print(f"# sha256 {a.carrier} = {sha256(a.carrier)}  size={os.path.getsize(a.carrier)}")
    frames, w, h = read_frames(a.carrier, a.max_frames)
    print(f"# frames used: {len(frames)}  {w}x{h}  random payload seed {SEED}+load")
    base = None
    if a.encode:
        base = encoded_size(frames, w, h)
        print(f"[size] source file={os.path.getsize(a.carrier)}  lossless baseline (unembedded, {len(frames)} frames)={base}")
        print("       note: source→baseline is only meaningful when all source frames are used (no --max-frames)")
    for m in a.methods:
        run_method(m, frames, w, h, a.loads, a.payload_kib, a.encode, base)


if __name__ == "__main__":
    main()
