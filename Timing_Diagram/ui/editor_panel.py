from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, 
                               QPushButton, QColorDialog, QHBoxLayout, QSpinBox, QFrame, QComboBox)
from PyQt6.QtGui import QColor, QKeyEvent, QKeySequence # Added QKeySequence
from PyQt6.QtCore import pyqtSignal, Qt, QEvent # Added Qt, QEvent

class NavigableLineEdit(QLineEdit):
    # Signal to request navigation (dx, dy)
    navigation_requested = pyqtSignal(int, int)
    copy_requested = pyqtSignal()
    navigation_requested = pyqtSignal(int, int)
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    edit_started = pyqtSignal() # New signal
    
    def focusInEvent(self, event):
        self.edit_started.emit()
        super().focusInEvent(event)

    
    def keyPressEvent(self, event: QKeyEvent):
        # Ignore Ctrl+C and Ctrl+V so they propagate (or trigger global shortcuts)
        if event.matches(QKeySequence.StandardKey.Copy) or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C):
            self.copy_requested.emit()
            return
        if event.matches(QKeySequence.StandardKey.Paste) or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V):
            self.paste_requested.emit()
            return

        if event.matches(QKeySequence.StandardKey.Undo) or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Z):
            self.undo_requested.emit()
            self.clearFocus() # Unfocus input
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo) or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Y):
            self.redo_requested.emit()
            self.clearFocus() # Unfocus input
            event.accept()
            return

        if event.key() == Qt.Key.Key_Left:
            self.navigation_requested.emit(-1, 0)
        elif event.key() == Qt.Key.Key_Right:
            self.navigation_requested.emit(1, 0)
        elif event.key() == Qt.Key.Key_Up:
            self.navigation_requested.emit(0, -1)
        elif event.key() == Qt.Key.Key_Down:
            self.navigation_requested.emit(0, 1)
        else:
            super().keyPressEvent(event)

class BusEditorPanel(QFrame):
    # signal: value, color, start, end
    changed = pyqtSignal(str, object, int, int) 
    # Forward navigation request from input
    navigation_requested = pyqtSignal(int, int) 
    
    # Forward Copy/Paste
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    before_change = pyqtSignal() # For Undo


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setMaximumWidth(300)
        self.setVisible(True) # Always visible
        
        self.current_signal = None
        self.current_cycle_idx = 0
        self.total_cycles = 100
        self.selected_color = None # Initialize to avoid Attribute Error
        
        self.init_ui()
        # Default state: Disabled until selection
        self.setEnabled(False)
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        layout.addWidget(QLabel("<b>Bus/State Editor</b>"))


        # Value Input
        layout.addWidget(QLabel("Value / Name:"))
        self.input = NavigableLineEdit()
        self.input.navigation_requested.connect(self.navigation_requested) # Forward signal
        self.input.copy_requested.connect(self.copy_requested) # Forward
        self.input.paste_requested.connect(self.paste_requested) # Forward
        self.input.undo_requested.connect(self.undo_requested)
        self.input.redo_requested.connect(self.redo_requested)
        self.input.edit_started.connect(self.before_change) # Snapshot on Focus
        
        self.input.setPlaceholderText("Enter Value...") # Placeholder
        self.input.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.input)
        
        # Validation Warning Label
        self.warning_label = QLabel("Please enter a value to enable settings.")
        self.warning_label.setStyleSheet("color: #ff5555; font-style: italic; font-size: 10px;")
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        # Color Input (Palette)
        layout.addWidget(QLabel("Color:"))
        color_layout = QHBoxLayout()
        self.color_btn = QPushButton("Select Color")
        self.color_btn.clicked.connect(self.pick_color)
        self.color_btn.setEnabled(False) # Default disabled
        color_layout.addWidget(self.color_btn)
        
        self.color_preview = QLabel("   ")
        self.color_preview.setStyleSheet("background-color: transparent; border: 1px solid #555;")
        self.color_preview.setFixedWidth(30)
        color_layout.addWidget(self.color_preview)
        layout.addLayout(color_layout)

        # Duration
        self.dur_label = QLabel("Duration (Cycles):")
        layout.addWidget(self.dur_label)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 9999)
        self.duration_spin.valueChanged.connect(self.on_duration_changed)
        layout.addWidget(self.duration_spin)

        # Range
        self.range_label = QLabel("Range:")
        layout.addWidget(self.range_label)
        range_layout = QHBoxLayout()
        
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 9999)
        self.start_spin.valueChanged.connect(self.on_start_changed)
        range_layout.addWidget(self.start_spin)
        
        range_layout.addWidget(QLabel("to"))
        
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 9999)
        self.end_spin.valueChanged.connect(self.on_end_changed)
        range_layout.addWidget(self.end_spin)
        
        range_layout.addWidget(self.end_spin)
        
        layout.addLayout(range_layout)
        
        # Install Event Filters for Undo Snapshot on Focus
        self.duration_spin.installEventFilter(self)
        self.start_spin.installEventFilter(self)
        self.end_spin.installEventFilter(self)

        
        # Mode Selection
        self.mode_label = QLabel("Edit Mode:")
        layout.addWidget(self.mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Overwrite", "Insert"])
        # self.mode_combo.currentIndexChanged.connect(self.emit_change) # Removed: Mode switch shouldn't trigger data change
        layout.addWidget(self.mode_combo)
        
        layout.addStretch()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.FocusIn:
            if source in [self.duration_spin, self.start_spin, self.end_spin]:
                 self.before_change.emit()
        return super().eventFilter(source, event)

    def on_text_changed(self, text):
        is_valid = bool(text.strip())
        
        # Enable/Disable Controls
        self.duration_spin.setEnabled(is_valid)
        self.start_spin.setEnabled(is_valid)
        self.end_spin.setEnabled(is_valid)
        self.color_btn.setEnabled(is_valid)
        self.mode_combo.setEnabled(is_valid)
        
        # Show/Hide Warning
        self.warning_label.setVisible(not is_valid)
        
        # Styling for emphasis (Optional, but Qt disabled state is usually gray enough)
        # We can dim labels if we want, but standard disabled state is usually sufficient.
        
        if self.current_signal:
             self.emit_change()


    def load_target(self, signal, cycle_idx, total_cycles):
        self.setEnabled(True) # Enable panel
        self.blockSignals(True)
        self.input.blockSignals(True)
        self.duration_spin.blockSignals(True)
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.mode_combo.blockSignals(True)
        
        self.current_signal = signal
        # Snapshot for live preview restoration
        self.original_values = list(signal.values)
        
        self.current_cycle_idx = cycle_idx
        self.total_cycles = total_cycles
        
        # Update Limits
        self.start_spin.setRange(0, 9999) # Allow expansion
        self.end_spin.setRange(0, 9999)
        self.duration_spin.setRange(1, 9999)

        # Get current state
        val = signal.get_value_at(cycle_idx)
        
        # UI Requirement: Hide 'X' in the input box (show blank), 
        # but keep it as 'X' in the model/waveform.
        display_val = "" if val == 'X' else val
        self.input.setText(display_val)
        
        # Color initialization first
        self.selected_color = None
        if val in signal.value_colors:
            self.selected_color = signal.value_colors[val]
            self.color_preview.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid #fff;")
        else:
            self.color_preview.setStyleSheet("background-color: transparent; border: 1px solid #555;")
            
        # Check text validity for controls (Now safe to call emit_change internally if needed)
        # Passing display_val means if it is "", controls are disabled -> Correct.
        self.on_text_changed(display_val)

        # Detect Range (consecutive identical values)
        start = cycle_idx
        end = cycle_idx
        
        # Scan backward
        for t in range(cycle_idx, -1, -1):
            if signal.get_value_at(t) == val:
                start = t
            else:
                break
        
        # Scan forward
        for t in range(cycle_idx, total_cycles):
            if signal.get_value_at(t) == val:
                end = t
            else:
                break
        
        # Heuristic: 
        # 1. If value is 'X' (Unknown/Default), default to single cycle selection 
        #    to make it easy to start defining a new block.
        # 2. If it's a defined value, select the whole block range.
        if val == 'X':
            start = cycle_idx
            end = cycle_idx
            
        # Store initial block range for Insert Mode calculations
        self.initial_block_start = start
        self.initial_block_end = end

        self.start_spin.setValue(start)
        self.end_spin.setValue(end)
        self.duration_spin.setValue(end - start + 1)
        
        self.blockSignals(False)
        self.input.blockSignals(False)
        self.duration_spin.blockSignals(False)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        self.mode_combo.blockSignals(False)
        
        # Auto-focus input for direct typing
        self.input.setFocus()
        self.input.selectAll()

    def on_duration_changed(self, val):
        self.end_spin.blockSignals(True)
        new_end = self.start_spin.value() + val - 1
        if new_end >= self.total_cycles:
             new_end = self.total_cycles - 1
        self.end_spin.setValue(new_end)
        self.end_spin.blockSignals(False)
        self.emit_change()

    def on_start_changed(self, val):
        self.end_spin.blockSignals(True)
        new_end = val + self.duration_spin.value() - 1
        if new_end >= self.total_cycles:
             new_end = self.total_cycles - 1
        self.end_spin.setValue(new_end)
        self.end_spin.blockSignals(False)
        self.emit_change()
        
    def on_end_changed(self, val):
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
        self.before_change.emit() # Snapshot before color dialog logic
        color = QColorDialog.getColor()
        if color.isValid():
            self.selected_color = color.name()
            self.color_preview.setStyleSheet(f"background-color: {self.selected_color}; border: 1px solid #fff;")
            self.emit_change()

    def emit_change(self):
        if self.current_signal:
             self.changed.emit(self.input.text(), self.selected_color, self.start_spin.value(), self.end_spin.value())

    def reset(self):
        self.current_signal = None
        self.current_cycle_idx = 0
        self.input.setText("")
        self.color_preview.setStyleSheet("background-color: transparent; border: 1px solid #555;")
        self.setEnabled(False)
