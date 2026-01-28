from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any
import PyQt6.QtGui as QtGui

class SignalType(Enum):
    INPUT = "Input"
    OUTPUT = "Output"
    INOUT = "Inout"
    CLK = "Clock"
    BUS = "Bus"

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
    pinned: bool = False # Pinned signals are saved/restored
    
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
            'pinned': self.pinned
        }

    @classmethod
    def from_dict(cls, data):
        s = cls(name=data.get('name', 'New Signal'))
        type_name = data.get('type', 'INPUT')
        if type_name in SignalType.__members__:
            s.type = SignalType[type_name]
        s.color = data.get('color', '#00d2ff')
        s.values = data.get('values', [])
        s.value_colors = data.get('value_colors', {})
        s.clk_rising_edge = data.get('clk_rising_edge', True)
        s.clk_mod = data.get('clk_mod', 1)
        s.pinned = data.get('pinned', False)
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
