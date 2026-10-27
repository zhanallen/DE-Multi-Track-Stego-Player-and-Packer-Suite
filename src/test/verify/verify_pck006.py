"""TC-PCK-006（REQ-PCK-006，DEF-007／TBD-08）：負載超過容量時，StegoPacker 應顯示錯誤對話框且不得啟動封裝。

以 offscreen 模式建立 StegoEmbedApp，設定「payload > 估計容量」後呼叫 start_embedding()；
攔截 QMessageBox 與 EmbeddingThread，檢查：不拋例外、critical 對話框出現一次且文字符合 SRS、未建立封裝執行緒。
另以 payload ≤ 容量的對照組確認會進入封裝（執行緒被建立）。

用法：python src/test/verify/verify_pck006.py > <log>
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from _common import print_header

from PySide6.QtWidgets import QApplication, QMessageBox
import embed_app


def run_case(win, payload, capacity):
    calls, threads = [], []
    QMessageBox.critical = staticmethod(lambda *a, **k: calls.append(("critical", a[2] if len(a) > 2 else "")))
    QMessageBox.warning = staticmethod(lambda *a, **k: calls.append(("warning", a[2] if len(a) > 2 else "")))

    class FakeThread:
        def __init__(self, *a, **k):
            threads.append(a)
            self.progress_signal = self.finished_signal = self.error_signal = self
        def connect(self, *_):
            pass
        def start(self, *_):
            pass

    embed_app.EmbeddingThread = FakeThread
    win.video_path, win.audio_paths, win.output_path = "carrier.mp4", ["a_audio_en.mp3"], "out_stego.mp4"
    win.total_payload_size, win.estimated_capacity = payload, capacity
    try:
        win.start_embedding()
        exc = None
    except Exception as e:  # noqa: BLE001
        exc = f"{type(e).__name__}: {e}"
    return calls, len(threads), exc


def main():
    print_header(__file__, sys.argv)
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    win = embed_app.StegoEmbedApp()
    fails = 0

    calls, nthreads, exc = run_case(win, payload=10 * 1024 * 1024, capacity=1 * 1024 * 1024)
    ok = exc is None and nthreads == 0 and [c[0] for c in calls] == ["critical"] and "exceeds video carrier capacity" in calls[0][1]
    fails += not ok
    print(f"[overflow] exception={exc}  dialogs={calls}  embedding_threads={nthreads}  -> {'PASS' if ok else 'FAIL'}")

    calls, nthreads, exc = run_case(win, payload=1 * 1024 * 1024, capacity=10 * 1024 * 1024)
    ok = exc is None and nthreads == 1 and not calls
    fails += not ok
    print(f"[control ] exception={exc}  dialogs={calls}  embedding_threads={nthreads}  -> {'PASS' if ok else 'FAIL'}")
    print(f"[RESULT] {'PASS' if fails == 0 else f'FAIL ({fails})'}")


if __name__ == "__main__":
    main()
