import os
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QListWidget, QProgressBar,
    QFileDialog, QMessageBox, QFrame, QGroupBox, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont

# Import unified Stego Facade core
from stego_facade import encode_video_multi, estimate_capacity, get_payload_size, ALGORITHMS

class EmbeddingThread(QThread):
    progress_signal = Signal(int, int) # current_frame, total_frames
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, video_path, audio_paths, output_path, method="coltuc_pee"):
        super().__init__()
        self.video_path = video_path
        self.audio_paths = audio_paths
        self.output_path = output_path
        self.method = method

    def run(self):
        try:
            def progress_cb(current_frame, total_frames, current_bits, total_bits):
                self.progress_signal.emit(current_frame, total_frames)

            encode_video_multi(
                self.video_path,
                self.audio_paths,
                self.output_path,
                method=self.method,
                progress_callback=progress_cb
            )
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))

class StegoEmbedApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("醫療/鑑識級 - 雙演算法 (PEE vs 2D HS) 影音藏密封裝系統")
        self.resize(640, 720)

        self.video_path = ""
        self.audio_paths = []
        self.output_path = ""
        self.estimated_capacity = 0
        self.total_payload_size = 0
        self.selected_method = "coltuc_pee"

        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header title
        title_label = QLabel("🛡️ Video RDH Steganography Multi-Audio Packer")
        title_label.setObjectName("TitleLabel")
        layout.addWidget(title_label)

        # 0. Algorithm Selector Group
        algo_group = QGroupBox("⚙️ Steganography Algorithm Selection (藏密演算法選擇)")
        algo_layout = QVBoxLayout()

        self.combo_algo = QComboBox()
        self.combo_algo.addItem("🔷 Coltuc 2x2 Low-Distortion PEE (空間域預測誤差擴張 / 超高速、高容量)", "coltuc_pee")
        self.combo_algo.addItem("🟣 Zhang-Zeng-Ou 2D HS + Matrix Embedding (Signal Processing 2026 SOTA / 頂刊高 PSNR 畫質)", "zhang_zeng_ou_hs")
        self.combo_algo.currentIndexChanged.connect(self.on_algo_changed)
        algo_layout.addWidget(self.combo_algo)

        self.lbl_algo_desc = QLabel(ALGORITHMS["coltuc_pee"]["description"])
        self.lbl_algo_desc.setWordWrap(True)
        self.lbl_algo_desc.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
        algo_layout.addWidget(self.lbl_algo_desc)

        algo_group.setLayout(algo_layout)
        layout.addWidget(algo_group)

        # 1. Video Selection Group
        video_group = QGroupBox("🎬 Carrier Video Selection (載體影片選擇)")
        video_layout = QHBoxLayout()
        self.video_edit = QLineEdit()
        self.video_edit.setPlaceholderText("Select a video file (.mp4, .webm)...")
        self.video_edit.setReadOnly(True)
        video_layout.addWidget(self.video_edit)

        btn_browse_video = QPushButton("Browse")
        btn_browse_video.setObjectName("BrowseButton")
        btn_browse_video.clicked.connect(self.browse_video)
        video_layout.addWidget(btn_browse_video)
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # Capacity display
        self.lbl_capacity = QLabel("Estimated Carrier Capacity: Select a video file first")
        self.lbl_capacity.setObjectName("CapacityLabel")
        layout.addWidget(self.lbl_capacity)
        
        # 2. Audio Files Group
        audio_group = QGroupBox("🎵 Audio Tracks Selection (藏入音軌選擇)")
        audio_layout = QVBoxLayout()
        
        self.audio_list = QListWidget()
        self.audio_list.setObjectName("AudioList")
        audio_layout.addWidget(self.audio_list)
        
        btn_row = QHBoxLayout()
        btn_add_audio = QPushButton("➕ Add Tracks")
        btn_add_audio.setObjectName("AddButton")
        btn_add_audio.clicked.connect(self.add_audio_tracks)
        btn_row.addWidget(btn_add_audio)
        
        btn_clear_audio = QPushButton("🗑️ Clear List")
        btn_clear_audio.setObjectName("ClearButton")
        btn_clear_audio.clicked.connect(self.clear_audio_tracks)
        btn_row.addWidget(btn_clear_audio)
        
        audio_layout.addLayout(btn_row)
        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)
        
        # Payload Size and Capacity Match Label
        self.lbl_payload_info = QLabel("Total Audio Payload: 0.00 MB / 0.00 MB (0% used)")
        self.lbl_payload_info.setObjectName("PayloadInfoLabel")
        layout.addWidget(self.lbl_payload_info)
        
        # 3. Output Path Group
        output_group = QGroupBox("💾 Target Stego File Path (輸出影片儲存位置)")
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Specify output stego file (.mp4)...")
        self.output_edit.setReadOnly(True)
        output_layout.addWidget(self.output_edit)
        
        btn_browse_output = QPushButton("Save As")
        btn_browse_output.setObjectName("BrowseButton")
        btn_browse_output.clicked.connect(self.browse_output)
        output_layout.addWidget(btn_browse_output)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # 4. Progress and Start Group
        progress_group = QFrame()
        progress_group.setObjectName("ProgressFrame")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(10, 10, 10, 10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.lbl_status = QLabel("Status: System Ready")
        self.lbl_status.setObjectName("StatusLabel")
        progress_layout.addWidget(self.lbl_status)
        
        layout.addWidget(progress_group)
        
        self.btn_start = QPushButton("🚀 Start Stego Packaging")
        self.btn_start.setObjectName("StartButton")
        self.btn_start.clicked.connect(self.start_embedding)
        layout.addWidget(self.btn_start)

    def apply_stylesheet(self):
        stylesheet = """
            QMainWindow {
                background-color: #0F172A; /* Deep Slate 900 */
            }
            QWidget#CentralWidget {
                background-color: #0F172A;
            }
            QLabel#TitleLabel {
                color: #F8FAFC;
                font-size: 18px;
                font-weight: bold;
                padding-bottom: 5px;
                border-bottom: 2px solid #334155;
            }
            QGroupBox {
                color: #CBD5E1;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QLineEdit {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }
            QListWidget#AudioList {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #475569;
                border-radius: 6px;
                min-height: 100px;
            }
            QListWidget#AudioList::item {
                padding: 6px;
                color: #E2E8F0;
            }
            QPushButton {
                background-color: #334155;
                color: #F8FAFC;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:pressed {
                background-color: #1E293B;
            }
            QPushButton#StartButton {
                background-color: #4F46E5;
                font-size: 14px;
                padding: 12px;
                border-radius: 8px;
            }
            QPushButton#StartButton:hover {
                background-color: #6366F1;
            }
            QPushButton#StartButton:pressed {
                background-color: #4338CA;
            }
            QPushButton#AddButton {
                background-color: #059669;
            }
            QPushButton#AddButton:hover {
                background-color: #10B981;
            }
            QPushButton#ClearButton {
                background-color: #DC2626;
            }
            QPushButton#ClearButton:hover {
                background-color: #EF4444;
            }
            QProgressBar {
                background-color: #1E293B;
                color: white;
                border: 1px solid #334155;
                border-radius: 6px;
                text-align: center;
                height: 20px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #4F46E5;
                border-radius: 5px;
            }
            QLabel#CapacityLabel, QLabel#PayloadInfoLabel {
                color: #94A3B8;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#StatusLabel {
                color: #CBD5E1;
                font-size: 13px;
                font-style: italic;
            }
            QFrame#ProgressFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """
        self.setStyleSheet(stylesheet)

    def browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Carrier Video File", "", "Video Files (*.mp4 *.webm *.avi *.mkv)"
        )
        if file_path:
            self.video_path = file_path
            self.video_edit.setText(file_path)
            
            # Reset default output file
            video_dir = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            base_name, _ = os.path.splitext(filename)
            self.output_path = os.path.join(video_dir, f"{base_name}_stego.mp4")
            self.output_edit.setText(self.output_path)
            
            # Start capacity estimation in a thread so UI doesn't lag
            self.lbl_capacity.setText("Estimated Carrier Capacity: 🔍 Estimating video capacity...")
            self.lbl_capacity.setStyleSheet("color: #F59E0B;") # Yellow
            
            # Disable start button during estimation
            self.btn_start.setEnabled(False)
            
            # Run estimate in background QThread or Timer (since 10 frames check is very fast)
            QTimer.singleShot(100, self.estimate_capacity_async)

    def on_algo_changed(self, index):
        self.selected_method = self.combo_algo.currentData()
        self.lbl_algo_desc.setText(ALGORITHMS[self.selected_method]["description"])
        if self.video_path:
            self.lbl_capacity.setText("Estimated Carrier Capacity: 🔍 Re-estimating capacity...")
            self.lbl_capacity.setStyleSheet("color: #F59E0B;")
            QTimer.singleShot(100, self.estimate_capacity_async)

    def estimate_capacity_async(self):
        try:
            # Estimate capacity using selected algorithm method
            cap_bytes = estimate_capacity(self.video_path, method=self.selected_method)
            self.estimated_capacity = cap_bytes
            cap_mb = cap_bytes / (1024 * 1024)
            self.lbl_capacity.setText(f"Estimated Carrier Capacity: ✅ {cap_mb:.2f} MB ({cap_bytes} bytes)")
            self.lbl_capacity.setStyleSheet("color: #10B981;") # Green
            self.update_capacity_matching()
        except Exception as e:
            self.lbl_capacity.setText(f"Estimated Carrier Capacity: ❌ Estimate failed ({e})")
            self.lbl_capacity.setStyleSheet("color: #EF4444;") # Red
        finally:
            self.btn_start.setEnabled(True)

    def add_audio_tracks(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Audio Tracks to Hide", "", "Audio Files (*.mp3 *.m4a *.webm)"
        )
        if file_paths:
            for fp in file_paths:
                if fp not in self.audio_paths:
                    self.audio_paths.append(fp)
                    self.audio_list.addItem(os.path.basename(fp))
            self.calculate_payload_size()

    def clear_audio_tracks(self):
        self.audio_paths = []
        self.audio_list.clear()
        self.calculate_payload_size()

    def calculate_payload_size(self):
        self.total_payload_size = 0
        for fp in self.audio_paths:
            # Estimate payload bytes including zlib compression
            self.total_payload_size += get_payload_size(fp)
        self.update_capacity_matching()

    def update_capacity_matching(self):
        payload_mb = self.total_payload_size / (1024 * 1024)
        cap_mb = self.estimated_capacity / (1024 * 1024)
        
        percent = 0
        if self.estimated_capacity > 0:
            percent = (self.total_payload_size / self.estimated_capacity) * 100
            
        self.lbl_payload_info.setText(
            f"Total Audio Payload: {payload_mb:.2f} MB / {cap_mb:.2f} MB ({percent:.1f}% used)"
        )
        
        # Color match status
        if self.estimated_capacity == 0:
            self.lbl_payload_info.setStyleSheet("color: #94A3B8;")
        elif self.total_payload_size <= self.estimated_capacity:
            self.lbl_payload_info.setStyleSheet("color: #10B981;") # Green: Safe
        else:
            self.lbl_payload_info.setStyleSheet("color: #EF4444; font-weight: bold;") # Red: Overflow

    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Stego Video As", self.output_path, "MP4 Video (*.mp4)"
        )
        if file_path:
            self.output_path = file_path
            self.output_edit.setText(self.output_path)

    def start_embedding(self):
        if not self.video_path:
            QMessageBox.warning(self, "Warning", "Please select a carrier video first!")
            return
            
        if not self.audio_paths:
            QMessageBox.warning(self, "Warning", "Please add at least one audio track to hide!")
            return
            
        if not self.output_path:
            QMessageBox.warning(self, "Warning", "Please specify an output file path!")
            return
            
        if self.total_payload_size > self.estimated_capacity:
            QMessageBox.critical(
                self, "Error", 
                f"Audio payload ({self.total_payload_size / (1024*1024):.2f} MB) exceeds video carrier capacity ({self.estimated_capacity / (1024*1024):.2f} MB)!"
            )
            if reply == QMessageBox.No:
                return

        # Disable all inputs during operation
        self.set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Status: Starting stego packaging...")
        
        # Start worker thread
        self.thread = EmbeddingThread(self.video_path, self.audio_paths, self.output_path)
        self.thread.progress_signal.connect(self.on_progress)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.error_signal.connect(self.on_error)
        self.thread.start()

    def set_ui_enabled(self, enabled):
        self.btn_start.setEnabled(enabled)
        self.audio_list.setEnabled(enabled)
        # Find all buttons and line edits and toggle them
        for child in self.findChildren(QPushButton):
            if child != self.btn_start:
                child.setEnabled(enabled)

    def on_progress(self, current_frame, total_frames):
        if total_frames > 0:
            val = int((current_frame / total_frames) * 100)
            self.progress_bar.setValue(val)
            self.lbl_status.setText(f"Status: Packaging frames... [{current_frame} / {total_frames} frames] ({val}%)")

    def on_finished(self):
        self.progress_bar.setValue(100)
        self.lbl_status.setText("Status: Finished successfully!")
        QMessageBox.information(
            self, "Success", 
            f"🎉 Lossless stego video successfully generated!\n\nSaved at: {self.output_path}"
        )
        self.set_ui_enabled(True)

    def on_error(self, err_msg):
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Status: Error occurred")
        QMessageBox.critical(self, "Stego Packaging Failed", f"💥 Packaging failed:\n\n{err_msg}")
        self.set_ui_enabled(True)

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = StegoEmbedApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
