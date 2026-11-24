import os
import sys
import re
import shutil
import time
import datetime
from collections import deque

import pyinstaller_utils
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFrame, QMessageBox,
    QFileDialog, QStackedWidget, QProgressBar, QPlainTextEdit, QSizePolicy,
    QAbstractItemView
)
from PySide6.QtCore import Qt, QUrl, QTimer, QThread, Signal, QLocale, QSettings, QSize, QEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PySide6.QtGui import QFont, QKeySequence, QShortcut

# Import unified Stego Facade module supporting both Coltuc PEE and Zhang-Zeng-Ou 2D HS
from stego_facade import decode_video_multi

# Warm Retro Pixel Tactile UI modules (0px sharp corners, Cubic 11 pixel font, zero blur)
from player_ui_theme import (
    RETRO_PIXEL,
    build_player_stylesheet,
    enable_windows_integrated_chrome,
    handle_windows_native_event,
    load_display_font,
    load_pixel_font,
)
from player_ui_icons import get_icon
from player_ui_widgets import (
    ROLE_BADGE_TEXT,
    ROLE_DISPLAY_NAME,
    ROLE_TRACK_STATE,
    RetroDropHeroWidget,
    RetroSegmentedSlider,
    RetroToggleSwitch,
    RetroTrackDelegate,
    RetroVolumeBar,
    VideoStageWidget,
)

# Supported video extensions for drag-and-drop & file dialog
SUPPORTED_VIDEO_EXTS = (".mp4", ".webm", ".avi", ".mkv")

# Clean concise native language labels matching the retro track list
LANGUAGE_MAP = {
    "ar": "العربية",
    "bn": "বাংলা",
    "de-DE": "Deutsch",
    "en": "English (UK)",
    "en-US": "English",
    "es-US": "Español",
    "fr-FR": "Français",
    "hi": "हिन्दी",
    "id": "Indonesia",
    "it": "Italiano",
    "iw": "עברית",
    "ja": "日本語",
    "ko": "한국어",
    "ml": "Malayalam",
    "nl-NL": "Nederlands",
    "pl": "Polski",
    "pt-BR": "Português",
    "ru": "Русский",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "uk": "Українська",
    "zh-TW": "繁體中文",
    "zh-CN": "简体中文",
    "zh": "中文",
}


def is_same_path(p1, p2):
    if not p1 or not p2:
        return False
    return os.path.normcase(os.path.normpath(str(p1))) == os.path.normcase(os.path.normpath(str(p2)))


def _set_dynamic_prop(widget, name: str, value) -> None:
    """Update a Qt dynamic property and re-polish only when the value changes."""
    if widget.property(name) != value:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class _RetroCloseButton(QPushButton):
    """Square cream close button that flips its X icon to cream on crimson hover."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WinCloseBtn")
        self.setIcon(get_icon("win_close", 13, RETRO_PIXEL["ink"]))
        self.setIconSize(QSize(13, 13))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("關閉")

    def enterEvent(self, event):
        self.setIcon(get_icon("win_close", 13, RETRO_PIXEL["on_dark"]))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(get_icon("win_close", 13, RETRO_PIXEL["ink"]))
        super().leaveEvent(event)


class ExtractionThread(QThread):
    progress_signal = Signal(int, int, int, int)  # current_frame, total_frames, bit_idx, target_bits
    manifest_signal = Signal(dict)                # manifest info dictionary resolved in Frame 0
    chunk_signal = Signal(int, dict, bool)        # chunk_idx, tracks_dict, is_last
    finished_signal = Signal(dict)                # extracted tracks dictionary
    error_signal = Signal(str)

    def __init__(self, video_path, temp_dir):
        super().__init__()
        self.video_path = video_path
        self.temp_dir = temp_dir
        self.file_md5 = "Calculating..."

    def run(self):
        try:
            # 1. Compute file MD5 in background for Zero-Trust verification
            import hashlib
            md5_hash = hashlib.md5()
            with open(self.video_path, "rb") as f:
                for chunk in iter(lambda: f.read(81920), b""):
                    md5_hash.update(chunk)
            self.file_md5 = md5_hash.hexdigest()

            # 2. Extract stego payload with streaming chunk callbacks
            def progress_cb(current_frame, total_frames, bit_idx, target_bits):
                self.progress_signal.emit(current_frame, total_frames, bit_idx, target_bits)

            def manifest_cb(manifest_info):
                self.manifest_signal.emit(manifest_info)

            def chunk_cb(chunk_idx, tracks_dict, is_last):
                self.chunk_signal.emit(chunk_idx, tracks_dict, is_last)

            tracks = decode_video_multi(
                self.video_path,
                self.temp_dir,
                progress_callback=progress_cb,
                on_manifest_ready=manifest_cb,
                on_chunk_ready=chunk_cb,
            )
            self.finished_signal.emit(tracks)
        except Exception as e:
            self.file_md5 = "Error"
            self.error_signal.emit(str(e))


class I18nDetectionWorker(QThread):
    finished_signal = Signal(str, object)

    def __init__(self, session_id, available_tracks, system_languages, history_lang, db_path, ip_lock_mode=True):
        super().__init__()
        self.session_id = session_id
        self.available_tracks = available_tracks
        self.system_languages = system_languages
        self.history_lang = history_lang
        self.db_path = db_path
        self.ip_lock_mode = ip_lock_mode

    def run(self):
        try:
            from i18n_detector import detect_best_locale
            res = detect_best_locale(
                self.available_tracks,
                self.system_languages,
                self.history_lang,
                self.db_path,
                ip_lock_mode=self.ip_lock_mode,
            )
            self.finished_signal.emit(self.session_id, res)
        except Exception as e:
            from i18n_detector import DetectionResult
            fallback_res = DetectionResult(
                track_key=self.available_tracks[0] if self.available_tracks else "en-US",
                source="THREAD_ERROR",
                resolved_by="THREAD_ERROR",
                detail=f"Thread execution error: {str(e)}",
            )
            self.finished_signal.emit(self.session_id, fallback_res)


class MultiTrackPlayer(QMainWindow):
    PAGE_LANDING = 0
    PAGE_PLAYER = 1
    SIDEBAR_TRACKS = 0
    SIDEBAR_DETAILS = 1

    def __init__(self, initial_video_path=None):
        super().__init__()
        self.pixel_font_family = load_pixel_font()
        self.display_font_family = load_display_font()
        self.setWindowTitle("DE_STEGO_PLAYER.EXE")
        self.resize(1120, 680)
        self.setMinimumSize(740, 480)
        self.setAcceptDrops(True)

        # Core playback & extraction state
        self.video_path = None
        self.audio_tracks = {}
        self.temp_dir = None
        self.slider_is_dragging = False
        self.current_lang = None
        self.is_user_playing = False
        self.last_sync_seek = 0
        self.extract_thread = None
        self.current_i18n_thread = None
        self.user_manually_selected = False
        self.pending_language = None

        # Zero-Trust IP Lock & Geo-Fencing State
        settings = QSettings("GradProject", "StegoPlayer")
        raw_lock_val = settings.value("ip_lock_enabled", True)
        if isinstance(raw_lock_val, str):
            self.ip_lock_enabled = raw_lock_val.lower() in ("true", "1")
        else:
            self.ip_lock_enabled = bool(raw_lock_val)

        self.detected_country = "TW"
        self.detected_ip = "127.0.0.1"
        self.ip_matched_track = None
        self.ip_allowed_tracks = []
        self.cached_i18n_result = None

        # Extraction telemetry & lazy log buffer (zero hidden DOM/QTextEdit churn)
        self.extraction_start_time = 0.0
        self.last_reported_frame = 0
        self.metadata_parsed = False
        self.audio_tracks_manifest = []
        self.audio_pending_seek = None
        self.current_volume = 0.8
        self._last_progress_ui_time = 0.0
        self._last_progress_pct = -1
        self._log_buffer = deque(maxlen=250)
        self._log_dirty = False
        self._in_fullscreen = False
        self._was_maximized_before_fs = False
        self._sidebar_open_before_fs = False
        self._titlebar_styled = False

        # Initialize Media Players
        self.video_player = QMediaPlayer()
        self.video_audio_output = QAudioOutput()
        self.video_player.setAudioOutput(self.video_audio_output)
        self.video_audio_output.setVolume(self.current_volume)

        # Dual-player seamless gapless audio pipeline
        self.audio_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.current_volume)

        self.audio_player_next = QMediaPlayer()
        self.audio_output_next = QAudioOutput()
        self.audio_player_next.setAudioOutput(self.audio_output_next)
        self.audio_output_next.setVolume(self.current_volume)

        self.is_playing_chunk0 = False
        self.audio_player_next_ready = False
        self.audio_player_next_loading = False
        self.audio_player_next_seeked = False
        self.handoff_pending_resume = False
        self.initial_chunk_sec = 3.0
        self.is_buffering_chunk1 = False

        # Build Warm Retro Pixel UI & keyboard shortcuts
        self.init_ui()
        self._setup_shortcuts()

        # Setup System Default Audio Device (auto-tracking)
        self.setup_default_audio_device()

        # Pre-warm GeoIP detection in background
        QTimer.singleShot(50, self.prewarm_geoip_context)

        # Connect Media Signals
        self.video_player.positionChanged.connect(self.on_video_position_changed)
        self.video_player.durationChanged.connect(self.on_duration_changed)

        self.video_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.audio_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.audio_player_next.mediaStatusChanged.connect(self.on_media_status_changed)

        # Timer for sync
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(50)
        self.sync_timer.timeout.connect(self.sync_check)
        self.sync_timer.start()

        # If a file was passed as argument, load it immediately
        if initial_video_path:
            self.load_new_video_file(initial_video_path)

    # ── UI Construction ────────────────────────────────────────────────────

    def init_ui(self):
        self.root_container = QWidget()
        self.root_container.setObjectName("RootContainer")
        root_vbox = QVBoxLayout(self.root_container)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        self._build_title_bar()
        root_vbox.addWidget(self.title_bar)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("StackedWidget")
        self.stacked_widget.currentChanged.connect(self._sync_titlebar_for_page)
        root_vbox.addWidget(self.stacked_widget, stretch=1)

        self.setCentralWidget(self.root_container)

        self._build_landing_page()
        self._build_player_page()
        self._sync_titlebar_for_page(self.PAGE_LANDING)
        self.apply_stylesheet()

    def _build_title_bar(self):
        """Integrated 40px Terracotta retro title bar with square cream hardware buttons."""
        self.title_bar = QFrame()
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(40)
        self.player_header = self.title_bar

        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(14, 0, 8, 0)
        tb_layout.setSpacing(10)

        # Landing-only app title
        self.lbl_app_name = QLabel("DE_STEGO_PLAYER.EXE")
        self.lbl_app_name.setObjectName("TitleAppName")
        tb_layout.addWidget(self.lbl_app_name, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Player-only filename + clean status badge (no status dot)
        self.lbl_header_filename = QLabel("PLAYER")
        self.lbl_header_filename.setObjectName("HeaderFileName")
        self.lbl_header_filename.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        tb_layout.addWidget(self.lbl_header_filename, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_hud_fps = QLabel("就緒")
        self.lbl_hud_fps.setObjectName("StatusBadge")
        self.lbl_hud_fps.setFixedHeight(22)
        self.lbl_hud_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hud_fps.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        tb_layout.addWidget(self.lbl_hud_fps, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Flexible native draggable empty space
        tb_layout.addStretch(1)

        # Player-only compact Open File button
        self.open_button = QPushButton(" 開啟檔案")
        self.open_button.setObjectName("HeaderOpenBtn")
        self.open_button.setIcon(get_icon("folder_open", 14, RETRO_PIXEL["ink"]))
        self.open_button.setIconSize(QSize(14, 14))
        self.open_button.setFixedHeight(26)
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_button.setToolTip("開啟影片檔案 (Ctrl+O)")
        self.open_button.clicked.connect(self.open_file_dialog)
        tb_layout.addWidget(self.open_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Square Cream Retro Caption Buttons
        cap_box = QHBoxLayout()
        cap_box.setContentsMargins(2, 0, 0, 0)
        cap_box.setSpacing(6)

        self.btn_win_min = QPushButton()
        self.btn_win_min.setObjectName("WinMinBtn")
        self.btn_win_min.setIcon(get_icon("win_minimize", 13, RETRO_PIXEL["ink"]))
        self.btn_win_min.setIconSize(QSize(13, 13))
        self.btn_win_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_win_min.setToolTip("最小化")
        self.btn_win_min.clicked.connect(self.showMinimized)
        cap_box.addWidget(self.btn_win_min)

        self.btn_win_max = QPushButton()
        self.btn_win_max.setObjectName("WinMaxBtn")
        self.btn_win_max.setIcon(get_icon("win_maximize", 13, RETRO_PIXEL["ink"]))
        self.btn_win_max.setIconSize(QSize(13, 13))
        self.btn_win_max.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_win_max.setToolTip("最大化")
        self.btn_win_max.clicked.connect(self.toggle_maximize)
        cap_box.addWidget(self.btn_win_max)

        self.btn_win_close = _RetroCloseButton()
        self.btn_win_close.clicked.connect(self.close)
        cap_box.addWidget(self.btn_win_close)

        tb_layout.addLayout(cap_box)

        self._player_titlebar_widgets = (
            self.lbl_header_filename,
            self.lbl_hud_fps,
            self.open_button,
        )

    def _sync_titlebar_for_page(self, page_index: int):
        is_player = page_index == self.PAGE_PLAYER
        self.lbl_app_name.setVisible(not is_player)
        for w in self._player_titlebar_widgets:
            w.setVisible(is_player)

    def _build_landing_page(self):
        self.page_landing = QFrame()
        self.page_landing.setObjectName("LandingPage")
        outer = QVBoxLayout(self.page_landing)
        outer.setContentsMargins(52, 42, 52, 44)
        outer.setSpacing(0)

        lbl_title = QLabel("DE Multi-Track Stego Player")
        lbl_title.setObjectName("WelcomeTitle")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(lbl_title)

        outer.addSpacing(14)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)
        sub_row.setSpacing(6)
        sub_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_sub = QLabel("> 把聲音藏進畫面裡，再完美還原")
        lbl_sub.setObjectName("WelcomeSub")
        cursor_block = QFrame()
        cursor_block.setObjectName("CursorBlock")
        sub_row.addWidget(lbl_sub)
        sub_row.addWidget(cursor_block, alignment=Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(sub_row)

        outer.addSpacing(34)

        self.drop_hero = RetroDropHeroWidget(self.pixel_font_family, self.display_font_family)
        self.drop_hero.clicked.connect(self.open_file_dialog)
        outer.addWidget(self.drop_hero, stretch=1)

        self.stacked_widget.addWidget(self.page_landing)

    def _build_player_page(self):
        self.page_player = QFrame()
        self.page_player.setObjectName("PlayerPage")
        root_layout = QVBoxLayout(self.page_player)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Middle Content Row: Video Stage + Collapsible Warm Cream Right Sidebar
        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)

        stage_col = QVBoxLayout()
        stage_col.setContentsMargins(0, 0, 0, 0)
        stage_col.setSpacing(0)

        self.video_container = QFrame()
        self.video_container.setObjectName("VideoContainerFrame")
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)

        self.video_widget = VideoStageWidget()
        self.video_widget.doubleClicked.connect(self.toggle_fullscreen)
        video_layout.addWidget(self.video_widget)
        self.video_player.setVideoOutput(self.video_widget)

        stage_col.addWidget(self.video_container, stretch=1)

        # Docked Retro Buffering / Decoding Strip (sits outside QVideoWidget, zero flicker)
        self.buffer_strip = QFrame()
        self.buffer_strip.setObjectName("BufferStrip")
        buffer_layout = QHBoxLayout(self.buffer_strip)
        buffer_layout.setContentsMargins(14, 7, 14, 7)
        buffer_layout.setSpacing(12)

        self.lbl_buffer_title = QLabel("首塊音訊解碼中")
        self.lbl_buffer_title.setObjectName("BufferStripTitle")
        buffer_layout.addWidget(self.lbl_buffer_title)

        self.buffer_progress_bar = QProgressBar()
        self.buffer_progress_bar.setObjectName("BufferProgressBar")
        self.buffer_progress_bar.setRange(0, 100)
        self.buffer_progress_bar.setValue(0)
        self.buffer_progress_bar.setFixedHeight(14)
        self.buffer_progress_bar.setTextVisible(False)
        buffer_layout.addWidget(self.buffer_progress_bar, stretch=1)

        self.lbl_buffer_status = QLabel("正在啟動解密管線...")
        self.lbl_buffer_status.setObjectName("BufferStripDetail")
        buffer_layout.addWidget(self.lbl_buffer_status)

        self.buffer_strip.hide()
        stage_col.addWidget(self.buffer_strip)

        body_row.addLayout(stage_col, stretch=1)

        # Right Collapsible Warm Cream Sidebar (Audio Tracks + Details sub-view)
        self._build_retro_sidebar()
        body_row.addWidget(self.sidebar)

        root_layout.addLayout(body_row, stretch=1)

        # 2. Single-Row Hardware Bottom Control Bar
        self.control_bar = QFrame()
        self.control_bar.setObjectName("ControlBarFrame")
        self.control_bar.setFixedHeight(56)
        ctrl_layout = QHBoxLayout(self.control_bar)
        ctrl_layout.setContentsMargins(12, 0, 12, 0)
        ctrl_layout.setSpacing(10)

        # Sage Green Square Play/Pause Button
        self.play_button = QPushButton()
        self.play_button.setObjectName("PlayButton")
        self.play_button.setIcon(get_icon("play", 16, RETRO_PIXEL["ink"]))
        self.play_button.setIconSize(QSize(16, 16))
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_button.setToolTip("播放 / 暫停 (Space)")
        self.play_button.clicked.connect(self.toggle_play)
        ctrl_layout.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Segmented Terracotta Block Timeline
        self.progress_slider = RetroSegmentedSlider()
        self.progress_slider.dragStarted.connect(self.on_slider_pressed)
        self.progress_slider.previewChanged.connect(self.on_slider_preview_changed)
        self.progress_slider.seekRequested.connect(self.on_slider_seek_requested)
        ctrl_layout.addWidget(self.progress_slider, stretch=1)

        # Pixel Timecode
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("TimeLabel")
        ctrl_layout.addWidget(self.time_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Mute Square Button
        self.mute_button = QPushButton()
        self.mute_button.setObjectName("MuteButton")
        self.mute_button.setIcon(get_icon("volume_high", 15, RETRO_PIXEL["ink"]))
        self.mute_button.setIconSize(QSize(15, 15))
        self.mute_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mute_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mute_button.setToolTip("靜音 / 取消靜音 (M)")
        self.mute_button.clicked.connect(self.toggle_mute)
        ctrl_layout.addWidget(self.mute_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Crisp Bordered Volume Bar
        self.volume_slider = RetroVolumeBar()
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.seekRequested.connect(self.on_volume_changed)
        self.audio_output.setVolume(0.8)
        ctrl_layout.addWidget(self.volume_slider, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Vertical Ink Divider
        ctrl_div = QFrame()
        ctrl_div.setObjectName("ControlDivider")
        ctrl_layout.addWidget(ctrl_div, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Stats / Details Toggle Button
        self.btn_stats = QPushButton()
        self.btn_stats.setObjectName("StatsButton")
        self.btn_stats.setIcon(get_icon("stats_bars", 15, RETRO_PIXEL["ink"]))
        self.btn_stats.setIconSize(QSize(15, 15))
        self.btn_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stats.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stats.setToolTip("詳細資訊與安全驗證 (I)")
        self.btn_stats.clicked.connect(self.toggle_details_panel)
        ctrl_layout.addWidget(self.btn_stats, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Audio Tracks Sidebar Toggle Button (inverted dark when active)
        self.tracks_toggle_button = QPushButton()
        self.tracks_toggle_button.setObjectName("TracksToggleButton")
        self.tracks_toggle_button.setIcon(get_icon("globe", 15, RETRO_PIXEL["ink"]))
        self.tracks_toggle_button.setIconSize(QSize(15, 15))
        self.tracks_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tracks_toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tracks_toggle_button.setToolTip("展開 / 收合音軌面板 (T)")
        self.tracks_toggle_button.clicked.connect(self.toggle_tracks_panel)
        ctrl_layout.addWidget(self.tracks_toggle_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Fullscreen Square Button
        self.fullscreen_button = QPushButton()
        self.fullscreen_button.setObjectName("FullscreenButton")
        self.fullscreen_button.setIcon(get_icon("fullscreen", 15, RETRO_PIXEL["ink"]))
        self.fullscreen_button.setIconSize(QSize(15, 15))
        self.fullscreen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fullscreen_button.setToolTip("切換全螢幕 (F / 雙擊畫面)")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        ctrl_layout.addWidget(self.fullscreen_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        root_layout.addWidget(self.control_bar)
        self.stacked_widget.addWidget(self.page_player)

        self._sync_sidebar_buttons()

    def _build_retro_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("SidebarFrame")
        self.sidebar.setFixedWidth(298)
        outer = QVBoxLayout(self.sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar_stack = QStackedWidget()
        outer.addWidget(self.sidebar_stack)

        # ── View 0: Audio Tracks Panel (matching reference 1-to-1) ─────────
        tracks_view = QWidget()
        tv_layout = QVBoxLayout(tracks_view)
        tv_layout.setContentsMargins(16, 16, 16, 14)
        tv_layout.setSpacing(12)

        # Header row: Globe icon + "音軌" + [>>] collapse button
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(8)

        globe_lbl = QLabel()
        globe_lbl.setFixedSize(20, 20)
        globe_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        globe_lbl.setPixmap(get_icon("globe", 18, RETRO_PIXEL["ink"]).pixmap(18, 18))
        hdr.addWidget(globe_lbl)

        lbl_tracks_title = QLabel("音軌")
        lbl_tracks_title.setObjectName("SidebarTitle")
        hdr.addWidget(lbl_tracks_title)
        hdr.addStretch()

        btn_collapse = QPushButton()
        btn_collapse.setObjectName("DrawerCollapseBtn")
        btn_collapse.setIcon(get_icon("collapse_right", 13, RETRO_PIXEL["ink"]))
        btn_collapse.setIconSize(QSize(13, 13))
        btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_collapse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_collapse.setToolTip("收合側邊欄")
        btn_collapse.clicked.connect(self.collapse_sidebar)
        hdr.addWidget(btn_collapse)
        tv_layout.addLayout(hdr)

        # IP Lock Mechanical Toggle Card
        ip_box = QFrame()
        ip_box.setObjectName("IpLockBox")
        ip_box.setFixedHeight(42)
        ip_row = QHBoxLayout(ip_box)
        ip_row.setContentsMargins(12, 0, 10, 0)
        ip_row.setSpacing(8)

        self.lbl_ip_lock_icon = QLabel()
        self.lbl_ip_lock_icon.setFixedSize(16, 16)
        self.lbl_ip_lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ip_row.addWidget(self.lbl_ip_lock_icon)

        lbl_ip_text = QLabel("IP 鎖定")
        lbl_ip_text.setObjectName("IpLockTitle")
        ip_row.addWidget(lbl_ip_text)
        ip_row.addStretch()

        self.ip_lock_switch = RetroToggleSwitch()
        self.ip_lock_switch.clicked.connect(self.toggle_ip_lock)
        ip_row.addWidget(self.ip_lock_switch)
        tv_layout.addWidget(ip_box)

        # Micro section header: AUDIO TRACKS · N
        self.lbl_track_count = QLabel("AUDIO TRACKS · 0")
        self.lbl_track_count.setObjectName("TrackCountCaption")
        tv_layout.addWidget(self.lbl_track_count)

        # Custom Delegate Track List (zero child-widget overhead)
        self.lang_list = QListWidget()
        self.lang_list.setObjectName("LanguageList")
        self.lang_list.setFont(QFont(self.pixel_font_family, 11, QFont.Weight.Bold))
        self.lang_list.setItemDelegate(RetroTrackDelegate(self.lang_list))
        self.lang_list.setMouseTracking(True)
        self.lang_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lang_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.lang_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lang_list.setSpacing(0)
        self.lang_list.itemClicked.connect(self.on_lang_item_clicked)
        tv_layout.addWidget(self.lang_list, stretch=1)

        # Bottom pinned [ⓘ 詳細資訊] button
        self.btn_open_details = QPushButton(" 詳細資訊")
        self.btn_open_details.setObjectName("DetailsBottomBtn")
        self.btn_open_details.setIcon(get_icon("info", 15, RETRO_PIXEL["ink"]))
        self.btn_open_details.setIconSize(QSize(15, 15))
        self.btn_open_details.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_details.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open_details.clicked.connect(lambda: self.show_sidebar_view(self.SIDEBAR_DETAILS))
        tv_layout.addWidget(self.btn_open_details)

        self.sidebar_stack.addWidget(tracks_view)

        # ── View 1: Details Panel (Zero-Trust Security + Deferred Logs) ────
        details_view = QWidget()
        dv_layout = QVBoxLayout(details_view)
        dv_layout.setContentsMargins(16, 16, 16, 14)
        dv_layout.setSpacing(10)

        dhdr = QHBoxLayout()
        dhdr.setContentsMargins(0, 0, 0, 0)
        dhdr.setSpacing(8)

        btn_back = QPushButton()
        btn_back.setObjectName("DrawerBackBtn")
        btn_back.setIcon(get_icon("back_left", 13, RETRO_PIXEL["ink"]))
        btn_back.setIconSize(QSize(13, 13))
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_back.setToolTip("返回音軌清單")
        btn_back.clicked.connect(lambda: self.show_sidebar_view(self.SIDEBAR_TRACKS))
        dhdr.addWidget(btn_back)

        lbl_det_title = QLabel("詳細資訊")
        lbl_det_title.setObjectName("SidebarTitle")
        dhdr.addWidget(lbl_det_title)
        dhdr.addStretch()

        btn_collapse2 = QPushButton()
        btn_collapse2.setObjectName("DrawerCollapseBtn")
        btn_collapse2.setIcon(get_icon("collapse_right", 13, RETRO_PIXEL["ink"]))
        btn_collapse2.setIconSize(QSize(13, 13))
        btn_collapse2.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_collapse2.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_collapse2.setToolTip("收合側邊欄")
        btn_collapse2.clicked.connect(self.collapse_sidebar)
        dhdr.addWidget(btn_collapse2)
        dv_layout.addLayout(dhdr)

        # Retro Segmented Tabs: 安全驗證 | 解碼日誌
        seg_bar = QFrame()
        seg_bar.setObjectName("SegmentBar")
        seg_layout = QHBoxLayout(seg_bar)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)

        self.btn_tab_info = QPushButton("安全驗證")
        self.btn_tab_info.setObjectName("TabInfoBtn")
        self.btn_tab_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_info.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tab_info.clicked.connect(lambda: self._switch_inspector_tab(0))

        self.btn_tab_log = QPushButton("解碼日誌")
        self.btn_tab_log.setObjectName("TabLogBtn")
        self.btn_tab_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tab_log.clicked.connect(lambda: self._switch_inspector_tab(1))

        seg_layout.addWidget(self.btn_tab_info)
        seg_layout.addWidget(self.btn_tab_log)
        dv_layout.addWidget(seg_bar)

        self.inspector_stack = QStackedWidget()

        # Tab 0: Security & Forensics Info
        tab_info = QWidget()
        info_layout = QVBoxLayout(tab_info)
        info_layout.setContentsMargins(0, 2, 0, 0)
        info_layout.setSpacing(10)

        sec_card = QFrame()
        sec_card.setObjectName("SecurityInfoFrame")
        sec_layout = QVBoxLayout(sec_card)
        sec_layout.setContentsMargins(12, 10, 12, 10)
        sec_layout.setSpacing(7)

        cap_sec = QLabel("ZERO-TRUST 驗證狀態")
        cap_sec.setObjectName("SectionCaption")
        sec_layout.addWidget(cap_sec)

        def add_kv_row(key_text: str, initial_val: str = "載入中...") -> QLabel:
            row = QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(1)
            k = QLabel(key_text)
            k.setObjectName("InfoKey")
            v = QLabel(initial_val)
            v.setObjectName("InfoVal")
            v.setWordWrap(True)
            row.addWidget(k)
            row.addWidget(v)
            sec_layout.addLayout(row)
            return v

        self.lbl_info_decode = add_kv_row("解碼進度", "待命")
        self.lbl_stego_checksum = add_kv_row("檔案 MD5", "待命")
        self.lbl_sec_ip = add_kv_row("客戶端 IP")
        self.lbl_sec_proxy = add_kv_row("本機代理")
        self.lbl_sec_geo = add_kv_row("地理國家")
        self.lbl_sec_decision = add_kv_row("決策路徑")
        self.lbl_sec_trust = add_kv_row("信任等級")

        info_layout.addWidget(sec_card)

        self.btn_web_sim = QPushButton(" 開啟安全性分析網頁")
        self.btn_web_sim.setObjectName("WebSimButton")
        self.btn_web_sim.setIcon(get_icon("external_link", 14, RETRO_PIXEL["on_dark"]))
        self.btn_web_sim.setIconSize(QSize(14, 14))
        self.btn_web_sim.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_web_sim.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_web_sim.clicked.connect(self.launch_web_dashboard)
        info_layout.addWidget(self.btn_web_sim)

        is_dev_mode = (
            not getattr(sys, "frozen", False)
            and (os.environ.get("DE_DEV_MODE") == "1" or "--dev" in sys.argv or "--debug" in sys.argv)
        )
        if not is_dev_mode:
            self.btn_web_sim.hide()

        info_layout.addStretch()
        self.inspector_stack.addWidget(tab_info)

        # Tab 1: Deferred Plain-Text Console Log
        tab_log = QWidget()
        log_layout = QVBoxLayout(tab_log)
        log_layout.setContentsMargins(0, 2, 0, 0)
        log_layout.setSpacing(0)

        self.console_output = QPlainTextEdit()
        self.console_output.setObjectName("TerminalConsole")
        self.console_output.setReadOnly(True)
        self.console_output.setMaximumBlockCount(250)
        log_layout.addWidget(self.console_output)
        self.inspector_stack.addWidget(tab_log)

        dv_layout.addWidget(self.inspector_stack, stretch=1)

        btn_back_bottom = QPushButton(" 返回音軌清單")
        btn_back_bottom.setObjectName("DetailsBottomBtn")
        btn_back_bottom.setIcon(get_icon("back_left", 13, RETRO_PIXEL["ink"]))
        btn_back_bottom.setIconSize(QSize(13, 13))
        btn_back_bottom.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back_bottom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_back_bottom.clicked.connect(lambda: self.show_sidebar_view(self.SIDEBAR_TRACKS))
        dv_layout.addWidget(btn_back_bottom)

        self.sidebar_stack.addWidget(details_view)

        self.update_ip_lock_button_ui()
        self._switch_inspector_tab(0)
        self.sidebar_stack.setCurrentIndex(self.SIDEBAR_TRACKS)
        # Open by default on player page to match the retro hardware layout
        self.sidebar.show()

    def apply_stylesheet(self):
        self.setStyleSheet(
            build_player_stylesheet(RETRO_PIXEL, self.pixel_font_family, self.display_font_family)
        )

    def showEvent(self, event):
        super().showEvent(event)
        if not self._titlebar_styled:
            self._titlebar_styled = True
            enable_windows_integrated_chrome(self)

    def nativeEvent(self, eventType, message):
        handled, result = handle_windows_native_event(
            self, getattr(self, "title_bar", None), eventType, message
        )
        if handled:
            return True, result
        return super().nativeEvent(eventType, message)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "btn_win_max"):
            if self.isMaximized():
                self.btn_win_max.setIcon(get_icon("win_restore", 13, RETRO_PIXEL["ink"]))
                self.btn_win_max.setToolTip("還原")
            else:
                self.btn_win_max.setIcon(get_icon("win_maximize", 13, RETRO_PIXEL["ink"]))
                self.btn_win_max.setToolTip("最大化")

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ── Keyboard Shortcuts & Drag-and-Drop ─────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_file_dialog)

    def keyPressEvent(self, event):
        key = event.key()
        on_player = self.stacked_widget.currentIndex() == self.PAGE_PLAYER

        if key == Qt.Key.Key_Escape:
            if self._in_fullscreen:
                self.toggle_fullscreen()
                return
            if not self.sidebar.isHidden():
                self.collapse_sidebar()
                return

        if not on_player:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Space:
            self.toggle_play()
        elif key == Qt.Key.Key_Left:
            self.seek_relative(-5000)
        elif key == Qt.Key.Key_Right:
            self.seek_relative(5000)
        elif key == Qt.Key.Key_Up:
            self._step_volume(5)
        elif key == Qt.Key.Key_Down:
            self._step_volume(-5)
        elif key == Qt.Key.Key_M:
            self.toggle_mute()
        elif key == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_T:
            self.toggle_tracks_panel()
        elif key == Qt.Key.Key_I:
            self.toggle_details_panel()
        else:
            super().keyPressEvent(event)

    def _extract_dropped_video(self, mime_data):
        if mime_data and mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(SUPPORTED_VIDEO_EXTS) and os.path.isfile(path):
                        return path
        return None

    def dragEnterEvent(self, event):
        video_path = self._extract_dropped_video(event.mimeData())
        if video_path:
            event.acceptProposedAction()
            if self.stacked_widget.currentIndex() == self.PAGE_LANDING:
                self.drop_hero.set_drag_state(True, os.path.basename(video_path))
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_hero.set_drag_state(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_hero.set_drag_state(False)
        video_path = self._extract_dropped_video(event.mimeData())
        if video_path:
            event.acceptProposedAction()
            self.load_new_video_file(video_path)
        else:
            event.ignore()

    # ── UI Helper Updates & Sidebar Navigation ─────────────────────────────

    def _update_play_button_icon(self):
        icon_name = "pause" if self.is_user_playing else "play"
        self.play_button.setIcon(get_icon(icon_name, 16, RETRO_PIXEL["ink"]))

    def _update_volume_icon(self):
        if self.audio_output.isMuted() or self.volume_slider.value() == 0:
            icon_name = "volume_mute"
        elif self.volume_slider.value() < 50:
            icon_name = "volume_low"
        else:
            icon_name = "volume_high"
        self.mute_button.setIcon(get_icon(icon_name, 15, RETRO_PIXEL["ink"]))

    def _set_status_badge(self, text: str, state: str = "idle"):
        self.lbl_hud_fps.setText(text)
        _set_dynamic_prop(self.lbl_hud_fps, "state", state)

    def _sync_sidebar_buttons(self):
        is_open = not self.sidebar.isHidden()
        in_tracks = is_open and self.sidebar_stack.currentIndex() == self.SIDEBAR_TRACKS
        in_details = is_open and self.sidebar_stack.currentIndex() == self.SIDEBAR_DETAILS

        _set_dynamic_prop(self.tracks_toggle_button, "active", in_tracks)
        self.tracks_toggle_button.setIcon(
            get_icon("globe", 15, RETRO_PIXEL["on_dark"] if in_tracks else RETRO_PIXEL["ink"])
        )

        _set_dynamic_prop(self.btn_stats, "active", in_details)
        self.btn_stats.setIcon(
            get_icon("stats_bars", 15, RETRO_PIXEL["on_dark"] if in_details else RETRO_PIXEL["ink"])
        )

    def show_sidebar_view(self, view_idx: int):
        self.sidebar_stack.setCurrentIndex(view_idx)
        self.sidebar.show()
        self._sync_sidebar_buttons()
        if view_idx == self.SIDEBAR_DETAILS and self.inspector_stack.currentIndex() == 1 and self._log_dirty:
            self._flush_logs_to_console()

    def collapse_sidebar(self):
        self.sidebar.hide()
        self._sync_sidebar_buttons()

    def toggle_tracks_panel(self):
        if not self.sidebar.isHidden() and self.sidebar_stack.currentIndex() == self.SIDEBAR_TRACKS:
            self.collapse_sidebar()
        else:
            self.show_sidebar_view(self.SIDEBAR_TRACKS)

    def toggle_details_panel(self):
        if not self.sidebar.isHidden() and self.sidebar_stack.currentIndex() == self.SIDEBAR_DETAILS:
            self.collapse_sidebar()
        else:
            self.show_sidebar_view(self.SIDEBAR_DETAILS)

    # Backwards-compatible aliases
    def toggle_sidebar(self):
        self.toggle_tracks_panel()

    def toggle_inspector(self):
        self.toggle_details_panel()

    def _switch_inspector_tab(self, idx: int):
        self.inspector_stack.setCurrentIndex(idx)
        _set_dynamic_prop(self.btn_tab_info, "active", idx == 0)
        _set_dynamic_prop(self.btn_tab_log, "active", idx == 1)
        if idx == 1 and self._log_dirty:
            self._flush_logs_to_console()

    def _flush_logs_to_console(self):
        self.console_output.setPlainText("\n".join(self._log_buffer))
        bar = self.console_output.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._log_dirty = False

    def toggle_fullscreen(self):
        if self._in_fullscreen:
            self._in_fullscreen = False
            _set_dynamic_prop(self.root_container, "fullscreen", False)
            self.title_bar.show()
            if self._sidebar_open_before_fs:
                self.sidebar.show()
            self._sync_sidebar_buttons()
            if self._was_maximized_before_fs:
                self.showMaximized()
            else:
                self.showNormal()
            self.fullscreen_button.setIcon(get_icon("fullscreen", 15, RETRO_PIXEL["ink"]))
        else:
            self._was_maximized_before_fs = self.isMaximized()
            self._sidebar_open_before_fs = not self.sidebar.isHidden()
            self._in_fullscreen = True
            self.sidebar.hide()
            self._sync_sidebar_buttons()
            self.title_bar.hide()
            _set_dynamic_prop(self.root_container, "fullscreen", True)
            self.showFullScreen()
            self.fullscreen_button.setIcon(get_icon("fullscreen_exit", 15, RETRO_PIXEL["ink"]))

    def seek_relative(self, delta_ms: int):
        duration = self.video_player.duration()
        if duration <= 0:
            return
        target = max(0, min(duration, self.video_player.position() + delta_ms))
        self.progress_slider.setValue(target)
        self.update_time_label(target)
        self.on_slider_seek_requested(target)

    def _step_volume(self, delta: int):
        val = max(0, min(100, self.volume_slider.value() + delta))
        self.volume_slider.setValue(val)
        self.on_volume_changed(val)

    # ── Audio Device Management ────────────────────────────────────────────

    def setup_default_audio_device(self):
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.update_default_audio_device)
        self.update_default_audio_device()

    def update_default_audio_device(self):
        default_dev = QMediaDevices.defaultAudioOutput()
        if default_dev:
            self.audio_output.setDevice(default_dev)
            self.audio_output_next.setDevice(default_dev)
            self.video_audio_output.setDevice(default_dev)

    # ── Gapless Chunk Handoff ──────────────────────────────────────────────

    def handoff_to_full_track(self):
        if not self.audio_player_next_ready:
            return
        self.is_playing_chunk0 = False
        self.audio_player_next_ready = False
        self.audio_player_next_loading = False
        self.audio_player_next_seeked = False
        self.is_buffering_chunk1 = False

        if self.is_user_playing:
            self.audio_player_next.play()

        old_player = self.audio_player
        QTimer.singleShot(35, old_player.stop)

        self.audio_player, self.audio_player_next = self.audio_player_next, self.audio_player
        self.audio_output, self.audio_output_next = self.audio_output_next, self.audio_output
        self.append_log("音訊串流無縫接續完成，零中斷持續播放。", "SUCCESS")

    # ── File Dialog & Deferred Logging ─────────────────────────────────────

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Stego/Raw Video File", "", "Video Files (*.mp4 *.webm *.avi *.mkv)"
        )
        if file_path:
            self.load_new_video_file(file_path)

    def append_log(self, text, level="INFO"):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{now}] [{level}] {text}"
        self._log_buffer.append(line)
        if (
            not self.sidebar.isHidden()
            and self.sidebar_stack.currentIndex() == self.SIDEBAR_DETAILS
            and self.inspector_stack.currentIndex() == 1
        ):
            self.console_output.appendPlainText(line)
        else:
            self._log_dirty = True

    # ── Video Loading & Background Extraction ──────────────────────────────

    def load_new_video_file(self, video_file):
        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.terminate()
            self.extract_thread.wait()

        self.video_player.stop()
        self.audio_player.stop()
        self.audio_player_next.stop()
        self.video_player.setSource(QUrl())
        self.audio_player.setSource(QUrl())
        self.audio_player_next.setSource(QUrl())

        self.cleanup_temp_dir()

        self.audio_tracks = {}
        self.lang_list.clear()
        self.lbl_track_count.setText("AUDIO TRACKS · 0")
        self.current_lang = None
        self.pending_language = None
        self.audio_pending_seek = None
        self.is_playing_chunk0 = False
        self.audio_player_next_ready = False
        self.audio_player_next_loading = False
        self.audio_player_next_seeked = False
        self.handoff_pending_resume = False
        self.is_buffering_chunk1 = False
        self.initial_chunk_sec = 3.0
        self.is_user_playing = False
        self._last_progress_ui_time = 0.0
        self._last_progress_pct = -1
        self._update_play_button_icon()
        self.video_audio_output.setVolume(self.current_volume)

        # Enter Player Page immediately with docked retro decoding strip
        self.stacked_widget.setCurrentIndex(self.PAGE_PLAYER)
        self.video_path = video_file
        filename = os.path.basename(video_file)
        self.lbl_header_filename.setText(f"PLAYER - {filename.upper()}")
        self.lbl_header_filename.setToolTip(video_file)
        self.setWindowTitle(f"PLAYER - {filename.upper()}")

        self.load_video()
        self.video_player.pause()

        self.lbl_buffer_title.setText("首塊音訊解碼中")
        self.lbl_buffer_status.setText("正在啟動解密管線...")
        self.buffer_progress_bar.setValue(0)
        self.buffer_strip.show()
        self._set_status_badge("解碼中", "decoding")

        # Reset inspector info & deferred logs
        self._log_buffer.clear()
        self._log_dirty = True
        if (
            not self.sidebar.isHidden()
            and self.sidebar_stack.currentIndex() == self.SIDEBAR_DETAILS
            and self.inspector_stack.currentIndex() == 1
        ):
            self.console_output.clear()

        self.lbl_info_decode.setText("0 / -- 幀")
        self.lbl_sec_ip.setText("載入中...")
        self.lbl_sec_proxy.setText("載入中...")
        self.lbl_sec_geo.setText("載入中...")
        self.lbl_sec_decision.setText("載入中...")
        self.lbl_sec_trust.setText("載入中...")
        self.lbl_stego_checksum.setText("計算中...")

        self.extraction_start_time = time.time()
        self.last_reported_frame = 0
        self.metadata_parsed = False

        self.append_log("初始化 DE 多軌藏密播放系統...", "INFO")
        self.append_log(f"載入載體影片檔: {filename}", "INFO")
        self.append_log("啟動 FFmpeg YUV420p 原生像素讀取管線...", "PROCESS")

        self.temp_dir = pyinstaller_utils.get_temp_dir("temp_extracted_tracks")
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)

        self.extract_thread = ExtractionThread(video_file, self.temp_dir)
        self.extract_thread.progress_signal.connect(self.on_extraction_progress)
        self.extract_thread.manifest_signal.connect(self.on_manifest_received)
        self.extract_thread.chunk_signal.connect(self.on_chunk_received)
        self.extract_thread.finished_signal.connect(lambda tracks: self.on_extraction_finished(video_file, tracks))
        self.extract_thread.error_signal.connect(lambda err: self.on_extraction_error(video_file, err))
        self.extract_thread.start(QThread.Priority.LowPriority)

    def on_manifest_received(self, manifest_info):
        tracks_meta = manifest_info.get("tracks", [])
        self.audio_tracks_manifest = tracks_meta
        self.initial_chunk_sec = float(manifest_info.get("initial_sec", 3.0))
        self.append_log(
            f"[串流解碼] 第 0 幀已解析語系清冊 (Manifest)，共 {len(tracks_meta)} 國語系 (首塊切片: {self.initial_chunk_sec:.1f}s)",
            "SUCCESS",
        )

        self.lang_list.clear()
        for t in tracks_meta:
            lang_code = t["id"]
            if lang_code not in self.audio_tracks:
                self.audio_tracks[lang_code] = None
            display_name = LANGUAGE_MAP.get(lang_code, lang_code)
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, lang_code)
            item.setData(ROLE_DISPLAY_NAME, display_name)
            self.lang_list.addItem(item)

        self.lbl_track_count.setText(f"AUDIO TRACKS · {self.lang_list.count()}")

        from i18n_detector import detect_best_locale
        from pyinstaller_utils import get_resource_path
        db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
        if not os.path.exists(db_path):
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))

        pre_res = detect_best_locale(
            [t["id"] for t in tracks_meta],
            db_path=db_path,
            ip_lock_mode=self.ip_lock_enabled,
        )
        self.ip_matched_track = pre_res.track_key
        self.detected_ip = pre_res.metadata.get("ip", "127.0.0.1")
        self.detected_country = pre_res.metadata.get("country", "TW")
        self.ip_allowed_tracks = pre_res.metadata.get("allowed_tracks", [pre_res.track_key])

        self.refresh_track_list_badges()
        self.start_i18n_detection()

        for i in range(self.lang_list.count()):
            it = self.lang_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == self.ip_matched_track:
                self.lang_list.setCurrentItem(it)
                break

    def on_chunk_received(self, chunk_idx, tracks_dict, is_last):
        for lang, path in tracks_dict.items():
            self.audio_tracks[lang] = path

        if chunk_idx == 0:
            self.append_log(
                f"[串流解碼] 首塊音訊 (Chunk 0, 前 {self.initial_chunk_sec:.1f} 秒) 就緒，立即同步開播。",
                "SUCCESS",
            )
            self.buffer_strip.hide()

            chosen_track = (
                self.pending_language
                if (self.pending_language and self.pending_language in self.audio_tracks and self.audio_tracks[self.pending_language])
                else self.ip_matched_track
            )
            if not chosen_track or chosen_track not in self.audio_tracks or not self.audio_tracks[chosen_track]:
                chosen_track = next((k for k, v in self.audio_tracks.items() if v), None)

            self.pending_language = None
            self.is_user_playing = True
            self._update_play_button_icon()
            if chosen_track:
                self.select_audio_track(chosen_track)

            self.video_player.play()
            self.audio_player.play()
            self._set_status_badge("背景解碼中", "decoding")

        elif chunk_idx == 1 or is_last:
            self.append_log("完整音訊串流解碼完畢，多語音軌接續完成。", "SUCCESS")
            for lang, path in tracks_dict.items():
                self.audio_tracks[lang] = path

            if self.current_lang and self.current_lang in tracks_dict:
                full_file = tracks_dict[self.current_lang]
                full_url = QUrl.fromLocalFile(os.path.abspath(full_file))
                if self.is_playing_chunk0:
                    v_pos = self.video_player.position()
                    boundary_ms = int(self.initial_chunk_sec * 1000)
                    if (
                        self.is_buffering_chunk1
                        or self.audio_player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
                        or v_pos >= boundary_ms - 100
                        or self.video_player.playbackState() == QMediaPlayer.PlaybackState.PausedState
                    ):
                        self.is_buffering_chunk1 = False
                        self.handoff_pending_resume = True
                        self.audio_player_next_ready = False
                        self.audio_player_next_loading = True
                        self.audio_player_next_seeked = False
                        self.audio_player_next.setSource(full_url)
                    else:
                        self.handoff_pending_resume = False
                        self.audio_player_next_ready = False
                        self.audio_player_next_loading = True
                        self.audio_player_next_seeked = False
                        self.audio_player_next.setSource(full_url)
                else:
                    pos = self.video_player.position()
                    self.audio_pending_seek = pos
                    self.audio_player.setSource(full_url)

    def on_extraction_progress(self, current_frame, total_frames, bit_idx, target_bits):
        now = time.monotonic()
        val = int((current_frame / total_frames) * 100) if total_frames > 0 else 0

        if not self.metadata_parsed and target_bits > 0:
            self.metadata_parsed = True
            target_bytes = target_bits // 8
            target_mb = target_bytes / 1024 / 1024
            self.append_log("解析成功，已讀取 PEE 隱寫中繼資料標頭 (Metadata Header)", "SUCCESS")
            self.append_log(f"壓縮載荷大小: {target_bytes:,} Bytes ({target_mb:.2f} MB) | {target_bits:,} bits", "METADATA")

        if current_frame - self.last_reported_frame >= 30:
            self.last_reported_frame = current_frame
            elapsed = max(1e-6, time.time() - self.extraction_start_time)
            fps = int(current_frame / elapsed)
            percent_str = f" ({val}%)" if total_frames > 0 else ""
            self.append_log(f"已掃描 {current_frame}/{total_frames} 幀{percent_str} | {bit_idx:,} bits | {fps} FPS", "INFO")

        # Throttle GUI updates to <= 10 Hz unless percentage changes or finished
        if (
            val == self._last_progress_pct
            and (now - self._last_progress_ui_time) < 0.10
            and current_frame < total_frames
        ):
            return

        self._last_progress_ui_time = now
        self._last_progress_pct = val

        if total_frames > 0:
            if self.buffer_strip.isVisible():
                self.buffer_progress_bar.setValue(val)
                self.lbl_buffer_status.setText(f"{current_frame} / {total_frames} 幀 ({val}%)")

            self._set_status_badge(f"解碼中 {val}%", "decoding")

            if not self.sidebar.isHidden() and self.sidebar_stack.currentIndex() == self.SIDEBAR_DETAILS:
                elapsed = max(1e-6, time.time() - self.extraction_start_time)
                fps = int(current_frame / elapsed)
                extracted_mb = bit_idx / 8 / 1024 / 1024
                self.lbl_info_decode.setText(f"{current_frame}/{total_frames} 幀 ({val}%) · {extracted_mb:.2f} MB · {fps} FPS")

    def on_extraction_finished(self, video_file, audio_tracks):
        for lang_code, file_path in audio_tracks.items():
            self.audio_tracks[lang_code] = file_path
        self.video_path = video_file

        if self.lang_list.count() == 0:
            self.repopulate_sidebar_items()
        else:
            self.refresh_track_list_badges()

        self.append_log(f"解碼完成：全片 {len(audio_tracks)} 組多語音軌皆已解密就緒。", "SUCCESS")

        self.buffer_progress_bar.setValue(100)
        self.buffer_strip.hide()
        self._set_status_badge("解碼完成", "ready")
        self.lbl_info_decode.setText(f"完成 · {len(audio_tracks)} 組音軌就緒")

        file_md5 = self.extract_thread.file_md5 if (self.extract_thread and hasattr(self.extract_thread, "file_md5")) else "Unknown"
        self.lbl_stego_checksum.setText(f"{file_md5[:12]}..." if len(file_md5) > 12 else file_md5)
        self.lbl_stego_checksum.setToolTip(f"完整檔案 MD5:\n{file_md5}")

        if not self.is_user_playing:
            from i18n_detector import detect_best_locale
            from pyinstaller_utils import get_resource_path
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
            if not os.path.exists(db_path):
                db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))

            pre_res = detect_best_locale(
                list(self.audio_tracks.keys()),
                db_path=db_path,
                ip_lock_mode=self.ip_lock_enabled,
            )
            best_track = pre_res.track_key
            self.ip_matched_track = best_track
            self.detected_ip = pre_res.metadata.get("ip", "127.0.0.1")
            self.detected_country = pre_res.metadata.get("country", "TW")
            self.ip_allowed_tracks = pre_res.metadata.get("allowed_tracks", [best_track])

            chosen_track = (
                self.pending_language
                if (self.pending_language and self.pending_language in self.audio_tracks and self.audio_tracks[self.pending_language])
                else best_track
            )
            self.pending_language = None
            self.is_user_playing = True
            self._update_play_button_icon()
            self.select_audio_track(chosen_track)
            self.refresh_track_list_badges()
            self.start_i18n_detection()

            self.video_player.play()
            self.audio_player.play()

    # ── GeoIP & Zero-Trust Controls ────────────────────────────────────────

    def prewarm_geoip_context(self):
        def _worker():
            try:
                from i18n_detector import get_client_geo_context
                from pyinstaller_utils import get_resource_path
                db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
                if not os.path.exists(db_path):
                    db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))
                ctx = get_client_geo_context(db_path)
                self.detected_ip = ctx.get("ip", "127.0.0.1")
                self.detected_country = ctx.get("country", "TW")
            except Exception:
                pass
        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def toggle_ip_lock(self):
        self.ip_lock_enabled = not self.ip_lock_enabled
        settings = QSettings("GradProject", "StegoPlayer")
        settings.setValue("ip_lock_enabled", self.ip_lock_enabled)

        self.update_ip_lock_button_ui()
        self.refresh_track_list_badges()

        if self.ip_lock_enabled:
            self.append_log("已啟用「自動 IP 鎖定模式」：強制鎖定當前 IP 地理區域許可之音軌。", "SUCCESS")
            from i18n_detector import is_track_allowed_by_ip
            if self.ip_matched_track and (
                not self.current_lang
                or not is_track_allowed_by_ip(self.current_lang, self.detected_country, list(self.audio_tracks.keys()))
            ):
                self.select_audio_track(self.ip_matched_track)
        else:
            self.append_log("已停用「自動 IP 鎖定模式」：切換為自由選軌模式。", "INFO")

    def update_ip_lock_button_ui(self):
        self.ip_lock_switch.setChecked(self.ip_lock_enabled)
        icon_name = "lock" if self.ip_lock_enabled else "unlock"
        self.lbl_ip_lock_icon.setPixmap(get_icon(icon_name, 15, RETRO_PIXEL["ink"]).pixmap(15, 15))
        self.ip_lock_switch.setToolTip(
            "已啟用 IP 區域鎖定（僅允許授權音軌）" if self.ip_lock_enabled else "已停用 IP 鎖定（自由切換音軌）"
        )

    def refresh_track_list_badges(self):
        from i18n_detector import is_track_allowed_by_ip
        all_keys = list(self.audio_tracks.keys())
        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            lang_code = item.data(Qt.ItemDataRole.UserRole)
            display_name = LANGUAGE_MAP.get(lang_code, lang_code)
            item.setData(ROLE_DISPLAY_NAME, display_name)

            if self.ip_lock_enabled:
                if lang_code == self.ip_matched_track:
                    item.setData(ROLE_BADGE_TEXT, "IP 配對")
                    item.setData(ROLE_TRACK_STATE, "matched")
                    item.setToolTip("當前 IP 最適配音軌 (自動鎖定中)")
                elif is_track_allowed_by_ip(lang_code, self.detected_country, all_keys):
                    item.setData(ROLE_BADGE_TEXT, "地區許可")
                    item.setData(ROLE_TRACK_STATE, "allowed")
                    item.setToolTip("本地區許可收聽之音軌")
                else:
                    item.setData(ROLE_BADGE_TEXT, "區域鎖定")
                    item.setData(ROLE_TRACK_STATE, "locked")
                    item.setToolTip("受 IP 地理區域限制保護 (僅限授權地區播放)")
            else:
                if lang_code == self.ip_matched_track:
                    item.setData(ROLE_BADGE_TEXT, "IP 推薦")
                    item.setData(ROLE_TRACK_STATE, "matched")
                    item.setToolTip("依據 IP 地理位置推薦之音軌")
                else:
                    item.setData(ROLE_BADGE_TEXT, "")
                    item.setData(ROLE_TRACK_STATE, "free")
                    item.setToolTip("點選即可無縫切換")

        self.lbl_track_count.setText(f"AUDIO TRACKS · {self.lang_list.count()}")
        self.lang_list.viewport().update()

    def start_i18n_detection(self):
        self.user_manually_selected = False
        available_tracks = list(self.audio_tracks.keys())
        system_langs = QLocale.system().uiLanguages()

        settings = QSettings("GradProject", "StegoPlayer")
        history_lang = settings.value("preferred_language", None)

        from pyinstaller_utils import get_resource_path
        db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
        if not os.path.exists(db_path):
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))

        session_id = self.video_path

        if self.current_i18n_thread and self.current_i18n_thread.isRunning():
            self.current_i18n_thread.terminate()
            self.current_i18n_thread.wait()

        self.current_i18n_thread = I18nDetectionWorker(
            session_id, available_tracks, system_langs, history_lang, db_path, ip_lock_mode=self.ip_lock_enabled
        )
        self.current_i18n_thread.finished_signal.connect(self.on_i18n_detection_completed)
        self.current_i18n_thread.start()

    def on_i18n_detection_completed(self, session_id, result):
        if session_id != self.video_path:
            return

        meta = result.metadata if result.metadata else {}
        client_ip = meta.get("ip", self.detected_ip)
        country = meta.get("country", self.detected_country)
        self.detected_ip = client_ip
        self.detected_country = country
        self.ip_matched_track = result.track_key
        self.ip_allowed_tracks = meta.get("allowed_tracks", [result.track_key])
        self.cached_i18n_result = result

        proxy_detected = meta.get("proxy_detected", False)
        proxy_details = meta.get("details", "Direct Connection")
        proxy_status_str = f"啟用 ({proxy_details})" if proxy_detected else "未啟用 (直連)"

        trust_map = {
            "P0 IP_LOCK_ENFORCED": "頂級置信 (IP 區域鎖定)",
            "P1 EXPLICIT_HISTORY": "高置信度 (使用者偏好)",
            "P2a OS_UI_LANGS_EXACT": "高置信度 (系統原生)",
            "P4a TIMEZONE_CROSS": "高置信度 (時區比對)",
            "P2b OS_UI_LANGS_FUZZY": "中置信度 (系統模糊)",
            "P4c GEOIP_VERIFIED": "中置信度 (地理驗證)",
            "P4b LOCAL_DB_ONLY": "中置信度 (離線地理)",
            "P5 SYSTEM_DEFAULT": "低置信度 (保底選軌)",
            "THREAD_ERROR": "執行緒異常",
        }
        trust_level = trust_map.get(result.source, "中置信度")

        self.lbl_sec_ip.setText(client_ip)
        self.lbl_sec_proxy.setText(proxy_status_str)
        self.lbl_sec_geo.setText(country)
        self.lbl_sec_decision.setText(result.source)
        self.lbl_sec_trust.setText(trust_level)

        file_md5 = self.extract_thread.file_md5 if (self.extract_thread and hasattr(self.extract_thread, "file_md5")) else "Unknown"
        self.lbl_stego_checksum.setText(f"{file_md5[:12]}..." if len(file_md5) > 12 else file_md5)
        self.lbl_stego_checksum.setToolTip(f"完整檔案 MD5:\n{file_md5}")

        self.refresh_track_list_badges()

        if self.user_manually_selected and not self.ip_lock_enabled:
            self.append_log("使用者已手動指定音軌，忽略背景自動偵測結果。", "INFO")
            return

        self.append_log(f"I18N 決策完成：{result.detail} | 決策源: {result.source} (置信度: {result.confidence:.2f})", "METADATA")
        self.select_audio_track(result.track_key)

    def on_extraction_error(self, video_file, err_msg):
        self.append_log(f"影像解密提示/異常: {err_msg}", "WARNING")
        self.append_log("無法從影像像素中讀取有效 PEE 藏密標頭，進入降級處理...", "WARNING")
        self.append_log("搜尋同目錄外部音軌檔案...", "PROCESS")

        video_dir = os.path.dirname(os.path.abspath(video_file))
        audio_tracks = {}
        for filename in os.listdir(video_dir):
            if "_audio_" in filename and (filename.endswith(".mp3") or filename.endswith(".m4a") or filename.endswith(".webm")):
                match = re.search(r"_audio_(.+)\.(mp3|m4a|webm)$", filename)
                if match:
                    lang = match.group(1)
                    audio_tracks[lang] = os.path.join(video_dir, filename)
                    lang_display = LANGUAGE_MAP.get(lang, lang)
                    self.append_log(f"偵測到外部音軌: {filename} -> {lang_display}", "METADATA")

        self.cleanup_temp_dir()

        if not audio_tracks:
            self.append_log("影片未含隱寫音軌或外部語音檔，切換為原生載體音訊播放模式。", "INFO")
            self.buffer_strip.hide()
            self._set_status_badge("原生音訊", "ready")
            self.lbl_info_decode.setText("原生載體音訊模式")
            self.lbl_track_count.setText("AUDIO TRACKS · 0")
            self.video_audio_output.setVolume(self.current_volume)
            self.stacked_widget.setCurrentIndex(self.PAGE_PLAYER)
            self.load_video()
            self.is_user_playing = True
            self._update_play_button_icon()
            self.video_player.play()
            return

        self.audio_tracks = audio_tracks
        self.video_path = video_file

        self.append_log(f"已載入本地 {len(audio_tracks)} 組外部配音，準備啟動播放...", "SUCCESS")
        self.repopulate_sidebar_items()

        def transition_fallback():
            self.buffer_strip.hide()
            self._set_status_badge("外部音軌", "warning")
            self.lbl_info_decode.setText(f"降級模式 · {len(audio_tracks)} 組外部音軌")
            self.stacked_widget.setCurrentIndex(self.PAGE_PLAYER)
            self.load_video()

            from i18n_detector import detect_best_locale
            from pyinstaller_utils import get_resource_path
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
            if not os.path.exists(db_path):
                db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))

            pre_res = detect_best_locale(
                list(self.audio_tracks.keys()),
                db_path=db_path,
                ip_lock_mode=self.ip_lock_enabled,
            )
            best_track = pre_res.track_key
            self.ip_matched_track = best_track
            self.detected_ip = pre_res.metadata.get("ip", "127.0.0.1")
            self.detected_country = pre_res.metadata.get("country", "TW")
            self.ip_allowed_tracks = pre_res.metadata.get("allowed_tracks", [best_track])

            self.is_user_playing = True
            self._update_play_button_icon()
            self.select_audio_track(best_track)
            self.refresh_track_list_badges()
            self.start_i18n_detection()
            self.video_player.play()
            self.audio_player.play()

        QTimer.singleShot(1200, transition_fallback)

    def repopulate_sidebar_items(self):
        self.lang_list.clear()
        for lang_code in self.audio_tracks:
            display_name = LANGUAGE_MAP.get(lang_code, lang_code)
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, lang_code)
            item.setData(ROLE_DISPLAY_NAME, display_name)
            self.lang_list.addItem(item)
            if lang_code == self.current_lang:
                self.lang_list.setCurrentItem(item)
        self.refresh_track_list_badges()

    # ── Media Control Logic ────────────────────────────────────────────────

    def load_video(self):
        url = QUrl.fromLocalFile(os.path.abspath(self.video_path))
        self.video_player.setSource(url)

    def select_audio_track(self, lang_code):
        if not self.audio_tracks or lang_code not in self.audio_tracks:
            return

        audio_file = self.audio_tracks[lang_code]
        if not audio_file or not os.path.exists(audio_file):
            return

        self.current_lang = lang_code
        current_pos = self.video_player.position()

        # Seamless hot-swap: Only reload audio source without pausing video
        self.audio_pending_seek = current_pos
        self.audio_player.pause()
        self.audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(audio_file)))

        # Stego audio track takes control: mute carrier audio, restore stego volume
        self.video_audio_output.setVolume(0.0)
        self.audio_output.setVolume(self.current_volume)
        self.audio_output_next.setVolume(self.current_volume)

        # Reset secondary player during track switch
        self.audio_player_next.stop()
        self.audio_player_next_ready = False
        self.audio_player_next_loading = False
        self.audio_player_next_seeked = False
        self.handoff_pending_resume = False

        self.is_playing_chunk0 = "_chunk0" in os.path.basename(audio_file)

        if self.is_user_playing:
            if self.audio_player.mediaStatus() in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            ):
                self.audio_player.setPosition(current_pos)
                self.audio_pending_seek = None
                self.audio_player.play()

        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == lang_code:
                self.lang_list.setCurrentItem(item)
                break
        self.lang_list.viewport().update()

    def toggle_play(self):
        if self.is_user_playing:
            self.is_user_playing = False
            self.video_player.pause()
            self.audio_player.pause()
            self.audio_player_next.pause()
            self._update_play_button_icon()
        else:
            self.is_user_playing = True
            self._update_play_button_icon()
            self.check_and_resume_playback()

    def toggle_mute(self):
        new_mute = not self.audio_output.isMuted()
        self.audio_output.setMuted(new_mute)
        self.audio_output_next.setMuted(new_mute)
        self.video_audio_output.setMuted(new_mute)
        self._update_volume_icon()

    def on_volume_changed(self, val):
        vol = val / 100.0
        self.current_volume = vol
        if val > 0 and self.audio_output.isMuted():
            self.audio_output.setMuted(False)
            self.audio_output_next.setMuted(False)
            self.video_audio_output.setMuted(False)

        self.audio_output.setVolume(vol)
        self.audio_output_next.setVolume(vol)
        if self.current_lang and (self.audio_player.source().isValid() or self.audio_player_next.source().isValid()):
            self.video_audio_output.setVolume(0.0)
        else:
            self.video_audio_output.setVolume(vol)

        self._update_volume_icon()

    def check_and_resume_playback(self):
        if not self.is_user_playing:
            return
        v_status = self.video_player.mediaStatus()
        a_status = self.audio_player.mediaStatus()
        buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)
        if v_status not in buffering_states:
            self.video_player.play()
        if a_status not in buffering_states:
            if self.current_lang and self.audio_tracks.get(self.current_lang):
                self.audio_player.play()
            else:
                self.video_audio_output.setVolume(self.current_volume)

    # ── Synchronization Logic ──────────────────────────────────────────────

    def sync_check(self):
        if not self.is_user_playing:
            return
        v_status = self.video_player.mediaStatus()
        a_status = self.audio_player.mediaStatus()
        buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)

        if v_status in buffering_states or a_status in buffering_states:
            return

        v_pos = self.video_player.position()
        a_pos = self.audio_player.position()
        boundary_ms = int(getattr(self, "initial_chunk_sec", 3.0) * 1000)

        if self.is_playing_chunk0 and self.audio_player_next_ready and (a_pos >= boundary_ms - 150 or v_pos >= boundary_ms - 50):
            self.handoff_to_full_track()
            return

        if self.is_playing_chunk0 and not self.audio_player_next_ready and (
            a_pos >= boundary_ms - 50 or a_status == QMediaPlayer.MediaStatus.EndOfMedia
        ):
            if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.is_buffering_chunk1 = True
                self.video_player.pause()
                self.lbl_buffer_title.setText("等待後續音訊切片解碼")
                self.buffer_strip.show()
                self.append_log("正在等待音訊串流後續切片解碼完成 (平滑緩衝中)...", "PROCESS")
            return

        diff = abs(v_pos - a_pos)
        current_time = time.time()
        if diff > 450 and (current_time - self.last_sync_seek) > 3.0:
            if not (self.is_playing_chunk0 and not self.audio_player_next_ready):
                self.audio_player.setPosition(v_pos)
                self.last_sync_seek = current_time

    # ── Slider Interactions (Zero-Spam Seek) ───────────────────────────────

    def on_slider_pressed(self):
        self.slider_is_dragging = True

    def on_slider_preview_changed(self, pos):
        self.update_time_label(pos)

    def on_slider_seek_requested(self, pos):
        self.slider_is_dragging = False
        self.video_player.setPosition(pos)

        boundary_ms = int(getattr(self, "initial_chunk_sec", 3.0) * 1000)
        if self.is_playing_chunk0 and self.audio_player_next_ready and pos >= boundary_ms - 100:
            self.handoff_to_full_track()

        self.audio_player.setPosition(pos)
        self.update_time_label(pos)
        if self.is_user_playing:
            self.check_and_resume_playback()

    # ── Media Player Signal Callbacks ──────────────────────────────────────

    def on_video_position_changed(self, pos):
        if not self.slider_is_dragging:
            self.progress_slider.setValue(pos)
            self.update_time_label(pos)

    def on_duration_changed(self, duration):
        self.progress_slider.setRange(0, duration)
        self.update_time_label(self.video_player.position())

    def update_time_label(self, pos):
        duration = self.video_player.duration()
        self.time_label.setText(f"{self.format_time(pos)} / {self.format_time(duration)}")

    def format_time(self, ms):
        s = max(0, ms) // 1000
        h = s // 3600
        m = (s % 3600) // 60
        s = s % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def on_media_status_changed(self, status):
        sender = self.sender()
        if sender == self.audio_player_next:
            if getattr(self, "audio_player_next_loading", False) and status in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            ):
                boundary_ms = int(getattr(self, "initial_chunk_sec", 3.0) * 1000)
                target_pos = max(boundary_ms, self.video_player.position())
                if not getattr(self, "audio_player_next_seeked", False):
                    self.audio_player_next.setPosition(target_pos)
                    self.audio_player_next_seeked = True
                self.audio_player_next_ready = True
                self.audio_player_next_loading = False
                if getattr(self, "handoff_pending_resume", False):
                    self.handoff_pending_resume = False
                    self.buffer_strip.hide()
                    self.handoff_to_full_track()
                    if self.is_user_playing:
                        self.video_player.play()
            return

        v_status = self.video_player.mediaStatus()
        a_status = self.audio_player.mediaStatus()

        if v_status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.is_user_playing = False
            self.video_player.pause()
            self.audio_player.pause()
            self.audio_player_next.pause()
            self._update_play_button_icon()
            return

        if a_status == QMediaPlayer.MediaStatus.EndOfMedia and v_status != QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_playing_chunk0:
                if self.audio_player_next_ready:
                    self.handoff_to_full_track()
                    return
                if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self.is_buffering_chunk1 = True
                    self.video_player.pause()
                    self.lbl_buffer_title.setText("等待後續音訊切片解碼")
                    self.buffer_strip.show()
                    self.append_log("正在等待音訊串流後續切片解碼完成 (平滑緩衝中)...", "PROCESS")
                return
            if self.current_lang and self.current_lang in self.audio_tracks:
                track_path = self.audio_tracks[self.current_lang]
                if track_path and os.path.exists(track_path):
                    current_src = self.audio_player.source().toLocalFile()
                    if not is_same_path(current_src, track_path):
                        self.audio_pending_seek = self.video_player.position()
                        self.audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(track_path)))
                        return

        if self.audio_pending_seek is not None and a_status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            target_pos = self.audio_pending_seek
            self.audio_pending_seek = None
            self.audio_player.setPosition(target_pos)
            if self.is_user_playing:
                self.audio_player.play()

        buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)
        if v_status in buffering_states:
            self.video_player.pause()
            self.audio_player.pause()
        elif a_status in buffering_states:
            pass
        else:
            if self.is_user_playing and not self.is_buffering_chunk1:
                self.check_and_resume_playback()

    # ── Track Selection Interaction ────────────────────────────────────────

    def on_lang_item_clicked(self, item):
        lang_code = item.data(Qt.ItemDataRole.UserRole)
        display_name = LANGUAGE_MAP.get(lang_code, lang_code)

        # 0. Pre-select during initial decode before playback starts
        if self.extract_thread and self.extract_thread.isRunning() and not self.is_user_playing:
            self.pending_language = lang_code
            self.append_log(f"已記錄預選語系: [{display_name}]，解碼完成將自動以該語言起播。", "INFO")
            for i in range(self.lang_list.count()):
                it = self.lang_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == lang_code:
                    self.lang_list.setCurrentItem(it)
                    break
            return

        # 1. Zero-Trust IP Lock security guard
        if self.ip_lock_enabled:
            from i18n_detector import is_track_allowed_by_ip
            if not is_track_allowed_by_ip(lang_code, self.detected_country, list(self.audio_tracks.keys())):
                self.append_log(
                    f"[SECURITY] 阻擋非授權切換：音軌 [{lang_code}] 受 IP 區域版權鎖定保護 (當前地區: {self.detected_country})",
                    "WARNING",
                )
                QMessageBox.warning(
                    self,
                    "IP 區域版權鎖定保護",
                    f"目前系統已啟用「IP 鎖定」模式。\n"
                    f"您的 IP 判定為：{self.detected_country} ({self.detected_ip})\n\n"
                    f"音軌 [{display_name}] 受到地理區域版權鎖定，不允許在當前地區播放。\n\n"
                    f"如需自由試聽所有多語音軌，請先關閉右側欄上方的「IP 鎖定」開關。",
                )
                for i in range(self.lang_list.count()):
                    it = self.lang_list.item(i)
                    if it.data(Qt.ItemDataRole.UserRole) == self.current_lang:
                        self.lang_list.setCurrentItem(it)
                        break
                return

        # 2. Instant seamless hot-swap switching
        if lang_code != self.current_lang:
            track_ready = (
                lang_code in self.audio_tracks
                and self.audio_tracks[lang_code] is not None
                and os.path.exists(self.audio_tracks[lang_code])
            )
            if not track_ready:
                self.pending_language = lang_code
                self.append_log(f"音軌 [{display_name}] 正在解碼中，完成時將自動切換。", "INFO")
                return

            self.user_manually_selected = True
            self.select_audio_track(lang_code)
            self.append_log(f"即時熱切換音軌至: [{display_name}]", "INFO")
            if not self.ip_lock_enabled:
                try:
                    settings = QSettings("GradProject", "StegoPlayer")
                    settings.setValue("preferred_language", lang_code)
                except Exception:
                    pass

    # ── Temp Cleanup & Dev Dashboard ───────────────────────────────────────

    def cleanup_temp_dir(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            cleaned = False
            for _ in range(5):
                try:
                    shutil.rmtree(self.temp_dir)
                    cleaned = True
                    break
                except Exception:
                    time.sleep(0.05)
            if not cleaned:
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except Exception:
                    pass
        self.temp_dir = None

    def launch_web_dashboard(self):
        import subprocess
        import webbrowser
        import urllib.request
        self.append_log("正在啟動 Smart i18n 零信任安全模擬控制台...", "PROCESS")

        server_already_running = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/my-context", timeout=0.5) as resp:
                if resp.status == 200:
                    server_already_running = True
        except Exception:
            server_already_running = False

        if server_already_running:
            self.append_log("偵測到安全性分析伺服器已在運行中，直接開啟瀏覽器頁面...", "SUCCESS")
            webbrowser.open("http://127.0.0.1:8000")
            return

        from pyinstaller_utils import get_resource_path
        main_py = get_resource_path(os.path.join("for_ip", "main.py"))
        bat_path = get_resource_path(os.path.join("for_ip", "run_dashboard.bat"))

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        venv_python = os.path.join(project_root, ".venv", "Scripts", "python.exe")

        python_exe = sys.executable
        if os.path.exists(venv_python):
            python_exe = venv_python

        started = False
        if os.path.exists(main_py):
            try:
                creation_flags = 0
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0
                    creation_flags = subprocess.CREATE_NO_WINDOW

                subprocess.Popen(
                    [python_exe, main_py],
                    cwd=os.path.dirname(main_py),
                    creationflags=creation_flags,
                    startupinfo=startupinfo,
                )
                self.append_log("安全性分析伺服器已於背景啟動 (FastAPI on Port 8000)。", "SUCCESS")
                started = True
            except Exception as e:
                self.append_log(f"無法直接啟動伺服器: {e}，嘗試呼叫批次檔...", "WARNING")

        if not started and os.path.exists(bat_path):
            try:
                subprocess.Popen([bat_path], cwd=os.path.dirname(bat_path))
                started = True
            except Exception as e:
                self.append_log(f"無法啟動批次檔: {e}", "WARNING")

        QTimer.singleShot(1500, lambda: webbrowser.open("http://127.0.0.1:8000"))

    def closeEvent(self, event):
        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.terminate()
            self.extract_thread.wait()

        if self.current_i18n_thread and self.current_i18n_thread.isRunning():
            self.current_i18n_thread.terminate()
            self.current_i18n_thread.wait()

        self.video_player.stop()
        self.audio_player.stop()
        self.audio_player_next.stop()
        self.video_player.setSource(QUrl())
        self.audio_player.setSource(QUrl())
        self.audio_player_next.setSource(QUrl())
        self.sync_timer.stop()

        self.cleanup_temp_dir()
        event.accept()


def main():
    app = QApplication(sys.argv)
    pixel_font = load_pixel_font()
    load_display_font()
    app.setFont(QFont(pixel_font, 11, QFont.Weight.Bold))

    initial_file = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and os.path.exists(arg):
            initial_file = arg
            break

    player = MultiTrackPlayer(initial_file)
    player.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
