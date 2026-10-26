"""StegoPlayer GUI 探針：載入 stego 影片，記錄 chunk0 開播、chunk0 → 完整音軌切換前後的播放器狀態時間線，並自動截圖。

無法代替人耳判斷斷音；以下列客觀指標判定：
  - 切換瞬間舊/新音訊播放器位置差（應 ≈ 0 ms）
  - 切換前後作用中音訊播放器是否持續處於 Playing 狀態
  - 影片是否因等待 chunk1 而暫停（is_buffering_chunk1）
  - 影音位置差（audio - video）隨時間變化

用法：python src/test/verify/gui_handoff_probe.py <stego.mp4> <out_dir> [--after-handoff 6] [--timeout 90] > <out_dir>/gui_probe_log.txt
"""
import os
import sys
import time
import argparse

from _common import print_header

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
import player_app

STATE = {QMediaPlayer.PlaybackState.PlayingState: "Play", QMediaPlayer.PlaybackState.PausedState: "Pause",
         QMediaPlayer.PlaybackState.StoppedState: "Stop"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stego")
    ap.add_argument("out_dir")
    ap.add_argument("--after-handoff", type=float, default=6.0)
    ap.add_argument("--timeout", type=float, default=90.0)
    a = ap.parse_args()
    print_header(__file__, sys.argv)
    os.makedirs(a.out_dir, exist_ok=True)

    app = QApplication(sys.argv)
    t0 = time.perf_counter()
    now = lambda: (time.perf_counter() - t0) * 1000
    events, samples, shots = [], [], []
    mark = {}

    def ev(name, **kw):
        events.append((now(), name, kw))

    def shot(tag):
        path = os.path.join(a.out_dir, f"{len(shots):02d}_{tag}.png")
        # QVideoWidget 為原生表面，QWidget.grab() 擷取不到影像；改用螢幕擷取視窗範圍
        g = player.frameGeometry()
        player.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(path)
        shots.append((now(), path))

    player = player_app.MultiTrackPlayer(None)

    # 包裝關鍵方法以記錄事件（不改變行為）
    orig_chunk, orig_handoff, orig_log = player.on_chunk_received, player.handoff_to_full_track, player.append_log

    def on_chunk(idx, tracks, last):
        ev(f"chunk{idx}_received", n_tracks=len(tracks), video_pos=player.video_player.position())
        orig_chunk(idx, tracks, last)
        if idx == 0:
            mark["chunk0"] = now()
            QTimer.singleShot(500, lambda: shot("chunk0_playing"))

    def handoff():
        old, new = player.audio_player, player.audio_player_next
        before = dict(video=player.video_player.position(), old_audio=old.position(), new_audio=new.position(),
                      new_ready=player.audio_player_next_ready)
        orig_handoff()
        if before["new_ready"] and "handoff" not in mark:
            mark["handoff"] = now()
            ev("handoff", **before, old_src=os.path.basename(old.source().toLocalFile()),
               new_src=os.path.basename(new.source().toLocalFile()))
            QTimer.singleShot(500, lambda: shot("after_handoff_0.5s"))
            QTimer.singleShot(3000, lambda: shot("after_handoff_3s"))
            QTimer.singleShot(int(a.after_handoff * 1000), finish)

    def log(text, level="INFO"):
        ev("log", level=level, text=text)
        if "平滑緩衝" in text and "buffer_shot" not in mark:
            mark["buffer_shot"] = now()
            QTimer.singleShot(200, lambda: shot("waiting_chunk1"))
        orig_log(text, level)

    player.on_chunk_received, player.handoff_to_full_track, player.append_log = on_chunk, handoff, log

    def sample():
        ap_ = player.audio_player
        samples.append((now(), player.video_player.position(), STATE[player.video_player.playbackState()],
                        ap_.position(), STATE[ap_.playbackState()], ap_.duration(),
                        os.path.basename(ap_.source().toLocalFile()), player.is_playing_chunk0,
                        player.is_buffering_chunk1, player.audio_player_next_ready))

    def finish():
        if "finished" in mark:
            return
        mark["finished"] = now()
        tick.stop()
        shot("final")
        report()
        player.close()
        app.quit()

    def report():
        print("[N] events (t_ms since launch):")
        for t, name, kw in events:
            if name == "log":
                print(f"    {t:9.1f} log[{kw['level']}] {kw['text']}")
            else:
                print(f"    {t:9.1f} {name} {kw}")
        print("[O] timeline samples every 20 ms: t video_pos video_state audio_pos audio_state audio_dur src chunk0 buffering next_ready")
        for s in samples:
            print(f"    {s[0]:9.1f} {s[1]:6d} {s[2]:5s} {s[3]:6d} {s[4]:5s} {s[5]:6d} {s[6]} {int(s[7])} {int(s[8])} {int(s[9])}")
        print("[P] screenshots:")
        for t, p in shots:
            print(f"    {t:9.1f} {os.path.basename(p)}")
        # 判定
        print("[Q] metrics:")
        c0 = mark.get("chunk0")
        first_play = next((s for s in samples if s[4] == "Play" and c0 and s[0] >= c0), None)
        print(f"    chunk0 received at {c0:.1f} ms; first audio Playing at "
              f"{first_play[0]:.1f} ms (+{first_play[0] - c0:.1f} ms)" if c0 and first_play else "    chunk0 never played")
        paused = [s for s in samples if s[8]]
        if paused:
            print(f"    video paused waiting for chunk1: {paused[0][0]:.1f} → {paused[-1][0]:.1f} ms "
                  f"({paused[-1][0] - paused[0][0]:.1f} ms), at video_pos={paused[0][1]}")
        else:
            print("    video never paused waiting for chunk1")
        h = next((e for e in events if e[1] == "handoff"), None)
        if h:
            kw = h[2]
            print(f"    handoff at {h[0]:.1f} ms: video={kw['video']} old_audio={kw['old_audio']} new_audio={kw['new_audio']} "
                  f"(new - old = {kw['new_audio'] - kw['old_audio']:+d} ms) {kw['old_src']} -> {kw['new_src']}")
            win = [s for s in samples if h[0] - 1000 <= s[0] <= h[0] + 2000]
            not_playing = [s for s in win if s[4] != "Play" or s[2] != "Play"]
            print(f"    samples within [-1 s, +2 s] of handoff: {len(win)}, with audio or video not Playing: {len(not_playing)}")
            post = [s for s in samples if s[0] > h[0] + 300 and s[4] == "Play" and s[2] == "Play"]
            if post:
                d = [s[3] - s[1] for s in post]
                print(f"    audio - video after handoff: min={min(d)} max={max(d)} mean={sum(d) / len(d):.1f} ms (n={len(d)})")
        else:
            print("    handoff never happened")

    tick = QTimer()
    tick.timeout.connect(sample)
    tick.start(20)
    QTimer.singleShot(int(a.timeout * 1000), finish)

    player.show()
    ev("load_start")
    player.load_new_video_file(os.path.abspath(a.stego))
    app.exec()


if __name__ == "__main__":
    main()
