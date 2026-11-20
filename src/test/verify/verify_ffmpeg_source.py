"""TC-ENV-02（與 TC-ENV-01 的機制）：確認程式使用哪一個 ffmpeg。

1. 靜態掃描 src/*.py：所有 ffmpeg 子行程是否都經由 imageio_ffmpeg.get_ffmpeg_exe() 取得路徑
2. 在 PATH 最前面放一個誘餌 ffmpeg.exe（內附 ffmpeg 的複本，位於暫存目錄），於子行程中解析並實際跑一次分塊
3. 設定 IMAGEIO_FFMPEG_EXE 指向誘餌，確認會被採用（外部 FFmpeg 的切換機制）

用法：python src/test/verify/verify_ffmpeg_source.py <some.mp3> > <log>
"""
import os
import re
import sys
import glob
import json
import shutil
import tempfile
import subprocess

from _common import FF, REPO, print_header

PROBE = r"""
import sys, json, os
sys.path.insert(0, sys.argv[1])
import imageio_ffmpeg, audio_chunker, tempfile
exe = imageio_ffmpeg.get_ffmpeg_exe()
d = tempfile.mkdtemp()
c0, c1 = audio_chunker.split_audio_into_chunks(sys.argv[2], initial_sec=3.0, output_dir=d)
print(json.dumps({"get_ffmpeg_exe": exe, "chunker_ffmpeg": audio_chunker.get_ffmpeg_cmd(),
                  "chunks_ok": os.path.getsize(c0) > 0 and os.path.getsize(c1) > 0}))
"""


def main():
    mp3 = sys.argv[1]
    print_header(__file__, sys.argv)
    src = os.path.join(REPO, "src")
    print("[S] static scan of src/*.py for ffmpeg invocations:")
    bad = 0
    for p in sorted(glob.glob(os.path.join(src, "*.py"))):
        for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
            if re.search(r"""['"]ffmpeg(\.exe)?['"]|shutil\.which\(\s*['"]ffmpeg""", line):
                bad += 1
                print(f"    HARDCODED {os.path.basename(p)}:{i}: {line.strip()}")
            elif "get_ffmpeg_exe" in line:
                print(f"    ok        {os.path.basename(p)}:{i}: {line.strip()}")
    print(f"    hardcoded ffmpeg references: {bad}")

    decoy_dir = tempfile.mkdtemp(prefix="decoy_ffmpeg_")
    decoy = os.path.join(decoy_dir, "ffmpeg.exe")
    shutil.copyfile(FF, decoy)
    base_env = {k: v for k, v in os.environ.items() if k != "IMAGEIO_FFMPEG_EXE"}
    cases = [("default", base_env),
             ("decoy first on PATH", {**base_env, "PATH": decoy_dir + os.pathsep + base_env.get("PATH", "")}),
             ("IMAGEIO_FFMPEG_EXE=decoy", {**base_env, "IMAGEIO_FFMPEG_EXE": decoy})]
    print(f"[R] bundled ffmpeg: {FF}")
    print(f"    decoy ffmpeg  : {decoy}")
    fails = 0
    for label, env in cases:
        r = subprocess.run([sys.executable, "-c", PROBE, src, mp3], env=env, capture_output=True, text=True)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            print(f"    {label}: probe failed: {r.stderr[-300:]}")
            fails += 1
            continue
        used = "decoy" if os.path.normcase(res["get_ffmpeg_exe"]) == os.path.normcase(decoy) else \
               ("bundled" if os.path.normcase(res["get_ffmpeg_exe"]) == os.path.normcase(FF) else "other")
        expect = "decoy" if label.startswith("IMAGEIO") else "bundled"
        ok = used == expect and res["chunks_ok"] and res["get_ffmpeg_exe"] == res["chunker_ffmpeg"]
        fails += not ok
        print(f"    {label:26s} -> {used:7s} (expect {expect})  chunker uses same={res['get_ffmpeg_exe'] == res['chunker_ffmpeg']}  "
              f"chunks_ok={res['chunks_ok']}  {'PASS' if ok else 'FAIL'}")
    shutil.rmtree(decoy_dir, ignore_errors=True)
    print(f"[RESULT] {'PASS' if fails == 0 and bad == 0 else 'FAIL'}")


if __name__ == "__main__":
    main()
