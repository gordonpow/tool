from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPlainTextEdit, QTableWidget, QTableWidgetItem, 
                             QPushButton, QComboBox, QSpinBox, QHeaderView)
from PyQt6.QtCore import Qt
from core.hdl_parser import HDLParser
from core.models import SignalType, Signal

class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Signals from HDL (VHDL/Verilog)")
        self.resize(900, 600)
        
        self.init_ui()
        self.signals_data = []

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Splitter-like layout: Left (Code) | Right (Table)
        h_layout = QHBoxLayout()
        
        # Left Side: Code Input
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Paste VHDL Entity or Verilog Module:"))
        self.code_input = QPlainTextEdit()
        self.code_input.setPlaceholderText("entity ... Port (...) end entity;\nOR\nmodule ... (input ...); endmodule")
        self.code_input.textChanged.connect(self.on_code_changed)
        left_layout.addWidget(self.code_input)
        h_layout.addLayout(left_layout, 2)
        
        # Right Side: Table Preview
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Live Preview (Editable):"))
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Bits"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.table)
        h_layout.addLayout(right_layout, 3)
        
        layout.addLayout(h_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Import Selected")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setEnabled(False)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def on_code_changed(self):
        text = self.code_input.toPlainText()
        parsed_signals = HDLParser.parse(text)
        self.update_table(parsed_signals)
        self.ok_btn.setEnabled(len(parsed_signals) > 0)

    def update_table(self, signals):
        self.table.setRowCount(0)
        self.signals_data = signals
        
        for i, sig in enumerate(signals):
            self.table.insertRow(i)
            
            # Name
            name_item = QTableWidgetItem(sig['name'])
            self.table.setItem(i, 0, name_item)
            
            # Type Dropdown
            type_combo = QComboBox()
            for t in SignalType:
                type_combo.addItem(t.value, t)
            
            # Set initial guess
            idx = type_combo.findData(sig['type'])
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
            self.table.setCellWidget(i, 1, type_combo)
            
            # Bits Spinbox
            bits_spin = QSpinBox()
            bits_spin.setRange(1, 128)
            bits_spin.setValue(sig['bits'])
            self.table.setCellWidget(i, 2, bits_spin)

    def get_imported_signals(self):
        result = []
        for i in range(self.table.rowCount()):
            name = self.table.item(i, 0).text()
            type_combo = self.table.cellWidget(i, 1)
            sig_type = type_combo.currentData()
            bits_spin = self.table.cellWidget(i, 2)
            bits = bits_spin.value()
            
            # Create a new Signal object
            new_sig = Signal(name=name, type=sig_type, bits=bits)
            # Default initialization based on type
            if sig_type == SignalType.CLK:
                # Add a few cycles of clock
                new_sig.values = ['0', '1'] * 10
            else:
                new_sig.values = ['X'] # Single default value
            
            result.append(new_sig)
        return result
