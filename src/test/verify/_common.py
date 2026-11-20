"""驗證腳本共用：log 標頭（腳本路徑、commit、環境）與雜湊工具。"""
import os
import sys
import time
import hashlib
import platform
import subprocess

# 受測模組 import 時即會印出 emoji；重導到檔案時 Windows 預設 cp950 會拋 UnicodeEncodeError
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

import numpy as np
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True).stdout.strip()


def print_header(script_file, argv):
    """每份 log 開頭：腳本路徑、HEAD commit、工作區是否有未提交修改、執行環境。"""
    rel =os.path.relpath(os.path.abspath(script_file), REPO).replace("\\", "/")
    # 只以已追蹤檔案的修改判定 dirty；未追蹤的 .py 另列（不影響受測程式碼，但留下紀錄）
    dirty = _git("status", "--porcelain", "--untracked-files=no", "--", "src")
    untracked_py = [l[3:] for l in _git("status", "--porcelain", "--untracked-files=all", "--", "src").splitlines()
                    if l.startswith("??") and l.endswith(".py")]
    print(f"# script  : {rel}  (sha256 {sha256(script_file)[:16]})")
    print(f"# args    : {' '.join(argv[1:])}")
    print(f"# commit  : {_git('rev-parse', 'HEAD')}{'  (src/ has uncommitted changes)' if dirty else ''}")
    if untracked_py:
        print(f"# untracked .py in src/ (not part of commit): {', '.join(untracked_py)}")
    print(f"# run at  : {time.strftime('%Y-%m-%d %H:%M:%S %z')}  host={platform.node()}")
    print(f"# env     : python={platform.python_version()} numpy={np.__version__} ffmpeg={os.path.basename(FF)}")
