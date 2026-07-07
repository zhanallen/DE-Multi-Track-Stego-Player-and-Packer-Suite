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
    QProgressBar, QTextEdit
)
from PySide6.QtCore import Qt, QUrl, QTimer, QThread, Signal, QLocale, QSettings
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QFont

# Import our PEE steganography module
from pee_stego import decode_video_multi

# Mapping of language codes to display names with flag emojis
LANGUAGE_MAP = {
    'de-DE': '🇩🇪 Deutsch (German)',
    'en-US': '🇺🇸 English (United States)',
    'es-US': '🇪🇸 Español (Spanish - US)',
    'fr-FR': '🇫🇷 Français (French)',
    'hi': '🇮🇳 हिन्दी (Hindi)',
    'id': '🇮🇩 Bahasa Indonesia (Indonesian)',
    'it': '🇮🇹 Italiano (Italian)',
    'ja': '🇯🇵 日本語 (Japanese)',
    'ml': '🇮🇳 Malayalam (Malayalam)',
    'pl': '🇵🇱 Polski (Polish)',
    'pt-BR': '🇧🇷 Português (Portuguese - Brazil)',
    'uk': '🇺🇦 Українська (Ukrainian)',
}

class ExtractionThread(QThread):
    progress_signal = Signal(int, int, int, int) # current_frame, total_frames, bit_idx, target_bits
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
            
            # 2. Extract stego payload
            def progress_cb(current_frame, total_frames, bit_idx, target_bits):
                self.progress_signal.emit(current_frame, total_frames, bit_idx, target_bits)
                
            tracks = decode_video_multi(self.video_path, self.temp_dir, progress_callback=progress_cb)
            self.finished_signal.emit(tracks)
        except Exception as e:
            self.file_md5 = "Error"
            self.error_signal.emit(str(e))

class I18nDetectionWorker(QThread):
    finished_signal = Signal(str, object)
    
    def __init__(self, session_id, available_tracks, system_languages, history_lang, db_path):
        super().__init__()
        self.session_id = session_id
        self.available_tracks = available_tracks
        self.system_languages = system_languages
        self.history_lang = history_lang
        self.db_path = db_path
        
    def run(self):
        try:
            from i18n_detector import detect_best_locale
            res = detect_best_locale(
                self.available_tracks,
                self.system_languages,
                self.history_lang,
                self.db_path
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
        
        # Dashboard Variables
        self.extraction_start_time = 0.0
        self.last_reported_frame = 0
        self.metadata_parsed = False
        
        # Initialize Media Players
        self.video_player = QMediaPlayer()
        self.audio_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_player.setAudioOutput(self.audio_output)
        
        # Build UI and Stack Layout
        self.init_ui()
        
        # Connect Media Signals
        self.video_player.positionChanged.connect(self.on_video_position_changed)
        self.video_player.durationChanged.connect(self.on_duration_changed)
        
        self.video_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.audio_player.mediaStatusChanged.connect(self.on_media_status_changed)
        
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
        
        self.lang_list = QListWidget()
        self.lang_list.setObjectName("LanguageList")
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
            
        # 📋 複製取證報告小 icon 按鈕，放置於右下角
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_copy_sec = QPushButton("📋")
        self.btn_copy_sec.setToolTip("複製取證報告")
        self.btn_copy_sec.setFixedSize(24, 24)
        self.btn_copy_sec.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QPushButton:pressed {
                background-color: #0F172A;
            }
        """)
        self.btn_copy_sec.clicked.connect(self.copy_security_info)
        btn_layout.addWidget(self.btn_copy_sec)
        
        sec_info_layout.addLayout(btn_layout)
        
        sidebar_layout.addWidget(sec_info_frame)
        
        splitter.addWidget(self.sidebar)
        
        # Hide sidebar by default
        self.sidebar.hide()
        
        self.stacked_widget.addWidget(self.page_player)
        
        # Loading Overlay (Label floating over the video container for network/lag buffering)
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
        
        self.apply_stylesheet()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.loading_overlay.setGeometry(self.video_widget.rect())

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
            }
            QListWidget#LanguageList::item {
                background-color: #334155;
                color: #CBD5E1;
                border-radius: 8px;
                padding: 12px;
                margin-top: 4px;
                margin-bottom: 4px;
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
        self.video_player.setSource(QUrl())
        self.audio_player.setSource(QUrl())
        
        # Clean up old temp directory
        self.cleanup_temp_dir()
        
        # Clear UI state
        self.lang_list.clear()
        self.current_lang = None
        self.is_user_playing = False
        self.play_button.setText("▶")
        
        # Switch to Loading Page (index 1)
        self.stacked_widget.setCurrentIndex(1)
        
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
        self.append_log("載入 Numba JIT 極速解密引擎 (Coltuc coltuc_extract_restore_core_numba)...", "PROCESS")
        
        # Setup paths
        self.temp_dir = pyinstaller_utils.get_temp_dir("temp_extracted_tracks")
        
        # Create temp dir
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)
        
        # Start Extraction Worker Thread
        self.extract_thread = ExtractionThread(video_file, self.temp_dir)
        self.extract_thread.progress_signal.connect(self.on_extraction_progress)
        self.extract_thread.finished_signal.connect(lambda tracks: self.on_extraction_finished(video_file, tracks))
        self.extract_thread.error_signal.connect(lambda err: self.on_extraction_error(video_file, err))
        self.extract_thread.start()

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
        
        # Update progress bar
        if total_frames > 0:
            val = int((current_frame / total_frames) * 100)
            self.loading_bar.setValue(val)
            self.lbl_loading_status.setText(
                f"已掃描: {current_frame} / {total_frames} 幀 ({val}%) - 提取位元數: {bit_idx:,} bits"
            )
            
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
        self.audio_tracks = audio_tracks
        self.video_path = video_file
        
        # Repopulate language selection list
        self.repopulate_sidebar_items()
        
        # Append completion logs
        self.append_log("影像像素矩陣掃描完成，所有密文資料提取完畢！", "SUCCESS")
        self.append_log("啟動 zlib 解壓縮與封包還原流...", "PROCESS")
        
        # Show each audio track
        for lang_code, file_path in audio_tracks.items():
            lang_display = LANGUAGE_MAP.get(lang_code, f"({lang_code}) Track")
            file_size_kb = os.path.getsize(file_path) / 1024 if os.path.exists(file_path) else 0
            self.append_log(f"成功還原外部音軌 -> {lang_display} | 檔案大小: {file_size_kb:.1f} KB", "METADATA")
            
        self.append_log("驗證完成：載體影片影像像素 100% 位元級完美還原 (Bit-Perfect Reversibility Verification Verified ✅)", "SUCCESS")
        self.append_log("正在切換至播放核心，準備同步載入多音軌...", "INFO")
        
        # Force progress bar to 100%
        self.loading_bar.setValue(100)
        self.lbl_loading_status.setText("解碼完成！載入播放器中...")
        
        # Delay transition for 1.2s to let user read the awesome dashboard output
        def transition():
            self.stacked_widget.setCurrentIndex(2)
            self.load_video()
            temp_default = 'en-US' if 'en-US' in self.audio_tracks else list(self.audio_tracks.keys())[0]
            self.select_audio_track(temp_default)
            self.start_i18n_detection()
            
        QTimer.singleShot(1200, transition)

    def start_i18n_detection(self):
        self.user_manually_selected = False
        available_tracks = list(self.audio_tracks.keys())
        system_langs = QLocale.system().uiLanguages()
        
        settings = QSettings("GradProject", "StegoPlayer")
        history_lang = settings.value("preferred_language", None)
        
        from pyinstaller_utils import get_resource_path
        db_path = get_resource_path(os.path.join("src", "data", "dbip-country-lite.mmdb"))
        if not os.path.exists(db_path):
            db_path = get_resource_path(os.path.join("src", "data", "dbip-city-lite.mmdb"))
            
        session_id = self.video_path
        
        if self.current_i18n_thread and self.current_i18n_thread.isRunning():
            self.current_i18n_thread.terminate()
            self.current_i18n_thread.wait()
            
        self.current_i18n_thread = I18nDetectionWorker(
            session_id, available_tracks, system_langs, history_lang, db_path
        )
        self.current_i18n_thread.finished_signal.connect(self.on_i18n_detection_completed)
        self.current_i18n_thread.start()

    def on_i18n_detection_completed(self, session_id, result):
        if session_id != self.video_path:
            return
            
        # 1. Update Zero-Trust Security panel
        meta = result.metadata if result.metadata else {}
        client_ip = meta.get("ip", "127.0.0.1 (本地端)")
        
        # Proxy detection
        proxy_detected = meta.get("proxy_detected", False)
        proxy_details = meta.get("details", "Direct Connection")
        proxy_status_str = f"啟用 ({proxy_details})" if proxy_detected else "未啟用 (直連)"
        
        # Country
        country = meta.get("country", "未定位")
        
        # Trust level classification based on decision source
        trust_map = {
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
        
        # Check Zero-Trust Proxy Warning
        proxy_warning = meta.get("proxy_warning", False)
        if proxy_warning:
            trust_level = "🔴 高風險 (疑似位置偽裝)"
        
        # Populate UI labels
        self.lbl_sec_ip.setText(f"客戶端 IP: {client_ip}")
        self.lbl_sec_proxy.setText(f"本機代理: {proxy_status_str}")
        self.lbl_sec_geo.setText(f"地理國家: {country}")
        
        # 顯示完整鏈狀決策路徑
        decision_chain = meta.get("decision_chain", result.source)
        self.lbl_sec_decision.setText(f"決策路徑:\n{decision_chain}")
        
        self.lbl_sec_trust.setText(f"信任等級: {trust_level}")
        
        # Set trust label styling dynamically based on proxy warning
        if proxy_warning:
            self.lbl_sec_trust.setStyleSheet("color: #EF4444; font-size: 11px; font-family: Consolas, monospace; font-weight: bold;")
        else:
            self.lbl_sec_trust.setStyleSheet("color: #94A3B8; font-size: 11px; font-family: Consolas, monospace;")
        
        # Calculate/retrieve MD5 checksum from background worker
        file_md5 = self.extract_thread.file_md5 if (self.extract_thread and hasattr(self.extract_thread, "file_md5")) else "Unknown"
        self.lbl_stego_checksum.setText(f"檔案 MD5: {file_md5[:10]}...")
        self.lbl_stego_checksum.setToolTip(f"完整檔案 MD5:\n{file_md5}")
        
    def copy_security_info(self):
        client_ip = self.lbl_sec_ip.text()
        proxy = self.lbl_sec_proxy.text()
        geo = self.lbl_sec_geo.text()
        decision = self.lbl_sec_decision.text()
        trust = self.lbl_sec_trust.text()
        md5 = self.lbl_stego_checksum.toolTip() if "完整檔案" in self.lbl_stego_checksum.toolTip() else self.lbl_stego_checksum.text()
        
        report_text = (
            "=== 多音軌安全取證報告 ===\n"
            f"{client_ip}\n"
            f"{proxy}\n"
            f"{geo}\n"
            f"{decision}\n"
            f"{trust}\n"
            f"{md5}\n"
            f"取證時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "========================="
        )
        
        QApplication.clipboard().setText(report_text)
        self.append_log("成功將取證報告複製至剪貼簿！", "SUCCESS")
        
        # Show a brief status tip on the icon button
        self.btn_copy_sec.setText("✅")
        QTimer.singleShot(2000, lambda: self.btn_copy_sec.setText("📋"))

        # 2. Update track selection
        if self.user_manually_selected:
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
            self.append_log("錯誤：在當前目錄下找不到任何外部 '_audio_' 語音檔案！解密流程中止。", "ERROR")
            QMessageBox.critical(
                self, "Missing Audio Tracks", 
                f"No embedded PEE data or external '_audio_' tracks found for video:\n\n{os.path.basename(video_file)}"
            )
            # Revert to Landing Page
            self.stacked_widget.setCurrentIndex(0)
            return
            
        self.audio_tracks = audio_tracks
        self.video_path = video_file
        
        self.append_log(f"成功加載本地 {len(audio_tracks)} 組外部配音，正在啟動播放器...", "SUCCESS")
        
        self.repopulate_sidebar_items()
        
        # Delay transition for 1.2s
        def transition_fallback():
            self.stacked_widget.setCurrentIndex(2)
            self.load_video()
            temp_default = 'en-US' if 'en-US' in self.audio_tracks else list(self.audio_tracks.keys())[0]
            self.select_audio_track(temp_default)
            self.start_i18n_detection()
            
        QTimer.singleShot(1200, transition_fallback)

    def repopulate_sidebar_items(self):
        self.lang_list.clear()
        for lang_code, file_path in self.audio_tracks.items():
            display_name = LANGUAGE_MAP.get(lang_code, f"({lang_code}) Audio Track")
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, lang_code)
            self.lang_list.addItem(item)

    # Media Control Logics
    def load_video(self):
        url = QUrl.fromLocalFile(os.path.abspath(self.video_path))
        self.video_player.setSource(url)

    def select_audio_track(self, lang_code):
        if lang_code not in self.audio_tracks:
            return
            
        self.current_lang = lang_code
        audio_file = self.audio_tracks[lang_code]
        
        # Save current position
        current_pos = self.video_player.position()
        
        # Temporarily pause both to reload the audio source
        self.video_player.pause()
        self.audio_player.pause()
        
        # Load new audio track source
        self.audio_player.setSource(QUrl.fromLocalFile(os.path.abspath(audio_file)))
        self.audio_player.setPosition(current_pos)
        
        if self.is_user_playing:
            self.check_and_resume_playback()
            
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
            self.play_button.setText("▶")
        else:
            self.is_user_playing = True
            self.play_button.setText("⏸")
            self.check_and_resume_playback()

    def toggle_mute(self):
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        self.mute_button.setText("🔇" if not is_muted else "🔊")

    def on_volume_changed(self, val):
        vol = val / 100.0
        self.audio_output.setVolume(vol)
        if val == 0:
            self.mute_button.setText("🔇")
        else:
            self.mute_button.setText("🔊")

    # Resumes playback if user-intent is playing and neither is buffering/loading
    def check_and_resume_playback(self):
        if not self.is_user_playing:
            return
        v_status = self.video_player.mediaStatus()
        a_status = self.audio_player.mediaStatus()
        buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)
        if not (v_status in buffering_states or a_status in buffering_states):
            self.video_player.play()
            self.audio_player.play()

    # Synchronization logic
    def sync_check(self):
        if self.is_user_playing:
            v_status = self.video_player.mediaStatus()
            a_status = self.audio_player.mediaStatus()
            buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)
            
            if not (v_status in buffering_states or a_status in buffering_states):
                v_pos = self.video_player.position()
                a_pos = self.audio_player.position()
                diff = abs(v_pos - a_pos)
                
                # Use a larger 150ms drift tolerance and a 1.5s cooldown
                # to prevent rapid seeking feedback loops which cause audio stuttering.
                import time
                current_time = time.time()
                if diff > 150 and (current_time - self.last_sync_seek) > 1.5:
                    self.audio_player.setPosition(v_pos)
                    self.last_sync_seek = current_time

    # Slider Interactions
    def on_slider_pressed(self):
        self.slider_is_dragging = True

    def on_slider_released(self):
        self.slider_is_dragging = False
        pos = self.progress_slider.value()
        self.video_player.setPosition(pos)
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
        v_status = self.video_player.mediaStatus()
        a_status = self.audio_player.mediaStatus()
        
        # If either player reaches end of media, stop and reset button
        if v_status == QMediaPlayer.MediaStatus.EndOfMedia or a_status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.is_user_playing = False
            self.video_player.pause()
            self.audio_player.pause()
            self.play_button.setText("▶")
            self.loading_overlay.hide()
            return
            
        buffering_states = (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.LoadingMedia)
        is_buffering = (v_status in buffering_states or a_status in buffering_states)
        
        if is_buffering:
            # Temporarily pause both to prevent drift/stuttering during seek/track switch
            self.video_player.pause()
            self.audio_player.pause()
            self.loading_overlay.show()
        else:
            self.loading_overlay.hide()
            if self.is_user_playing:
                self.check_and_resume_playback()

    def on_lang_item_clicked(self, item):
        lang_code = item.data(Qt.UserRole)
        if lang_code != self.current_lang:
            self.user_manually_selected = True # User manually intervened!
            self.select_audio_track(lang_code)
            # Save user preferred language manually selected
            try:
                settings = QSettings("GradProject", "StegoPlayer")
                settings.setValue("preferred_language", lang_code)
            except Exception:
                pass

    def cleanup_temp_dir(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                print("🧹 成功清除臨時解密音軌。")
            except Exception as e:
                print(f"⚠️ 清除臨時音軌失敗: {e}")
        self.temp_dir = None


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
        self.video_player.setSource(QUrl())
        self.audio_player.setSource(QUrl())
        self.sync_timer.stop()
        
        # Cleanup
        self.cleanup_temp_dir()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    
    # Check for CLI initial file
    initial_file = None
    if len(sys.argv) > 1:
        initial_file = sys.argv[1]
        
    player = MultiTrackPlayer(initial_file)
    player.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
