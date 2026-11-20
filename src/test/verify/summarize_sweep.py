"""把 verify_load_sweep.py 的 log 彙整成 Markdown 表格（每列一個載體 × 方法 × 負載）。

用法：python src/test/verify/summarize_sweep.py <log> [<log> ...] > <summary.md>
表格中的每個數字都來自輸入 log；本腳本只做解析與排版，並在表頭列出各 log 的 commit 與 SHA-256。
"""
import os
import re
import sys

from _common import sha256

ROW = re.compile(r"^\[(\w+)\] (load=\s*\d+%|payload=\d+KiB)\s+bits=(\d+) \(([\d.]+)% of capacity\)\s+"
                 r"payload_frames=(\d+)/(\d+) \(alpha_video=([\d.]+)\)\s+bpp_payload=([\d.]+)\s+"
                 r"restore_fail=(\d+)\s+payload_ok=(\w+)")
PS = re.compile(r"old\(5f,100cap\)=([\d.]+)\s+meandB\(all,100cap\)=([\d.]+)\s+MSEfirst\(all\)=([\d.]+)\s+"
                r"MSEfirst\(payload\)=([\d.na]+)")
SZ = re.compile(r"size: stego=(\d+)\s+vs lossless baseline (\d+): ([+\-][\d.]+)%")
CAP = re.compile(r"^\[(\w+)\] capacity: total=(\d+) bits .*bpp\(avg\)=([\d.]+)")
BASE = re.compile(r"^\[size\] source file=(\d+)\s+lossless baseline \(unembedded, (\d+) frames\)=(\d+)")


def parse(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    meta = {"commit": "", "carrier": "", "frames": "", "base": None, "src": None, "caps": {}}
    rows = []
    for i, l in enumerate(lines):
        if l.startswith("# commit"):
            meta["commit"] = l.split(":", 1)[1].strip()[:7]
        elif l.startswith("# sha256 "):
            meta["carrier"] = os.path.basename(l.split(" = ")[0][9:])
        elif l.startswith("# frames used:"):
            meta["frames"] = l.split()[3]
        elif (m := BASE.match(l)):
            meta["src"], meta["base"] = int(m.group(1)), int(m.group(3))
        elif (m := CAP.match(l)):
            meta["caps"][m.group(1)] = (int(m.group(2)), float(m.group(3)))
        elif (m := ROW.match(l)):
            r = dict(method=m.group(1), case=m.group(2).replace(" ", ""), bits=int(m.group(3)), pct=float(m.group(4)),
                     used=int(m.group(5)), n=int(m.group(6)), alpha=float(m.group(7)), bpp=float(m.group(8)),
                     fail=int(m.group(9)), ok=m.group(10))
            e = re.search(r"embedded_bits=(\d+)\s+extracted_ok=(\w+)", l)       # 新版 log 才有
            r["embedded"], r["extracted_ok"] = (int(e.group(1)), e.group(2)) if e else (None, None)
            p = PS.search(lines[i + 1])
            r.update(old=p.group(1), meandb=p.group(2), mse_all=p.group(3), mse_pay=p.group(4))
            s = SZ.search(lines[i + 2]) if i + 2 < len(lines) else None
            r["size"] = s.group(3) if s else "—"
            rows.append(r)
    return meta, rows


def main():
    print("| 載體 | 方法 | 負載 | payload (KiB) | α_video | bpp（嵌入幀） | PSNR 舊算法 | PSNR 全片 dB 平均 | "
          "**PSNR MSE-first 全片** | PSNR MSE-first 嵌入幀 | 無損基準→stego | 可逆 |")
    print("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |")
    notes = []
    for path in sys.argv[1:]:
        meta, rows = parse(path)
        for r in rows:
            if r["fail"] == 0 and r["ok"] == "True":
                rev = "✅"
            elif r["fail"] == 0 and r["extracted_ok"] == "True":
                rev = f"✅（只嵌入 {r['embedded'] / r['bits']:.1%}）"   # 已嵌入者全部正確取回，但容量不足未嵌完
            else:
                rev = "❌"
            print(f"| {meta['carrier']} | {r['method']} | {r['case']} | {r['bits'] / 8192:.0f} | {r['alpha']:.3f} | "
                  f"{r['bpp']:.4f} | {r['old']} | {r['meandb']} | **{r['mse_all']}** | {r['mse_pay']} | "
                  f"{r['size']}{'%' if r['size'] != '—' else ''} | {rev} |")
        caps = "；".join(f"{k} {v[0] / 8192:.0f} KiB（{v[1]:.4f} bpp）" for k, v in meta["caps"].items())
        stage1 = (f"來源 {meta['src']:,} B → 無損基準 {meta['base']:,} B（{100 * (meta['base'] - meta['src']) / meta['src']:+.2f}%）"
                  if meta["base"] else "未編碼")
        try:
            shown = os.path.relpath(path)
        except ValueError:                      # 與目前目錄位於不同磁碟機
            shown = path
        notes.append(f"- `{shown.replace(os.sep, '/')}`（sha256 {sha256(path)[:12]}，commit {meta['commit']}）："
                     f"{meta['carrier']}，{meta['frames']} 幀；容量 {caps}；{stage1}")
    print("\n來源 log：")
    print("\n".join(notes))


if __name__ == "__main__":
    main()
