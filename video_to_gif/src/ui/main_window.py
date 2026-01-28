from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QListWidget, QGroupBox, QFormLayout,
                             QSpinBox, QDoubleSpinBox, QSplitter, QFileDialog, QListWidgetItem, QCheckBox, QProgressBar, QMessageBox, QComboBox)
from PyQt6.QtCore import Qt
from ui.widgets.drop_zone import DropZone
from ui.widgets.preview_player import PreviewPlayer
from ui.widgets.preview_player import PreviewPlayer
from core.converter import Converter
import os
import subprocess

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TECH GIF CONVERTER v1.0")
        self.resize(1100, 900)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # --- Left Panel: Controls & List ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)

        # Header
        header_label = QLabel("MISSION CONTROL")
        header_label.setObjectName("header")
        left_layout.addWidget(header_label)

        # Drop Zone
        self.drop_zone = DropZone()
        self.drop_zone.setFixedHeight(100)
        self.drop_zone.files_dropped.connect(self.handle_files_dropped)
        left_layout.addWidget(self.drop_zone)

        # Output Folder Selection
        output_layout = QHBoxLayout()
        self.output_label = QLabel("Output: Source Folder")
        self.output_label.setStyleSheet("""
            background-color: #222; 
            color: #00f3ff; 
            font-size: 13px; 
            padding: 8px; 
            border: 1px solid #444; 
            border-radius: 4px;
        """)
        self.output_label.setWordWrap(True)
        output_layout.addWidget(self.output_label, stretch=1)
        
        self.browse_btn = QPushButton("📂")
        self.browse_btn.setToolTip("Select Output Folder")
        self.browse_btn.setFixedSize(40, 36)
        self.browse_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; 
                background-color: #333; 
                border: 1px solid #555;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #444;
                border-color: #00f3ff;
            }
        """)
        self.browse_btn.clicked.connect(self.select_output_folder)
        output_layout.addWidget(self.browse_btn)
        left_layout.addLayout(output_layout)
        self.custom_output_dir = None

        # List
        self.video_list = QListWidget()
        self.video_list.itemClicked.connect(self.handle_video_selected)
        self.video_list.itemChanged.connect(self.on_item_changed)
        left_layout.addWidget(self.video_list)
        
        # List Controls (Select All / Deselect All)
        list_controls_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("SELECT ALL")
        self.select_all_btn.clicked.connect(self.select_all_videos)
        self.select_all_btn.setFixedHeight(30)
        self.select_all_btn.setStyleSheet("font-size: 10px; padding: 2px;")
        
        self.deselect_all_btn = QPushButton("DESELECT ALL")
        self.deselect_all_btn.clicked.connect(self.deselect_all_videos)
        self.deselect_all_btn.setFixedHeight(30)
        self.deselect_all_btn.setStyleSheet("font-size: 10px; padding: 2px;")
        
        self.deselect_all_btn.setStyleSheet("font-size: 10px; padding: 2px;")
        
        self.delete_btn = QPushButton("DELETE")
        self.delete_btn.clicked.connect(self.delete_selected_videos)
        self.delete_btn.setFixedHeight(30)
        self.delete_btn.setStyleSheet("font-size: 10px; padding: 2px; color: red;")

        list_controls_layout.addWidget(self.select_all_btn)
        list_controls_layout.addWidget(self.deselect_all_btn)
        list_controls_layout.addWidget(self.delete_btn)
        left_layout.addLayout(list_controls_layout)

        # Settings Group
        settings_group = QGroupBox("PARAMETERS")
        settings_layout = QFormLayout()
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(10)
        self.fps_spin.setSuffix(" FPS")
        settings_layout.addRow("Frame Rate:", self.fps_spin)

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 10.0)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setSuffix(" x")
        settings_layout.addRow("Speed:", self.speed_spin)
        
        # New: Length (Trim) - Visualized as Start/End inputs for now, 
        # ideally this would be a range slider, but inputs are safer to start.
        self.start_time_spin = QDoubleSpinBox()
        self.start_time_spin.setRange(0, 9999)
        self.start_time_spin.setSuffix(" sec")
        settings_layout.addRow("Start Time:", self.start_time_spin)
        
        self.end_time_spin = QDoubleSpinBox()
        self.end_time_spin.setRange(0, 9999)
        self.end_time_spin.setSuffix(" sec")
        settings_layout.addRow("End Time:", self.end_time_spin)

        self.ignore_trim_check = QCheckBox("Ignore Trim (Batch Mode)")
        self.ignore_trim_check.setToolTip("If checked, converts the full length of the video, ignoring Start/End times.")
        settings_layout.addRow(self.ignore_trim_check)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["Original", "240p", "360p", "480p", "540p", "720p", "1080p", "1440p", "2k", "4k"])
        self.resolution_combo.setCurrentText("720p") 
        self.resolution_combo.setToolTip("Select output resolution height/width approximation.")
        settings_layout.addRow("Resolution:", self.resolution_combo)

        settings_group.setLayout(settings_layout)
        left_layout.addWidget(settings_group)

        # Actions
        btn_layout = QHBoxLayout()
        
        self.convert_btn = QPushButton("INITIATE CONVERSION")
        self.convert_btn.setFixedHeight(50)
        self.convert_btn.clicked.connect(self.start_conversion)
        btn_layout.addWidget(self.convert_btn)
        
        self.stop_btn = QPushButton("FORCE STOP")
        self.stop_btn.setFixedHeight(50)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff3333;
                color: #fff;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #ff6666;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #555;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_conversion)
        btn_layout.addWidget(self.stop_btn)
        
        left_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.progress_bar)

        # --- Right Panel: Preview ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        preview_header = QLabel("VISUAL FEED")
        preview_header.setObjectName("header")
        right_layout.addWidget(preview_header)

        # Video Player
        self.preview_player = PreviewPlayer()
        right_layout.addWidget(self.preview_player, stretch=1)

        # Splitter to allow resizing
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)
    
    def handle_video_selected(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return
            
        self.selected_video = file_path # Store selected
        self.preview_player.load_video(file_path, play_immediately=True)
        
        # Determine duration for default end time
        info = Converter.get_video_info(file_path)
        if info:
            self.end_time_spin.setValue(info['duration'])
            
    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.custom_output_dir = folder
            self.output_label.setText(f"Output: .../{os.path.basename(folder)}")
        else:
            self.custom_output_dir = None
            self.output_label.setText("Output: Source Folder")

    def handle_files_dropped(self, files):
        for file in files:
            # Display only basename
            display_name = os.path.basename(file)
            item = QListWidgetItem(display_name)
            # Store full path in UserRole
            item.setData(Qt.ItemDataRole.UserRole, file)
            
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.video_list.addItem(item)
            # Select first if none selected
            if self.video_list.count() == 1:
                 self.handle_video_selected(self.video_list.item(0))

    def select_all_videos(self):
        for i in range(self.video_list.count()):
            item = self.video_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)

    def on_item_changed(self, item):
        # Auto-check logic: if > 1 items are checked, enable Ignore Trim
        checked_count = 0
        for i in range(self.video_list.count()):
            if self.video_list.item(i).checkState() == Qt.CheckState.Checked:
                checked_count += 1
        
        if checked_count >= 2:
            if not self.ignore_trim_check.isChecked():
                self.ignore_trim_check.setChecked(True)

    def deselect_all_videos(self):
        for i in range(self.video_list.count()):
            item = self.video_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)

    def delete_selected_videos(self):
        # Identify items to remove: Checked items OR currently selected item
        items_to_remove = []
        for i in range(self.video_list.count()):
            item = self.video_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                items_to_remove.append(item)
        
        # If no checked items, check for currently selected
        if not items_to_remove:
            selected_items = self.video_list.selectedItems()
            if selected_items:
                items_to_remove.extend(selected_items)
        
        # Remove them
        for item in items_to_remove:
            row = self.video_list.row(item)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.video_list.takeItem(row)
            # Also clear selection if it matches
            if hasattr(self, 'selected_video') and self.selected_video == file_path:
                 self.selected_video = None
                 self.preview_player.stop() # Stop playback if removed
        
        header = self.findChild(QLabel, "header")
        if header: header.setText(f"REMOVED {len(items_to_remove)} FILES")

    def start_conversion(self):
        # Validation: Check if output dir is selected
        if not self.custom_output_dir:
            QMessageBox.warning(self, "Validation Error", "Please select an output folder before converting.")
            return

        # Identify targets: Checked items OR currently selected item
        targets = []
        
        # 1. Check for checked items
        for i in range(self.video_list.count()):
            item = self.video_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                targets.append(item.data(Qt.ItemDataRole.UserRole))
        
        # 2. If no checked items, use current selection
        if not targets and hasattr(self, 'selected_video') and self.selected_video:
            targets.append(self.selected_video)
            
        if not targets:
           header = self.findChild(QLabel, "header")
           if header: header.setText("SELECT VIDEO(S)")
           return
           
        # Determine resolution
        res_text = self.resolution_combo.currentText()
        resize_val = None
        
        if "k" in res_text:
            if "2k" in res_text:
                resize_val = 2560
            elif "4k" in res_text:
                resize_val = 3840
        elif "p" in res_text:
            try:
                # Extract number before 'p'
                resize_val = int(res_text.replace("p", ""))
            except:
                pass

        settings = {
            'fps': self.fps_spin.value(),
            'speed': self.speed_spin.value(),
            'start_time': self.start_time_spin.value(),
            'end_time': self.end_time_spin.value(),
            'output_dir': self.custom_output_dir,
            'resize': resize_val
        }
        
        if self.ignore_trim_check.isChecked():
             settings['start_time'] = 0
             settings['end_time'] = float('inf')
        
        self.progress_bar.setValue(0)
        self.progress_bar.setValue(0)
        self.convert_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.convert_btn.setText(f"CONVERTING {len(targets)} FILES...")
        
        from core.worker import ConversionWorker
        self.worker = ConversionWorker(targets, settings)
        self.worker.finished_signal.connect(self.on_conversion_finished)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.item_status_signal.connect(self.update_item_status)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_item_status(self, file_path, status):
        # Update specific item in the list
        for i in range(self.video_list.count()):
            item = self.video_list.item(i)
            # Compare file paths
            item_path = item.data(Qt.ItemDataRole.UserRole)
            if item_path == file_path:
                # Keep basename, append status
                base_name = os.path.basename(file_path)
                item.setText(f"{base_name} - {status}")
                break

    def on_conversion_finished(self, success, message):
        self.convert_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.convert_btn.setText("INITIATE CONVERSION")
        self.progress_bar.setValue(100 if success else 0)
        header = self.findChild(QLabel, "header")
        if success:
             if header: header.setText("BATCH COMPLETE")
             QMessageBox.information(self, "Success", message)
        else:
             if header: header.setText("ERROR")
             QMessageBox.critical(self, "Error", message)

    def stop_conversion(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            # Force kill ffmpeg processes
            try:
                subprocess.run("taskkill /F /IM ffmpeg.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Error killing ffmpeg: {e}")
            
            self.update_log("Status: Conversion Stopped by User")
            self.convert_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.convert_btn.setText("INITIATE CONVERSION")
            self.progress_bar.setValue(0)
            
    def update_log(self, message):
         print(message) # Placeholder if no log widget

