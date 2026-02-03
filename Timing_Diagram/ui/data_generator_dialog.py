from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QSpinBox, QComboBox, QPushButton, 
                             QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QWidget)
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QBrush, QPainterPath
from PyQt6.QtCore import Qt, QRect, QPoint
import math

class SignalPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.data = [] # List of strings
        self.bits = 8
        self.color = "#00d2ff"
        self.error_msg = ""

    def set_preview_data(self, data, bits, color, error=""):
        self.data = data
        self.bits = bits
        self.color = color
        self.error_msg = error
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fill background
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        
        if self.error_msg:
            painter.setPen(QColor("#ff5555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"Preview Error: {self.error_msg}")
            return

        if not self.data:
            painter.setPen(QColor("#808080"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "(Waveform preview will appear here)")
            return

        # Draw Waveform
        cw = 40 # cycle width for preview
        start_x = 10
        y_center = self.height() // 2
        row_height = 40
        high_y = y_center - 15
        low_y = y_center + 15
        
        base_color = QColor(self.color)
        
        # Group identical values for Bus rendering
        groups = []
        if self.data:
            current_val = self.data[0]
            current_start = 0
            for t in range(1, len(self.data)):
                if self.data[t] != current_val:
                    groups.append((current_start, t - 1, current_val))
                    current_val = self.data[t]
                    current_start = t
            groups.append((current_start, len(self.data) - 1, current_val))

        for start_t, end_t, val in groups:
            x1 = start_x + start_t * cw
            x2 = start_x + (end_t + 1) * cw
            
            # Draw Hexagon/Bus shape
            slant = 5
            poly_pts = [
                QPoint(int(x1), int(y_center)),
                QPoint(int(x1 + slant), int(high_y)),
                QPoint(int(x2 - slant), int(high_y)),
                QPoint(int(x2), int(y_center)),
                QPoint(int(x2 - slant), int(low_y)),
                QPoint(int(x1 + slant), int(low_y)),
                QPoint(int(x1), int(y_center))
            ]
            
            painter.setPen(QPen(base_color, 2))
            painter.setBrush(QBrush(QColor(base_color.red(), base_color.green(), base_color.blue(), 100)))
            painter.drawPolygon(poly_pts)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Label
            text_rect = QRect(int(x1), int(high_y), int(x2-x1), int(low_y - high_y))
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPointSize(7)
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(val))

class DataGeneratorDialog(QDialog):
    def __init__(self, project, parent=None, initial_signal_index=None, initial_start=0, initial_end=0):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Data Generator")
        self.resize(600, 500)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # 1. Target Signal and Range
        grid_layout = QHBoxLayout()
        
        grid_layout.addWidget(QLabel("Target Signal:"))
        self.signal_combo = QComboBox()
        self.populate_signals(initial_signal_index)
        grid_layout.addWidget(self.signal_combo)
        
        grid_layout.addWidget(QLabel("Start Cycle:"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(initial_start)
        grid_layout.addWidget(self.start_spin)
        
        grid_layout.addWidget(QLabel("End Cycle:"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 999999)
        self.end_spin.setValue(initial_end)
        grid_layout.addWidget(self.end_spin)
        
        layout.addLayout(grid_layout)
        
        # 2. Formula Input
        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("Formula (e.g. x+1, x**2):"))
        self.formula_input = QLineEdit()
        self.formula_input.setPlaceholderText("x + 1")
        form_layout.addWidget(self.formula_input)
        layout.addLayout(form_layout)
        
        # 3. Variables Table
        layout.addWidget(QLabel("Variables (Define ranges):"))
        self.var_table = QTableWidget()
        self.var_table.setColumnCount(4)
        self.var_table.setHorizontalHeaderLabels(["Name", "Start", "End", "Step"])
        self.var_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.var_table)
        
        btn_layout = QHBoxLayout()
        self.add_var_btn = QPushButton("Add Variable")
        self.add_var_btn.clicked.connect(self.add_variable_row)
        self.remove_var_btn = QPushButton("Remove Variable")
        self.remove_var_btn.clicked.connect(self.remove_variable_row)
        btn_layout.addWidget(self.add_var_btn)
        btn_layout.addWidget(self.remove_var_btn)
        layout.addLayout(btn_layout)
        # 4. Waveform Preview
        self.preview_widget = SignalPreviewWidget()
        layout.addWidget(self.preview_widget)
        
        # 4.1 Error Info (Optional text fallback)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #ff5555; font-weight: bold;")
        self.info_label.setWordWrap(True)
        self.info_label.setVisible(False)
        layout.addWidget(self.info_label)
        
        # 5. Buttons
        action_layout = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.clicked.connect(self.generate)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        action_layout.addWidget(self.generate_btn)
        action_layout.addWidget(self.cancel_btn)
        layout.addLayout(action_layout)

        # 6. Initialize Variables and Connections (Triggering events)
        # Add default 'x' variable
        self.add_variable_row("x", 0, 9, 1)

        # Connect formula changed and table changed ONLY after info_label exists
        self.formula_input.textChanged.connect(self.update_preview)
        self.var_table.itemChanged.connect(self.update_preview)

        # Initial preview
        self.update_preview()
        
    def update_preview(self):
        formula = self.formula_input.text().strip()
        if not formula:
            self.preview_widget.set_preview_data([], 8, "#00d2ff")
            return

        # 1. Parse Variables
        variables = {}
        for r in range(self.var_table.rowCount()):
            name_item = self.var_table.item(r, 0)
            start_item = self.var_table.item(r, 1)
            end_item = self.var_table.item(r, 2)
            step_item = self.var_table.item(r, 3)
            
            if not (name_item and start_item and end_item and step_item):
                continue
                
            name = name_item.text().strip()
            if not name: continue
            try:
                variables[name] = {
                    'start': float(start_item.text()),
                    'end': float(end_item.text()),
                    'step': float(step_item.text()),
                    'current': float(start_item.text())
                }
                if variables[name]['step'] == 0: variables[name]['step'] = 1
            except:
                continue

        # 2. Evaluate samples for preview (more cycles for visual)
        preview_values = []
        try:
            start_cycle = self.start_spin.value()
            for t in range(start_cycle, start_cycle + 15):
                # Context
                eval_context = {}
                for v_name, v_data in variables.items():
                    eval_context[v_name] = v_data['current']
                    # Local update for next cycle in preview
                    nxt = v_data['current'] + v_data['step']
                    if v_data['step'] > 0:
                        if nxt > v_data['end']: nxt = v_data['start']
                    else:
                        if nxt < v_data['end']: nxt = v_data['start']
                    v_data['current'] = nxt
                
                eval_context.update(math.__dict__)
                eval_context['t'] = t
                eval_context['i'] = t - start_cycle

                # Eval
                res = eval(formula, {"__builtins__": {}}, eval_context)
                if isinstance(res, float) and res.is_integer():
                    res = int(res)
                preview_values.append(str(res))

            # Get target signal metadata for preview color/type
            sig_color = "#00d2ff"
            sig_bits = 8
            if self.signal_combo.currentIndex() < len(self.signal_map):
                logical_idx = self.signal_map[self.signal_combo.currentIndex()]
                sig = self.project.signals[logical_idx]
                sig_color = sig.color
                sig_bits = sig.bits

            self.preview_widget.set_preview_data(preview_values, sig_bits, sig_color)
            self.info_label.setVisible(False)
        except Exception as e:
            self.preview_widget.set_preview_data([], 8, "#00d2ff")
            self.info_label.setText(f"(Error) {str(e)}")
            self.info_label.setVisible(True)

    def populate_signals(self, initial_idx):
        self.signal_map = [] # stores logical index
        for i, sig in enumerate(self.project.signals):
            if sig.type.name in ['BUS_DATA', 'BUS_STATE']:
                self.signal_combo.addItem(sig.name)
                self.signal_map.append(i)
                
        if initial_idx is not None and initial_idx in self.signal_map:
            combo_idx = self.signal_map.index(initial_idx)
            self.signal_combo.setCurrentIndex(combo_idx)

    def add_variable_row(self, name="x", start=0, end=10, step=1):
        row = self.var_table.rowCount()
        self.var_table.insertRow(row)
        
        # Name
        self.var_table.setItem(row, 0, QTableWidgetItem(name))
        # Start
        self.var_table.setItem(row, 1, QTableWidgetItem(str(start)))
        # End
        self.var_table.setItem(row, 2, QTableWidgetItem(str(end)))
        # Step
        self.var_table.setItem(row, 3, QTableWidgetItem(str(step)))

    def remove_variable_row(self):
        cur = self.var_table.currentRow()
        if cur >= 0:
            self.var_table.removeRow(cur)
        elif self.var_table.rowCount() > 0:
            self.var_table.removeRow(self.var_table.rowCount() - 1)

    def generate(self):
        # 1. Parse Formula
        formula = self.formula_input.text().strip()
        if not formula:
            QMessageBox.warning(self, "Error", "Please enter a formula.")
            return

        # 2. Parse Variables
        variables = {}
        for r in range(self.var_table.rowCount()):
            name_item = self.var_table.item(r, 0)
            start_item = self.var_table.item(r, 1)
            end_item = self.var_table.item(r, 2)
            step_item = self.var_table.item(r, 3)
            
            if not (name_item and start_item and end_item and step_item):
                continue
                
            name = name_item.text().strip()
            try:
                start = float(start_item.text())
                end = float(end_item.text())
                step = float(step_item.text())
                
                # Create generator/sequence
                # If step is 0, avoid infinite loop
                if step == 0: step = 1
                
                # Sequence: 0, 1, ... 9, 0, 1... (Repeating)
                variables[name] = {
                    'start': start,
                    'end': end,
                    'step': step,
                    'current': start
                }
            except ValueError:
                QMessageBox.warning(self, "Error", f"Invalid number format in variable row {r+1}")
                return

        # 3. Target Range
        start_cycle = self.start_spin.value()
        end_cycle = self.end_spin.value()
        
        if end_cycle < start_cycle:
             QMessageBox.warning(self, "Error", "End Cycle must be >= Start Cycle")
             return

        sig_idx = self.signal_combo.currentIndex()
        if sig_idx < 0: return
        logical_sig_idx = self.signal_map[sig_idx]
        signal = self.project.signals[logical_sig_idx]

        # 4. Generate Data
        generated_count = 0
        try:
            for t in range(start_cycle, end_cycle + 1):
                # Prepare eval context
                eval_context = {}
                for v_name, v_data in variables.items():
                    eval_context[v_name] = v_data['current']
                    
                    # Update variable for next step
                    nxt = v_data['current'] + v_data['step']
                    if v_data['step'] > 0:
                        if nxt > v_data['end']:
                            nxt = v_data['start'] # Loop
                    else:
                        if nxt < v_data['end']:
                            nxt = v_data['start']
                    v_data['current'] = nxt
                
                # Add built-in Math
                eval_context.update(math.__dict__)
                
                # Allow 't' as current absolute cycle
                eval_context['t'] = t
                # Allow 'i' as relative index (0 based)
                eval_context['i'] = t - start_cycle

                # Evaluate
                res = eval(formula, {"__builtins__": {}}, eval_context)
                
                # Format result (User requested NO floating point if possible)
                if isinstance(res, float):
                    if res.is_integer():
                        res = int(res)
                    # Else keep as float? Or maybe user wants truncation?
                    # "不要顯示浮點數" usually means they expect integers or hex.
                    # If they calculate something like sin(x), keeping float is correct but maybe round?
                    # For now, stripping .0 is the safest interpretation of "No float for integer values".
                
                # Convert to string for Signal
                signal.set_value_at(t, str(res))
                generated_count += 1
                
            # Expand project if needed
            if end_cycle >= self.project.total_cycles:
                self.project.total_cycles = end_cycle + 1
            
            QMessageBox.information(self, "Success", f"Generated {generated_count} values.")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Evaluation Error", str(e))
