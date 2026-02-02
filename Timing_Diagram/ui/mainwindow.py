from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QListWidget, QPushButton, QLabel, QSplitter, 
                               QFrame, QInputDialog, QListWidgetItem, QComboBox, QLineEdit, QSpinBox, 
                               QColorDialog, QCheckBox, QScrollArea, QFileDialog, QMessageBox)
import json
import colorsys
import random
from PyQt6.QtGui import QColor, QPalette, QAction, QKeySequence, QCloseEvent
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTime, QTimer
from core.models import Project, Signal, SignalType
from ui.editor_panel import BusEditorPanel
from ui.canvas import WaveformCanvas
from ui.data_generator_dialog import DataGeneratorDialog
from ui.import_dialog import ImportDialog
from core.undo_manager import UndoManager

class PropertyNameLineEdit(QLineEdit):
    delete_pressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)

class SignalListItemWidget(QWidget):
    def __init__(self, signal, on_pin_toggle):
        super().__init__()
        self.signal = signal
        self.on_pin_toggle = on_pin_toggle
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        self.name_label = QLabel(f"{signal.name} [{signal.type.name}]")
        self.name_label.setStyleSheet("color: #e0e0e0; background-color: transparent;")
        layout.addWidget(self.name_label)
        
        layout.addStretch()
        
        self.pin_btn = QPushButton()
        self.pin_btn.setFixedSize(30, 30)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(signal.pinned)
        self.update_icon()
        self.pin_btn.clicked.connect(self.handle_click)
        
        layout.addWidget(self.pin_btn)
        
    def update_icon(self):
        self.pin_btn.setText("📌")
        
        # High Contrast / Solid Background Style
        if self.signal.pinned:
            # Active: Neon Cyan Background, Black Text
            self.pin_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #00E5FF; 
                    border: 1px solid #00E5FF; 
                    color: black; 
                    font-size: 18px; 
                    border-radius: 4px;
                }
                QPushButton:hover { 
                    background-color: #66FFFF; 
                }
            """)
        else:
            # Inactive: Solid Dark Grey Background (Visible), White Text
            self.pin_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #454555; 
                    border: 1px solid #666666; 
                    color: #FFFFFF; 
                    font-size: 18px; 
                    border-radius: 4px;
                }
                QPushButton:hover { 
                    background-color: #555566; 
                    border: 1px solid #888888;
                }
            """)

    def handle_click(self):
        self.signal.pinned = self.pin_btn.isChecked()
        self.on_pin_toggle()
        self.update_icon()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IC Waveform Generator - Antigravity")
        self.resize(1300, 800) # Slightly wider
        
        # State Tracking
        self.current_project_path = None
        self.is_dirty = False
        self.update_title()
        
        
        # Data
        self.project = Project()
        self.undo_manager = UndoManager(self.project)
        
        # Load Pinned Signals
        loaded = self.load_pinned_signals()
        
        if not loaded:
            # Add some demo signals if nothing pinned
            self.project.add_signal(Signal(name="i_clk", type=SignalType.CLK, color="#00ff00"))
            self.project.add_signal(Signal(name="i_rst", type=SignalType.INPUT, color="#ff5555"))
            self.project.add_signal(Signal(name="ADDR", type=SignalType.BUS_DATA, color="#00d2ff"))
            self.project.add_signal(Signal(name="DATA_RD", type=SignalType.BUS_DATA, color="#ffff00"))
        
        # Settings Store
        from PyQt6.QtCore import QSettings
        self.settings = QSettings("Antigravity", "TimingDiagram")

        # Auto Save
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.perform_auto_save)
        self.init_auto_save()

        # Init UI
        self.init_ui()

    def load_pinned_signals(self):
        from PyQt6.QtCore import QSettings
        import json
        settings = QSettings("Antigravity", "TimingDiagram")
        data = settings.value("pinned_signals", "[]")
        
        try:
            signals_data = json.loads(data)
            if not signals_data:
                return False
                
            for s_data in signals_data:
                try:
                    s = Signal.from_dict(s_data)
                    self.project.add_signal(s)
                except Exception as e:
                    print(f"Error loading signal: {e}")
            return True
        except:
             return False

    def save_pinned_signals(self):
        from PyQt6.QtCore import QSettings
        import json
        
        pinned_list = [s.to_dict() for s in self.project.signals if s.pinned]
        
        settings = QSettings("Antigravity", "TimingDiagram")
        settings.setValue("pinned_signals", json.dumps(pinned_list))

    def init_ui(self):
        # Menu Bar
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("File")
        
        load_action = file_menu.addAction("Load Project")
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self.load_project_file)
        
        save_proj_action = file_menu.addAction("Save Project")
        save_proj_action.setShortcut(QKeySequence("Ctrl+S"))
        save_proj_action.triggered.connect(self.save_project)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        setting_menu = menubar.addMenu("Setting") # User requested 'setting' (lowercase handling?) "名称為setting" -> "Setting"
        
        pref_action = setting_menu.addAction("Preferences")
        pref_action.triggered.connect(self.open_settings_dialog)
        
        # Unsaved Badge (Top Right)
        # Standard Window Title doesn't support color, so we use a corner widget
        self.unsaved_badge = QLabel(" UNSAVED ")
        self.unsaved_badge.setStyleSheet("background-color: #ff0000; color: white; font-weight: bold; border-radius: 2px;")
        self.unsaved_badge.setVisible(False)
        menubar.setCornerWidget(self.unsaved_badge, Qt.Corner.TopRightCorner)
        
        # Shortcut for Save (Now in File Menu, but this provides global backup if menu not visible)
        # self.addAction(save_proj_action) # QAction added to menu is already active
        
        # Edit Menu
        edit_menu = menubar.addMenu("Edit")
        
        copy_action = edit_menu.addAction("Copy")
        copy_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_action.triggered.connect(lambda: self.canvas.copy_selection())
        
        paste_action = edit_menu.addAction("Paste")
        paste_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_action.triggered.connect(lambda: self.canvas.paste_selection())

        edit_menu.addSeparator()
        
        undo_action = edit_menu.addAction("Undo")
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.triggered.connect(self.perform_undo)
        
        redo_action = edit_menu.addAction("Redo")
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.triggered.connect(self.perform_redo)
        
        # Tools Menu
        tools_menu = menubar.addMenu("Tools")
        
        gen_action = tools_menu.addAction("Data Generator")
        gen_action.triggered.connect(self.open_data_generator)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        
        tools_menu.addSeparator()
        
        import_hdl_action = tools_menu.addAction("Import from HDL...")
        import_hdl_action.triggered.connect(self.import_hdl_signals)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter to resize panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # --- Left Panel: Controls ---
        left_panel = QFrame()
        left_panel.setMinimumWidth(220) # Ensure visibility of list and pin icons
        left_layout = QVBoxLayout(left_panel)
        
        left_layout.addWidget(QLabel("Signals"))
        
        # Save / Load (Moved to File Menu)
        # sl_layout = QHBoxLayout()
        # btn_save = QPushButton("Save Project")
        # btn_save.clicked.connect(self.save_project)
        # sl_layout.addWidget(btn_save)
        
        # btn_load = QPushButton("Load Project")
        # btn_load.clicked.connect(self.load_project_file)
        # sl_layout.addWidget(btn_load)
        # left_layout.addLayout(sl_layout)
        
        self.signal_list = QListWidget()
        self.signal_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.signal_list.model().rowsMoved.connect(self.on_list_reordered)
        # CHANGED: itemClicked -> currentRowChanged to ensure Programmatic selection (via add_signal) also triggers it
        self.signal_list.currentRowChanged.connect(self.on_signal_selected)
        left_layout.addWidget(self.signal_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self.add_signal)
        btn_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("Del")
        btn_remove.clicked.connect(self.remove_signal)
        btn_layout.addWidget(btn_remove)
        left_layout.addLayout(btn_layout)

        # --- Property Editor ---
        left_layout.addSpacing(10)
        left_layout.addWidget(QLabel("Properties"))
        
        # We wrap properties in a scroll area if it gets too long
        prop_scroll = QScrollArea()
        prop_scroll.setWidgetResizable(True)
        prop_scroll.setFrameShape(QFrame.Shape.NoFrame)
        prop_widget = QWidget()
        self.prop_layout = QVBoxLayout(prop_widget)
        self.prop_layout.setContentsMargins(0, 5, 0, 5)
        
        # Name
        self.prop_layout.addWidget(QLabel("Name:"))
        self.name_edit = PropertyNameLineEdit()
        self.name_edit.textChanged.connect(self.on_name_changed)
        self.name_edit.delete_pressed.connect(self.remove_signal)
        self.prop_layout.addWidget(self.name_edit)
        
        # Type
        self.prop_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        for t in SignalType:
            display_name = t.value
            self.type_combo.addItem(display_name, t)
        self.type_combo.currentIndexChanged.connect(self.update_signal_properties)
        self.prop_layout.addWidget(self.type_combo)
        
        # BUS DATA Config
        self.bus_config_container = QWidget()
        bus_layout = QVBoxLayout(self.bus_config_container)
        bus_layout.setContentsMargins(0, 0, 0, 0)
        self.bus_bits_spin = QSpinBox()
        self.bus_bits_spin.setRange(1, 128)
        self.bus_bits_spin.valueChanged.connect(self.update_signal_properties)
        bus_row1 = QHBoxLayout(); bus_row1.addWidget(QLabel("Bits:")); bus_row1.addWidget(self.bus_bits_spin)
        bus_layout.addLayout(bus_row1)
        self.bus_input_base_combo = QComboBox(); self.bus_input_base_combo.addItems(["Bin (2)", "Oct (8)", "Dec (10)", "Hex (16)"]); self.bus_input_base_combo.currentIndexChanged.connect(self.update_signal_properties)
        bus_row2 = QHBoxLayout(); bus_row2.addWidget(QLabel("Raw Base:")); bus_row2.addWidget(self.bus_input_base_combo)
        bus_layout.addLayout(bus_row2)
        self.bus_display_base_combo = QComboBox(); self.bus_display_base_combo.addItems(["Bin (2)", "Oct (8)", "Dec (10)", "Hex (16)"]); self.bus_display_base_combo.currentIndexChanged.connect(self.update_signal_properties)
        bus_row3 = QHBoxLayout(); bus_row3.addWidget(QLabel("Disp Base:")); bus_row3.addWidget(self.bus_display_base_combo)
        bus_layout.addLayout(bus_row3)
        self.prop_layout.addWidget(self.bus_config_container)
        self.bus_config_container.setVisible(False)

        # Clock Config
        self.clk_edge_combo = QComboBox(); self.clk_edge_combo.addItems(["Rising Edge (Pos)", "Falling Edge (Neg)"]); self.clk_edge_combo.currentIndexChanged.connect(self.update_signal_properties); self.clk_edge_combo.setVisible(False)
        self.prop_layout.addWidget(self.clk_edge_combo)
        self.clk_mod_container = QWidget(); mod_layout = QHBoxLayout(self.clk_mod_container); mod_layout.setContentsMargins(0,0,0,0); mod_layout.addWidget(QLabel("Mod:")); self.clk_mod_spin = QSpinBox(); self.clk_mod_spin.setRange(1, 100); self.clk_mod_spin.valueChanged.connect(self.update_signal_properties); mod_layout.addWidget(self.clk_mod_spin)
        self.prop_layout.addWidget(self.clk_mod_container); self.clk_mod_container.setVisible(False)
        
        # Color
        self.prop_layout.addWidget(QLabel("Color:"))
        color_row = QHBoxLayout(); self.color_btn = QPushButton("Select"); self.color_btn.clicked.connect(self.pick_signal_color); color_row.addWidget(self.color_btn); self.color_preview = QLabel("   "); self.color_preview.setFixedWidth(40); self.color_preview.setStyleSheet("border: 1px solid #555; background-color: transparent;"); color_row.addWidget(self.color_preview)
        self.prop_layout.addLayout(color_row)
        
        # --- NEW: Integrated Range Editor (Formerly on the far right) ---
        self.editor_panel = BusEditorPanel()
        self.editor_panel.setVisible(True) # Force visibility
        
        # Defer signal connections that depend on self.canvas until after canvas is created
        
        self.prop_layout.addSpacing(15)
        self.prop_layout.addWidget(QLabel("<b>Selection Properties</b>"))
        self.prop_layout.addWidget(self.editor_panel)
        
        prop_scroll.setWidget(prop_widget)
        left_layout.addWidget(prop_scroll)

        
        splitter.addWidget(left_panel)
            
        # --- Center Panel: Canvas ---
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        
        # Toolbar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Cycles:"))
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(5, 100)
        self.cycles_spin.setValue(self.project.total_cycles)
        self.cycles_spin.valueChanged.connect(self.update_global_settings)
        top_bar.addWidget(self.cycles_spin)

        top_bar.addSpacing(15)
        top_bar.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(5, 200)
        self.width_spin.setValue(self.project.cycle_width)
        self.width_spin.valueChanged.connect(self.update_global_settings)
        top_bar.addWidget(self.width_spin)
        
        top_bar.addStretch()
        
        self.btn_export = QPushButton("Export Image")
        self.btn_export.clicked.connect(self.export_image)
        top_bar.addWidget(self.btn_export)
        
        left_layout.addStretch()
        right_layout.addLayout(top_bar)
        
        self.canvas = WaveformCanvas(self.project)
        self.canvas.data_changed.connect(self.canvas.update)
        self.canvas.data_changed.connect(lambda: self.set_dirty(True))
        # Also refresh list if structure changed (reordering in canvas)
        self.canvas.structure_changed.connect(self.refresh_list)
        
        # Now connect Editor Signals (dependencies on canvas are now safe)
        self.editor_panel.before_change.connect(self.undo_manager.request_snapshot)
        self.editor_panel.changed.connect(self.undo_manager.commit_snapshot)
        self.editor_panel.changed.connect(self.on_editor_changed)
        self.editor_panel.navigation_requested.connect(self.canvas.move_selection)
        self.editor_panel.copy_requested.connect(self.canvas.copy_selection)
        self.editor_panel.paste_requested.connect(self.canvas.paste_selection)
        self.editor_panel.undo_requested.connect(self.perform_undo)
        self.editor_panel.redo_requested.connect(self.perform_redo)
        self.editor_panel.mode_combo.currentIndexChanged.connect(self.on_editor_mode_changed)

        # Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.setWidgetResizable(True) # Resize to content
        
        # Sticky Header Sync: Repaint when scrolling
        self.scroll_area.verticalScrollBar().valueChanged.connect(lambda: self.canvas.update())
        
        right_layout.addWidget(self.scroll_area)
        
        # Connect Selection
        self.canvas.bus_selected.connect(self.on_bus_selected)
        self.canvas.region_updated.connect(self.on_region_updated)
        self.canvas.cycles_changed.connect(self.on_cycles_changed)
        self.canvas.zoom_changed.connect(self.width_spin.setValue)
        self.canvas.signal_clicked.connect(self.signal_list.setCurrentRow)
        
        splitter.addWidget(right_panel)
        
        # Distribute space: Left (300px), Center (flexible)
        splitter.setSizes([300, 1000])

        self.refresh_list()

    def keyPressEvent(self, event):
        focus_widget = self.focusWidget()

        # 1. Check if we are currently editing text (QLineEdit focus)
        if isinstance(focus_widget, QLineEdit):
            if event.key() == Qt.Key.Key_Delete:
                 # Fallthrough to delete logic (don't return, let it hit section 3)
                 pass
            else:
                # Let the QLineEdit handle its own input/backspace
                super().keyPressEvent(event)
                return

        # 2. Canvas Deletion Logic
        if self.canvas.hasFocus():
             if event.key() == Qt.Key.Key_Delete:
                 # ... existing canvas delete logic ...
                 if self.canvas.selected_regions:
                     for (sig_idx, start, end) in self.canvas.selected_regions:
                         if 0 <= sig_idx < len(self.project.signals):
                             sig = self.project.signals[sig_idx]
                             if sig.type in [SignalType.BUS_DATA, SignalType.BUS_STATE]:
                                 for t in range(start, end + 1):
                                     sig.set_value_at(t, 'X')
                     
                     self.canvas.data_changed.emit()
                     self.canvas.update()
                     self.set_dirty(True)
                     return

        # 3. List Item Interaction (Delete & Type-to-Rename)
        curr = self.signal_list.currentRow()
        if curr >= 0:
            # 3a. Deletion
            if event.key() == Qt.Key.Key_Delete:
                 self.remove_signal()
                 return

            # 3b. Type-to-Rename (Auto-focus input)
            # Check if list has focus OR if we are bubbling up from somewhere
            # If text is printable and not a special key
            text = event.text()
            if text and text.isprintable() and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
                # Get widget
                item = self.signal_list.item(curr)
                if item:
                    # Redirect to Property Panel Logic
                    self.name_edit.setFocus()
                    self.name_edit.setText(text)
                    return

        # Forward other keys
        super().keyPressEvent(event)

    def on_bus_selected(self, sig_idx, cycle_idx):
        if 0 <= sig_idx < len(self.project.signals):
            # Sync Signal List Selection
            self.signal_list.blockSignals(True)
            self.signal_list.setCurrentRow(sig_idx)
            self.signal_list.blockSignals(False)
            
            # Sync Properties Panel (Force refresh)
            self.on_signal_selected(sig_idx)
            
            signal = self.project.signals[sig_idx]
            self.editor_panel.load_target(signal, cycle_idx, self.project.total_cycles)
            
            # Sync mode state
            self.on_editor_mode_changed(self.editor_panel.mode_combo.currentIndex())
            
            # REMOVED: Do not force-set canvas selection here. 
            # Canvas is the source of truth for selection (especially multi-select).
            # The canvas has already highlighted the region(s) before emitting this signal.
            
            # Update Canvas Selection Highlight from Editor's detected range
            # start = self.editor_panel.start_spin.value()
            # end = self.editor_panel.end_spin.value()
            # self.canvas.selected_region = (sig_idx, start, end)
            
            self.safe_canvas_update()

    def on_region_updated(self, sig_idx, start, end):
        # Called when dragging on canvas to extend/reduce duration
        # Sync the Editor Panel spinners
        self.editor_panel.blockSignals(True)
        self.editor_panel.start_spin.blockSignals(True)
        self.editor_panel.end_spin.blockSignals(True)
        self.editor_panel.duration_spin.blockSignals(True)
        
        self.editor_panel.start_spin.setValue(start)
        self.editor_panel.end_spin.setValue(end)
        self.editor_panel.duration_spin.setValue(end - start + 1)
        
        # Sync initial block state so subsequent edits (like Insert) calculate correctly from the new "Base"
        self.editor_panel.initial_block_start = start
        self.editor_panel.initial_block_end = end
        
        self.editor_panel.blockSignals(False)
        self.editor_panel.start_spin.blockSignals(False)
        self.editor_panel.end_spin.blockSignals(False)
        self.editor_panel.duration_spin.blockSignals(False)
        
        # Update Canvas Selection Highlight
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.selected_region = (sig_idx, start, end)
        self.set_dirty(True)

    def on_cycles_changed(self, new_total):
        self.cycles_spin.blockSignals(True)
        self.cycles_spin.setValue(new_total)
        self.cycles_spin.blockSignals(False)

    def on_editor_mode_changed(self, index):
        mode_text = self.editor_panel.mode_combo.currentText()
        is_insert = (mode_text == "Insert")
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.is_insert_mode = is_insert

    def on_editor_changed(self, val, color, start, end):
        # Update logic from editor
        # The logic is practically same as dialog but live
        # We need to know WHICH signal we are editing. EditorPanel stores current_signal.
        
        signal = self.editor_panel.current_signal
        if signal and hasattr(self.editor_panel, 'original_values'):
             # Restore clean state first to handle reducing range
             signal.values = list(self.editor_panel.original_values)
             
             # Convert empty input back to 'X' for the model
             model_val = val if val.strip() else 'X'
             
             mode = self.editor_panel.mode_combo.currentText()
             
             if mode == "Impossible_Safety_Check": # Placeholder for diff
                 pass
             elif mode == "Insert":
                 # Insert Mode: Splicing behavior
                 # We need to know the ORIGINAL block we are modifying to replace it efficiently?
                 # Actually, we can just use the editor's Start/End relative to the *Original* values?
                 
                 # 1. Identify where we are modifying. 
                 # In Insert Mode, 'start' is the insertion point/beginning of block.
                 # 'end' is derived from duration.
                 # We want to replace the [initial_block_start:initial_block_end] from 'original_values'
                 # with [model_val] * current_duration
                 # and keep the suffixes shifted.
                 
                 if hasattr(self.editor_panel, 'initial_block_start') and hasattr(self.editor_panel, 'initial_block_end'):
                     req_duration = end - start + 1
                     old_start = self.editor_panel.initial_block_start
                     old_end = self.editor_panel.initial_block_end
                     
                     # Construct new values list
                     # Prefix: [0 ... old_start-1]
                     # New Block: [model_val] * duration
                     # Suffix: [old_end+1 ... ] (Shifted)
                     
                     prefix = signal.values[:old_start]
                     suffix = signal.values[old_end+1:]
                     new_block = [model_val] * req_duration
                     
                     # Reassemble (This auto-shifts the suffix)
                     signal.values = prefix + new_block + suffix
                     
                     # If we exceeded total cycles, update project setting? 
                     # Or just clamp? Usually Insert Mode implies expanding the timeline if needed.
                     # For now, let's auto-expand project cycles if needed.
                     if len(signal.values) > self.project.total_cycles:
                         self.project.total_cycles = len(signal.values)
                         self.cycles_spin.blockSignals(True)
                         self.cycles_spin.setValue(self.project.total_cycles)
                         self.cycles_spin.blockSignals(False)
                 
             else: # Overwrite Mode (Default)
                 for t in range(start, end + 1):
                    # Auto-expand if writing beyond current length
                    if t >= self.project.total_cycles:
                        self.project.total_cycles = t + 1
                        self.cycles_spin.blockSignals(True)
                        self.cycles_spin.setValue(self.project.total_cycles)
                        self.cycles_spin.blockSignals(False)
                        
                    signal.set_value_at(t, model_val)
                 
                 # Handling "Shortening" of the original block:
                 # If we are editing an existing block and we shorten it, the remaining part 
                 # of the ORIGINAL block should be cleared to 'X' (or Default) so it doesn't 
                 # visually merge with the previous value.
                 if hasattr(self.editor_panel, 'initial_block_start') and hasattr(self.editor_panel, 'initial_block_end'):
                     orig_start = self.editor_panel.initial_block_start
                     orig_end = self.editor_panel.initial_block_end
                     
                     # Clear Head (if new start is after original start)
                     if start > orig_start:
                         for t in range(orig_start, start):
                             if t < self.project.total_cycles:
                                 signal.set_value_at(t, 'X')
                                 
                     # Clear Tail (if new end is before original end)
                     if end < orig_end:
                         for t in range(end + 1, orig_end + 1):
                             if t < self.project.total_cycles:
                                 signal.set_value_at(t, 'X')
             
             if color:
                 signal.value_colors[model_val] = color
            
             # Update selection highlight to match new range
             # Find signal index?
             if hasattr(self, 'canvas') and self.canvas:
                 if signal in self.project.signals:
                     sig_idx = self.project.signals.index(signal)
                     self.canvas.selected_region = (sig_idx, start, end)
                     self.safe_canvas_update()
             self.set_dirty(True)

    def refresh_list(self):
        # Save selection
        current_row = self.signal_list.currentRow()
        
        # Block signals to prevent feedback loops if needed, though rowsMoved is user interaction
        self.signal_list.blockSignals(True)
        self.signal_list.clear()
        for s in self.project.signals:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s) # Store object
            
            # Custom Widget
            widget = SignalListItemWidget(s, self.save_pinned_signals)
            item.setSizeHint(QSize(0, 36)) # Fixed height to ensure visibility
            
            self.signal_list.addItem(item)
            self.signal_list.setItemWidget(item, widget)
            
        # Restore selection
        if current_row >= 0 and current_row < self.signal_list.count():
             self.signal_list.setCurrentRow(current_row)
             
        self.signal_list.blockSignals(False)

    def on_signal_selected(self, row=None):
        # Changed: Accept 'row' (int) from currentRowChanged, or none.
        # Fallback if None passed (shouldn't happen with connect)
        if row is None or isinstance(row, QListWidgetItem): # legacy safety
             row = self.signal_list.currentRow()
             
        if row >= 0:
            signal = self.project.signals[row]
            # Avoid loop: block signals on name edit if it's just being updated from selection
            self.name_edit.blockSignals(True)
            self.name_edit.setText(signal.name)
            self.name_edit.blockSignals(False)
            
            self.color_preview.setStyleSheet(f"background-color: {signal.color}; border: 1px solid #e0e0e0;")
            
            # Set Combo
            idx = self.type_combo.findData(signal.type)
            if idx >= 0:
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(idx)
                self.type_combo.blockSignals(False)
            
            # Clock Edge Props
            self.clk_edge_combo.blockSignals(True)
            self.clk_edge_combo.setCurrentIndex(0 if signal.clk_rising_edge else 1)
            self.clk_edge_combo.setVisible(signal.type == SignalType.CLK)
            self.clk_edge_combo.blockSignals(False)
            
            # Clock Mod props
            self.clk_mod_spin.blockSignals(True)
            self.clk_mod_spin.setValue(signal.clk_mod)
            self.clk_mod_container.setVisible(signal.type == SignalType.CLK)
            self.clk_mod_spin.blockSignals(False)
            
            # Bus Props
            is_bus_data = (signal.type == SignalType.BUS_DATA)
            self.bus_config_container.setVisible(is_bus_data)
            if is_bus_data:
                self.bus_bits_spin.blockSignals(True)
                self.bus_bits_spin.setValue(signal.bits)
                self.bus_bits_spin.blockSignals(False)
                
                self.bus_input_base_combo.blockSignals(True)
                base_to_idx = {2:0, 8:1, 10:2, 16:3}
                self.bus_input_base_combo.setCurrentIndex(base_to_idx.get(signal.input_base, 2))
                self.bus_input_base_combo.blockSignals(False)
                
                self.bus_display_base_combo.blockSignals(True)
                self.bus_display_base_combo.setCurrentIndex(base_to_idx.get(signal.display_base, 2))
                self.bus_display_base_combo.blockSignals(False)
            
            # Auto-Focus and Select Name for quick editing
            self.name_edit.setFocus()
            self.name_edit.selectAll()


    def pick_signal_color(self):
        row = self.signal_list.currentRow()
        if row >= 0:
            signal = self.project.signals[row]
            initial = QColor(signal.color)
            color = QColorDialog.getColor(initial, self, "Select Signal Color")
            
            if color.isValid():
                self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #e0e0e0;")
                self.update_signal_properties()

    def safe_canvas_update(self):
        """Helper to update canvas safely, avoiding 'RuntimeError: wrapped C/C++ object has been deleted'"""
        if hasattr(self, 'canvas') and self.canvas:
            try:
                self.canvas.update()
            except RuntimeError:
                pass

    def update_signal_properties(self):
        row = self.signal_list.currentRow()
        if row >= 0:
            signal = self.project.signals[row]
            signal.name = self.name_edit.text()
            
            # Get color from preview style or internal state? 
            # Easier to parse the style string or store a temp variable. 
            # Let's extract from style sheet for now as it is the source of truth for the UI state
            style = self.color_preview.styleSheet()
            if "background-color:" in style:
                # Extract color code roughly
                # format: background-color: #code; ...
                try:
                    c = style.split("background-color:")[1].split(";")[0].strip()
                    signal.color = c
                except:
                    pass
            
            signal.type = self.type_combo.currentData()
            
            # Save Clock Edge
            if signal.type == SignalType.CLK:
                # Index 0 = Rising (True), Index 1 = Falling (False)
                signal.clk_rising_edge = (self.clk_edge_combo.currentIndex() == 0)
                signal.clk_mod = self.clk_mod_spin.value()
            
            # Save Bus Props
            if signal.type == SignalType.BUS_DATA:
                signal.bits = self.bus_bits_spin.value()
                idx_to_base = {0:2, 1:8, 2:10, 3:16}
                signal.input_base = idx_to_base.get(self.bus_input_base_combo.currentIndex(), 16)
                signal.display_base = idx_to_base.get(self.bus_display_base_combo.currentIndex(), 16)

            # Update Visibility
            self.clk_edge_combo.setVisible(signal.type == SignalType.CLK)
            self.clk_mod_container.setVisible(signal.type == SignalType.CLK)
            self.bus_config_container.setVisible(signal.type == SignalType.BUS_DATA)

            self.save_pinned_signals()

            self.refresh_list()
            self.safe_canvas_update()
            self.set_dirty(True)

    def on_list_reordered(self):
        # Reconstruct project.signals based on list order
        new_signals = []
        for i in range(self.signal_list.count()):
            item = self.signal_list.item(i)
            signal = item.data(Qt.ItemDataRole.UserRole)
            if signal:
                new_signals.append(signal)
        
        self.project.signals = new_signals
        self.safe_canvas_update()
        self.set_dirty(True)

    def update_global_settings(self):
        self.project.total_cycles = self.cycles_spin.value()
        self.project.cycle_width = self.width_spin.value()
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.update_dimensions()
        self.safe_canvas_update()
        self.set_dirty(True)

    def generate_distinct_color(self):
        existing_colors = [s.color for s in self.project.signals]
        
        best_color = "#00d2ff" 
        max_min_dist = -1
        
        # Try 50 random candidates
        for _ in range(50):
            # HSV: Random Hue, High Saturation, High Value (Bright/Vibrant)
            h = random.random()
            s = 0.6 + random.random() * 0.4 # 0.6-1.0
            v = 0.8 + random.random() * 0.2 # 0.8-1.0
            
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            r, g, b = int(r*255), int(g*255), int(b*255)
            hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b)
            
            if not existing_colors:
                return hex_color
            
            # Find distance to nearest existing color
            min_dist = float('inf')
            for ec in existing_colors:
                try:
                    ec_clean = ec.lstrip('#')
                    if len(ec_clean) == 6:
                        er, eg, eb = tuple(int(ec_clean[i:i+2], 16) for i in (0, 2, 4))
                        dist = ((r-er)**2 + (g-eg)**2 + (b-eb)**2)**0.5
                        if dist < min_dist:
                            min_dist = dist
                except:
                    pass
            
            if min_dist > max_min_dist:
                max_min_dist = min_dist
                best_color = hex_color
            
            # Accept if distinct enough
            if min_dist > 100: 
                return best_color
                
        return best_color

    def add_signal(self):
        self.undo_manager.push_snapshot()
        new_color = self.generate_distinct_color()
        self.project.add_signal(Signal(name="New Signal", color=new_color))
        self.refresh_list()
        self.canvas.update_dimensions()
        self.canvas.update()
        self.set_dirty(True)
        self.signal_list.setCurrentRow(len(self.project.signals) - 1)

    def remove_signal(self):
        row = self.signal_list.currentRow()
        if row >= 0:
            self.undo_manager.push_snapshot()
            self.project.remove_signal(row)
            self.save_pinned_signals()
            self.refresh_list()
            self.canvas.update_dimensions()
            self.canvas.update()
            self.set_dirty(True)

    def on_name_changed(self, text):
        row = self.signal_list.currentRow()
        if row >= 0:
            signal = self.project.signals[row]
            signal.name = text
            
            # Update List Item Widget directly
            item = self.signal_list.item(row)
            if item:
                widget = self.signal_list.itemWidget(item)
                if isinstance(widget, SignalListItemWidget):
                    widget.name_label.setText(f"{signal.name} [{signal.type.name}]")
            
            # Update Canvas
            self.canvas.update()
            self.set_dirty(True)

    def export_image(self):
        from ui.dialogs import ExportDialog
        from PyQt6.QtCore import QSettings
        
        settings_store = QSettings("Antigravity", "TimingDiagram")
        
        # Load saved settings
        initial_settings = {
            'path': settings_store.value("export_path", ""),
            'bg_color': settings_store.value("export_bg_color", "#1e1e1e"),
            'font_color': settings_store.value("export_font_color", "#e0e0e0"),
            'font_size': int(settings_store.value("export_font_size", 10)),
            'format': settings_store.value("export_format", "PNG"),
            'filename': settings_store.value("export_filename", "waveform")
        }
        
        dlg = ExportDialog(self.canvas, initial_settings, self)
        if dlg.exec():
            settings = dlg.get_settings()
            
            output_dir = settings['path']
            if not output_dir:
                 return
            
            # Save settings for next time
            settings_store.setValue("export_path", output_dir)
            settings_store.setValue("export_bg_color", settings['bg_color'].name())
            settings_store.setValue("export_font_color", settings['font_color'].name())
            settings_store.setValue("export_font_size", settings['font_size'])
            settings_store.setValue("export_format", settings['format'])
            settings_store.setValue("export_filename", settings['filename'])
            
            # Render and Save
            img = self.canvas.render_to_image_object(settings)
            
            path = output_dir
            fmt = settings['format']
            filename = settings.get('filename', 'waveform')
            
            # Construct full path
            import os
            full_path = os.path.join(path, f"{filename}.{fmt.lower()}")
            
            img.save(full_path)
            QMessageBox.information(self, "Success", f"Image saved to:\n{full_path}")



    def init_auto_save(self):
        enabled = self.settings.value("auto_save_enabled", False, type=bool)
        interval = int(self.settings.value("auto_save_interval", 5))
        
        if enabled:
            self.auto_save_timer.start(interval * 60 * 1000)
        else:
            self.auto_save_timer.stop()
            
    def open_settings_dialog(self):
        from ui.dialogs import SettingsDialog
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            settings = dlg.get_settings()
            
            # Save
            self.settings.setValue("auto_save_enabled", settings['enabled'])
            self.settings.setValue("auto_save_interval", settings['interval'])
            
            # Apply
            self.init_auto_save()
            
    def perform_auto_save(self):
        # Requirement: "Auto save is when there is a save path... if not yet saved, do not save"
        if not self.current_project_path:
            return
            
        try:
            data = self.project.to_dict()
            with open(self.current_project_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            # Auto-save implies data is safe, so we can clear dirty flag?
            # User requirement: "Automatically save to set path".
            self.set_dirty(False)
            self.statusBar().showMessage(f"Auto-saved at {QTime.currentTime().toString('HH:mm:ss')}", 3000)
        except Exception as e:
            print(f"Auto-save failed: {e}")

    def save_project(self):
        # 1. Ctrl+S logic
        if self.current_project_path:
            # Overwrite
            try:
                data = self.project.to_dict()
                with open(self.current_project_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                self.set_dirty(False)
                self.statusBar().showMessage("Project Saved", 2000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project: {e}")
        else:
            # Save As
            self.save_project_as()

    def save_project_as(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json)")
        if not file_path:
            return
            
        try:
            data = self.project.to_dict()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            
            self.current_project_path = file_path
            self.set_dirty(False)
            QMessageBox.information(self, "Success", "Project saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project: {e}")

    # Renamed/Deprecated save_project_file to maintain compatibility if called elsewhere, 
    # but mapped to save_project_as for the button if that's what we want?
    # I replaced the button call to save_project, so this is replaced fully.

    def load_project_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "JSON Files (*.json)")
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Reconstruct Project
            self.project = Project.from_dict(data)
            
            # Rebind Canvas
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.project = self.project
                self.canvas.update_dimensions()
            
            # Refresh UI
            self.refresh_list()
            self.safe_canvas_update()
            
            # Reset editors
            self.editor_panel.reset()
            
            self.refresh_global_controls()
            
            # Update State
            self.current_project_path = file_path
            self.set_dirty(False)

            QMessageBox.information(self, "Success", "Project loaded successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project: {e}")
            
    def set_dirty(self, dirty):
        self.is_dirty = dirty
        self.update_title()
        
    def update_title(self):
        base_title = "IC Waveform Generator - Antigravity"
        if self.is_dirty:
            self.setWindowTitle(base_title + " (Unsaved)")
            if hasattr(self, 'unsaved_badge'):
                self.unsaved_badge.setVisible(True)
        else:
            self.setWindowTitle(base_title)
            if hasattr(self, 'unsaved_badge'):
                self.unsaved_badge.setVisible(False)

    def closeEvent(self, event: QCloseEvent):
        if self.is_dirty:
            msg = QMessageBox(self)
            msg.setWindowTitle("Unsaved Changes")
            msg.setText("This file has not been saved.")
            msg.setInformativeText("Do you want to save your changes?")
            msg.setIcon(QMessageBox.Icon.Warning)
            
            # Custom buttons to match user request "save", "no save", "cancel"
            btn_save = msg.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
            btn_no_save = msg.addButton("No Save", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton(QMessageBox.StandardButton.Cancel)
            
            msg.exec()
            
            clicked = msg.clickedButton()
            
            if clicked == btn_save:
                # Try to save
                self.save_project()
                # If save failed or was cancelled (in Save As path), check is_dirty
                if self.is_dirty: 
                    # Save was cancelled or failed
                    event.ignore()
                else:
                    event.accept()
            elif clicked == btn_no_save:
                # No Save -> Close
                event.accept()
            else:
                # Cancel -> Do not close
                event.ignore()
        else:
            event.accept()

    def refresh_global_controls(self):
        # Trigger updates if possible, or just rely on user interaction
        pass

    def open_data_generator(self):
        # Determine initial context from selection
        sig_idx = None
        start = 0
        end = self.project.total_cycles - 1
        
        if hasattr(self, 'canvas') and self.canvas and self.canvas.selected_regions:
            # Use the last selected region
            s_idx, s_start, s_end = self.canvas.selected_regions[-1]
            
            # Verify if this is a Bus Signal
            if 0 <= s_idx < len(self.project.signals):
                if self.project.signals[s_idx].type in [SignalType.BUS_DATA, SignalType.BUS_STATE]:
                    sig_idx = s_idx
                    start = s_start
                    end = s_end
        
        dlg = DataGeneratorDialog(self.project, self, initial_signal_index=sig_idx, initial_start=start, initial_end=end)
        self.undo_manager.push_snapshot() # Capture before DataGen applies changes (it applies directly to referenced project? No, usually dialog applies on OK)
        # Wait, DataGeneratorDialog takes 'project'. Does it modify in-place?
        # If so, push BEFORE exec is safer, but redundant on cancel.
        # If it modifies ON ACCEPT (inside exec loop or after), we need to know.
        # Usually strict dialogs modify on accept. 
        # If I push here, safe assuming Dialog *already modified*? No.
        # Checking: DataGeneratorDialog logic.
        # If logic (dlg.exec) returns True, changes likely applied? 
        # OR logic is inside separate method? 
        # If Logic applied inside `accept()`, then state is ALREADY CHANGED here.
        # Then snapshot is TOO LATE.
        # I must push BEFORE `exec` to be safe, or check dialog implementation.
        # For correctness with unknown dialog: Push -> Exec -> if Cancel -> Pop? (UndoManager doesn't have pop_snapshot).
        # I will push before Exec. If cancel, one extra undo step (No-op). Acceptable.
        
        if dlg.exec():
            self.safe_canvas_update()
            self.set_dirty(True)
            self.refresh_global_controls() # If cycles expanded

    def perform_undo(self):
        if self.undo_manager.undo():
            self.refresh_ui_after_restore()
            self.set_dirty(True)

    def perform_redo(self):
        if self.undo_manager.redo():
            self.refresh_ui_after_restore()
            self.set_dirty(True)
            
    def refresh_ui_after_restore(self):
        # 1. Refresh Signal List
        self.refresh_list()
        
        # 2. Update Cycles Control
        self.cycles_spin.blockSignals(True)
        self.cycles_spin.setValue(self.project.total_cycles)
        self.cycles_spin.blockSignals(False)
        
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.cycles_changed.emit(self.project.total_cycles)
            self.safe_canvas_update()
            
            # 4. Editor Panel (Clear)
            self.canvas.selected_regions = []
            self.canvas.bus_selected.emit(-1, -1)
        
        self.editor_panel.reset()

    def import_hdl_signals(self):
        dialog = ImportDialog(self)
        if dialog.exec():
            new_signals = dialog.get_imported_signals()
            if new_signals:
                self.undo_manager.push_snapshot()
                for sig in new_signals:
                    # Assign a distinct color for each imported signal
                    sig.color = self.generate_distinct_color()
                    self.project.add_signal(sig)
                self.refresh_list()
                self.safe_canvas_update()
                self.set_dirty(True)
                QMessageBox.information(self, "Import Successful", f"Imported {len(new_signals)} signals.")

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
