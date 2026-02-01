from PyQt6.QtWidgets import QWidget, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QPointF, QEvent, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QBrush, QPainterPath, QMouseEvent, QKeySequence
from core.models import Project, Signal, SignalType

class WaveformCanvas(QWidget):
    # Signal emitted when data changes (e.g. user clicks to toggle bit)
    data_changed = pyqtSignal()
    # Signal emitted when structure changes (e.g. reorder)
    structure_changed = pyqtSignal()
    # Signal emitted when a bus item is selected (signal_index, cycle_index)
    bus_selected = pyqtSignal(int, int)
    # Signal emitted when region changes during drag (signal_index, start, end)
    region_updated = pyqtSignal(int, int, int)
    # Signal emitted when total cycles change (new_total)
    cycles_changed = pyqtSignal(int)
    # Signal emitted when zoom level (cycle width) changes
    zoom_changed = pyqtSignal(int)
    # Signal emitted when a signal name is clicked (signal_index)
    signal_clicked = pyqtSignal(int)
    # Signal emitted before a change that should be undoable
    before_change = pyqtSignal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hover_pos = None  # (signal_index, cycle_index)
        self.selected_regions = [] # List of (signal_index, start_cycle, end_cycle)
        
        # Dragging state (Row Reorder)
        self.reorder_candidate_idx = None # Potential drag wait
        self.dragging_signal_index = None
        self.drag_start_y = 0
        self.current_drag_y = 0
        
        # Dragging state (Duration Edit)
        self.is_editing_duration = False
        self.edit_signal_index = None
        self.edit_start_cycle = 0 # The click cycle
        self.edit_orig_start = 0
        self.edit_orig_end = 0
        self.edit_value = None
        self.edit_mode = None # 'START' or 'END'
        self.edit_initial_values = None # Snapshot for drag
        self.is_insert_mode = False # Synchronized from EditorPanel
        
        # Block Move State (Ctrl + Drag)
        self.is_moving_block = False
        self.move_block_info = None # Holds main block info (primary)
        self.moving_blocks_snapshot = {} # Snapshot for multi-move {key: values}
        self.move_drag_start_cycle = 0 
        self.drag_start_x = 0 # Pixel start for smooth drag
        self.move_target_cycle = 0
        self.preview_signal_values = {} # {sig_idx: preview_list}
        
        # Paint / Toggle State
        self.paint_start_pos = None
        self.is_painting = False
        self.paint_val = None # '1' or '0'
        
        # Geometry constants
        self.signal_header_width = 100
        self.row_height = 40
        self.header_height = 30
        
        self.header_height = 30
        
        # Long Press Drag State
        from PyQt6.QtCore import QTimer
        self.long_press_timer = QTimer()
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self.on_long_press)
        self.press_start_pos = None
        self.press_context = None # {sig_idx, cycle_idx, val, original_region}
        
        # Auto-Scroll State
        self.scroll_timer = QTimer()
        self.scroll_timer.setInterval(50) 
        self.scroll_timer.timeout.connect(self.process_auto_scroll)
        self.auto_scroll_direction = 0
        
        # Layout State
        self.signal_layout = [] # List of {index, y, height, sub_rows, signal}
        self.expand_rects = {} # Map sig_idx -> QRect for expand buttons
        
        self.update_dimensions()

    @property
    def selected_region(self):
        if self.selected_regions:
            return self.selected_regions[-1]
        return None
        
    @selected_region.setter
    def selected_region(self, val):
        if val is None:
            self.selected_regions = []
        else:
            self.selected_regions = [val]

    def update_dimensions(self):
        w = self.signal_header_width + self.project.total_cycles * self.project.cycle_width + 50
        h = self.header_height + len(self.project.signals) * self.row_height + 50
        self.setMinimumSize(w, h)

    def is_part_of_selection(self, r):
        # r is (sig, start, end)
        for s_sig, s_start, s_end in self.selected_regions:
            if r[0] == s_sig:
               # Check intersection or containment
               # If r overlaps s: max(start1, start2) <= min(end1, end2)
               if max(s_start, r[1]) <= min(s_end, r[2]):
                   return True
        return False

    def format_value(self, val_str: str, in_base: int, out_base: int) -> str:
        if val_str in ['X', 'Z', 'x', 'z', '', None]: 
            return val_str.upper() if val_str else 'X'
        
        try:
            # Parse
            int_val = int(val_str, in_base)
            
            # Format
            if out_base == 2:
                return bin(int_val)[2:]
            elif out_base == 8:
                return oct(int_val)[2:]
            elif out_base == 16:
                return hex(int_val)[2:].upper()
            else:
                return str(int_val)
        except:
            return val_str # Fallback (e.g. invalid chars for base)

    def refresh_layout(self):
        """Recalculate Y positions for all signals."""
        self.signal_layout = [] # List of dict: {index, y, height, sub_rows}
        current_y = self.header_height
        
        for i, signal in enumerate(self.project.signals):
            h = self.row_height
            sub_rows = 0
            
            if signal.type == SignalType.BUS_DATA and signal.expanded and signal.bus_width > 0:
                sub_rows = signal.bus_width
                h += sub_rows * self.row_height
            
            self.signal_layout.append({
                'index': i,
                'y': current_y,
                'height': h,
                'sub_rows': sub_rows,
                'signal': signal
            })
            current_y += h
            
        return current_y # Total height

    def get_signal_from_y(self, y: int):
        """Returns (signal_index, is_sub_row, sub_row_index)"""
        # Linear search is fine for < 500 signals
        for item in self.signal_layout:
            if item['y'] <= y < item['y'] + item['height']:
                # Found the block
                # Check if it's main row or sub row
                rel_y = y - item['y']
                row_idx = int(rel_y / self.row_height)
                
                if row_idx == 0:
                    return item['index'], False, 0 # Main Bus Row
                else:
                    return item['index'], True, row_idx - 1 # Sub Row (Bit index depends on order)
                    # Visual: Top is Bit N-1, Bottom is Bit 0?
                    # User: "Down to Up: Q[0]...Q[7]" -> Q[0] at bottom.
                    # My rendering loop will determine visual order.
        return None, False, 0

    def update_dimensions(self):
        total_h = self.refresh_layout()
        w = self.signal_header_width + self.project.total_cycles * self.project.cycle_width + 50
        h = total_h + 50
        self.setMinimumSize(w, h)
        # Trigger update to use new layout?

    def render_to_image_object(self, settings):
        bg_color = settings['bg_color']
        font_color = settings['font_color']
        font_size = settings['font_size']
        
        # Calculate Dimensions (Force layout refresh)
        total_h = self.refresh_layout()
        cw = self.project.cycle_width
        full_w = self.signal_header_width + self.project.total_cycles * cw 
        full_h = total_h + 1 # +1 to include bottom border
        
        from PyQt6.QtGui import QImage, QPainter
        img = QImage(full_w, full_h, QImage.Format.Format_ARGB32)
        img.fill(bg_color)
        
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Apply Font Settings
        font = painter.font()
        font.setPointSize(font_size)
        painter.setFont(font)
        
        # Draw Content
        self.draw_header(painter, settings.get('font_color'), width=full_w, height=full_h)
        
        for item in self.signal_layout:
            i = item['index']
            y = item['y']
            signal = self.project.signals[i]
            # render using draw_signal helper
            self.draw_signal(painter, signal, y, width=full_w, text_color=font_color, signal_index=i)

        painter.end()
        return img

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fill background
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        
        # Draw Time/Cycle Header
        self.draw_header(painter)
        
        # Draw Signals
        for i, signal in enumerate(self.project.signals):
            # If dragging this signal, draw it at the dragged position later (or transparent here)
            if i == self.dragging_signal_index:
                continue
                
            # Use the layout to get the correct Y position and height
            layout_item = next((item for item in self.signal_layout if item['index'] == i), None)
            if layout_item:
                y = layout_item['y']
                
                # Check for Preview Override
                override = None
                # CHANGED: preview_signal_values is now a dict {sig_idx: list}
                if self.is_moving_block and self.preview_signal_values and i in self.preview_signal_values:
                    override = self.preview_signal_values[i]
                
                # Highlight Dragged Blocks:
                # We convert float preview regions to integer intervals for highlighting
                highlights = []
                if self.is_moving_block and hasattr(self, 'preview_selection_regions') and self.preview_selection_regions:
                     for (s_idx, start, end) in self.preview_selection_regions:
                         if s_idx == i:
                             highlights.append((int(round(start)), int(round(end))))
                    
                self.draw_signal(painter, signal, y, is_dragging=False, override_values=override, highlight_ranges=highlights, signal_index=i)

        # Draw the dragged signal last (on top) - For Reordering
        if self.dragging_signal_index is not None:
            signal = self.project.signals[self.dragging_signal_index]
            drag_y = int(self.current_drag_y - self.row_height/2)
            self.draw_signal(painter, signal, drag_y, is_dragging=True, signal_index=self.dragging_signal_index)
            
            # Draw drop indicator
            drop_idx = self.get_drop_index(self.current_drag_y)
            if drop_idx is not None:
                line_y = self.header_height + drop_idx * self.row_height
                painter.setPen(QPen(QColor("#00ff00"), 2))
                painter.drawLine(0, line_y, self.width(), line_y)

        # Draw Selection Highlight (Standard)
        if self.selected_region and not self.is_moving_block:
            self.draw_selection_highlight(painter)

        # Draw Cursor/Guide if hovering and NOT dragging
        if self.hover_pos and self.dragging_signal_index is None:
            self.draw_guide(painter)

        # Draw Move-Insert Highlight (Visual Feedback) -- (Previous logic here)
        # (Assuming the rest of paintEvent is intact below...)

        # Draw Selection Highlight (Standard)
        if self.selected_region and not self.is_moving_block:
            self.draw_selection_highlight(painter)

        # Draw Cursor/Guide if hovering and NOT dragging
        if self.hover_pos and self.dragging_signal_index is None:
            self.draw_guide(painter)

        # Draw Move-Insert Highlight (Visual Feedback)
        if self.is_moving_block and self.move_block_info:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False) # Sharp lines
            
            # Use Multi-Select Preview if available (Preferred)
            if hasattr(self, 'preview_selection_regions') and self.preview_selection_regions:
                 # Find min visual start (Float)
                 # This ensures the Red Line is always at the visual HEAD of the group
                 min_start = min(r[1] for r in self.preview_selection_regions)
                 
                 # Draw on the dragged signal row (reference)
                 sig_idx = self.move_block_info['sig_idx']
                 y = self.header_height + sig_idx * self.row_height
                 
                 cw = self.project.cycle_width
                 x1 = self.signal_header_width + min_start * cw
                 
                 # Red Start Line
                 painter.setPen(QPen(QColor("#ff0000"), 4))
                 painter.drawLine(int(x1), int(y - 2), int(x1), int(y + self.row_height + 2))
                 
            else:
                # Fallback / Single Block Legacy
                info = self.move_block_info
                sig_idx = info['sig_idx']
                
                # Logic to find VISUAL location of the inserted block in the preview:
                target = self.move_target_cycle
                start_cycle = target
                if info['start'] < target:
                     block_len = (info['end'] - info['start'] + 1)
                     start_cycle = max(0, target - block_len)
                start_cycle = min(self.project.total_cycles, max(0, start_cycle))
                
                cw = self.project.cycle_width
                x1 = self.signal_header_width + start_cycle * cw
                y = self.header_height + sig_idx * self.row_height
                
                # Red Start Line
                painter.setPen(QPen(QColor("#ff0000"), 4))
                painter.drawLine(int(x1), int(y - 2), int(x1), int(y + self.row_height + 2))
            
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    def get_drop_index(self, y):
        # Calculate which index we would drop into
        # y is the center of the dragged item
        # We want to find the insertion point
        relative_y = y - self.header_height
        idx = int(round(relative_y / self.row_height))
        idx = max(0, min(idx, len(self.project.signals)))
        return idx

    def draw_header(self, painter: QPainter, font_color=None, width=None, height=None):
        if width is None: width = self.width()
        if height is None: height = self.height()
        default_color = QColor("#808080")
        
        # Draw Cycle Numbers
        painter.setPen(font_color if font_color else default_color)
        font = painter.font()
        # font.setPointSize(8) # Don't force size if set externally
        if font.pointSize() > 20: pass # Sanity check?
        
        # Only set if not already set? 
        # Actually paintEvent sets size 8 before calling? No, it used local font.
        # If external render set font size, we should respect it.
        # Existing code: `font = painter.font(); font.setPointSize(8); painter.setFont(font)`
        # I should Make it conditional.
        if font_color is None: # Assuming export sets font on painter before
             font.setPointSize(8)
             painter.setFont(font)
             
        cw = self.project.cycle_width
        
        # Clip header drawing area
        # painter.setClipRect(0, 0, self.width(), self.header_height)
        
        # Only draw visible cycles effectively? For now draw all
        for t in range(self.project.total_cycles):
            x = self.signal_header_width + t * cw
            rect = QRect(x, 0, cw, self.header_height)
            
            # Highlight selected cycles in header
            # Highlight selected cycles in header
            is_selected = False
            
            # Use Preview regions if moving, else actual selection
            regions_to_check = self.selected_regions
            if self.is_moving_block and hasattr(self, 'preview_selection_regions') and self.preview_selection_regions:
                 regions_to_check = self.preview_selection_regions
                 
            for (sig, start, end) in regions_to_check:
                if start <= t <= end:
                    is_selected = True
                    # Draw highlight background
                    painter.fillRect(rect, QColor(255, 170, 0, 80)) # Orange-ish semi-transparent
                    break
            
            if is_selected:
                painter.setPen(QColor("#ffffff")) # White text for selected
                f = painter.font()
                f.setBold(True)
                painter.setFont(f)
            else:
                painter.setPen(font_color if font_color else default_color) # Gray text for normal
                f = painter.font()
                f.setBold(False)
                painter.setFont(f)
            
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(t))
            
            # Subtle vertical grid line
            painter.setPen(QColor("#333333"))
            painter.drawLine(x, 0, x, height)

    def draw_signal(self, painter: QPainter, signal: Signal, y: int, is_dragging=False, override_values=None, highlight_ranges=None, width=None, text_color=None, signal_index=-1):
        if width is None: width = self.width()
        
        if is_dragging:
            painter.setOpacity(0.8)
            painter.fillRect(0, y, width, self.row_height, QColor("#333333"))
        
        # Draw Separator
        if not is_dragging:
            painter.setPen(QColor("#333333"))
            painter.drawLine(0, y + self.row_height, width, y + self.row_height)

        # Draw Signal Name & Expand Button
        name_rect = QRect(20, y, self.signal_header_width - 30, self.row_height) # Shifted for button
        painter.setPen(text_color if text_color else QColor("#e0e0e0"))
        
        name_str = signal.name
        if signal.type == SignalType.BUS_DATA and signal.bus_width > 0:
             # Draw Button
             btn_rect = QRect(2, y + 10, 16, 16)
             if signal_index >= 0:
                 self.expand_rects[signal_index] = btn_rect
             
             painter.setPen(QColor("#808080"))
             painter.drawRect(btn_rect)
             signer = "-" if signal.expanded else "+"
             painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, signer)
             
             name_str += f" [{signal.display_base}]" # Hint display base
        
        painter.setPen(text_color if text_color else QColor("#e0e0e0"))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name_str)
        
        # Draw Waveform
        cw = self.project.cycle_width
        start_x = self.signal_header_width
        
        # Helper to get value
        def get_val(t):
            if override_values is not None:
                if 0 <= t < len(override_values):
                    return override_values[t]
                return 'X' # Out of bounds for override, treat as unknown
            return signal.get_value_at(t)

        # Setup Pen for Waveform
        base_color = QColor(signal.color)
        pen = QPen(base_color)
        pen.setWidth(2)
        painter.setPen(pen)
        
        # Calculate Y levels
        high_y = y + 5
        mid_y = y + self.row_height // 2
        low_y = y + self.row_height - 5
        
        path = QPainterPath()
        
        # --- BUS RENDER LOGIC (Merged) ---
        if signal.type in [SignalType.BUS_DATA, SignalType.BUS_STATE]:
            # Group consecutive identical values
            groups = []
            if self.project.total_cycles > 0:
                current_val = get_val(0)
                current_start = 0
                for t in range(1, self.project.total_cycles):
                    val = get_val(t)
                    if val != current_val:
                        groups.append((current_start, t - 1, current_val))
                        current_val = val
                        current_start = t
                groups.append((current_start, self.project.total_cycles - 1, current_val))

            for start_t, end_t, val in groups:
                # Calculate coordinates
                x1 = start_x + start_t * cw
                x2 = start_x + (end_t + 1) * cw # End of the last cycle
                
                # Determine Fill Color (Custom if set)
                fill_color = base_color
                if val is not None and val in signal.value_colors:
                    fill_color = QColor(signal.value_colors[val])
                
                # Draw Hexagon/Bus shape
                path = QPainterPath() # New path per block for bus
                
                # Always use base signal color for outline (User Request)
                # Unless Highlighted
                is_highlighted = False
                if highlight_ranges:
                    # Check if this block (start_t, end_t) is inside any highlight range
                    # Relaxed check: overlap or containment
                    for (hs, he) in highlight_ranges:
                        # If block is roughly within the highlight range
                        # highlight range is the box. Block should be inside.
                        if start_t >= hs and end_t <= he:
                            is_highlighted = True
                            break
                        # Overlap check (safer for edge cases)
                        if max(start_t, hs) <= min(end_t, he):
                             is_highlighted = True
                             break
                
                if is_highlighted:
                     painter.setPen(QPen(QColor("#ffffff"), 3)) # Bold White
                else:
                     painter.setPen(QPen(base_color, 2))
                
                if val == 'Z':
                    painter.drawLine(x1, mid_y, x2, mid_y)
                else:
                    # Determine Shape based on Flavor
                    
                    if signal.type == SignalType.BUS_STATE:
                        # Rounded Rectangle
                        rect = QRectF(x1, y + 4, x2 - x1, self.row_height - 8)
                        painter.setBrush(QBrush(QColor(fill_color.red(), fill_color.green(), fill_color.blue(), 100)))
                        painter.drawRoundedRect(rect, 8, 8)
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                    else:
                        # Standard Hexagon (DATA)

                        slant = 5
                        poly_pts = [
                            QPoint(int(x1), int(mid_y)),
                            QPoint(int(x1 + slant), int(high_y)),
                            QPoint(int(x2 - slant), int(high_y)),
                            QPoint(int(x2), int(mid_y)),
                            QPoint(int(x2 - slant), int(low_y)),
                            QPoint(int(x1 + slant), int(low_y)),
                            QPoint(int(x1), int(mid_y))
                        ]
                        
                        # Fill logic
                        painter.setBrush(QBrush(QColor(fill_color.red(), fill_color.green(), fill_color.blue(), 100)))
                        painter.drawPolygon(poly_pts)
                        painter.setBrush(Qt.BrushStyle.NoBrush)

                    # Draw Text - Centered
                    text_rect = QRect(int(x1), int(high_y), int(x2-x1), int(low_y - high_y))
                    painter.setPen(text_color if text_color else QColor("#ffffff"))
                    
                    # Format Value
                    display_label = self.format_value(val, signal.input_base, signal.display_base)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_label)

            # --- SUB-ROW RENDERING (If Expanded) ---
            if signal.expanded and signal.bus_width > 0:
                # Iterate Bits: MSB (width-1) -> LSB (0)
                # Visual Row 1 -> width
                
                for bit_idx in range(signal.bus_width - 1, -1, -1):
                    # Visual Offset (1-based index from main row)
                    row_offset = (signal.bus_width - 1 - bit_idx) + 1
                    sub_y = y + row_offset * self.row_height
                    
                    # Draw Separator
                    painter.setPen(QColor("#222222"))
                    painter.drawLine(0, sub_y + self.row_height, width, sub_y + self.row_height)
                    
                    # Draw Bit Name
                    name_rect = QRect(30, sub_y, self.signal_header_width - 40, self.row_height)
                    painter.setPen(QColor("#aaaaaa"))
                    painter.drawText(name_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"[{bit_idx}]")
                    
                    # Draw Binary Waveform for this bit
                    path_bit = QPainterPath()
                    bit_high_y = sub_y + 5
                    bit_low_y = sub_y + self.row_height - 5
                    
                    painter.setPen(QPen(base_color, 1)) # Thinner for bits
                    
                    for t in range(self.project.total_cycles):
                        curr_x = start_x + t * cw
                        next_x = curr_x + cw
                        
                        # Get Bit Value
                        val_str = get_val(t)
                        bit_val = 0
                        is_z = False
                        is_x = False
                        
                        if val_str in ['X', 'x', '', None]: is_x = True
                        elif val_str in ['Z', 'z']: is_z = True
                        else:
                            try:
                                full_int = int(val_str, signal.input_base)
                                bit_val = (full_int >> bit_idx) & 1
                            except:
                                is_x = True # Fail to parse
                        
                        if is_x:

                            painter.setPen(QPen(QColor("#ff5555"), 1))
                            mid_bit = sub_y + self.row_height // 2
                            # Draw 'X' cross
                            painter.drawLine(int(curr_x), int(sub_y + 10), int(next_x), int(sub_y + 30))
                            painter.drawLine(int(curr_x), int(sub_y + 30), int(next_x), int(sub_y + 10))
                        elif is_z:
                             painter.setPen(QPen(QColor("#888888"), 1, Qt.PenStyle.DashLine))
                             mid = sub_y + self.row_height // 2
                             painter.drawLine(int(curr_x), int(mid), int(next_x), int(mid))
                        else:
                             painter.setPen(QPen(base_color, 1))
                             curr_y_bit = bit_high_y if bit_val else bit_low_y
                             
                             if t == 0:
                                 path_bit.moveTo(curr_x, curr_y_bit)
                             else:
                                 path_bit.lineTo(curr_x, curr_y_bit)
                                 
                             path_bit.lineTo(next_x, curr_y_bit)
                    
                    painter.drawPath(path_bit)

        # --- BINARY RENDER LOGIC (Cycle by Cycle usually fine, but path is continuous) ---
        else: 
            for t in range(self.project.total_cycles):
                curr_x = start_x + t * cw
                next_x = curr_x + cw
                
                if signal.type == SignalType.CLK:
                    # --- Custom Clock Render Logic (Sub-cycle precision) ---
                    # Period is defined by clk_mod (1 = 1 cycle, 2 = 2 cycles, etc.)
                    period = max(1, signal.clk_mod)
                    half = period / 2.0
                    
                    # 1. Determine Start State at 't'
                    phase = t % period
                    is_first_half = (phase < half)
                    
                    # Logic: Rising Edge = Start High (Transition 0->1 happens AT the boundary)
                    is_high = is_first_half if signal.clk_rising_edge else (not is_first_half)
                    
                    curr_val = '1' if is_high else '0'
                    curr_y = high_y if curr_val == '1' else low_y
                    
                    if t == 0:
                        path.moveTo(curr_x, curr_y)
                        
                    # 2. Check for Mid-Cycle Switch
                    # Occurs if (t + 0.5) is a multiple of (period/2)
                    # Specifically, if (2*t + 1) % period == 0
                    if (2 * t + 1) % period == 0:
                        mid_x = curr_x + cw / 2.0
                        path.lineTo(mid_x, curr_y)
                        
                        # Invert for second half
                        opp_y = low_y if curr_val == '1' else high_y
                        path.lineTo(mid_x, opp_y)
                        path.lineTo(next_x, opp_y)
                        curr_y = opp_y # End Y for vertical transition check
                    else:
                        path.lineTo(next_x, curr_y)
                        
                    # 3. Vertical Transition to Next Cycle
                    if t < self.project.total_cycles - 1:
                        phase_next = (t + 1) % period
                        is_first_half_next = (phase_next < half)
                        is_high_next = is_first_half_next if signal.clk_rising_edge else (not is_first_half_next)
                        
                        next_y = high_y if is_high_next else low_y
                        if curr_y != next_y:
                            path.lineTo(next_x, next_y)
                            
                else:
                    # --- Standard Binary Signal Logic ---
                    val = get_val(t)
                    curr_y = high_y if val == '1' else low_y
                    
                    if t == 0:
                        path.moveTo(curr_x, curr_y)
                    
                    path.lineTo(next_x, curr_y)
                    
                    # Draw Vertical Transition
                    if t < self.project.total_cycles - 1:
                        next_val = get_val(t+1)
                        next_y = high_y if next_val == '1' else low_y
                        
                        if curr_y != next_y:
                            path.lineTo(next_x, next_y)
            
            painter.setPen(QPen(base_color, 2))
            painter.drawPath(path)
            
        if is_dragging:
            painter.setOpacity(1.0)


    def draw_selection_highlight(self, painter: QPainter):
        # Draw All Selected Regions
        cw = self.project.cycle_width
        
        # Use Preview regions if moving, else actual selection
        regions_to_draw = self.selected_regions
        if self.is_moving_block and hasattr(self, 'preview_selection_regions') and self.preview_selection_regions:
            regions_to_draw = self.preview_selection_regions
        
        for (sig_idx, start, end) in regions_to_draw:
            if sig_idx >= len(self.project.signals): continue
            
            x1 = self.signal_header_width + start * cw
            x2 = self.signal_header_width + (end + 1) * cw
            
            y = self.header_height + sig_idx * self.row_height
            
            # Draw explicit box (Yellow/Cyan) to show "Modify Position"
            rect = QRect(int(x1), int(y), int(x2 - x1), int(self.row_height))
            
            # Outer glow/border
            painter.setPen(QPen(QColor("#ffaa00"), 3)) # Orange highlight
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
        
    def draw_guide(self, painter: QPainter):
        if not self.hover_pos: return
        sig_idx, cycle_idx = self.hover_pos
        cw = self.project.cycle_width
        
        # Highlight Cycle Column
        x = self.signal_header_width + cycle_idx * cw
        painter.fillRect(int(x), 0, int(cw), int(self.height()), QColor(255, 255, 255, 10))
        
        # Highlight Signal Row
        y = self.header_height + sig_idx * self.row_height
        painter.setPen(QPen(QColor("#00d2ff"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(0, int(y), int(self.width()), int(self.row_height))
        

    def get_block_bounds(self, signal, cycle_idx):
        """Helper to find the start and end cycles of a contiguous value block."""
        if cycle_idx < 0 or cycle_idx >= self.project.total_cycles:
             return cycle_idx, cycle_idx, 'X'
             
        val = signal.get_value_at(cycle_idx)
        o_start = cycle_idx
        o_end = cycle_idx
        
        # Only expand for defined values (Not 'X')
        if val != 'X':
            # Scan Left
            for t in range(cycle_idx, -1, -1):
                if signal.get_value_at(t) == val: 
                    o_start = t
                else: 
                    break
            
            # Scan Right
            for t in range(cycle_idx, self.project.total_cycles):
                if signal.get_value_at(t) == val: 
                    o_end = t
                else: 
                    break
                
        return o_start, o_end, val

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        self.last_global_pos = event.globalPosition().toPoint()
        
        # Update Hover Pos
        if x > self.signal_header_width and y > self.header_height:
            cw = self.project.cycle_width
            h_cycle_idx = (x - self.signal_header_width) // cw
            h_sig_idx, is_sub, sub_idx = self.get_signal_from_y(y)
            
            if h_sig_idx is not None and 0 <= h_sig_idx < len(self.project.signals) and 0 <= h_cycle_idx < self.project.total_cycles:
                self.hover_pos = (h_sig_idx, h_cycle_idx)
            else:
                self.hover_pos = None
        else:
            self.hover_pos = None
        
        # --- Auto-Scroll Detection ---
        is_dragging_any = (self.is_painting or 
                           self.is_moving_block or 
                           self.is_editing_duration or 
                           getattr(self, 'is_selection_sweeping', False) or
                           self.dragging_signal_index is not None)
                           
        if is_dragging_any:
            parent = self.parent()
            if parent:
                vp_pos = self.mapTo(parent, event.pos())
                vp_rect = parent.rect()
                
                margin = 30
                if vp_pos.x() > vp_rect.width() - margin:
                    self.auto_scroll_direction = 1
                    if not self.scroll_timer.isActive():
                        self.scroll_timer.start()
                elif vp_pos.x() < margin:
                    self.auto_scroll_direction = -1
                    if not self.scroll_timer.isActive():
                        self.scroll_timer.start()
                else:
                    self.auto_scroll_direction = 0
                    self.scroll_timer.stop()
        else:
             self.auto_scroll_direction = 0
             self.scroll_timer.stop()
        
        if self.long_press_timer.isActive():
            diff = (event.pos() - self.paint_start_pos).manhattanLength() if self.paint_start_pos else 0
            if self.press_start_pos:
                 diff = max(diff, (event.pos() - self.press_start_pos).manhattanLength())
            
            if diff > 5:
                self.long_press_timer.stop()
        
        # --- IMMEDIATE MOVE ---
        if getattr(self, 'allow_immediate_move', False) and not self.is_moving_block:
             diff = (event.pos() - self.press_start_pos).manhattanLength() if self.press_start_pos else 0
             if diff > 5:
                  self.start_moving_block()
                  return 
        
        # --- SWEEP SELECTION ---
        if getattr(self, 'is_selection_sweeping', False):
            if self.hover_pos:
                sig_idx, cycle_idx = self.hover_pos
                if 0 <= sig_idx < len(self.project.signals):
                    signal = self.project.signals[sig_idx]
                    o_start, o_end, val = self.get_block_bounds(signal, cycle_idx)
                    current_region = (sig_idx, o_start, o_end)
                    
                    if not self.is_part_of_selection(current_region):
                        self.selected_regions.append(current_region)
                        self.update()
            return

        if self.paint_start_pos:
            diff = (event.pos() - self.paint_start_pos).manhattanLength()
            if diff > 5:
                self.is_painting = True
                
            if self.is_painting:
                # Paint!
                sig_idx, is_sub, sub_idx = self.get_signal_from_y(y)

                if sig_idx is not None and 0 <= sig_idx < len(self.project.signals):
                    signal = self.project.signals[sig_idx]
                    if signal.type in [SignalType.INPUT, SignalType.OUTPUT, SignalType.INOUT]:
                         cw = self.project.cycle_width
                         cycle_idx = int((x - self.signal_header_width) / cw)
                         
                         if cycle_idx >= 0:
                             signal.set_value_at(cycle_idx, self.paint_val)
                             if cycle_idx >= self.project.total_cycles:
                                 if self.auto_scroll_direction == 0:
                                     self.project.total_cycles = cycle_idx + 1
                                     self.cycles_changed.emit(self.project.total_cycles)
                                     self.update_dimensions()

                             self.data_changed.emit()
                             self.update()
                             
        if self.is_moving_block:
             cw = self.project.cycle_width
             raw_delta_px = x - self.drag_start_x
             delta_float = raw_delta_px / cw
             delta = int(round(delta_float))
             
             self.move_target_cycle = self.move_drag_start_cycle + delta
             
             # Re-generate previews for ALL moving blocks
             self.preview_signal_values = {} 
             if not hasattr(self, 'move_new_regions_map'):
                 self.move_new_regions_map = {} 
             self.move_new_regions_map = {} 
             
             signals_to_update = {}
             sorted_sel = sorted(self.selected_regions, key=lambda r: (r[0], r[1]))
             
             for region in sorted_sel:
                 s_idx = region[0]
                 if s_idx not in signals_to_update:
                     signals_to_update[s_idx] = []
                 signals_to_update[s_idx].append(region)
             
             for s_idx, regions in signals_to_update.items():
                 if s_idx not in self.moving_blocks_snapshot:
                     continue
                 
                 orig_full_values = self.moving_blocks_snapshot[s_idx]
                 preview = list(orig_full_values)
                 
                 # 1. DELETE
                 regions_desc = sorted(regions, key=lambda r: r[1], reverse=True)
                 for _, start, end in regions_desc:
                     if start < len(preview):
                         safe_end = min(end, len(preview) - 1)
                         if safe_end >= start:
                             del preview[start : safe_end + 1]

                 # 2. PREPARE INSERTION
                 insert_tasks = []
                 regions_asc = sorted(regions, key=lambda r: r[1])
                 
                 for _, start, end in regions_asc:
                     block_vals = []
                     if start < len(orig_full_values):
                         safe_end = min(end, len(orig_full_values) - 1)
                         block_vals = orig_full_values[start : safe_end + 1]
                     else:
                         block_vals = ['X'] * (end - start + 1)
                         
                     target_start = start + delta
                     insert_tasks.append({
                         'target': target_start,
                         'values': block_vals
                     })
                 
                 # 3. APPLY INSERTIONS
                 insert_tasks.sort(key=lambda x: x['target'])
                 self.move_new_regions_map[s_idx] = []
                 
                 for task in insert_tasks:
                     tgt = task['target']
                     vals = task['values']
                     if tgt < 0: tgt = 0
                     
                     if tgt > len(preview):
                         preview.extend(['X'] * (tgt - len(preview)))
                     
                     preview[tgt:tgt] = vals
                     
                     new_blk_len = len(vals)
                     self.move_new_regions_map[s_idx].append((tgt, tgt + new_blk_len - 1))
                 
                 self.preview_signal_values[s_idx] = preview
             
             # Preview Regions Update
             self.preview_selection_regions = []
             for (sig_idx, start, end) in self.selected_regions:
                 n_start = max(0, start + delta_float)
                 n_end = n_start + (end - start)
                 self.preview_selection_regions.append((sig_idx, n_start, n_end))
             
             self.update()
             return

        # 1. Handle Duration Dragging
        if self.is_editing_duration and self.edit_signal_index is not None:
             self.is_duration_dragged = True
             cw = self.project.cycle_width
             current_cycle = int((x - self.signal_header_width) / cw)
             current_cycle = max(0, min(current_cycle, self.project.total_cycles - 1))
             
             signal = self.project.signals[self.edit_signal_index]
             
             if self.edit_initial_values:
                 signal.values = list(self.edit_initial_values)

             if self.edit_mode is None:
                 diff = x - self.press_start_pos.x()
                 if abs(diff) < 5: return 
                 if diff < 0: self.edit_mode = 'START'
                 else: self.edit_mode = 'END'
             
             left_bound = 0
             right_bound = self.project.total_cycles - 1
             
             if self.is_insert_mode:
                 for t in range(self.edit_orig_start - 1, -1, -1):
                     val_at_t = self.edit_initial_values[t] if t < len(self.edit_initial_values) else 'X'
                     if val_at_t != 'X' and val_at_t != self.edit_value:
                         left_bound = t + 1
                         break
                 for t in range(self.edit_orig_end + 1, self.project.total_cycles):
                     val_at_t = self.edit_initial_values[t] if t < len(self.edit_initial_values) else 'X'
                     if val_at_t != 'X' and val_at_t != self.edit_value:
                         right_bound = t - 1
                         break
             
             delta = current_cycle - self.edit_start_cycle
             final_start = self.edit_orig_start
             final_end = self.edit_orig_end
             
             if self.edit_mode == 'END':
                 target = self.edit_orig_end + delta
                 final_end = max(self.edit_orig_start, min(target, right_bound))
                 final_start = self.edit_orig_start
                 
                 for t in range(final_start, final_end + 1):
                     signal.set_value_at(t, self.edit_value)
                 if final_end < self.edit_orig_end:
                     for t in range(final_end + 1, self.edit_orig_end + 1):
                         signal.set_value_at(t, 'X')
                         
             elif self.edit_mode == 'START':
                 target = self.edit_orig_start + delta
                 final_start = max(left_bound, min(target, self.edit_orig_end))
                 final_end = self.edit_orig_end
                 
                 for t in range(final_start, final_end + 1):
                     signal.set_value_at(t, self.edit_value)
                 if final_start > self.edit_orig_start:
                     for t in range(self.edit_orig_start, final_start):
                         signal.set_value_at(t, 'X')
             
             self.data_changed.emit()
             self.region_updated.emit(self.edit_signal_index, final_start, final_end)
             self.update()
             return

        if self.reorder_candidate_idx is not None:
             diff = (event.pos() - self.paint_start_pos).manhattanLength()
             if diff > 5:
                 self.dragging_signal_index = self.reorder_candidate_idx
                 self.reorder_candidate_idx = None
                 self.current_drag_y = y
                 self.update()

        # 2. Handle Reorder Dragging
        if self.dragging_signal_index is not None:
            self.current_drag_y = y
            self.update()
            return
        
        # 3. Handle Hover
        if x > self.signal_header_width and y > self.header_height:
            cw = self.project.cycle_width
            cycle_idx = (x - self.signal_header_width) // cw
            sig_idx, _, _ = self.get_signal_from_y(y)
            
            if sig_idx is not None and 0 <= sig_idx < len(self.project.signals) and 0 <= cycle_idx < self.project.total_cycles:
                self.hover_pos = (sig_idx, cycle_idx)
                self.update()
                return

        self.hover_pos = None
        self.update()
        
        # --- Auto-Scroll Detection ---
        # Only if dragging something
        is_dragging_any = (self.is_painting or 
                           self.is_moving_block or 
                           self.is_editing_duration or 
                           getattr(self, 'is_selection_sweeping', False) or
                           self.dragging_signal_index is not None)
                           
        if is_dragging_any:
            # Check bounds relative to Viewport
            # We can use mapToParent(pos) if parent is viewport?
            # Or mapToGlobal compared to parent's Global Rect?
            parent = self.parent()
            # Viewport
            if parent:
                # Viewport coordinates
                vp_pos = self.mapTo(parent, event.pos())
                vp_rect = parent.rect()
                
                margin = 30
                if vp_pos.x() > vp_rect.width() - margin:
                    self.auto_scroll_direction = 1
                    if not self.scroll_timer.isActive():
                        self.scroll_timer.start()
                elif vp_pos.x() < margin:
                    self.auto_scroll_direction = -1
                    if not self.scroll_timer.isActive():
                        self.scroll_timer.start()
                else:
                    self.auto_scroll_direction = 0
                    self.scroll_timer.stop()
        else:
             self.auto_scroll_direction = 0
             self.scroll_timer.stop()
        
        if self.long_press_timer.isActive():
            diff = (event.pos() - self.paint_start_pos).manhattanLength() if self.paint_start_pos else 0
            # Also check distance from initial click for canvas items
            if self.press_start_pos:
                 diff = max(diff, (event.pos() - self.press_start_pos).manhattanLength())
            
            if diff > 5:
                # print(f"DEBUG: Timer Cancelled. Diff: {diff}")
                self.long_press_timer.stop()
                # If we moved, it's a normal drag (Duration Edit or Paint), NOT a long press move
        
        # --- IMMEDIATE MOVE (Multi-Selection) ---
        if getattr(self, 'allow_immediate_move', False) and not self.is_moving_block and not self.is_editing_duration:
             diff = (event.pos() - self.press_start_pos).manhattanLength() if self.press_start_pos else 0
             if diff > 5:
                  self.start_moving_block()
                  return # Stop processing (don't paint or duration edit)
        
        # --- SWEEP SELECTION (Ctrl + Drag) ---
        if getattr(self, 'is_selection_sweeping', False):
            if self.hover_pos:
                sig_idx, cycle_idx = self.hover_pos
                if 0 <= sig_idx < len(self.project.signals):
                    signal = self.project.signals[sig_idx]
                    
                    # Use helper to get block
                    o_start, o_end, val = self.get_block_bounds(signal, cycle_idx)
                    current_region = (sig_idx, o_start, o_end)
                    
                    if not self.is_part_of_selection(current_region):
                        self.selected_regions.append(current_region)
                        self.update()
            return

        if self.paint_start_pos:
            diff = (event.pos() - self.paint_start_pos).manhattanLength()
            if diff > 5:
                self.is_painting = True
                
            if self.is_painting:
                # Paint!
                sig_idx = (y - self.header_height) // self.row_height
                if 0 <= sig_idx < len(self.project.signals):
                    # Ensure we are painting the same signal we started on?
                    # Or allow cross-lane painting?
                    # Usually stricter to keep to start signal or allow changing if we drag vertically?
                    # Using start signal index is safer.
                    # But if we didn't store start signal idx, we re-calculate.
                    # Let's rely on Y.
                    
                    signal = self.project.signals[sig_idx]
                    if signal.type in [SignalType.INPUT, SignalType.OUTPUT, SignalType.INOUT]:
                         cw = self.project.cycle_width
                         # Use round logic
                         cycle_idx = int(round((x - self.signal_header_width) / cw))
                         # Floor logic might be better for "painting over cycle X", 
                         # but consistent with cursor is good.
                         # Paint implies touching the cycle.
                         # Let's use standard floor index for "cell under mouse".
                         cycle_idx = int((x - self.signal_header_width) / cw)
                         
                         if cycle_idx >= 0:
                             signal.set_value_at(cycle_idx, self.paint_val)
                             
                             # Auto-expand ONLY if not auto-scrolling
                             if cycle_idx >= self.project.total_cycles:
                                 if self.auto_scroll_direction == 0:
                                     self.project.total_cycles = cycle_idx + 1
                                     self.cycles_changed.emit(self.project.total_cycles)
                                     self.update_dimensions()

                             self.data_changed.emit()
                             self.update()
        if self.is_moving_block:
             cw = self.project.cycle_width
             
             # Calculate Delta based on PIXELS (Smooth)
             raw_delta_px = x - self.drag_start_x
             delta_float = raw_delta_px / cw
             delta = int(round(delta_float)) # Integer Delta for Data Logic
             
             current_cycle = int(round((x - self.signal_header_width) / cw))
             current_cycle = max(0, current_cycle) 
             self.move_target_cycle = self.move_drag_start_cycle + delta
             
             # Re-generate previews for ALL moving blocks
             self.preview_signal_values = {} # Reset
             if not hasattr(self, 'move_new_regions_map'):
                 self.move_new_regions_map = {} 
             self.move_new_regions_map = {} # Reset map
             
             # Group moves by signal index
             signals_to_update = {}
             # Sort selection first to handle multi-select cleanly
             sorted_sel = sorted(self.selected_regions, key=lambda r: (r[0], r[1]))
             
             for region in sorted_sel:
                 s_idx = region[0]
                 if s_idx not in signals_to_update:
                     signals_to_update[s_idx] = []
                 signals_to_update[s_idx].append(region)
             
             for s_idx, regions in signals_to_update.items():
                 if s_idx not in self.moving_blocks_snapshot:
                     continue # Should have snapshot
                 
                 # Base content (Original signal state)
                 orig_full_values = self.moving_blocks_snapshot[s_idx]
                 preview = list(orig_full_values)
                 
                 # 1. DELETE STEP (Remove all moving blocks from the timeline)
                 # Sort regions Descending to avoid index shift issues during delete
                 regions_desc = sorted(regions, key=lambda r: r[1], reverse=True)
                 
                 for _, start, end in regions_desc:
                     # Remove [start, end]
                     if start < len(preview):
                         # Handle end bound
                         safe_end = min(end, len(preview) - 1)
                         if safe_end >= start:
                             del preview[start : safe_end + 1]

                 # 2. PREPARE INSERTION TASKS
                 insert_tasks = []
                 regions_asc = sorted(regions, key=lambda r: r[1])
                 
                 for _, start, end in regions_asc:
                     # Extract the block values from original snapshot
                     block_vals = []
                     if start < len(orig_full_values):
                         safe_end = min(end, len(orig_full_values) - 1)
                         block_vals = orig_full_values[start : safe_end + 1]
                     else:
                         block_vals = ['X'] * (end - start + 1)
                         
                     # Target Start = Original Start + Delta
                     target_start = start + delta
                     
                     insert_tasks.append({
                         'target': target_start,
                         'values': block_vals
                     })
                 
                 # 3. APPLY INSERTIONS
                 # Sort by target index ascending
                 insert_tasks.sort(key=lambda x: x['target'])
                 
                 self.move_new_regions_map[s_idx] = []
                 
                 for task in insert_tasks:
                     tgt = task['target']
                     vals = task['values']
                     
                     if tgt < 0: tgt = 0
                     
                     # Check bounds and Pad if needed
                     curr_len = len(preview)
                     if tgt > curr_len:
                         preview.extend(['X'] * (tgt - curr_len))
                         tgt = len(preview) # Cap at end after extension
                     
                     # Insert
                     preview[tgt:tgt] = vals
                     
                     # Record position
                     new_end = tgt + len(vals) - 1
                     self.move_new_regions_map[s_idx].append((s_idx, tgt, new_end))

                 self.preview_signal_values[s_idx] = preview
             
             # Decoupled Visual Preview: Visualize FLOAT delta (Smooth Sliding)
             self.preview_selection_regions = []
             for (sig_idx, start, end) in self.selected_regions:
                 n_start = max(0, start + delta_float) # Keep as Float!
                 n_end = n_start + (end - start)
                 self.preview_selection_regions.append((sig_idx, n_start, n_end))
             
             self.update()
             return

        # 1. Handle Duration Dragging (Highest Priority)
        if self.is_editing_duration and self.edit_signal_index is not None:
             self.is_duration_dragged = True
             cw = self.project.cycle_width
             # Calculate current cycle
             current_cycle = int((x - self.signal_header_width) / cw)
             current_cycle = max(0, min(current_cycle, self.project.total_cycles - 1))
             
             signal = self.project.signals[self.edit_signal_index]
             
             # Restore state from start of drag
             if self.edit_initial_values:
                 signal.values = list(self.edit_initial_values)

             # --- Determine Edit Mode from Drag Direction (If not yet set) ---
             if self.edit_mode is None:
                 diff = x - self.press_start_pos.x()
                 if abs(diff) < 5:
                     return # Wait for clear movement
                 
                 # Drag Left -> Modify Start (Left Edge)
                 # Drag Right -> Modify End (Right Edge)
                 if diff < 0:
                     self.edit_mode = 'START'
                 else:
                     self.edit_mode = 'END'
             
             # --- COLLISION DETECTION ---
             # Only active in INSERT Mode. In Overwrite mode, we can drag over anything.
             
             left_bound = 0
             right_bound = self.project.total_cycles - 1
             
             if self.is_insert_mode:
                 # Find bounds based on initial state. 
                 # We can only expand into 'X' or our own value (effectively shrinking or re-occupying).
                 # We cannot expand into other defined values.
                 
                 # 1. Left Bound search (Scan left from orig_start - 1)
                 for t in range(self.edit_orig_start - 1, -1, -1):
                     val_at_t = 'X'
                     if t < len(self.edit_initial_values):
                         val_at_t = self.edit_initial_values[t]
                         
                     if val_at_t != 'X' and val_at_t != self.edit_value:
                         left_bound = t + 1
                         break
                
                 # 2. Right Bound search (Scan right from orig_end + 1)
                 for t in range(self.edit_orig_end + 1, self.project.total_cycles):
                     val_at_t = 'X'
                     if t < len(self.edit_initial_values):
                         val_at_t = self.edit_initial_values[t]
                         
                     if val_at_t != 'X' and val_at_t != self.edit_value:
                         right_bound = t - 1
                         break
             
             # Clamp cursor to bounds
             # clamped_cycle = max(left_bound, min(current_cycle, right_bound)) # Old Snap Logic
             
             # RELATIVE DRAG LOGIC
             delta = current_cycle - self.edit_start_cycle
             
             final_start = self.edit_orig_start
             final_end = self.edit_orig_end
             
             if self.edit_mode == 'END':
                 # Adjust Right Edge
                 target = self.edit_orig_end + delta
                 # Clamp target
                 final_end = max(self.edit_orig_start, min(target, right_bound))
                 final_start = self.edit_orig_start
                 
                 # 1. Fill Content [orig_start, new_end]
                 # Note: signal.values might need extension if final_end > len
                 for t in range(final_start, final_end + 1):
                     signal.set_value_at(t, self.edit_value)
                     
                 # 2. Clear Excess [new_end+1, orig_end] (SHRINKING FROM RIGHT)
                 if final_end < self.edit_orig_end:
                     for t in range(final_end + 1, self.edit_orig_end + 1):
                         signal.set_value_at(t, 'X')
                         
             elif self.edit_mode == 'START':
                 # Adjust Left Edge
                 target = self.edit_orig_start + delta
                 # Clamp target
                 final_start = max(left_bound, min(target, self.edit_orig_end))
                 final_end = self.edit_orig_end
                 
                 # 1. Fill Content [new_start, orig_end]
                 for t in range(final_start, final_end + 1):
                     signal.set_value_at(t, self.edit_value)
                     
                 # 2. Clear Excess [orig_start, new_start-1] (SHRINKING FROM LEFT)
                 if final_start > self.edit_orig_start:
                     for t in range(self.edit_orig_start, final_start):
                         signal.set_value_at(t, 'X')
            
             self.data_changed.emit()
             # Emit update to sync Editor Panel
             self.region_updated.emit(self.edit_signal_index, final_start, final_end)
                 
             self.update()
             return
            
             self.data_changed.emit()
             # Emit update to sync Editor Panel
             self.region_updated.emit(self.edit_signal_index, final_start, final_end)
                 
             self.update()
             return

        if self.reorder_candidate_idx is not None:
             diff = (event.pos() - self.press_start_pos).manhattanLength()
             if diff > 5:
                 self.dragging_signal_index = self.reorder_candidate_idx
                 self.reorder_candidate_idx = None # Committed to drag
                 self.current_drag_y = y
                 self.update()

        # 2. Handle Reorder Dragging
        if self.dragging_signal_index is not None:
            self.current_drag_y = y
            self.update()
            return
        
        # 3. Handle Hover
        if x > self.signal_header_width and y > self.header_height:
            cw = self.project.cycle_width
            cycle_idx = (x - self.signal_header_width) // cw
            sig_idx = (y - self.header_height) // self.row_height
            
            if 0 <= sig_idx < len(self.project.signals) and 0 <= cycle_idx < self.project.total_cycles:
                self.hover_pos = (sig_idx, cycle_idx)
                self.update()
                return

        self.hover_pos = None
        self.update()

    def process_auto_scroll(self):
        if self.auto_scroll_direction == 0:
            return
            
        parent = self.parent()
        while parent and not isinstance(parent, QScrollArea):
            parent = parent.parent()
            
        if parent:
            sb = parent.horizontalScrollBar()
            if sb:
                step = 20 * self.auto_scroll_direction
                sb.setValue(sb.value() + step)
                
                # Synthesize Mouse Event to update drag state
                if hasattr(self, 'last_global_pos') and self.last_global_pos:
                     local_pos = self.mapFromGlobal(self.last_global_pos)
                     
                     # Construct event
                     # Note: We assume LeftButton as primary drag
                     event = QMouseEvent(
                         QEvent.Type.MouseMove,
                         QPointF(local_pos),
                         QPointF(self.last_global_pos),
                         Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier
                     )
                     self.mouseMoveEvent(event)

    def start_moving_block(self):
        """Initiates the block moving mode."""
        if not self.press_context: 
            return
            
        self.long_press_timer.stop() # Ensure timer is off
        
        # Trigger Move Mode
        self.is_moving_block = True
        self.is_editing_duration = False # Cancel duration edit
        
        ctx = self.press_context
        self.move_drag_start_cycle = ctx['cycle_idx']
        self.move_target_cycle = ctx['cycle_idx']
        # Ensure we have a drag start x
        if self.press_start_pos:
            self.drag_start_x = self.press_start_pos.x()
        else:
            self.drag_start_x = 0
        
        # Auto-select if not yet (should be covered by Press, but ensure)
        # If the item under mouse is not in selected_regions, select it.
        clicked_region = ctx['region']
        
        # Use fuzzy containment check (ONLY if not in immediate multi-move mode)
        # If immediate move is allowed, we trust the multi-selection from mousePress
        if not getattr(self, 'allow_immediate_move', False):
            if not self.is_part_of_selection(clicked_region):
                 self.selected_regions = [clicked_region]
            
        # Initialize Snapshots
        self.moving_blocks_snapshot = {}
        for r_sig, r_start, r_end in self.selected_regions:
            r_signal = self.project.signals[r_sig]
            if r_sig not in self.moving_blocks_snapshot:
                self.moving_blocks_snapshot[r_sig] = list(r_signal.values)
            vals = [r_signal.get_value_at(t) for t in range(r_start, r_end+1)]
            key = f"{r_sig}_{r_start}_{r_end}"
            self.moving_blocks_snapshot[key] = vals

        # Initialize Preview
        self.preview_selection_regions = []
        for (s, st, en) in self.selected_regions:
            self.preview_selection_regions.append((s, float(st), float(en)))
            
        self.move_block_info = {
           'sig_idx': ctx['sig_idx'],
           'start': clicked_region[1],
           'end': clicked_region[2],
           'val': ctx['val']
        }
        
        self.setCursor(Qt.CursorShape.SizeAllCursor) # Visual feedback
        self.update()

    def on_long_press(self):
        # Activated after Timer -> Switch to Resize Mode (Duration Edit)
        self.is_moving_block = False
        self.is_editing_duration = True
        
        # Cursor Feedback
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.update()

    def mousePressEvent(self, event):
        self.setFocus() # Ensure we get keyboard events (e.g. keyPress)
        
        x = event.pos().x()
        y = event.pos().y()
        self.press_start_pos = event.pos()
        
        # 1. Expand Button Interaction
        if self.expand_rects:
            for s_idx, rect in self.expand_rects.items():
                if rect.contains(event.pos()):
                    # Toggle Expand
                    if 0 <= s_idx < len(self.project.signals):
                        sig = self.project.signals[s_idx]
                        sig.expanded = not sig.expanded
                        
                        # "Clicking + converts ... to binary" -> Set Display Base to 2
                        if sig.expanded:
                            sig.display_base = 2
                        
                        self.structure_changed.emit()
                        self.update_dimensions()
                        self.update()
                        return
        
        # 2. Get Target Signal
        sig_idx, is_sub, sub_idx = self.get_signal_from_y(y)
        
        if sig_idx is not None and 0 <= sig_idx < len(self.project.signals) and x > self.signal_header_width:
             signal = self.project.signals[sig_idx]
             
             # --- New: Drag-to-Paint & Click Toggle (Binary) ---
             # Handle BOTH Left and Right buttons here
             if signal.type in [SignalType.INPUT, SignalType.OUTPUT, SignalType.INOUT]:
                 # Only Paint if NO Control Modifier
                 if getattr(event.modifiers(), 'value', event.modifiers()) & Qt.KeyboardModifier.ControlModifier:
                     pass # Fall through to selection logic
                 else:
                     self.before_change.emit() # Snapshot before Drag-Paint or Toggle
                     self.paint_start_pos = event.pos()
                     self.paint_val = '1' if event.button() == Qt.MouseButton.LeftButton else '0'
                     self.is_painting = False # Wait for drag
                     return
        
        if event.button() == Qt.MouseButton.LeftButton:
            
            if sig_idx is not None and 0 <= sig_idx < len(self.project.signals):
                # Check for Drag Reorder (Click on Header/Name area)
                if x < self.signal_header_width:
                     # Selection happens immediately
                     self.signal_clicked.emit(sig_idx)
                     
                     # Prepare for potential drag (wait for move threshold)
                     self.reorder_candidate_idx = sig_idx
                     self.current_drag_y = y
                     self.dragging_signal_index = None # Do NOT float yet
                     return

                # Check for Waveform Interaction
                if self.hover_pos:
                    curr_sig_idx, cycle_idx = self.hover_pos
                    signal = self.project.signals[sig_idx]
                    
                    # --- Generic Block Logic ---
                    # Now applies to ALL signals (Bus & Binary)
                    o_start, o_end, val = self.get_block_bounds(signal, cycle_idx)
                    clicked_region = (sig_idx, o_start, o_end)
                    
                    if True: # Wrapping to minimize indentation changes


                        # 1. HANDLING SELECTION
                        # Shift+Click: Range Selection
                        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                            if not self.selected_regions:
                                self.selected_regions = [clicked_region]
                            else:
                                # Range Selection Logic: Select all between Anchor and Current
                                anchor_sig, anchor_start, anchor_end = self.selected_regions[-1]
                                current_sig, current_start, current_end = clicked_region
                                
                                min_sig = min(anchor_sig, current_sig)
                                max_sig = max(anchor_sig, current_sig)
                                
                                # Determine Time Range
                                min_time = min(anchor_start, current_start)
                                max_time = max(anchor_end, current_end)
                                
                                new_selection = []
                                for s in range(min_sig, max_sig + 1):
                                    new_selection.append((s, min_time, max_time))
                                
                                self.selected_regions = new_selection
                                
                            self.bus_selected.emit(sig_idx, cycle_idx)
                            self.update()
                            return
                        
                        # Ctrl+Click: Toggle Selection & Start Sweep
                        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                            # Sweep Mode Engaged
                            self.is_selection_sweeping = True
                            
                            if self.is_part_of_selection(clicked_region):
                                # Deselect: Remove matching region
                                self.selected_regions = [
                                    r for r in self.selected_regions 
                                    if not (r[0] == sig_idx and max(r[1], clicked_region[1]) <= min(r[2], clicked_region[2]))
                                ]
                            else:
                                # Add
                                self.selected_regions.append(clicked_region)
                            
                            self.bus_selected.emit(sig_idx, cycle_idx)
                            self.update()
                            return

                        # 2. START LONG PRESS TIMER (Potential Move)
                        self.press_context = {
                            'sig_idx': sig_idx,
                            'cycle_idx': cycle_idx,
                            'val': val,
                            'region': clicked_region
                        }
                        
                        # --- "Center Split" Limit Logic (User Request) ---
                        # Determine if we are interacting with Start or End edge based on cursor position relative to block center.
                        # Logic:
                        # Center = Start + (Length / 2.0)
                        # Cursor < Center -> Edit Left Edge (START)
                        # Cursor > Center -> Edit Right Edge (END)
                        
                        cw = self.project.cycle_width
                        cycle_float = (x - self.signal_header_width) / cw
                        
                        region_start = o_start
                        region_len = o_end - o_start + 1
                        center_cycle = region_start + (region_len / 2.0)
                        
                        # Pre-determine edit mode
                        if region_len >= 2:
                            # Multi-Cycle: Use Center Split Logic (Positional)
                            if cycle_float < center_cycle:
                                self.edit_mode = 'START'
                            else:
                                self.edit_mode = 'END'
                        else:
                            # Single Cycle: Use Drag Direction (Dynamic)
                            # Leave edit_mode as None, let mouseMoveEvent determine it based on movement delta
                            self.edit_mode = None
                            
                        # Store this for mouseMove to pick up immediately without waiting for diff
                        # (But we still wait for diff > 5 to confirm it is a drag, not just a click)
                        
                        # Check for Immediate Move Condition 
                        # Allow immediate move ONLY if it is a Multi-Selection (User Request).
                        # Single selection (or just clicking one item) requires Long Press.
                        

                        # Helper for Multi-Block Detection
                        # A "Block" is a contiguous range of same value.
                        # If selection has >1 disjoint region OR span has >1 block inside, it is multi.
                        is_multi_block = False
                        if len(self.selected_regions) > 1:
                            is_multi_block = True
                        elif len(self.selected_regions) == 1:
                             r_sig, r_start, r_end = self.selected_regions[0]
                             if 0 <= r_sig < len(self.project.signals):
                                 sig = self.project.signals[r_sig]
                                 # Scan for value change within range
                                 first_val = sig.get_value_at(r_start)
                                 for t in range(r_start + 1, r_end + 1):
                                     if sig.get_value_at(t) != first_val:
                                         is_multi_block = True
                                         break
                        
                        # Check for Immediate Move Condition 
                        # Allow immediate move for any valid selection (User Request: Drag = Move)
                        can_move_immediately = self.is_part_of_selection(clicked_region)
                        self.allow_immediate_move = can_move_immediately
                        
                        if can_move_immediately:
                             # Set up Move context but don't start yet (wait for drag)
                             pass
                             
                        # Always start timer for potential Resize (Long Press)
                        self.long_press_timer.start(500) 

                        # 3. STANDARD CLICK (Replace Selection)
                        # Only reset selection if we didn't just add/toggle
                        # Note: If we are clicking an already selected item, we might be intending to drag it (Move).
                        # But we don't know yet.
                        # If we clear selection now, we lose the multi-selection context for the drag.
                        # CHECK: Is clicked item in current selection?
                        
                        
                        if self.is_part_of_selection(clicked_region):
                             # Defer selection reset until Release (if not dragged)
                             self.pending_selection_reset = True
                             self.pending_click_region = clicked_region
                        else:
                             self.selected_regions = [clicked_region]
                             self.pending_selection_reset = False
                             self.pending_click_region = None
                        
                        self.bus_selected.emit(sig_idx, cycle_idx)
                        
                        # SETUP DURATION EDIT CONTEXT (But do NOT enable it yet)
                        # It will be enabled ONLY if Long Press fires
                        self.is_editing_duration = False
                        self.is_duration_dragged = False 
                        self.edit_signal_index = sig_idx
                        self.edit_start_cycle = cycle_idx
                        self.edit_value = val
                        
                        self.edit_orig_start = o_start
                        self.edit_orig_end = o_end
                        self.edit_initial_values = list(signal.values)
                        
                        # edit_mode is already pre-calculated above!
                           
                                
        elif event.button() == Qt.MouseButton.RightButton:
             # Check for Right Click -> X (For Bus?)
             sig_idx = (y - self.header_height) // self.row_height
             
             if x > self.signal_header_width and 0 <= sig_idx < len(self.project.signals):
                 signal = self.project.signals[sig_idx]
                 if signal.type in [SignalType.BUS_DATA, SignalType.BUS_STATE]:
                     cw = self.project.cycle_width
                     cycle_idx = int((x - self.signal_header_width) / cw)
                     
                     # Check bounds
                     if 0 <= cycle_idx <= self.project.total_cycles:
                         # Insert 'X' at position (Generic Insert)
                         # This shifts everything to the right
                         if cycle_idx < len(signal.values):
                             signal.values.insert(cycle_idx, 'X')
                         else:
                             # If clicking past end, extend to there + 1
                             signal.set_value_at(cycle_idx, 'X')
                             
                         # Update total cycles if we pushed past the limit
                         if len(signal.values) > self.project.total_cycles:
                             self.project.total_cycles = len(signal.values)
                             self.cycles_changed.emit(self.project.total_cycles)
                             
                         self.data_changed.emit()
                         self.update()
                            
    def mouseReleaseEvent(self, event):
        self.reorder_candidate_idx = None
        self.scroll_timer.stop()
        self.auto_scroll_direction = 0
        self.long_press_timer.stop()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.is_selection_sweeping = False
        self.allow_immediate_move = False # Reset immediate move flag
        
        # Handle deferred selection reset (Click without Drag)
        if hasattr(self, 'pending_selection_reset') and self.pending_selection_reset:
             # Reset ONLY if we did NOT move a block AND did NOT drag duration
             was_duration_dragged = getattr(self, 'is_duration_dragged', False)
             
             if not self.is_moving_block and not was_duration_dragged:
                 # It was just a click, reset selection to the single item
                 # Ensure we have the region stored
                 if hasattr(self, 'pending_click_region') and self.pending_click_region:
                     self.selected_regions = [self.pending_click_region]
                     self.bus_selected.emit(self.pending_click_region[0], self.pending_click_region[1])
                     self.update()
             
             self.pending_selection_reset = False
             self.pending_click_region = None
             
        if self.is_moving_block:
            
            # Apply Previews to Real Signals
            if self.preview_signal_values:
                self.before_change.emit() # Snapshot before Drag Commit
                # 1. Update Signals
                for s_idx, new_values in self.preview_signal_values.items():
                    if 0 <= s_idx < len(self.project.signals):
                        signal = self.project.signals[s_idx]
                        signal.values = list(new_values)
                        
                        # Auto-expand project if needed
                        if len(signal.values) > self.project.total_cycles:
                            self.project.total_cycles = len(signal.values)
                            self.cycles_changed.emit(self.project.total_cycles)
                            
                # 2. Update Selection to follow the moved blocks
                new_selection = []
                
                # Use the decoupled visual preview regions for the final selection if available
                # This ensures the selection highlight lands exactly where the user saw it
                if hasattr(self, 'preview_selection_regions') and self.preview_selection_regions:
                     for (sig_idx, start, end) in self.preview_selection_regions:
                         # Snap float preview back to integer for final commit
                         new_selection.append((sig_idx, int(round(start)), int(round(end))))
                
                # Check if we have pre-calculated map from move logic (Fallback)
                elif hasattr(self, 'move_new_regions_map') and self.move_new_regions_map:
                     for s_idx, new_regions_list in self.move_new_regions_map.items():
                         if s_idx in self.preview_signal_values: # Only if signal was updated
                             new_selection.extend(new_regions_list)
                else:
                    # Fallback (Should typically rely on map if move occurred)
                    delta = self.move_target_cycle - self.move_drag_start_cycle
                    for (sig_idx, start, end) in self.selected_regions:
                        n_start = max(0, start + delta)
                        n_end = n_start + (end - start)
                        new_selection.append((sig_idx, n_start, n_end))
                
                self.selected_regions = new_selection
                
                # Update last selected for properties
                if self.selected_regions:
                     last = self.selected_regions[-1]
                     # Ensure we don't crash if empty
                     self.bus_selected.emit(last[0], last[1])
            
            self.data_changed.emit()
            self.update_dimensions()
            
            self.is_moving_block = False
            self.move_block_info = None
            self.preview_signal_values = {}
            if hasattr(self, 'move_new_regions_map'):
                self.move_new_regions_map = {}
            if hasattr(self, 'preview_selection_regions'):
                self.preview_selection_regions = []
            self.update()
            return

        if self.paint_start_pos:
            # If we didn't drag enough to paint, treat as Click -> Toggle
            if not self.is_painting:
                # Toggle
                x = event.pos().x()
                y = event.pos().y()
                cw = self.project.cycle_width
                cycle_idx = int((x - self.signal_header_width) / cw)
                sig_idx = (y - self.header_height) // self.row_height
                
                if 0 <= sig_idx < len(self.project.signals):
                    signal = self.project.signals[sig_idx]
                    # Double check type just in case
                    if signal.type in [SignalType.INPUT, SignalType.OUTPUT, SignalType.INOUT]:
                         curr = signal.get_value_at(cycle_idx)
                         # Toggle
                         new_val = '0' if curr == '1' else '1'
                         signal.set_value_at(cycle_idx, new_val)
                         self.data_changed.emit()
            
            # Reset
            self.paint_start_pos = None
            self.is_painting = False
            self.paint_val = None
            self.update()
            return

        if self.is_editing_duration:
            self.is_editing_duration = False
            self.edit_signal_index = None
            self.edit_value = None
            self.edit_mode = None
            self.edit_initial_values = None
        
        if self.dragging_signal_index is not None:
             # Calculate drop index
             drop_idx = self.get_drop_index(event.pos().y())
             
             # Reorder signals
             if drop_idx != self.dragging_signal_index and drop_idx <= len(self.project.signals):
                 # Move item
                 item = self.project.signals.pop(self.dragging_signal_index)
                 if drop_idx > self.dragging_signal_index:
                     drop_idx -= 1
                 self.project.signals.insert(drop_idx, item)
                 self.structure_changed.emit()
                 self.data_changed.emit()
             
             self.dragging_signal_index = None
             self.update()

    def mouseDoubleClickEvent(self, event):
        pass

    def keyPressEvent(self, event):
        if not self.selected_region:
            super().keyPressEvent(event)
            return
            
        if event.matches(QKeySequence.StandardKey.Copy) or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C):
            self.copy_selection()
            
        elif event.matches(QKeySequence.StandardKey.Paste) or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V):
            self.paste_selection()

        elif event.key() == Qt.Key.Key_Left:
            self.move_selection(-1, 0)
        elif event.key() == Qt.Key.Key_Right:
            self.move_selection(1, 0)
        elif event.key() == Qt.Key.Key_Up:
            self.move_selection(0, -1)
        elif event.key() == Qt.Key.Key_Down:
            self.move_selection(0, 1)

        # Removed duplicate move_selection stub

        else:
            super().keyPressEvent(event)

    def copy_selection(self):
        if not self.selected_regions:
            return
            
        from PyQt6.QtWidgets import QApplication
        import json
        
        # 1. Sort Regions
        # Sort by Signal Index, then Start Time
        sorted_regions = sorted(self.selected_regions, key=lambda r: (r[0], r[1]))
        
        # 2. Normalize Signal Index (Top-most selected signal becomes 0)
        min_sig_idx = sorted_regions[0][0]
        
        data = []
        for sig_idx, start, end in sorted_regions:
            if 0 <= sig_idx < len(self.project.signals):
                signal = self.project.signals[sig_idx]
                
                # Extract Data
                values = []
                for t in range(start, end + 1):
                    values.append(signal.get_value_at(t))
                    
                data.append({
                    'rel_sig': sig_idx - min_sig_idx,
                    'values': values,
                    'start_offset': start - sorted_regions[0][1] # Relative to very first block start
                })
        
        clipboard_text = json.dumps(data)
        QApplication.clipboard().setText(clipboard_text)

    def paste_selection(self):
        from PyQt6.QtWidgets import QApplication
        import json
        
        text = QApplication.clipboard().text()
        if not text: return
        
        try:
            data = json.loads(text)
            if not isinstance(data, list): return
        except:
            return # Not ours or invalid
            
        # Determine Paste Anchor
        anchor_sig_idx = 0
        anchor_cycle = 0
        
        if self.selected_regions:
            sorted_sel = sorted(self.selected_regions, key=lambda r: (r[0], r[1]))
            anchor_sig_idx, anchor_cycle, _ = sorted_sel[0]
        elif self.hover_pos:
            anchor_sig_idx, anchor_cycle = self.hover_pos
        else:
            return # No target
            
        # Snapshot before paste
        self.before_change.emit()
        
        # Group Data by Signal
        # data = list of {rel_sig, values, start_offset}
        from collections import defaultdict
        grouped_data = defaultdict(list)
        for item in data:
            grouped_data[item.get('rel_sig', 0)].append(item)
            
        new_selection = []
        max_len_needed = 0
        
        # Apply Insert per Signal
        for rel_sig, items in grouped_data.items():
            target_sig_idx = anchor_sig_idx + rel_sig
            if not (0 <= target_sig_idx < len(self.project.signals)):
                continue
                
            skill_signal = self.project.signals[target_sig_idx]
            
            # 1. Determine Span of this signal's paste data
            # Offsets are relative to anchor_cycle
            # Find min_offset for insertion point, and construct buffer
            min_offset = min(item.get('start_offset', 0) for item in items)
            
            # Max extent relative to min_offset
            # We want to create a contiguous buffer from min_offset to max_offset_end
            max_offset_end = max(item.get('start_offset', 0) + len(item.get('values', [])) for item in items)
            
            span_len = max_offset_end - min_offset
            insert_buffer = ['X'] * span_len
            
            # Fill Buffer
            for item in items:
                v = item.get('values', [])
                off = item.get('start_offset', 0) - min_offset
                for i, val in enumerate(v):
                    insert_buffer[off + i] = val
            
            # 2. Insert into Signal
            insert_pos = anchor_cycle + min_offset
            
            # Ensure signal is long enough to insert at pos
            curr_len = len(skill_signal.values)
            if insert_pos > curr_len:
                skill_signal.values.extend(['X'] * (insert_pos - curr_len))
                
            # PERFORM INSERT
            skill_signal.values[insert_pos:insert_pos] = insert_buffer
            
            # 3. Track Selection
            new_selection.append((target_sig_idx, insert_pos, insert_pos + span_len - 1))
            
            max_len_needed = max(max_len_needed, len(skill_signal.values))

        # Update Project Cycles
        if max_len_needed > self.project.total_cycles:
            self.project.total_cycles = max_len_needed
            self.cycles_changed.emit(self.project.total_cycles)
            
        # Update Visual Selection
        if new_selection:
            self.selected_regions = new_selection
            
        self.data_changed.emit()
        self.update()

    def move_selection(self, dx, dy=0):
        if not self.selected_region: return
        
        self.before_change.emit() # Snapshot before arrow move
        
        sig_idx, start, end = self.selected_region
        new_cycle = start # Default to current start
        
        # Horizontal Move
        if dx != 0:
            if dx < 0:
                new_cycle = max(0, start - 1)
            else:
                new_cycle = min(self.project.total_cycles - 1, end + 1)
        
        # Vertical Move
        new_sig_idx = sig_idx
        if dy != 0:
            new_sig_idx = sig_idx + dy
            # Clamp to signal list
            new_sig_idx = max(0, min(len(self.project.signals) - 1, new_sig_idx))
            
        # Check if anything changed
        if (new_cycle == start and new_cycle == end and new_sig_idx == sig_idx):
             return
             
        # Resolve New Selection
        signal = self.project.signals[new_sig_idx]
        val = signal.get_value_at(new_cycle)
        
        o_start = new_cycle
        o_end = new_cycle
        
        if signal.type in [SignalType.BUS_DATA, SignalType.BUS_STATE] and val != 'X':
             # Expand block (BUS Logic)
             for t in range(new_cycle, -1, -1):
                if signal.get_value_at(t) == val:
                    o_start = t
                else:
                    break
             for t in range(new_cycle, self.project.total_cycles):
                if signal.get_value_at(t) == val:
                    o_end = t
                else:
                    break
                    
        self.selected_region = (new_sig_idx, o_start, o_end)
        self.bus_selected.emit(new_sig_idx, new_cycle)
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = 5 if delta > 0 else -5
            
            new_width = self.project.cycle_width + step
            new_width = max(5, min(new_width, 200)) # Clamp
            
            if new_width != self.project.cycle_width:
                self.project.cycle_width = new_width
                self.zoom_changed.emit(new_width)
                self.update_dimensions()
                self.update()
                
            event.accept()
        else:
            super().wheelEvent(event)
