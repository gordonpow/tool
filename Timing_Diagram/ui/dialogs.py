from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QPushButton, QColorDialog, QHBoxLayout, QSpinBox
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal, Qt

class BusValueDialog(QDialog):
    changed = pyqtSignal(str, object, int, int) # value, color, start, end

    def __init__(self, current_value, start_cycle, total_cycles, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Bus/State")
        self.selected_color = None
        
        layout = QVBoxLayout(self)
        
        # Value Input
        layout.addWidget(QLabel("Value / Name:"))
        self.input = QLineEdit(current_value)
        self.input.textChanged.connect(self.emit_change)
        layout.addWidget(self.input)

        # Color Input (Palette)
        layout.addWidget(QLabel("Color:"))
        color_layout = QHBoxLayout()
        self.color_btn = QPushButton("Select Color")
        self.color_btn.clicked.connect(self.pick_color)
        color_layout.addWidget(self.color_btn)
        
        self.color_preview = QLabel("   ")
        self.color_preview.setStyleSheet("background-color: transparent; border: 1px solid #555;")
        self.color_preview.setFixedWidth(30)
        color_layout.addWidget(self.color_preview)
        layout.addLayout(color_layout)

        # Duration
        layout.addWidget(QLabel("Duration (Cycles):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, total_cycles)
        self.duration_spin.setValue(1)
        layout.addWidget(self.duration_spin)

        # Range / Duration
        layout.addWidget(QLabel("Range (Start Cycle - End Cycle):"))
        range_layout = QHBoxLayout()
        
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, total_cycles - 1)
        self.start_spin.setValue(start_cycle)
        range_layout.addWidget(self.start_spin)
        
        range_layout.addWidget(QLabel("to"))
        
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, total_cycles - 1)
        self.end_spin.setValue(start_cycle) # Default to single cycle
        range_layout.addWidget(self.end_spin)
        
        layout.addLayout(range_layout)
        
        # Connections for Auto-Update
        self.duration_spin.valueChanged.connect(self.on_duration_changed)
        self.start_spin.valueChanged.connect(self.on_start_changed)
        self.end_spin.valueChanged.connect(self.on_end_changed)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def on_duration_changed(self, val):
        self.end_spin.blockSignals(True)
        new_end = self.start_spin.value() + val - 1
        self.end_spin.setValue(new_end)
        self.end_spin.blockSignals(False)
        self.emit_change()

    def on_start_changed(self, val):
        # Update end based on duration
        self.end_spin.blockSignals(True)
        new_end = val + self.duration_spin.value() - 1
        self.end_spin.setValue(new_end)
        self.end_spin.blockSignals(False)
        self.emit_change()
        
    def on_end_changed(self, val):
        # Update duration based on new end
        self.duration_spin.blockSignals(True)
        start = self.start_spin.value()
        if val < start:
             val = start
             self.end_spin.setValue(start)
             
        new_dur = val - start + 1
        self.duration_spin.setValue(new_dur)
        self.duration_spin.blockSignals(False)
        self.emit_change()
        
    def pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.selected_color = color.name()
            self.color_preview.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid #fff;")
            self.emit_change()

    def emit_change(self):
        self.changed.emit(self.get_value(), self.get_color(), self.start_spin.value(), self.end_spin.value())

    def get_value(self):
        return self.input.text()

    def get_color(self):
        return self.selected_color

    def get_range(self):
        return self.start_spin.value(), self.end_spin.value()

from PyQt6.QtWidgets import QComboBox, QFileDialog, QFormLayout, QScrollArea
from PyQt6.QtGui import QPixmap

class ExportDialog(QDialog):
    def __init__(self, canvas, initial_settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Waveform Image")
        self.resize(1000, 700)
        self.canvas = canvas
        
        settings = initial_settings or {}
        
        layout = QVBoxLayout(self)
        
        # Splitter or Side-by-Side
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        form = QFormLayout()
        
        # Background Color
        self.bg_color = QColor(settings.get('bg_color', "#1e1e1e"))
        self.bg_btn = QPushButton("Select Color")
        self.bg_btn.clicked.connect(lambda: self.pick_color('bg'))
        self.bg_preview = QLabel("   ")
        self.bg_preview.setFixedWidth(40)
        self.update_color_preview(self.bg_preview, self.bg_color)
        
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(self.bg_btn)
        bg_layout.addWidget(self.bg_preview)
        form.addRow("Background Color:", bg_layout)
        
        # Font Color
        self.font_color = QColor(settings.get('font_color', "#e0e0e0"))
        self.font_btn = QPushButton("Select Color")
        self.font_btn.clicked.connect(lambda: self.pick_color('font'))
        self.font_preview = QLabel("   ")
        self.font_preview.setFixedWidth(40)
        self.update_color_preview(self.font_preview, self.font_color)
        
        font_layout = QHBoxLayout()
        font_layout.addWidget(self.font_btn)
        font_layout.addWidget(self.font_preview)
        form.addRow("Font Color:", font_layout)
        
        # Font Size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 72)
        self.font_size_spin.setValue(int(settings.get('font_size', 10)))
        self.font_size_spin.valueChanged.connect(self.refresh_preview)
        form.addRow("Font Size:", self.font_size_spin)
        
        # Format
        self.format_combo = QComboBox()
        formats = ["PNG", "JPG", "BMP"]
        self.format_combo.addItems(formats)
        current_fmt = settings.get('format', 'PNG')
        if current_fmt in formats:
             self.format_combo.setCurrentText(current_fmt)
        form.addRow("Format:", self.format_combo)

        # Filename
        self.filename_edit = QLineEdit(settings.get('filename', 'waveform'))
        form.addRow("Filename:", self.filename_edit)
        
        # Output Folder
        self.path_edit = QLineEdit(settings.get('path', ''))
        self.path_btn = QPushButton("Browse...")
        self.path_btn.clicked.connect(self.browse_folder)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.path_btn)
        form.addRow("Output Folder:", path_layout)
        
        left_layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        left_layout.addWidget(buttons)
        left_layout.addStretch()
        
        main_layout.addLayout(left_layout, 1)
        
        # PREVIEW AREA
        preview_group = QVBoxLayout()
        preview_group.addWidget(QLabel("Preview:"))
        
        self.scroll_area = QScrollArea()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True) # This allows label to center
        preview_group.addWidget(self.scroll_area)
        
        main_layout.addLayout(preview_group, 3) # Give more space to preview
        
        layout.addLayout(main_layout)
        
        self.cached_img = None
        # Initial Preview
        self.refresh_preview()
        
    def pick_color(self, target):
        initial = self.bg_color if target == 'bg' else self.font_color
        color = QColorDialog.getColor(initial, self)
        if color.isValid():
            if target == 'bg':
                self.bg_color = color
                self.update_color_preview(self.bg_preview, color)
            else:
                self.font_color = color
                self.update_color_preview(self.font_preview, color)
            self.refresh_preview()

    def update_color_preview(self, label, color):
        label.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #555;")
    
    def refresh_preview(self):
        settings = self.get_settings()
        # Render Full Image
        self.cached_img = self.canvas.render_to_image_object(settings)
        if self.cached_img:
            pixmap = QPixmap.fromImage(self.cached_img)
            self.image_label.setPixmap(pixmap)
            self.image_label.adjustSize()
            
            # Auto-resize dialog to fit image + controls
            # Estimate Control Panel Width ~ 320px + Margins
            controls_width = 340
            margins_w = 60
            margins_h = 100 # Title bar + buttons + preview header
            
            target_w = controls_width + pixmap.width() + margins_w
            target_h = max(600, pixmap.height() + margins_h)
            
            # Constrain to Screen Size (90%)
            screen = self.screen().availableGeometry()
            max_w = int(screen.width() * 0.9)
            max_h = int(screen.height() * 0.9)
            
            final_w = min(target_w, max_w)
            final_h = min(target_h, max_h)
            
            self.resize(final_w, final_h)
        
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)
            
    def get_settings(self):
        return {
            'bg_color': self.bg_color,
            'font_color': self.font_color,
            'font_size': self.font_size_spin.value(),
            'format': self.format_combo.currentText(),
            'filename': self.filename_edit.text(),
            'path': self.path_edit.text()
        }
