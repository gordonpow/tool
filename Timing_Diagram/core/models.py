from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any
import PyQt6.QtGui as QtGui

class SignalType(Enum):
    INPUT = "Input"
    OUTPUT = "Output"
    INOUT = "Inout"
    CLK = "Clock"
    BUS_DATA = "Bus[data]"
    BUS_STATE = "Bus[state]"

@dataclass
class Signal:
    name: str = "New Signal"
    type: SignalType = SignalType.INPUT
    color: str = "#00d2ff"  # Hex color
    values: List[str] = field(default_factory=list)  # '0', '1', 'Z', 'X', or Bus Value
    
    # Custom colors for specific values (e.g. "IDLE": "#ffff00")
    value_colors: Dict[str, str] = field(default_factory=dict)

    # Visualization properties
    height: int = 40
    clk_rising_edge: bool = True # True: Low->High (Pos Edge), False: High->Low (Neg Edge)
    clk_mod: int = 1 # Clock Divider/Modifier (1 = standard, 2 = div 2, etc.)
    pinned: bool = False # Pinned signals are saved/restored (Persistence Pinning)
    sticky: bool = False # Stuck to top when scrolling (Display Pinning)
    
    # BUS[data] properties
    bits: int = 8
    input_base: int = 10  # 2, 10, 16 (Default to Decimal)
    display_base: int = 10 # 2, 10, 16 (Default to Decimal)
    
    def format_bus_value(self, val: str) -> str:
        if self.type != SignalType.BUS_DATA or val in ['X', 'Z', '']:
            return val
        
        try:
            # 1. Parse from input_base
            # Strip common prefixes
            clean_val = val.lower().replace('0x', '').replace('0b', '')
            num = int(clean_val, self.input_base)
            
            # 2. Mask to bit-width
            mask = (1 << self.bits) - 1
            num = num & mask
            
            # 3. Format to display_base
            if self.display_base == 2:
                # Binary with padding
                fmt = f"{{:0{self.bits}b}}"
                return fmt.format(num)
            elif self.display_base == 10:
                return str(num)
            elif self.display_base == 16:
                # Hex with padding matching bits (4 bits = 1 hex digit)
                hex_len = (self.bits + 3) // 4
                fmt = f"{{:0{hex_len}X}}"
                return "0x" + fmt.format(num)
            elif self.display_base == 8:
                # Octal with padding (3 bits = 1 octal digit)
                oct_len = (self.bits + 2) // 3
                fmt = f"{{:0{oct_len}o}}"
                return "0o" + fmt.format(num)
        except:
            return val # Fallback for non-numeric or invalid input
            
    def set_value_at(self, cycle_index: int, value: str):
        # Extend list if needed
        if cycle_index >= len(self.values):
            self.values.extend(['X'] * (cycle_index - len(self.values) + 1))
        self.values[cycle_index] = value

    def get_value_at(self, cycle_index: int) -> str:
        if 0 <= cycle_index < len(self.values):
            return self.values[cycle_index]
        return 'X' # Default to Unknown

    def to_dict(self):
        return {
            'name': self.name,
            'type': self.type.name, # Store Enum name
            'color': self.color,
            'values': self.values,
            'value_colors': self.value_colors,
            'clk_rising_edge': self.clk_rising_edge,
            'clk_mod': self.clk_mod,
            'pinned': self.pinned,
            'sticky': self.sticky,
            'bits': self.bits,
            'input_base': self.input_base,
            'display_base': self.display_base
        }

    @classmethod
    def from_dict(cls, data):
        s = cls(name=data.get('name', 'New Signal'))
        type_name = data.get('type', 'INPUT')
        
        # Migration: Map old BUS to BUS_DATA
        if type_name == "BUS":
            type_name = "BUS_DATA"
            
        if type_name in SignalType.__members__:
            s.type = SignalType[type_name]
            
        s.color = data.get('color', '#00d2ff')
        s.values = data.get('values', [])
        s.value_colors = data.get('value_colors', {})
        s.clk_rising_edge = data.get('clk_rising_edge', True)
        s.clk_mod = data.get('clk_mod', 1)
        s.pinned = data.get('pinned', False)
        s.sticky = data.get('sticky', False)
        s.bits = data.get('bits', 8)
        s.input_base = data.get('input_base', 16)
        s.display_base = data.get('display_base', 16)
        return s

@dataclass
class Project:
    name: str = "Untitled"
    total_cycles: int = 20
    cycle_width: int = 40  # Pixels per cycle
    signals: List[Signal] = field(default_factory=list)

    def add_signal(self, signal: Signal):
        self.signals.append(signal)

    def remove_signal(self, index: int):
        if 0 <= index < len(self.signals):
            self.signals.pop(index)

    def to_dict(self):
        return {
            'name': self.name,
            'total_cycles': self.total_cycles,
            'cycle_width': self.cycle_width,
            'signals': [s.to_dict() for s in self.signals]
        }

    @classmethod
    def from_dict(cls, data):
        p = cls(
            name=data.get('name', 'Untitled'),
            total_cycles=data.get('total_cycles', 20),
            cycle_width=data.get('cycle_width', 40)
        )
        signals_data = data.get('signals', [])
        for s_data in signals_data:
            p.add_signal(Signal.from_dict(s_data))
        return p
