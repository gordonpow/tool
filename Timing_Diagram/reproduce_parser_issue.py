from core.hdl_parser import HDLParser

vhdl_code = """
entity CounterFSM is
    Port (
        i_clk        : in  STD_LOGIC;
        i_rst        : in  STD_LOGIC;
        i_en         : in  STD_LOGIC;
        i_Cnt1_lim_up: in  STD_LOGIC_VECTOR(7 downto 0);
        i_Cnt2_lim_up: in  STD_LOGIC_VECTOR(7 downto 0);
        o_Cnt1_q     : out STD_LOGIC_VECTOR(7 downto 0);
        o_Cnt2_q     : out STD_LOGIC_VECTOR(7 downto 0);
        o_state      : out STD_LOGIC_VECTOR(1 downto 0) -- 00:Idle, 01:Cnt1, 10:Cnt2
    );
end CounterFSM;
"""

signals = HDLParser.parse(vhdl_code)
print(f"Parsed {len(signals)} signals:")
for s in signals:
    print(s)
