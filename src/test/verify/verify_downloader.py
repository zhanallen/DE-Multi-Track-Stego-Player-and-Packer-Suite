"""TC-DL-01、TC-DL-02：不開 GUI，直接執行 download_app 的 FetchInfoThread / DownloadThread（呼叫 run()）。

TC-DL-01：解析 URL，列出與 GUI 相同規則（format 有 language 且非 storyboard）取得的語系清單
TC-DL-02：下載指定語系的 mp3（audio-only 模式；下載器仍會先下載影片本體），檢查檔名規則、可解碼、長度，
          並與參考資料夾中同名語系的 mp3 比對（SHA-256 與解碼後 PCM）

用法：python src/test/verify/verify_downloader.py <url> <out_dir> --langs ja fr-FR de-DE [--ref <dir> --ref-prefix audio_] > <log>
"""
import os
import sys
import glob
import argparse
import subprocess

from _common import FF, sha256, print_header

from PySide6.QtCore import QCoreApplication
import download_app
import yt_dlp


def pcm(path):
    return subprocess.run([FF, "-v", "error", "-i", path, "-f", "s16le", "-ac", "2", "-ar", "44100", "-"],
                          capture_output=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out_dir")
    ap.add_argument("--langs", nargs="+", required=True)
    ap.add_argument("--ref")
    ap.add_argument("--ref-prefix", default="audio_")
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    print(f"# yt-dlp={yt_dlp.version.__version__}  node={download_app.pyinstaller_utils.get_node_path()}")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)  # noqa: F841  QThread 訊號需要 Qt 應用物件

    got = {}
    t = download_app.FetchInfoThread(a.url)
    t.info_signal.connect(lambda info: got.setdefault("info", info))
    t.error_signal.connect(lambda msg: got.setdefault("error", msg))
    t.run()
    if "error" in got:
        print(f"[DL-01] FAIL fetch error: {got['error']}")
        return
    info = got["info"]
    langs = sorted({f.get("language") for f in info.get("formats", [])
                    if f.get("language") and not f.get("format_id", "").startswith("sb")})
    print(f"[DL-01] title={info.get('title')!r} uploader={info.get('uploader')!r} duration={info.get('duration')}s")
    print(f"[DL-01] languages ({len(langs)}): {', '.join(langs)}")
    missing = [l for l in a.langs if l not in langs]
    print(f"[DL-01] RESULT {'PASS' if langs and not missing else 'FAIL'}" + (f" (requested but missing: {missing})" if missing else ""))

    done = {}
    d = download_app.DownloadThread(a.url, a.langs, a.out_dir, info, download_video=False, download_audio=True)
    d.finished_signal.connect(lambda p: done.setdefault("dir", p))
    d.error_signal.connect(lambda m: done.setdefault("error", m))
    d.run()
    if "error" in done:
        print(f"[DL-02] FAIL download error: {done['error']}")
        return
    target = done["dir"]
    print(f"[DL-02] target dir: {os.path.relpath(target)}")
    for f in sorted(os.listdir(target)):
        p = os.path.join(target, f)
        print(f"    file: {f}  size={os.path.getsize(p)}  sha256={sha256(p)[:16]}…")
    fails = 0
    for lang in a.langs:
        hits = glob.glob(os.path.join(target, f"*_audio_{lang}.mp3"))
        if not hits:
            print(f"    {lang}: FAIL no *_audio_{lang}.mp3")
            fails += 1
            continue
        mp3 = hits[0]
        samples = len(pcm(mp3)) // 4
        line = f"    {lang}: name OK, decoded {samples} samples ({samples / 44100:.2f} s)"
        if a.ref:
            ref = os.path.join(a.ref, f"{a.ref_prefix}{lang}.mp3")
            if os.path.exists(ref):
                line += (f"; vs reference: sha_equal={sha256(ref) == sha256(mp3)} "
                         f"pcm_equal={pcm(ref) == pcm(mp3)} (ref {len(pcm(ref)) // 4} samples)")
            else:
                line += "; no reference file"
        fails += samples == 0
        print(line)
    print(f"[DL-02] RESULT {'PASS' if fails == 0 else f'FAIL ({fails})'}")


if __name__ == "__main__":
    main()
