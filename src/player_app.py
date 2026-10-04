import os
import sys
import re
import shutil
import time
import datetime
import pyinstaller_utils
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QListWidget, QListWidgetItem,
    QFrame, QSplitter, QMessageBox, QFileDialog, QStackedWidget,
    QProgressBar, QTextEdit, QAbstractItemView, QComboBox
)
from PySide6.QtCore import Qt, QUrl, QTimer, QThread, Signal, QLocale, QSettings
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QFont

# Import unified Stego Facade module supporting both Coltuc PEE and Zhang-Zeng-Ou 2D HS
from stego_facade import decode_video_multi

# Mapping of language codes to display names with flag emojis
LANGUAGE_MAP = {
    'ar': '🇸🇦 العربية (Arabic)',
    'bn': '🇧🇩 বাংলা (Bengali)',
    'de-DE': '🇩🇪 Deutsch (German)',
    'en': '🇬🇧 English (UK)',
    'en-US': '🇺🇸 English (United States)',
    'es-US': '🇪🇸 Español (Spanish - US)',
    'fr-FR': '🇫🇷 Français (French)',
    'hi': '🇮🇳 हिन्दी (Hindi)',
    'id': '🇮🇩 Bahasa Indonesia (Indonesian)',
    'it': '🇮🇹 Italiano (Italian)',
    'iw': '🇮🇱 עברית (Hebrew)',
    'ja': '🇯🇵 日本語 (Japanese)',
    'ko': '🇰🇷 한국어 (Korean)',
    'ml': '🇮🇳 Malayalam (Malayalam)',
    'nl-NL': '🇳🇱 Nederlands (Dutch)',
    'pl': '🇵🇱 Polski (Polish)',
    'pt-BR': '🇧🇷 Português (Portuguese - Brazil)',
    'ru': '🇷🇺 Русский (Russian)',
    'ta': '🇮🇳 தமிழ் (Tamil)',
    'te': '🇮🇳 తెలుగు (Telugu)',
    'uk': '🇺🇦 Українська (Ukrainian)',
    'zh-TW': '🇹🇼 繁體中文 (Traditional Chinese)',
    'zh-CN': '🇨🇳 简体中文 (Simplified Chinese)',
    'zh': '🌐 中文 (Chinese)',
}

def is_same_path(p1, p2):
    if not p1 or not p2:
        return False
    return os.path.normcase(os.path.normpath(str(p1))) == os.path.normcase(os.path.normpath(str(p2)))

class ExtractionThread(QThread):
    progress_signal = Signal(int, int, int, int) # current_frame, total_frames, bit_idx, target_bits
    manifest_signal = Signal(dict) # manifest info dictionary resolved in Frame 0
    chunk_signal = Signal(int, dict, bool) # chunk_idx, tracks_dict, is_last
    finished_signal = Signal(dict) # extracted tracks dictionary
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
                on_chunk_ready=chunk_cb
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
                ip_lock_mode=self.ip_lock_mode
            )
            self.finished_signal.emit(self.session_id, res)
        except Exception as e:
            from i18n_detector import DetectionResult
            fallback_res = DetectionResult(
                track_key=self.available_tracks[0] if self.available_tracks else "en-US",
                source="THREAD_ERROR",
                confidence=0.0,
                detail=f"Thread execution error: {str(e)}"
            )
            self.finished_signal.emit(self.session_id, fallback_res)

class MultiTrackPlayer(QMainWindow):
    def __init__(self, initial_video_path=None):
        super().__init__()
        self.setWindowTitle("DE Multi-Track Media Player")
        self.resize(1100, 700)
        
        # State variables
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
        
        # Dashboard Variables
        self.extraction_start_time = 0.0
        self.last_reported_frame = 0
        self.metadata_parsed = False
        self.audio_tracks_manifest = []
        self.audio_pending_seek = None
        self.current_volume = 0.8
        
        # Initialize Media Players
        self.video_player = QMediaPlayer()
        self.video_audio_output = QAudioOutput()
        self.video_player.setAudioOutput(self.video_audio_output)
        self.video_audio_output.setVolume(self.current_volume) # Audible by default for native carrier audio
        
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
        
        # Build UI and Stack Layout
        self.init_ui()
        
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

    def init_ui(self):
        # Base central stacked widget
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("StackedWidget")
        self.setCentralWidget(self.stacked_widget)
        
        # PAGE 0: Landing Page (Empty Start State)
        self.page_landing = QFrame()
        self.page_landing.setObjectName("LandingPage")
        landing_layout = QVBoxLayout(self.page_landing)
        landing_layout.setAlignment(Qt.AlignCenter)
        landing_layout.setSpacing(25)
        
        lbl_welcome_title = QLabel("🎬 DE Multi-Track Stego Player")
        lbl_welcome_title.setObjectName("WelcomeTitle")
        lbl_welcome_title.setAlignment(Qt.AlignCenter)
        
        lbl_welcome_sub = QLabel("無損預測誤差擴張 (PEE) 數位藏密解碼播放系統")
        lbl_welcome_sub.setObjectName("WelcomeSub")
        lbl_welcome_sub.setAlignment(Qt.AlignCenter)
        
        btn_start_open = QPushButton("📂 點擊選擇藏密影片 (Select Stego Video)")
        btn_start_open.setObjectName("StartOpenButton")
        btn_start_open.clicked.connect(self.open_file_dialog)
        
        lbl_welcome_desc = QLabel("支援 H.265 Lossless 影像隱寫多聲道音軌，逆向完美復原與即時切換")
        lbl_welcome_desc.setObjectName("WelcomeDesc")
        lbl_welcome_desc.setAlignment(Qt.AlignCenter)
        
        landing_layout.addStretch()
        landing_layout.addWidget(lbl_welcome_title)
        landing_layout.addWidget(lbl_welcome_sub)
        landing_layout.addWidget(btn_start_open)
        landing_layout.addWidget(lbl_welcome_desc)
        landing_layout.addStretch()
        
        self.stacked_widget.addWidget(self.page_landing)
        
        # PAGE 1: Loading Page (Forensic Dashboard Console)
        self.page_loading = QFrame()
        self.page_loading.setObjectName("LoadingPage")
        loading_layout = QVBoxLayout(self.page_loading)
        loading_layout.setContentsMargins(30, 25, 30, 25)
        loading_layout.setSpacing(15)
        
        # Header Title
        lbl_loading_title = QLabel("🔓 PEE 數位藏密解碼儀表板 (Extraction Console)")
        lbl_loading_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #F8FAFC;")
        
        lbl_loading_sub = QLabel("系統正在執行逆向預測誤差擴張 (PEE) 提取演算法，進行像素還原與音軌解密")
        lbl_loading_sub.setStyleSheet("font-size: 13px; color: #818CF8; margin-top: -8px;")
        
        loading_layout.addWidget(lbl_loading_title)
        loading_layout.addWidget(lbl_loading_sub)
        
        # Stats Cards Row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        
        def create_stats_card(title, obj_name):
            card = QFrame()
            card.setObjectName(obj_name)
            card.setStyleSheet("""
                QFrame#""" + obj_name + """ {
                    background-color: #111827;
                    border: 1px solid #1F2937;
                    border-radius: 8px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)
            
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #6B7280; font-size: 10px; font-weight: bold; text-transform: uppercase;")
            
            lbl_val = QLabel("--")
            lbl_val.setStyleSheet("color: #10B981; font-size: 18px; font-weight: bold; font-family: 'Consolas', monospace;")
            
            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_val)
            return card, lbl_val
            
        card_scan, self.lbl_scan_val = create_stats_card("Scan Progress / 掃描進度", "CardScan")
        card_bits, self.lbl_bits_val = create_stats_card("Extracted Bits / 提取位元", "CardBits")
        card_payload, self.lbl_payload_val = create_stats_card("Payload / 解密大小", "CardPayload")
        card_speed, self.lbl_speed_val = create_stats_card("Decode Velocity / 解密速度", "CardSpeed")
        
        stats_layout.addWidget(card_scan)
        stats_layout.addWidget(card_bits)
        stats_layout.addWidget(card_payload)
        stats_layout.addWidget(card_speed)
        loading_layout.addLayout(stats_layout)
        
        # Terminal Console QTextEdit
        self.console_output = QTextEdit()
        self.console_output.setObjectName("TerminalConsole")
        self.console_output.setReadOnly(True)
        loading_layout.addWidget(self.console_output)
        
        # Progress area
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 100)
        self.loading_bar.setValue(0)
        self.loading_bar.setFixedHeight(8)
        self.loading_bar.setTextVisible(False)
        loading_layout.addWidget(self.loading_bar)
        
        self.lbl_loading_status = QLabel("正在初始化 PEE 解碼管線...")
        self.lbl_loading_status.setObjectName("LoadingStatus")
        self.lbl_loading_status.setStyleSheet("color: #94A3B8; font-size: 12px; font-family: Consolas, monospace;")
        loading_layout.addWidget(self.lbl_loading_status)
        
        self.stacked_widget.addWidget(self.page_loading)
        
        # PAGE 2: Player Page (Video Viewer)
        self.page_player = QFrame()
        self.page_player.setObjectName("PlayerPage")
        player_layout = QHBoxLayout(self.page_player)
        player_layout.setContentsMargins(15, 15, 15, 15)
        player_layout.setSpacing(15)
        
        # Splitter to allow resizing sidebar
        splitter = QSplitter(Qt.Horizontal)
        player_layout.addWidget(splitter)
        
        # Left Panel: Video + Controls
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        # Video Frame Container
        self.video_container = QFrame()
        self.video_container.setObjectName("VideoContainerFrame")
        video_container_layout = QVBoxLayout(self.video_container)
        video_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QVideoWidget()
        video_container_layout.addWidget(self.video_widget)
        self.video_player.setVideoOutput(self.video_widget)
        
        left_layout.addWidget(self.video_container, stretch=1)
        
        # Control Bar Frame
        control_bar = QFrame()
        control_bar.setObjectName("ControlBarFrame")
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(15, 10, 15, 10)
        control_layout.setSpacing(15)
        
        # Open File Button
        self.open_button = QPushButton("📁")
        self.open_button.setObjectName("OpenButton")
        self.open_button.clicked.connect(self.open_file_dialog)
        control_layout.addWidget(self.open_button)
        
        # Play/Pause Button
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("PlayButton")
        self.play_button.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_button)
        
        # Progress Slider
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setObjectName("ProgressSlider")
        self.progress_slider.sliderPressed.connect(self.on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self.on_slider_released)
        self.progress_slider.sliderMoved.connect(self.on_slider_moved)
        control_layout.addWidget(self.progress_slider)
        
        # Time Duration Label
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("TimeLabel")
        control_layout.addWidget(self.time_label)
        
        # Mute / Volume Button
        self.mute_button = QPushButton("🔊")
        self.mute_button.setObjectName("MuteButton")
        self.mute_button.clicked.connect(self.toggle_mute)
        control_layout.addWidget(self.mute_button)
        
        # Volume Slider
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.audio_output.setVolume(0.8)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        control_layout.addWidget(self.volume_slider)
        
        # Audio Track Selector Toggle Button
        self.tracks_toggle_button = QPushButton("🌐 Tracks")
        self.tracks_toggle_button.setObjectName("TracksToggleButton")
        self.tracks_toggle_button.clicked.connect(self.toggle_sidebar)
        control_layout.addWidget(self.tracks_toggle_button)
        
        # Decoding Status Indicator
        self.lbl_hud_fps = QLabel("就緒")
        self.lbl_hud_fps.setObjectName("HudFpsLabel")
        self.lbl_hud_fps.setStyleSheet("""
            QLabel#HudFpsLabel {
                color: #10B981;
                font-size: 11px;
                font-weight: bold;
                font-family: Consolas, monospace;
                padding: 4px 8px;
                background-color: rgba(16, 185, 129, 0.1);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 6px;
            }
        """)
        control_layout.addWidget(self.lbl_hud_fps)
        
        left_layout.addWidget(control_bar)
        splitter.addWidget(left_container)
        
        # Right Panel: Sidebar Language list (collapsible) and Zero-Trust Panel
        self.sidebar = QFrame()
        self.sidebar.setObjectName("SidebarFrame")
        self.sidebar.setFixedWidth(280)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 15, 12, 15)
        sidebar_layout.setSpacing(10)
        
        sidebar_title = QLabel("🌐 Audio Languages")
        sidebar_title.setObjectName("SidebarTitle")
        sidebar_layout.addWidget(sidebar_title)
        
        # IP Lock Toggle Box
        ip_lock_box = QFrame()
        ip_lock_box.setObjectName("IpLockBox")
        ip_lock_box.setStyleSheet("""
            QFrame#IpLockBox {
                background-color: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        ip_lock_layout = QVBoxLayout(ip_lock_box)
        ip_lock_layout.setContentsMargins(6, 6, 6, 6)
        ip_lock_layout.setSpacing(4)
        
        self.btn_ip_lock = QPushButton()
        self.btn_ip_lock.setObjectName("BtnIpLock")
        self.btn_ip_lock.clicked.connect(self.toggle_ip_lock)
        ip_lock_layout.addWidget(self.btn_ip_lock)
        
        self.lbl_ip_lock_hint = QLabel()
        self.lbl_ip_lock_hint.setObjectName("IpLockHint")
        self.lbl_ip_lock_hint.setStyleSheet("color: #64748B; font-size: 10px;")
        self.lbl_ip_lock_hint.setWordWrap(True)
        ip_lock_layout.addWidget(self.lbl_ip_lock_hint)
        
        self.update_ip_lock_button_ui()
        sidebar_layout.addWidget(ip_lock_box)
        
        self.lang_list = QListWidget()
        self.lang_list.setObjectName("LanguageList")
        self.lang_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lang_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.lang_list.itemClicked.connect(self.on_lang_item_clicked)
        sidebar_layout.addWidget(self.lang_list)
        
        # Add Separator Line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #1E293B; margin: 8px 0;")
        sidebar_layout.addWidget(separator)
        
        # Zero-Trust Security Title
        sec_title = QLabel("🛡️ Zero-Trust Security Center")
        sec_title.setObjectName("SecurityTitle")
        sec_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981;")
        sidebar_layout.addWidget(sec_title)
        
        # Security Info Box
        sec_info_frame = QFrame()
        sec_info_frame.setObjectName("SecurityInfoFrame")
        sec_info_frame.setStyleSheet("""
            QFrame#SecurityInfoFrame {
                background-color: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        sec_info_layout = QVBoxLayout(sec_info_frame)
        sec_info_layout.setSpacing(8)
        sec_info_layout.setContentsMargins(10, 10, 10, 10)
        
        self.lbl_sec_ip = QLabel("客戶端 IP: 載入中...")
        self.lbl_sec_proxy = QLabel("本機代理: 載入中...")
        self.lbl_sec_geo = QLabel("地理國家: 載入中...")
        self.lbl_sec_decision = QLabel("決策路徑: 載入中...")
        self.lbl_sec_trust = QLabel("信任等級: 載入中...")
        self.lbl_stego_checksum = QLabel("檔案 MD5: 載入中...")
        
        for lbl in [self.lbl_sec_ip, self.lbl_sec_proxy, self.lbl_sec_geo, self.lbl_sec_decision, self.lbl_sec_trust, self.lbl_stego_checksum]:
            lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-family: Consolas, monospace;")
            lbl.setWordWrap(True)
            sec_info_layout.addWidget(lbl)
            
        sidebar_layout.addWidget(sec_info_frame)
        
        # Interactive Web Dashboard launcher (Hidden in release mode, shown only in dev/debug mode)
        self.btn_web_sim = QPushButton("🖥️ 開啟安全性分析網頁")
        self.btn_web_sim.setObjectName("WebSimButton")
        self.btn_web_sim.setStyleSheet("""
            QPushButton#WebSimButton {
                background-color: #111827;
                color: #38BDF8;
                border: 1px solid #0284C7;
                border-radius: 6px;
                padding: 10px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#WebSimButton:hover {
                background-color: #1F2937;
                border: 1px solid #38BDF8;
                color: #F8FAFC;
            }
        """)
        self.btn_web_sim.clicked.connect(self.launch_web_dashboard)
        sidebar_layout.addWidget(self.btn_web_sim)
        
        # 僅在開發或研究模式下顯示 (透過 --dev / --debug 參數或環境變數 DE_DEV_MODE=1)；一般發行版預設隱藏
        is_dev_mode = (
            not getattr(sys, "frozen", False) and
            (os.environ.get("DE_DEV_MODE") == "1" or "--dev" in sys.argv or "--debug" in sys.argv)
        )
        if not is_dev_mode:
            self.btn_web_sim.hide()
        
        splitter.addWidget(self.sidebar)
        
        # Hide sidebar by default
        self.sidebar.hide()
        
        self.stacked_widget.addWidget(self.page_player)
        
        # Secondary Audio Sync Overlay
        self.loading_overlay = QLabel("🔄 Synchronizing audio track...", self.video_widget)
        self.loading_overlay.setObjectName("LoadingOverlay")
        self.loading_overlay.setAlignment(Qt.AlignCenter)
        self.loading_overlay.setStyleSheet("""
            QLabel#LoadingOverlay {
                background-color: rgba(15, 23, 42, 0.8);
                color: #818CF8;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
        """)
        self.loading_overlay.hide()

        # Primary Glassmorphism Buffering & Streaming Decoding HUD Overlay
        self.buffer_overlay = QFrame(self.video_container)
        self.buffer_overlay.setObjectName("BufferOverlay")
        self.buffer_overlay.setStyleSheet("""
            QFrame#BufferOverlay {
                background-color: rgba(11, 15, 25, 0.88);
                border: 1px solid rgba(99, 102, 241, 0.4);
                border-radius: 12px;
            }
        """)
        buffer_overlay_layout = QVBoxLayout(self.buffer_overlay)
        buffer_overlay_layout.setAlignment(Qt.AlignCenter)
        buffer_overlay_layout.setSpacing(12)
        
        self.lbl_buffer_title = QLabel("⚡ 音訊串流解碼中...")
        self.lbl_buffer_title.setStyleSheet("color: #F8FAFC; font-size: 18px; font-weight: bold;")
        self.lbl_buffer_title.setAlignment(Qt.AlignCenter)
        buffer_overlay_layout.addWidget(self.lbl_buffer_title)
        
        self.buffer_progress_bar = QProgressBar()
        self.buffer_progress_bar.setRange(0, 100)
        self.buffer_progress_bar.setValue(0)
        self.buffer_progress_bar.setFixedHeight(8)
        self.buffer_progress_bar.setFixedWidth(360)
        self.buffer_progress_bar.setTextVisible(False)
        self.buffer_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #06B6D4);
                border-radius: 4px;
            }
        """)
        buffer_overlay_layout.addWidget(self.buffer_progress_bar, alignment=Qt.AlignCenter)
        
        self.lbl_buffer_status = QLabel("正在啟動解密管線 (預估緩衝: 2.8 秒)...")
        self.lbl_buffer_status.setStyleSheet("color: #94A3B8; font-size: 13px; font-family: Consolas, monospace;")
        self.lbl_buffer_status.setAlignment(Qt.AlignCenter)
        buffer_overlay_layout.addWidget(self.lbl_buffer_status)
        
        self.buffer_overlay.hide()
        
        self.apply_stylesheet()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay") and hasattr(self, "video_widget"):
            self.loading_overlay.setGeometry(self.video_widget.rect())
        if hasattr(self, "buffer_overlay") and hasattr(self, "video_container"):
            self.buffer_overlay.setGeometry(self.video_container.rect())

    def apply_stylesheet(self):
        stylesheet = """
            QMainWindow {
                background-color: #0B0F19; /* Deep Slate 950 */
            }
            QWidget#StackedWidget {
                background-color: #0B0F19;
            }
            QFrame#LandingPage, QFrame#LoadingPage {
                background-color: #0B0F19;
            }
            QLabel#WelcomeTitle {
                color: #F8FAFC;
                font-size: 28px;
                font-weight: bold;
            }
            QLabel#WelcomeSub {
                color: #818CF8;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#StartOpenButton {
                background-color: #4F46E5;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 16px 32px;
                border-radius: 8px;
                min-width: 320px;
            }
            QPushButton#StartOpenButton:hover {
                background-color: #6366F1;
            }
            QPushButton#StartOpenButton:pressed {
                background-color: #4338CA;
            }
            QLabel#WelcomeDesc {
                color: #64748B;
                font-size: 13px;
            }
            QLabel#LoadingTitle {
                color: #F8FAFC;
                font-size: 20px;
                font-weight: bold;
            }
            QLabel#LoadingStatus {
                color: #94A3B8;
                font-size: 14px;
                font-family: Consolas, monospace;
            }
            QProgressBar {
                background-color: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #06B6D4);
                border-radius: 4px;
            }
            QTextEdit#TerminalConsole {
                background-color: #050814;
                color: #CBD5E1;
                border: 1px solid #1E293B;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
            QFrame#VideoContainerFrame {
                background-color: #020617;
                border: 2px solid #1E293B;
                border-radius: 12px;
            }
            QFrame#ControlBarFrame {
                background-color: rgba(30, 41, 59, 0.75);
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QFrame#SidebarFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QLabel#SidebarTitle {
                color: #F8FAFC;
                font-size: 16px;
                font-weight: bold;
                padding-bottom: 8px;
                border-bottom: 1px solid #334155;
            }
            QListWidget#LanguageList {
                background-color: transparent;
                border: none;
                outline: none;
                padding-right: 2px;
            }
            QListWidget#LanguageList::item {
                background-color: #334155;
                color: #CBD5E1;
                border-radius: 8px;
                padding: 10px 12px;
                margin-top: 3px;
                margin-bottom: 3px;
                margin-right: 4px;
                border: 1px solid transparent;
            }
            QListWidget#LanguageList::item:hover {
                background-color: #475569;
                color: #FFFFFF;
            }
            QListWidget#LanguageList::item:selected {
                background-color: #4F46E5;
                color: #FFFFFF;
                border: 1px solid #818CF8;
                font-weight: bold;
            }
            /* Modern Sleek Scrollbars (Language List & Console) */
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #334155;
                min-height: 28px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #818CF8;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #4F46E5;
            }
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: none;
                border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 6px;
                margin: 0px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #334155;
                min-width: 28px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #818CF8;
            }
            QScrollBar::handle:horizontal:pressed {
                background-color: #4F46E5;
            }
            QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {
                width: 0px;
                background: none;
                border: none;
            }
            QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
                background: none;
                border: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
            QPushButton#PlayButton, QPushButton#MuteButton, QPushButton#OpenButton {
                background-color: #4F46E5;
                color: white;
                border: none;
                border-radius: 20px;
                min-width: 40px;
                min-height: 40px;
                max-width: 40px;
                max-height: 40px;
                font-size: 16px;
            }
            QPushButton#OpenButton {
                background-color: #334155;
            }
            QPushButton#PlayButton:hover, QPushButton#MuteButton:hover {
                background-color: #6366F1;
            }
            QPushButton#OpenButton:hover {
                background-color: #475569;
            }
            QPushButton#PlayButton:pressed, QPushButton#MuteButton:pressed {
                background-color: #4338CA;
            }
            QPushButton#OpenButton:pressed {
                background-color: #1E293B;
            }
            QPushButton#TracksToggleButton {
                background-color: #334155;
                color: #F8FAFC;
                border: none;
                border-radius: 8px;
                padding-left: 12px;
                padding-right: 12px;
                height: 40px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#TracksToggleButton:hover {
                background-color: #475569;
            }
            QPushButton#TracksToggleButton:pressed {
                background-color: #1E293B;
            }
            QSlider#ProgressSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #475569;
                border-radius: 3px;
            }
            QSlider#ProgressSlider::sub-page:horizontal {
                background: #4F46E5;
                border-radius: 3px;
            }
            QSlider#ProgressSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #818CF8;
                width: 14px;
                height: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QSlider#ProgressSlider::handle:horizontal:hover {
                background: #EEF2FF;
                border-color: #4F46E5;
                width: 16px;
                height: 16px;
                border-radius: 8px;
            }
            QSlider#VolumeSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #475569;
                border-radius: 2px;
            }
            QSlider#VolumeSlider::sub-page:horizontal {
                background: #10B981;
                border-radius: 2px;
            }
            QSlider#VolumeSlider::handle:horizontal {
                background: #FFFFFF;
                width: 12px;
                height: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QLabel#TimeLabel {
                color: #94A3B8;
                font-size: 13px;
                font-family: Consolas, monospace;
            }
        """
        self.setStyleSheet(stylesheet)

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

    def handoff_to_full_track(self):
        if not self.audio_player_next_ready:
            return
        self.is_playing_chunk0 = False
        self.audio_player_next_ready = False
        self.audio_player_next_loading = False
        self.audio_player_next_seeked = False
        self.is_buffering_chunk1 = False
        
        # audio_player_next has already been pre-seeked and primed at boundary_ms in background!
        if self.is_user_playing:
            self.audio_player_next.play()
        
        # Smooth cross-overlap: let old player finish its buffered tail for 35ms then stop
        old_player = self.audio_player
        QTimer.singleShot(35, old_player.stop)
        
        # Swap players so self.audio_player is always active
        self.audio_player, self.audio_player_next = self.audio_player_next, self.audio_player
        self.audio_output, self.audio_output_next = self.audio_output_next, self.audio_output
        self.append_log("⚡ 音訊串流無縫接續完成，零中斷持續播放。", "SUCCESS")

    def toggle_sidebar(self):
        is_visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not is_visible)
        if not is_visible:
            self.tracks_toggle_button.setStyleSheet("""
                QPushButton#TracksToggleButton {
                    background-color: #4F46E5;
                    border: 1px solid #818CF8;
                }
            """)
        else:
            self.tracks_toggle_button.setStyleSheet("")

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Stego/Raw Video File", "", "Video Files (*.mp4 *.webm *.avi *.mkv)"
        )
        if file_path:
            self.load_new_video_file(file_path)

    def append_log(self, text, level="INFO"):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        color_map = {
            "INFO": "#38BDF8",     # Cyan
            "SUCCESS": "#10B981",  # Emerald Green
            "WARNING": "#F59E0B",  # Amber
            "ERROR": "#EF4444",    # Red
            "PROCESS": "#A78BFA",  # Purple
            "METADATA": "#F472B6"  # Pink
        }
        color = color_map.get(level, "#CBD5E1")
        html_msg = f'<span style="color: #64748B;">[{now}]</span> <span style="color: {color}; font-weight: bold;">[{level}]</span> <span style="color: #E2E8F0;">{text}</span>'
        self.console_output.append(html_msg)
        self.console_output.ensureCursorVisible()

    def load_new_video_file(self, video_file):
        # Stop players and release files
        self.video_player.stop()
        self.audio_player.stop()
        self.audio_player_next.stop()
        self.video_player.setSource(QUrl())
        self.audio_player.setSource(QUrl())
        self.audio_player_next.setSource(QUrl())
        
        # Clean up old temp directory
        self.cleanup_temp_dir()
        
        # Clear UI state
        self.lang_list.clear()
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
        self.play_button.setText("▶")
        self.video_audio_output.setVolume(self.current_volume)
        
        # Switch directly to Player Page (index 2) - Instant entry with non-blocking buffering HUD
        self.stacked_widget.setCurrentIndex(2)
        self.video_path = video_file
        self.load_video()
        self.video_player.pause()  # Cue frame 0 behind the glassmorphism overlay
        
        # Display modern Glassmorphism Buffering & Streaming HUD
        if hasattr(self, "buffer_overlay") and hasattr(self, "video_container"):
            self.buffer_overlay.setGeometry(self.video_container.rect())
            self.buffer_overlay.show()
            self.lbl_buffer_title.setText("⚡ 音訊串流解碼中...")
            self.lbl_buffer_status.setText("正在啟動解密管線...")
            self.buffer_progress_bar.setValue(0)
            
        if hasattr(self, "lbl_hud_fps"):
            self.lbl_hud_fps.setText("⚡ 解碼中...")
        
        # Reset Stats Cards & Console
        self.lbl_scan_val.setText("0 / -- 幀")
        self.lbl_bits_val.setText("0 bits")
        self.lbl_payload_val.setText("0.00 / -- MB")
        self.lbl_speed_val.setText("0 FPS")
        self.console_output.clear()
        self.loading_bar.setValue(0)
        
        # Reset security center UI labels
        if hasattr(self, "lbl_sec_ip"):
            self.lbl_sec_ip.setText("客戶端 IP: 載入中...")
            self.lbl_sec_proxy.setText("本機代理: 載入中...")
            self.lbl_sec_geo.setText("地理國家: 載入中...")
            self.lbl_sec_decision.setText("決策路徑: 載入中...")
            self.lbl_sec_trust.setText("信任等級: 載入中...")
            self.lbl_stego_checksum.setText("檔案 MD5: 計算中...")
        
        self.extraction_start_time = time.time()
        self.last_reported_frame = 0
        self.metadata_parsed = False
        
        filename = os.path.basename(video_file)
        self.append_log("初始化 DE 多軌藏密播放系統...", "INFO")
        self.append_log(f"載入載體影片檔: {filename}", "INFO")
        self.append_log("啟動 FFmpeg YUV420p 原生像素讀取管線...", "PROCESS")
        self.append_log("載入解密引擎...", "PROCESS")
        
        # Setup paths
        self.temp_dir = pyinstaller_utils.get_temp_dir("temp_extracted_tracks")
        
        # Create temp dir
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)
        
        # Start Extraction Worker Thread
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
        self.append_log(f"⚡ [串流解碼] 讀取第 0 幀已即時解析出語系清冊 (Manifest)！共 {len(tracks_meta)} 國語系即時呈現 (首塊切片長度: {self.initial_chunk_sec:.1f}s)", "SUCCESS")
        
        # Immediate sidebar population
        self.lang_list.clear()
        for t in tracks_meta:
            lang_code = t["id"]
            if lang_code not in self.audio_tracks:
                self.audio_tracks[lang_code] = None
            display_name = LANGUAGE_MAP.get(lang_code, f"({lang_code}) Audio Track")
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, lang_code)
            self.lang_list.addItem(item)
            
        # Fast GeoIP matching
        from i18n_detector import detect_best_locale
        from pyinstaller_utils import get_resource_path
        db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
        if not os.path.exists(db_path):
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))
            
        pre_res = detect_best_locale(
            [t["id"] for t in tracks_meta],
            db_path=db_path,
            ip_lock_mode=self.ip_lock_enabled
        )
        self.ip_matched_track = pre_res.track_key
        self.detected_ip = pre_res.metadata.get("ip", "127.0.0.1")
        self.detected_country = pre_res.metadata.get("country", "TW")
        self.ip_allowed_tracks = pre_res.metadata.get("allowed_tracks", [pre_res.track_key])
        
        self.refresh_track_list_badges()
        self.start_i18n_detection()
        
        # Pre-select best track in sidebar
        for i in range(self.lang_list.count()):
            it = self.lang_list.item(i)
            if it.data(Qt.UserRole) == self.ip_matched_track:
                self.lang_list.setCurrentItem(it)
                break

    def on_chunk_received(self, chunk_idx, tracks_dict, is_last):
        for lang, path in tracks_dict.items():
            self.audio_tracks[lang] = path

        if chunk_idx == 0:
            self.append_log(f"⚡ [串流解碼] 首塊音訊 (Chunk 0, 前 {self.initial_chunk_sec:.1f} 秒) 解碼就緒！緩衝解除，立即同步開播有聲輸出！", "SUCCESS")
            if hasattr(self, "buffer_overlay"):
                self.buffer_overlay.hide()

            chosen_track = (
                self.pending_language
                if (self.pending_language and self.pending_language in self.audio_tracks and self.audio_tracks[self.pending_language])
                else self.ip_matched_track
            )
            if not chosen_track or chosen_track not in self.audio_tracks or not self.audio_tracks[chosen_track]:
                chosen_track = next((k for k, v in self.audio_tracks.items() if v), None)

            self.pending_language = None
            self.is_user_playing = True
            self.play_button.setText("⏸")
            if chosen_track:
                self.select_audio_track(chosen_track)

            self.video_player.play()
            self.audio_player.play()

            if hasattr(self, "lbl_hud_fps"):
                self.lbl_hud_fps.setText("⚡ 解碼中...")

        elif chunk_idx == 1 or is_last:
            self.append_log("🎉 完整音訊串流解碼完畢！多語音軌無縫接續完成。", "SUCCESS")
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
                        # Video was paused or reached boundary waiting for Chunk 1:
                        self.is_buffering_chunk1 = False
                        self.handoff_pending_resume = True
                        self.audio_player_next_ready = False
                        self.audio_player_next_loading = True
                        self.audio_player_next_seeked = False
                        self.audio_player_next.setSource(full_url)
                    else:
                        # Chunk 0 is still actively playing ahead of boundary:
                        # Preload into audio_player_next in background
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
        elapsed = time.time() - self.extraction_start_time
        fps = int(current_frame / elapsed) if elapsed > 0 else 0
        
        # Update Stats Cards
        self.lbl_scan_val.setText(f"{current_frame} / {total_frames if total_frames > 0 else '--'} 幀")
        self.lbl_bits_val.setText(f"{bit_idx:,} bits")
        
        extracted_mb = bit_idx / 8 / 1024 / 1024
        if target_bits > 0:
            target_mb = target_bits / 8 / 1024 / 1024
            self.lbl_payload_val.setText(f"{extracted_mb:.2f} / {target_mb:.2f} MB")
        else:
            self.lbl_payload_val.setText(f"{extracted_mb:.2f} / -- MB")
            
        self.lbl_speed_val.setText(f"{fps} FPS")
        
        # Update progress bar and streaming HUD
        if total_frames > 0:
            val = int((current_frame / total_frames) * 100)
            self.loading_bar.setValue(val)
            self.lbl_loading_status.setText(f"解碼中 ({val}%)")
            if hasattr(self, "buffer_progress_bar"):
                self.buffer_progress_bar.setValue(val)
            if hasattr(self, "lbl_buffer_status"):
                self.lbl_buffer_status.setText(
                    f"⚡ 解碼中: 已掃描 {current_frame}/{total_frames} 幀 ({val}%)"
                )
            if hasattr(self, "lbl_hud_fps") and not self.is_user_playing:
                self.lbl_hud_fps.setText("⚡ 解碼中...")
            
        # Log scan progress
        if not self.metadata_parsed and target_bits > 0:
            self.metadata_parsed = True
            target_bytes = target_bits // 8
            target_mb = target_bytes / 1024 / 1024
            self.append_log("解析成功！已讀取 PEE 隱寫中繼資料標頭 (Metadata Header)", "SUCCESS")
            self.append_log(f"偵測到壓縮載荷大小: {target_bytes:,} Bytes ({target_mb:.2f} MB) | 預期位元: {target_bits:,} bits", "METADATA")
            self.append_log("分配隱寫資料提取緩衝區... OK", "PROCESS")
            
        # Log scanning stats every 30 frames to avoid spamming the console
        if current_frame - self.last_reported_frame >= 30:
            self.last_reported_frame = current_frame
            percent_str = f" ({int(current_frame/total_frames*100)}%)" if total_frames > 0 else ""
            self.append_log(f"已掃描 {current_frame}/{total_frames} 幀{percent_str} | 已提取 {bit_idx:,} bits | 瞬時速度: {fps} FPS", "INFO")

    def on_extraction_finished(self, video_file, audio_tracks):
        for lang_code, file_path in audio_tracks.items():
            self.audio_tracks[lang_code] = file_path
        self.video_path = video_file
        
        # Repopulate language selection list only if empty, otherwise refresh badges
        if self.lang_list.count() == 0:
            self.repopulate_sidebar_items()
        else:
            self.refresh_track_list_badges()
        
        # Single clean completion log to prevent UI event loop freezes
        self.append_log(f"✅ 解碼完成：全片 {len(audio_tracks)} 組多語音軌皆已解密就緒。", "SUCCESS")
        
        # Force progress bar to 100%
        self.loading_bar.setValue(100)
        self.lbl_loading_status.setText("解碼完成")
        
        # Hide buffer overlay immediately
        if hasattr(self, "buffer_overlay"):
            self.buffer_overlay.hide()
            
        if hasattr(self, "lbl_hud_fps"):
            self.lbl_hud_fps.setText("✅ 解碼完成")
            
        # If playback has NOT started yet (e.g. legacy monolithic stego video), start it now
        if not self.is_user_playing:
            from i18n_detector import detect_best_locale
            from pyinstaller_utils import get_resource_path
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
            if not os.path.exists(db_path):
                db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))
                
            pre_res = detect_best_locale(
                list(self.audio_tracks.keys()), 
                db_path=db_path, 
                ip_lock_mode=self.ip_lock_enabled
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
            self.play_button.setText("⏸")
            self.select_audio_track(chosen_track)
            self.refresh_track_list_badges()
            self.start_i18n_detection()
            
            # Start playback immediately without delay
            self.video_player.play()
            self.audio_player.play()

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
            self.append_log("🔒 已啟用「自動 IP 鎖定模式」：系統強制鎖定當前公網 IP 地理區域許可之音軌。", "SUCCESS")
            # If current track is not allowed, switch back to IP matched track
            from i18n_detector import is_track_allowed_by_ip
            if self.ip_matched_track and (not self.current_lang or not is_track_allowed_by_ip(self.current_lang, self.detected_country, list(self.audio_tracks.keys()))):
                self.select_audio_track(self.ip_matched_track)
        else:
            self.append_log("🔓 已停用「自動 IP 鎖定模式」：切換為自由選軌模式，可自由點播任意語言配音。", "INFO")

    def update_ip_lock_button_ui(self):
        if self.ip_lock_enabled:
            self.btn_ip_lock.setText("🔒 自動 IP 鎖定：啟用中 (Active)")
            self.btn_ip_lock.setStyleSheet("""
                QPushButton#BtnIpLock {
                    background-color: #064E3B;
                    color: #34D399;
                    border: 1px solid #10B981;
                    border-radius: 6px;
                    padding: 8px 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton#BtnIpLock:hover {
                    background-color: #047857;
                    color: #FFFFFF;
                }
            """)
            self.lbl_ip_lock_hint.setText("模式：強制鎖定 IP 授權音軌 (限制未授權音軌)")
        else:
            self.btn_ip_lock.setText("🔓 自動 IP 鎖定：已停用 (自由選軌)")
            self.btn_ip_lock.setStyleSheet("""
                QPushButton#BtnIpLock {
                    background-color: #1E293B;
                    color: #94A3B8;
                    border: 1px solid #475569;
                    border-radius: 6px;
                    padding: 8px 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton#BtnIpLock:hover {
                    background-color: #334155;
                    color: #F8FAFC;
                }
            """)
            self.lbl_ip_lock_hint.setText("模式：自由切換模式 (可點選任意多國音軌)")

    def refresh_track_list_badges(self):
        from i18n_detector import is_track_allowed_by_ip
        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            lang_code = item.data(Qt.UserRole)
            display_name = LANGUAGE_MAP.get(lang_code, f"({lang_code}) Audio Track")
            
            if self.ip_lock_enabled:
                if lang_code == self.ip_matched_track:
                    item.setText(f"🌐 [IP 配對] {display_name}")
                    item.setToolTip("當前 IP 最適配音軌 (自動鎖定中)")
                elif is_track_allowed_by_ip(lang_code, self.detected_country, list(self.audio_tracks.keys())):
                    item.setText(f"✓ [地區許可] {display_name}")
                    item.setToolTip("本地區許可收聽之音軌")
                else:
                    item.setText(f"🔒 [區域鎖定] {display_name}")
                    item.setToolTip(f"受 IP 地理區域限制保護 (僅限授權地區播放)")
            else:
                if lang_code == self.ip_matched_track:
                    item.setText(f"🌐 [IP 推薦] {display_name}")
                    item.setToolTip("依據 IP 地理位置推薦之音軌")
                else:
                    item.setText(display_name)
                    item.setToolTip("自由點選切換")

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
            
        # 1. Update Zero-Trust Security panel
        meta = result.metadata if result.metadata else {}
        client_ip = meta.get("ip", self.detected_ip)
        country = meta.get("country", self.detected_country)
        self.detected_ip = client_ip
        self.detected_country = country
        self.ip_matched_track = result.track_key
        self.ip_allowed_tracks = meta.get("allowed_tracks", [result.track_key])
        self.cached_i18n_result = result
        
        # Proxy detection
        proxy_detected = meta.get("proxy_detected", False)
        proxy_details = meta.get("details", "Direct Connection")
        proxy_status_str = f"啟用 ({proxy_details})" if proxy_detected else "未啟用 (直連)"
        
        # Trust level classification based on decision source
        trust_map = {
            "P0 IP_LOCK_ENFORCED": "🛡️ 頂級置信 (IP 區域強制鎖定)",
            "P1 EXPLICIT_HISTORY": "🟢 高置信度 (使用者偏好)",
            "P2a OS_UI_LANGS_EXACT": "🟢 高置信度 (系統原生)",
            "P4a TIMEZONE_CROSS": "🟢 高置信度 (時區比對)",
            "P2b OS_UI_LANGS_FUZZY": "🟡 中置信度 (系統模糊)",
            "P4c GEOIP_VERIFIED": "🟡 中置信度 (地理驗證)",
            "P4b LOCAL_DB_ONLY": "🟡 中置信度 (離線地理)",
            "P5 SYSTEM_DEFAULT": "🔴 低置信度 (保底選軌)",
            "THREAD_ERROR": "❌ 執行緒異常"
        }
        trust_level = trust_map.get(result.source, "🟡 中置信度")
        
        # Populate UI labels
        self.lbl_sec_ip.setText(f"客戶端 IP: {client_ip}")
        self.lbl_sec_proxy.setText(f"本機代理: {proxy_status_str}")
        self.lbl_sec_geo.setText(f"地理國家: {country}")
        self.lbl_sec_decision.setText(f"決策路徑: {result.source}")
        self.lbl_sec_trust.setText(f"信任等級: {trust_level}")
        
        # Calculate/retrieve MD5 checksum from background worker
        file_md5 = self.extract_thread.file_md5 if (self.extract_thread and hasattr(self.extract_thread, "file_md5")) else "Unknown"
        self.lbl_stego_checksum.setText(f"檔案 MD5: {file_md5[:10]}...")
        self.lbl_stego_checksum.setToolTip(f"完整檔案 MD5:\n{file_md5}")
        
        # Refresh track badges
        self.refresh_track_list_badges()
        
        # 2. Update track selection
        if self.user_manually_selected and not self.ip_lock_enabled:
            self.append_log("使用者已手動指定音軌，忽略背景自動偵測結果。", "INFO")
            return
            
        self.append_log(f"I18N 決策鏈已完成：{result.detail} | 決策源: {result.source} (置信度: {result.confidence:.2f})", "METADATA")
        self.select_audio_track(result.track_key)

    def on_extraction_error(self, video_file, err_msg):
        self.append_log(f"影像解密提示/異常: {err_msg}", "WARNING")
        self.append_log("無法從影像像素中讀取有效 PEE 藏密標頭。進行降級 (Fallback) 處理...", "WARNING")
        self.append_log("啟動本地外部音軌目錄搜尋機制 (Searching local files)...", "PROCESS")
        
        # Fallback to scanning local files in the selected video's directory
        video_dir = os.path.dirname(os.path.abspath(video_file))
        audio_tracks = {}
        for filename in os.listdir(video_dir):
            if "_audio_" in filename and (filename.endswith(".mp3") or filename.endswith(".m4a") or filename.endswith(".webm")):
                match = re.search(r"_audio_(.+)\.(mp3|m4a|webm)$", filename)
                if match:
                    lang = match.group(1)
                    audio_tracks[lang] = os.path.join(video_dir, filename)
                    lang_display = LANGUAGE_MAP.get(lang, f"({lang}) Track")
                    self.append_log(f"在目錄下偵測到對應音軌檔案: {filename} -> {lang_display}", "METADATA")
                    
        self.cleanup_temp_dir()
        
        if not audio_tracks:
            self.append_log("影片未含多語隱寫音軌或外部語音檔，切換為「原生載體音訊播放模式」。", "INFO")
            if hasattr(self, "buffer_overlay"):
                self.buffer_overlay.hide()
            self.video_audio_output.setVolume(self.current_volume)
            self.stacked_widget.setCurrentIndex(2)
            self.load_video()
            self.is_user_playing = True
            self.play_button.setText("⏸")
            self.video_player.play()
            return
            
        self.audio_tracks = audio_tracks
        self.video_path = video_file
        
        self.append_log(f"成功加載本地 {len(audio_tracks)} 組外部配音，正在啟動播放器...", "SUCCESS")
        
        self.repopulate_sidebar_items()
        
        # Delay transition for 1.2s
        def transition_fallback():
            self.stacked_widget.setCurrentIndex(2)
            self.load_video()
            
            from i18n_detector import detect_best_locale
            from pyinstaller_utils import get_resource_path
            db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-country-lite.mmdb"))
            if not os.path.exists(db_path):
                db_path = get_resource_path(os.path.join("for_ip", "i18n_security", "data", "dbip-city-lite.mmdb"))
                
            pre_res = detect_best_locale(
                list(self.audio_tracks.keys()), 
                db_path=db_path, 
                ip_lock_mode=self.ip_lock_enabled
            )
            best_track = pre_res.track_key
            self.ip_matched_track = best_track
            self.detected_ip = pre_res.metadata.get("ip", "127.0.0.1")
            self.detected_country = pre_res.metadata.get("country", "TW")
            self.ip_allowed_tracks = pre_res.metadata.get("allowed_tracks", [best_track])
            
            self.is_user_playing = True
            self.play_button.setText("⏸")
            self.select_audio_track(best_track)
            self.refresh_track_list_badges()
            self.start_i18n_detection()
            self.video_player.play()
            self.audio_player.play()
            
        QTimer.singleShot(1200, transition_fallback)

    def repopulate_sidebar_items(self):
        self.lang_list.clear()
        for lang_code, file_path in self.audio_tracks.items():
            display_name = LANGUAGE_MAP.get(lang_code, f"({lang_code}) Audio Track")
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, lang_code)
            self.lang_list.addItem(item)
        self.refresh_track_list_badges()

    # Media Control Logics
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
        
        # Save current position
        current_pos = self.video_player.position()
        
        # Seamless hot-swap: Only reload audio source without pausing video for true instant switching
        self.audio_pending_seek = current_pos
        self.audio_player.pause()
        self.audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(audio_file)))
        
        # Stego audio track takes control: mute carrier audio, restore stego volume
        self.video_audio_output.setVolume(0.0)
        self.audio_output.setVolume(self.current_volume)
        self.audio_output_next.setVolume(self.current_volume)
        
        # Stop and reset secondary player during track switch
        self.audio_player_next.stop()
        self.audio_player_next_ready = False
        self.audio_player_next_loading = False
        self.audio_player_next_seeked = False
        self.handoff_pending_resume = False
        
        # Check if selected file is chunk0
        if "_chunk0" in os.path.basename(audio_file):
            self.is_playing_chunk0 = True
        else:
            self.is_playing_chunk0 = False
        
        if self.is_user_playing:
            if self.audio_player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
                self.audio_player.setPosition(current_pos)
                self.audio_pending_seek = None
                self.audio_player.play()
            
        # Select item in GUI sidebar list
        for i in range(self.lang_list.count()):
            item = self.lang_list.item(i)
            if item.data(Qt.UserRole) == lang_code:
                self.lang_list.setCurrentItem(item)
                break

    def toggle_play(self):
        if self.is_user_playing:
            self.is_user_playing = False
            self.video_player.pause()
            self.audio_player.pause()
            self.audio_player_next.pause()
            self.play_button.setText("▶")
        else:
            self.is_user_playing = True
            self.play_button.setText("⏸")
            self.check_and_resume_playback()

    def toggle_mute(self):
        is_muted = self.audio_output.isMuted()
        new_mute = not is_muted
        self.audio_output.setMuted(new_mute)
        self.audio_output_next.setMuted(new_mute)
        self.video_audio_output.setMuted(new_mute)
        self.mute_button.setText("🔇" if new_mute else "🔊")

    def on_volume_changed(self, val):
        vol = val / 100.0
        self.current_volume = vol
        self.audio_output.setVolume(vol)
        self.audio_output_next.setVolume(vol)
        if self.current_lang and (self.audio_player.source().isValid() or self.audio_player_next.source().isValid()):
            self.video_audio_output.setVolume(0.0)
        else:
            self.video_audio_output.setVolume(vol)
            
        if val == 0:
            self.mute_button.setText("🔇")
        else:
            self.mute_button.setText("🔊")

    # Resumes playback if user-intent is playing and respective media is ready
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

    # Synchronization logic
    def sync_check(self):
        if self.is_user_playing:
            v_status = self.video_player.mediaStatus()
            a_status = self.audio_player.mediaStatus()
            buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)
            
            if not (v_status in buffering_states or a_status in buffering_states):
                v_pos = self.video_player.position()
                a_pos = self.audio_player.position()
                boundary_ms = int(getattr(self, 'initial_chunk_sec', 3.0) * 1000)

                # Gapless seamless handoff at the Chunk 0 boundary
                if self.is_playing_chunk0 and self.audio_player_next_ready and (a_pos >= boundary_ms - 150 or v_pos >= boundary_ms - 50):
                    self.handoff_to_full_track()
                    return

                # If Chunk 0 reached end and Chunk 1 is not ready yet, pause video to prevent drift & audio dropouts
                if self.is_playing_chunk0 and not self.audio_player_next_ready and (a_pos >= boundary_ms - 50 or a_status == QMediaPlayer.MediaStatus.EndOfMedia):
                    if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                        self.is_buffering_chunk1 = True
                        self.video_player.pause()
                        self.append_log("⏳ 正在等待音訊串流後續切片解碼完成 (平滑緩衝中)...", "PROCESS")
                    return

                diff = abs(v_pos - a_pos)
                
                # Gentle clock alignment: Only resynchronize audio if drift is significant (> 450ms)
                # to completely prevent audio dropouts, pops, and stuttering.
                import time
                current_time = time.time()
                if diff > 450 and (current_time - self.last_sync_seek) > 3.0:
                    if not (self.is_playing_chunk0 and not self.audio_player_next_ready):
                        self.audio_player.setPosition(v_pos)
                        self.last_sync_seek = current_time

    # Slider Interactions
    def on_slider_pressed(self):
        self.slider_is_dragging = True

    def on_slider_released(self):
        self.slider_is_dragging = False
        pos = self.progress_slider.value()
        self.video_player.setPosition(pos)
        
        boundary_ms = int(getattr(self, 'initial_chunk_sec', 3.0) * 1000)
        # If user dragged slider past Chunk 0 and full track is preloaded
        if self.is_playing_chunk0 and self.audio_player_next_ready and pos >= boundary_ms - 100:
            self.handoff_to_full_track()

        self.audio_player.setPosition(pos)
        if self.is_user_playing:
            self.check_and_resume_playback()

    def on_slider_moved(self, pos):
        self.video_player.setPosition(pos)
        self.audio_player.setPosition(pos)
        self.update_time_label(pos)

    # Media Player Signal Callbacks
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
        s = ms // 1000
        m = s // 60
        s = s % 60
        return f"{m:02d}:{s:02d}"

    def on_media_status_changed(self, status):
        sender = self.sender()
        if sender == self.audio_player_next:
            if getattr(self, "audio_player_next_loading", False) and status in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            ):
                boundary_ms = int(getattr(self, 'initial_chunk_sec', 3.0) * 1000)
                target_pos = max(boundary_ms, self.video_player.position())
                if not getattr(self, "audio_player_next_seeked", False):
                    self.audio_player_next.setPosition(target_pos)
                    self.audio_player_next_seeked = True
                self.audio_player_next_ready = True
                self.audio_player_next_loading = False
                if getattr(self, "handoff_pending_resume", False):
                    self.handoff_pending_resume = False
                    self.handoff_to_full_track()
                    if self.is_user_playing:
                        self.video_player.play()
            return

        v_status = self.video_player.mediaStatus()
        a_status = self.audio_player.mediaStatus()
        
        # Only when video reaches end of media does master playback stop!
        if v_status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.is_user_playing = False
            self.video_player.pause()
            self.audio_player.pause()
            self.audio_player_next.pause()
            self.play_button.setText("▶")
            self.loading_overlay.hide()
            return

        # If audio reached EndOfMedia while video is still playing (e.g. Chunk 0 ended)
        if a_status == QMediaPlayer.MediaStatus.EndOfMedia and v_status != QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_playing_chunk0:
                if self.audio_player_next_ready:
                    self.handoff_to_full_track()
                    return
                else:
                    # Chunk 1 is still decoding: pause video cleanly to prevent skipping audio
                    if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                        self.is_buffering_chunk1 = True
                        self.video_player.pause()
                        self.append_log("⏳ 正在等待音訊串流後續切片解碼完成 (平滑緩衝中)...", "PROCESS")
                    return
            if self.current_lang and self.current_lang in self.audio_tracks:
                track_path = self.audio_tracks[self.current_lang]
                if track_path and os.path.exists(track_path):
                    current_src = self.audio_player.source().toLocalFile()
                    if not is_same_path(current_src, track_path):
                        self.audio_pending_seek = self.video_player.position()
                        self.audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(track_path)))
                        return

        # Apply pending seek when media finishes loading
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
        
        # Only pause video if video itself is buffering (e.g. initial read or seek)
        if v_status in buffering_states:
            self.video_player.pause()
            self.audio_player.pause()
            self.loading_overlay.show()
        elif a_status in buffering_states:
            # Audio is loading during hot-swap, video keeps playing smoothly!
            pass
        else:
            self.loading_overlay.hide()
            if self.is_user_playing and not self.is_buffering_chunk1:
                self.check_and_resume_playback()

    def on_lang_item_clicked(self, item):
        lang_code = item.data(Qt.UserRole)
        display_name = LANGUAGE_MAP.get(lang_code, f"({lang_code}) Track")
        
        # 0. Check if we are still in initial buffer phase before playback starts
        if self.extract_thread and self.extract_thread.isRunning() and not self.is_user_playing:
            self.pending_language = lang_code
            self.append_log(f"已記錄預選語系: [{display_name}]，解碼完成將自動以該語言起播。", "INFO")
            for i in range(self.lang_list.count()):
                it = self.lang_list.item(i)
                if it.data(Qt.UserRole) == lang_code:
                    self.lang_list.setCurrentItem(it)
                    break
            return
            
        # 1. Zero-Trust IP Lock security guard
        if self.ip_lock_enabled:
            from i18n_detector import is_track_allowed_by_ip
            if not is_track_allowed_by_ip(lang_code, self.detected_country, list(self.audio_tracks.keys())):
                self.append_log(f"⚠️ [SECURITY] 阻擋非授權切換：音軌 [{lang_code}] 受 IP 區域版權鎖定保護 (當前 IP 地區: {self.detected_country})", "WARNING")
                QMessageBox.warning(
                    self, 
                    "🔒 IP 區域版權鎖定保護", 
                    f"【Zero-Trust 區域版權防護機制】\n\n"
                    f"目前系統已啟用「自動 IP 鎖定模式」。\n"
                    f"您的 IP 判定為：{self.detected_country} ({self.detected_ip})\n\n"
                    f"音軌 [{display_name}] 受到地理區域版權鎖定，不允許在當前地區播放！\n\n"
                    f"如需自由試聽所有多語音軌，請先關閉側邊欄的「自動 IP 鎖定」模式開關。"
                )
                # Reselect the valid current track in the list
                for i in range(self.lang_list.count()):
                    it = self.lang_list.item(i)
                    if it.data(Qt.UserRole) == self.current_lang:
                        self.lang_list.setCurrentItem(it)
                        break
                return

        # 2. Instant seamless hot-swap switching
        if lang_code != self.current_lang:
            track_ready = (
                lang_code in self.audio_tracks and 
                self.audio_tracks[lang_code] is not None and 
                os.path.exists(self.audio_tracks[lang_code])
            )
            if not track_ready:
                self.pending_language = lang_code
                self.append_log(f"音軌 [{display_name}] 正在解碼中，完成時將自動切換。", "INFO")
                return

            self.user_manually_selected = True # User manually intervened!
            self.select_audio_track(lang_code)
            self.append_log(f"🔄 即時熱切換音軌至: [{display_name}]", "INFO")
            # Save user preferred language manually selected (only in free mode)
            if not self.ip_lock_enabled:
                try:
                    settings = QSettings("GradProject", "StegoPlayer")
                    settings.setValue("preferred_language", lang_code)
                except Exception:
                    pass

    def cleanup_temp_dir(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            cleaned = False
            for _ in range(5):
                try:
                    shutil.rmtree(self.temp_dir)
                    print("🧹 成功清除臨時解密音軌。")
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
        
        # 1. Quick check if dashboard server is ALREADY running on port 8000
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

        # 2. Locate main.py, run_dashboard.bat, and Python interpreter
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
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                subprocess.Popen(
                    [python_exe, main_py],
                    cwd=os.path.dirname(main_py),
                    creationflags=creation_flags,
                    startupinfo=startupinfo
                )
                self.append_log("安全性分析伺服器已成功於背景啟動 (FastAPI on Port 8000)。", "SUCCESS")
                started = True
            except Exception as e:
                self.append_log(f"無法直接啟動伺服器: {e}，嘗試呼叫批次檔...", "WARNING")

        if not started and os.path.exists(bat_path):
            try:
                subprocess.Popen([bat_path], cwd=os.path.dirname(bat_path))
                started = True
            except Exception as e:
                self.append_log(f"無法啟動批次檔: {e}", "WARNING")

        # Wait 1.5s for Uvicorn to bind port 8000, then open browser
        QTimer.singleShot(1500, lambda: webbrowser.open("http://127.0.0.1:8000"))

    def closeEvent(self, event):
        # Stop background extraction if active
        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.terminate()
            self.extract_thread.wait()
            
        # Stop background i18n thread if active
        if self.current_i18n_thread and self.current_i18n_thread.isRunning():
            self.current_i18n_thread.terminate()
            self.current_i18n_thread.wait()
            
        # Release players and locks
        self.video_player.stop()
        self.audio_player.stop()
        self.audio_player_next.stop()
        self.video_player.setSource(QUrl())
        self.audio_player.setSource(QUrl())
        self.audio_player_next.setSource(QUrl())
        self.sync_timer.stop()
        
        # Cleanup
        self.cleanup_temp_dir()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    
    # Check for CLI initial file (skip flags like --dev, --debug)
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
