from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QListWidget, QPushButton, QLabel, QSplitter, 
                               QFrame, QInputDialog, QListWidgetItem, QComboBox, QLineEdit, QSpinBox, 
                               QColorDialog, QCheckBox, QScrollArea, QFileDialog, QMessageBox)
import json
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import Qt, QSize
from core.models import Project, Signal, SignalType
from ui.editor_panel import BusEditorPanel
from ui.canvas import WaveformCanvas

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
        
        # Data
        self.project = Project()
        
        # Load Pinned Signals
        loaded = self.load_pinned_signals()
        
        if not loaded:
            # Add some demo signals if nothing pinned
            self.project.add_signal(Signal(name="i_clk", type=SignalType.CLK, color="#00ff00"))
            self.project.add_signal(Signal(name="i_rst", type=SignalType.INPUT, color="#ff5555"))
            self.project.add_signal(Signal(name="ADDR", type=SignalType.BUS, color="#00d2ff"))
            self.project.add_signal(Signal(name="DATA_RD", type=SignalType.BUS, color="#ffff00"))
        
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
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter to resize panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # --- Left Panel: Controls ---
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        
        left_layout.addWidget(QLabel("Signals"))
        
        # Save / Load
        sl_layout = QHBoxLayout()
        btn_save = QPushButton("Save Project")
        btn_save.clicked.connect(self.save_project_file)
        sl_layout.addWidget(btn_save)
        
        btn_load = QPushButton("Load Project")
        btn_load.clicked.connect(self.load_project_file)
        sl_layout.addWidget(btn_load)
        left_layout.addLayout(sl_layout)
        
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
        left_layout.addSpacing(20)
        left_layout.addWidget(QLabel("Properties"))
        
        # Name
        left_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self.on_name_changed)
        left_layout.addWidget(self.name_edit)
        
        # Type
        left_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        for t in SignalType:
            self.type_combo.addItem(t.value, t)
        self.type_combo.currentIndexChanged.connect(self.update_signal_properties)
        left_layout.addWidget(self.type_combo)
        
        # Clock Edge Config (Visible only for Clock)
        self.clk_edge_combo = QComboBox()
        self.clk_edge_combo.addItems(["Rising Edge (Pos)", "Falling Edge (Neg)"])
        self.clk_edge_combo.currentIndexChanged.connect(self.update_signal_properties)
        self.clk_edge_combo.setVisible(False)
        left_layout.addWidget(self.clk_edge_combo)

        # Clock Mod (Visible only for Clock)
        self.clk_mod_container = QWidget()
        mod_layout = QHBoxLayout(self.clk_mod_container)
        mod_layout.setContentsMargins(0,0,0,0)
        mod_layout.addWidget(QLabel("Mod:"))
        self.clk_mod_spin = QSpinBox()
        self.clk_mod_spin.setRange(1, 100)
        self.clk_mod_spin.valueChanged.connect(self.update_signal_properties)
        mod_layout.addWidget(self.clk_mod_spin)
        left_layout.addWidget(self.clk_mod_container)
        self.clk_mod_container.setVisible(False)
        
        # Color
        left_layout.addWidget(QLabel("Color:"))
        color_row = QHBoxLayout()
        self.color_btn = QPushButton("Select")
        self.color_btn.clicked.connect(self.pick_signal_color)
        color_row.addWidget(self.color_btn)
        
        self.color_preview = QLabel("   ")
        self.color_preview.setFixedWidth(40)
        self.color_preview.setStyleSheet("border: 1px solid #555; background-color: transparent;")
        color_row.addWidget(self.color_preview)
        
        left_layout.addLayout(color_row)
        
        left_layout.addStretch()
        
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
        # Also refresh list if structure changed (reordering in canvas)
        self.canvas.structure_changed.connect(self.refresh_list)
        
        # Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.setWidgetResizable(True) # Resize to content
        
        right_layout.addWidget(self.scroll_area)
        
        # Connect Selection
        self.canvas.bus_selected.connect(self.on_bus_selected)
        self.canvas.region_updated.connect(self.on_region_updated)
        self.canvas.cycles_changed.connect(self.on_cycles_changed)
        self.canvas.zoom_changed.connect(self.width_spin.setValue)
        
        splitter.addWidget(right_panel)
        
        # --- Right Panel: Editor ---
        self.editor_panel = BusEditorPanel()
        self.editor_panel.changed.connect(self.on_editor_changed)
        self.editor_panel.mode_combo.currentIndexChanged.connect(self.on_editor_mode_changed)
        layout.addWidget(self.editor_panel) # Not in splitter, fixed right? Or in splitter? User said "Directly on right". Layout usually fine.
        
        splitter.setSizes([250, 950])

        self.refresh_list()

    def keyPressEvent(self, event):
        if self.canvas.hasFocus():
             if event.key() == Qt.Key.Key_Delete:
                 # Delete selected BUS block if any
                 if self.canvas.selected_regions:
                     for (sig_idx, start, end) in self.canvas.selected_regions:
                         if 0 <= sig_idx < len(self.project.signals):
                             sig = self.project.signals[sig_idx]
                             if sig.type == SignalType.BUS:
                                 for t in range(start, end + 1):
                                     sig.set_value_at(t, 'X')
                     
                     self.canvas.data_changed.emit()
                     self.canvas.update()
                     return

        # Fallback to List Deletion
        if event.key() == Qt.Key.Key_Delete:
            if not isinstance(focus_widget, QLineEdit):
                # Ensure we don't accidentally delete when typing in some other input
                # Checking list focus or general non-input focus
                self.remove_signal()
        else:
            super().keyPressEvent(event)

    def on_bus_selected(self, sig_idx, cycle_idx):
        if 0 <= sig_idx < len(self.project.signals):
            signal = self.project.signals[sig_idx]
            self.editor_panel.load_target(signal, cycle_idx, self.project.total_cycles)
            
            # Sync mode state (load_target might have reset it or we just need to ensure canvas knows)
            self.on_editor_mode_changed(self.editor_panel.mode_combo.currentIndex())
            
            # REMOVED: Do not force-set canvas selection here. 
            # Canvas is the source of truth for selection (especially multi-select).
            # The canvas has already highlighted the region(s) before emitting this signal.
            
            # Update Canvas Selection Highlight from Editor's detected range
            # start = self.editor_panel.start_spin.value()
            # end = self.editor_panel.end_spin.value()
            # self.canvas.selected_region = (sig_idx, start, end)
            
            self.canvas.update()

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
        self.canvas.selected_region = (sig_idx, start, end)

    def on_cycles_changed(self, new_total):
        self.cycles_spin.blockSignals(True)
        self.cycles_spin.setValue(new_total)
        self.cycles_spin.blockSignals(False)

    def on_editor_mode_changed(self, index):
        mode_text = self.editor_panel.mode_combo.currentText()
        is_insert = (mode_text == "Insert")
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
             if signal in self.project.signals:
                 sig_idx = self.project.signals.index(signal)
                 self.canvas.selected_region = (sig_idx, start, end)

             self.canvas.update()

    def refresh_list(self):
        # Save selection
        current_row = self.signal_list.currentRow()
        
        # Block signals to prevent feedback loops if needed, though rowsMoved is user interaction
        self.signal_list.blockSignals(True)
        self.signal_list.clear()
        for s in self.project.signals:
            # pin_mark = "★ " if s.pinned else "" # Deprecated
            # item = QListWidgetItem(f"{pin_mark}{s.name} [{s.type.name}]")
            
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s) # Store object
            # self.signal_list.addItem(item) # Add first to list
            
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
            self.name_edit.setText(signal.name)
            # self.color_edit.setText(signal.color) # Removed
            self.color_preview.setStyleSheet(f"background-color: {signal.color}; border: 1px solid #e0e0e0;")
            
            # Set Combo
            idx = self.type_combo.findData(signal.type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            
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
            
            # Clock Mod props
            self.clk_mod_spin.blockSignals(True)
            self.clk_mod_spin.setValue(signal.clk_mod)
            self.clk_mod_container.setVisible(signal.type == SignalType.CLK)
            self.clk_mod_spin.blockSignals(False)


    def pick_signal_color(self):
        row = self.signal_list.currentRow()
        if row >= 0:
            signal = self.project.signals[row]
            initial = QColor(signal.color)
            color = QColorDialog.getColor(initial, self, "Select Signal Color")
            
            if color.isValid():
                self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #e0e0e0;")
                self.update_signal_properties()

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
            # Save Clock Edge
            if signal.type == SignalType.CLK:
                # Index 0 = Rising (True), Index 1 = Falling (False)
                signal.clk_rising_edge = (self.clk_edge_combo.currentIndex() == 0)
                signal.clk_mod = self.clk_mod_spin.value()
            
            # Update Visibility
            self.clk_edge_combo.setVisible(signal.type == SignalType.CLK)
            self.clk_mod_container.setVisible(signal.type == SignalType.CLK)

            self.save_pinned_signals()

            self.refresh_list()
            self.canvas.update()

    def on_list_reordered(self):
        # Reconstruct project.signals based on list order
        new_signals = []
        for i in range(self.signal_list.count()):
            item = self.signal_list.item(i)
            signal = item.data(Qt.ItemDataRole.UserRole)
            if signal:
                new_signals.append(signal)
        
        self.project.signals = new_signals
        self.canvas.update()

    def update_global_settings(self):
        self.project.total_cycles = self.cycles_spin.value()
        self.project.cycle_width = self.width_spin.value()
        self.canvas.update_dimensions()
        self.canvas.update()

    def add_signal(self):
        self.project.add_signal(Signal(name="New Signal"))
        self.refresh_list()
        self.canvas.update_dimensions()
        self.canvas.update()
        self.signal_list.setCurrentRow(len(self.project.signals) - 1)

    def remove_signal(self):
        row = self.signal_list.currentRow()
        if row >= 0:
            self.project.remove_signal(row)
            self.save_pinned_signals()
            self.refresh_list()
            self.canvas.update_dimensions()
            self.canvas.update()

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

    def keyPressEvent(self, event):
        if self.canvas.hasFocus():
             if event.key() == Qt.Key.Key_Delete:
                 # Delete selected BUS block if any
                 if self.canvas.selected_regions:
                     for (sig_idx, start, end) in self.canvas.selected_regions:
                         if 0 <= sig_idx < len(self.project.signals):
                             sig = self.project.signals[sig_idx]
                             if sig.type == SignalType.BUS:
                                 for t in range(start, end + 1):
                                     sig.set_value_at(t, 'X')
                     
                     self.canvas.data_changed.emit()
                     self.canvas.update()
                     return

        # Fallback to List Deletion
        if event.key() == Qt.Key.Key_Delete:
             curr = self.signal_list.currentRow()
             if curr >= 0:
                 self.remove_signal()

    def save_project_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json)")
        if not file_path:
            return
            
        try:
            data = self.project.to_dict()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(self, "Success", "Project saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project: {e}")

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
            self.canvas.project = self.project
            
            # Refresh UI
            self.refresh_list()
            self.canvas.update_dimensions()
            self.canvas.update()
            
            # Reset editors
            self.editor_panel.reset()
            
            self.refresh_global_controls()

            QMessageBox.information(self, "Success", "Project loaded successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project: {e}")

    def refresh_global_controls(self):
        # Trigger updates if possible, or just rely on user interaction
        pass
