import re
from core.models import SignalType

class HDLParser:
    @staticmethod
    def parse(text: str):
        """
        Main entry point to parse HDL text.
        Detects if it's VHDL or Verilog and calls appropriate parser.
        """
        if "entity" in text.lower() and "port" in text.lower():
            return HDLParser.parse_vhdl(text)
        elif "module" in text.lower():
            return HDLParser.parse_verilog(text)
        return []

    @staticmethod
    def parse_vhdl(text: str):
        # 1. Strip comments (VHDL uses --)
        text = re.sub(r"--.*", "", text)
        
        # 2. Find Port block content
        # We look for 'port (' and match until the last ');' in the text
        # This is more robust than non-greedy match which stops at vector closing parens ');'
        port_match = re.search(r"port\s*\((.*)\)\s*;", text, re.IGNORECASE | re.DOTALL)
        if not port_match:
            return []
        
        content = port_match.group(1).strip()
        
        signals = []
        # Split by semicolon (each port line)
        lines = content.split(';')
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Pattern: name(s) : direction type
            # Handles multiple names: i_clk, i_rst : in std_logic
            m = re.match(r"([\w\s,]+)\s*:\s*(in|out|inout)\s+([\w\s\(\) downto]+)", line, re.IGNORECASE)
            if m:
                names_raw = m.group(1)
                direction = m.group(2).lower()
                type_str = m.group(3).lower()
                
                bits = 1
                # Check for vector width
                width_m = re.search(r"(\d+)\s+downto\s+(\d+)", type_str)
                if width_m:
                    high = int(width_m.group(1))
                    low = int(width_m.group(2))
                    bits = abs(high - low) + 1
                
                # Split names if comma separated
                names = [n.strip() for n in names_raw.split(',')]
                for name in names:
                    if not name: continue
                    sig_type = HDLParser.guess_type(name, direction, bits, type_str)
                    signals.append({
                        'name': name,
                        'type': sig_type,
                        'bits': bits,
                        'direction': direction
                    })
        return signals

    @staticmethod
    def parse_verilog(text: str):
        signals = []
        # Support both old style (module M(a,b); input a; ...) and ANSI style (module M(input a, ...))
        # Simple approach: look for 'input/output/inout' keywords
        lines = text.split('\n')
        combined_text = " ".join(lines)
        
        # Regex for Verilog ports: (input|output|inout) [bits:bits] name
        # Handles: input clk, output [7:0] q, input wire [15:0] d
        pattern = re.compile(r"(input|output|inout)\s+(?:wire|reg\s+)?(?:\[(\d+)\s*:\s*(\d+)\]\s*)?(\w+)", re.IGNORECASE)
        
        for m in pattern.finditer(combined_text):
            direction = m.group(1).lower()
            high_str = m.group(2)
            low_str = m.group(3)
            name = m.group(4)
            
            bits = 1
            if high_str and low_str:
                bits = abs(int(high_str) - int(low_str)) + 1
            
            sig_type = HDLParser.guess_type(name, direction, bits, "")
            signals.append({
                'name': name,
                'type': sig_type,
                'bits': bits,
                'direction': direction
            })
            
        return signals

    @staticmethod
    def guess_type(name, direction, bits, raw_type_str):
        name_lower = name.lower()
        if "clk" in name_lower or "clock" in name_lower:
            return SignalType.CLK
        
        if bits > 1 or "vector" in raw_type_str.lower():
            # Usually data bus if it has name indicators like 'q', 'd', 'data', 'addr'
            # Or state if it has 'state'
            if "state" in name_lower:
                return SignalType.BUS_STATE
            return SignalType.BUS_DATA
            
        if direction == "in":
            return SignalType.INPUT
        elif direction == "out":
            return SignalType.OUTPUT
        else:
            return SignalType.INOUT
