from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QBrush, QPainterPath
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

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hover_pos = None  # (signal_index, cycle_index)
        self.selected_regions = [] # List of (signal_index, start_cycle, end_cycle)
        
        # Dragging state (Row Reorder)
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

    def render_to_image_object(self, settings):
        bg_color = settings['bg_color']
        font_color = settings['font_color']
        font_size = settings['font_size']
        
        # Calculate Dimensions
        cw = self.project.cycle_width
        full_w = self.signal_header_width + self.project.total_cycles * cw + 50
        full_h = self.header_height + len(self.project.signals) * self.row_height + 50
        
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
        
        for i, signal in enumerate(self.project.signals):
            y = self.header_height + i * self.row_height
            self.draw_signal(painter, signal, y, width=full_w, text_color=font_color)

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
                
            y = self.header_height + i * self.row_height
            
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
                
            self.draw_signal(painter, signal, y, is_dragging=False, override_values=override, highlight_ranges=highlights)

        # Draw the dragged signal last (on top) - For Reordering
        if self.dragging_signal_index is not None:
            signal = self.project.signals[self.dragging_signal_index]
            drag_y = int(self.current_drag_y - self.row_height/2)
            self.draw_signal(painter, signal, drag_y, is_dragging=True)
            
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
            is_selected = False
            if self.selected_region:
                _, start, end = self.selected_region
                if start <= t <= end:
                    is_selected = True
                    # Draw highlight background
                    painter.fillRect(rect, QColor(255, 170, 0, 80)) # Orange-ish semi-transparent
            
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

    def draw_signal(self, painter: QPainter, signal: Signal, y: int, is_dragging=False, override_values=None, highlight_ranges=None, width=None, text_color=None):
        if width is None: width = self.width()
        
        if is_dragging:
            painter.setOpacity(0.8)
            painter.fillRect(0, y, width, self.row_height, QColor("#333333"))
        
        # Draw Signal Name
        name_rect = QRect(0, y, self.signal_header_width - 10, self.row_height)
        painter.setPen(text_color if text_color else QColor("#e0e0e0"))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, signal.name)
        
        # Draw separating line
        if not is_dragging:
            painter.setPen(QColor("#333333"))
            painter.drawLine(0, y + self.row_height, width, y + self.row_height)
        
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
        if signal.type == SignalType.BUS:
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
                    # Polygon for [start_t, end_t]
                    # Indent slightly for slant
                    slant = 5
                    # Be careful with adjacent blocks
                    
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
                    # Use the custom fill color with transparency
                    painter.setBrush(QBrush(QColor(fill_color.red(), fill_color.green(), fill_color.blue(), 100)))
                    painter.drawPolygon(poly_pts)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    
                    # Draw Text - Centered in the whole merged block
                    text_rect = QRect(int(x1), int(high_y), int(x2-x1), int(low_y - high_y))
                    painter.setPen(text_color if text_color else QColor("#ffffff"))
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, val)

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
        

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        
        if self.long_press_timer.isActive():
            diff = (event.pos() - self.paint_start_pos).manhattanLength() if self.paint_start_pos else 0
            # Also check distance from initial click for canvas items
            if self.press_start_pos:
                 diff = max(diff, (event.pos() - self.press_start_pos).manhattanLength())
            
            if diff > 5:
                # print(f"DEBUG: Timer Cancelled. Diff: {diff}")
                self.long_press_timer.stop()
                # If we moved, it's a normal drag (Duration Edit or Paint), NOT a long press move
        
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
                             
                             # Auto-expand
                             if cycle_idx >= self.project.total_cycles:
                                 self.project.total_cycles = cycle_idx + 1
                                 self.cycles_changed.emit(self.project.total_cycles)
                                 self.update_dimensions()

                             self.data_changed.emit()
                             self.update()
        if self.is_moving_block:
             cw = self.project.cycle_width
             
             # Calculate Delta based on PIXELS (Smooth)
             # This prevents jumping due to floor/round mismatches and allows smooth preview
             raw_delta_px = x - self.drag_start_x
             delta_float = raw_delta_px / cw
             delta = int(round(delta_float)) # Integer Delta for Data Logic
             
             current_cycle = int(round((x - self.signal_header_width) / cw))
             current_cycle = max(0, current_cycle) 
             self.move_target_cycle = self.move_drag_start_cycle + delta
             
             # Re-generate previews for ALL moving blocks
             self.preview_signal_values = {} # Reset
             
             # Group moves by signal index
             signals_to_update = {}
             for region in self.selected_regions:
                 s_idx = region[0]
                 if s_idx not in signals_to_update:
                     signals_to_update[s_idx] = []
                 signals_to_update[s_idx].append(region)
             
             for s_idx, regions in signals_to_update.items():
                 if s_idx not in self.moving_blocks_snapshot:
                     continue # Should have snapshot (full signal values)
                 
                 # Base content (Original signal state)
                 orig_values = list(self.moving_blocks_snapshot[s_idx])
                 preview = list(orig_values)
                 
                 # Strategy: "Simultaneous Move"
                 # 1. Clear original locations to 'X' (or collapse? User wants "Translation")
                 #    Usually "Translation" implies shifting. "Move" in this tool (Ctrl+Drag) implies Insert/Reorder.
                 #    Let's stick to Reorder logic: Remove then Insert.
                 
                 # To robustly handle multiple blocks:
                 # 1. Identify all "Data Chunks" to move.
                 # 2. Delete them from the list (high index to low to preserve indices).
                 # 3. Calculate new insertion points.
                 
                 # SORT REGIONS TO DELETE FROM END FIRST
                 regions_sorted_desc = sorted(regions, key=lambda r: r[1], reverse=True)
                 
                 # 1. DELETE STEP
                 for _, start, end in regions_sorted_desc:
                     del preview[start : end + 1]
                     
                 # 2. INSERT STEP
                 # Consolidate Contiguous Regions to prevent interleaving
                 # Sort by start time
                 regions_asc = sorted(regions, key=lambda r: r[1])
                 merged_regions = []
                 if regions_asc:
                     # (start, end, distinct_original_regions_list)
                     curr_start, curr_end = regions_asc[0][1], regions_asc[0][2]
                     curr_subs = [regions_asc[0]]
                     
                     for r in regions_asc[1:]:
                         r_start, r_end = r[1], r[2]
                         # Check contiguous: new start == old_end + 1
                         if r_start == curr_end + 1:
                             curr_end = r_end
                             curr_subs.append(r)
                         else:
                             merged_regions.append((curr_start, curr_end, curr_subs))
                             curr_start, curr_end = r_start, r_end
                             curr_subs = [r]
                     merged_regions.append((curr_start, curr_end, curr_subs))
                 
                 insert_tasks = []
                 
                 # Helper logic to track where regions land
                 # We will store this to update selected_regions in Release
                 if not hasattr(self, 'move_new_regions_map'):
                     self.move_new_regions_map = {} # {sig_idx: [ (start, end) ]}
                 self.move_new_regions_map[s_idx] = []

                 # Process Merged Regions
                 # Note: adjustment must account for ALL deleted original regions.
                 # 'regions_asc' contains all original regions for this signal.
                 
                 for m_start, m_end, sub_regions in merged_regions:
                     # Reconstruct Full Values for this Merged Block
                     full_vals = []
                     for sub in sub_regions:
                         # key = f"{s_idx}_{sub[1]}_{sub[2]}"
                         # But we can just grab from snapshot since we have start/end
                         # sub[0] is sig, sub[1] start, sub[2] end
                         k = f"{s_idx}_{sub[1]}_{sub[2]}"
                         full_vals.extend(self.moving_blocks_snapshot.get(k, []))
                     
                     # Desired Visual Start of the HEAD
                     # HEAD is m_start.
                     target_visual = max(0, m_start + delta)
                     
                     # Calculate Insertion Index by scanning PREVENTION (Stationary Items)
                     # We want to find where 'target_visual' fits among the stationary blocks.
                     # 'preview' list currently holds the stationary items (logic: deleted items removed).
                     # We need to know the 'original start' of the items currently in 'preview' to compare.
                     
                     # Reconstruct stationary map: {index_in_preview: original_start}
                     # Converting simple values to starts is hard if we don't have metadata of preview items.
                     # But we know 'regions_asc' were deleted.
                     # Let's iterate the 'original full signal' and skip 'regions_asc', keeping track of starts.
                     
                     # Optimization: valid_starts = [t for t in original_starts if t NOT in deleted]
                     # But we deal with Blocks (Values).
                     # Let's deduce stationary blocks from 'regions_asc' and 'moving_blocks_snapshot'? No.
                     
                     # Alternative: The `adjustment` logic WAS trying to do this mapping.
                     # The issue was checking `d_end < target_visual`.
                     # If we just Count `d_len` for ALL deleted regions strictly BEFORE target_visual?
                     # But `target_visual` is in the "Full Time Coordinate System".
                     # The `adjustment` maps "Full Time" -> "Compressed Index".
                     # If we are "Inside" a deleted region (our own hole), the adjustment makes us point to the start of the hole.
                     # This is logically correct for "Index", but creates the "Dead Zone" because we stay at Index X until we leave the hole.
                     
                     # To jump 'Forward', we need to check if we passed the *Next Stationary Block*.
                     # Next block starts at `d_end + 1` of the hole? No.
                     # It starts at whatever strictly follows.
                     
                     # FIX: Use `adjustment` but exclude SELF from the calculation?
                     # We only exclude the 'sub_regions' that make up THIS merged block.
                     # `regions_asc` contains ALL deleted regions for this signal.
                     # `sub_regions` are the ones currently being handled.
                     
                     adjustment = 0
                     for _, d_start, d_end in regions_asc:
                         # Skip if this deleted region is part of the CURRENT moving group
                         is_self = False
                         for sub in sub_regions:
                             if sub[1] == d_start and sub[2] == d_end:
                                 is_self = True
                                 break
                         if is_self:
                             continue
                             
                         d_len = d_end - d_start + 1
                         
                         if d_end < target_visual:
                             adjustment += d_len
                         elif d_start < target_visual:
                             adjustment += (target_visual - d_start)
                     
                     ins_idx = max(0, target_visual - adjustment)
                     ins_idx = min(len(preview), ins_idx) # 'preview' size is reduced by deletions
                     
                     insert_tasks.append((ins_idx, full_vals, sub_regions))

                 # 3. APPLY INSERTIONS
                 # Sort DESC by Index to preserve earlier indices
                 insert_tasks.sort(key=lambda x: x[0], reverse=True)
                 
                 for idx, vals, subs in insert_tasks:
                     preview[idx:idx] = vals
                     
                     # Request: We need to know where these ended up for Selection Update
                     # Since we are inserting DESC, the indices are final for these blocks?
                     # A inserted at 10. B inserted at 5.
                     # B does not affect A's index (if 5 < 10).
                     # Correct.
                     
                     # Map sub-regions to new positions
                     current_offset = 0
                     for sub in subs:
                         # sub length
                         slen = sub[2] - sub[1] + 1
                         new_r_start = idx + current_offset
                         new_r_end = new_r_start + slen - 1
                         self.move_new_regions_map[s_idx].append((s_idx, new_r_start, new_r_end))
                         current_offset += slen

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
             cw = self.project.cycle_width
             # Calculate current cycle
             current_cycle = int((x - self.signal_header_width) / cw)
             current_cycle = max(0, min(current_cycle, self.project.total_cycles - 1))
             
             signal = self.project.signals[self.edit_signal_index]
             
             # Restore state from start of drag
             if self.edit_initial_values:
                 signal.values = list(self.edit_initial_values)
             
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
             clamped_cycle = max(left_bound, min(current_cycle, right_bound))
             
             
             final_start = self.edit_orig_start
             final_end = self.edit_orig_end
             
             if self.edit_mode == 'END':
                 # Adjust Right Edge
                 final_start = self.edit_orig_start
                 final_end = max(self.edit_orig_start, clamped_cycle)
                 
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
                 final_end = self.edit_orig_end
                 final_start = min(self.edit_orig_end, clamped_cycle)
                 
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

    def on_long_press(self):
        # Activated after 2 seconds
        if not self.press_context: 
            return
        
        # Trigger Move Mode
        self.is_moving_block = True
        self.is_editing_duration = False # Cancel duration edit
        
        ctx = self.press_context
        self.move_drag_start_cycle = ctx['cycle_idx']
        self.move_target_cycle = ctx['cycle_idx']
        self.drag_start_x = self.press_start_pos.x()
        
        # Auto-select if not yet (should be covered by Press, but ensure)
        # If the item under mouse is not in selected_regions, select it.
        clicked_region = ctx['region']
        if clicked_region not in self.selected_regions:
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

    def mousePressEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        self.press_start_pos = event.pos()
        
        sig_idx = (y - self.header_height) // self.row_height
        
        if 0 <= sig_idx < len(self.project.signals) and x > self.signal_header_width:
             signal = self.project.signals[sig_idx]
             
             # --- New: Drag-to-Paint & Click Toggle (Binary) ---
             # Handle BOTH Left and Right buttons here
             if signal.type in [SignalType.INPUT, SignalType.OUTPUT, SignalType.INOUT]:
                 self.paint_start_pos = event.pos()
                 self.paint_val = '1' if event.button() == Qt.MouseButton.LeftButton else '0'
                 self.is_painting = False # Wait for drag
                 return
        
        if event.button() == Qt.MouseButton.LeftButton:
            
            if 0 <= sig_idx < len(self.project.signals):
                # Check for Drag Reorder (Click on Header/Name area)
                if x < self.signal_header_width:
                     self.dragging_signal_index = sig_idx
                     self.current_drag_y = y
                     return

                # Check for Waveform Interaction
                if self.hover_pos:
                    curr_sig_idx, cycle_idx = self.hover_pos
                    signal = self.project.signals[sig_idx]
                    
                    # --- Bus Logic ---
                    if signal.type == SignalType.BUS:
                        
                        val = signal.get_value_at(cycle_idx)
                        
                        # Find block bounds for the clicked item
                        o_start = cycle_idx
                        o_end = cycle_idx
                        
                        # Only expand for defined values
                        if val != 'X':
                            # (Reuse scan logic)
                            for t in range(cycle_idx, -1, -1):
                                if signal.get_value_at(t) == val: o_start = t
                                else: break
                            
                            for t in range(cycle_idx, self.project.total_cycles):
                                if signal.get_value_at(t) == val: o_end = t
                                else: break
                            
                        clicked_region = (sig_idx, o_start, o_end)

                        # 1. HANDLING SELECTION (Shift + Click)
                        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                            if clicked_region in self.selected_regions:
                                self.selected_regions.remove(clicked_region)
                            else:
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
                        self.long_press_timer.start(500) # 0.5 seconds

                        # 3. STANDARD CLICK (Replace Selection)
                        # Only reset selection if we didn't just add/toggle
                        # Note: If we are clicking an already selected item, we might be intending to drag it (Move).
                        # But we don't know yet.
                        # If we clear selection now, we lose the multi-selection context for the drag.
                        # CHECK: Is clicked item in current selection?
                        
                        if clicked_region not in self.selected_regions:
                            self.selected_regions = [clicked_region]
                        
                        self.bus_selected.emit(sig_idx, cycle_idx)
                        
                        # SETUP DURATION EDIT (Default Drag Action)
                        # This will be overridden if Long Press fires
                        if True: # Always allow
                            self.is_editing_duration = True
                            self.edit_signal_index = sig_idx
                            self.edit_start_cycle = cycle_idx
                            self.edit_value = val
                            
                            self.edit_orig_start = o_start
                            self.edit_orig_end = o_end
                            self.edit_initial_values = list(signal.values)
                            
                            # Determine Active Edge: Left (Start) or Right (End)
                            cw = self.project.cycle_width
                            block_x1 = self.signal_header_width + o_start * cw
                            block_x2 = self.signal_header_width + (o_end + 1) * cw
                            mid_x = (block_x1 + block_x2) / 2
                            
                            if x <= mid_x:
                                self.edit_mode = 'START'
                            else:
                                self.edit_mode = 'END'
                           
                                
        elif event.button() == Qt.MouseButton.RightButton:
             # Check for Right Click -> X (For Bus?)
             # User said: "If attribute is Input/Output/Inout... Right Long Press -> Low".
             # So for Binary, Right Click handled above.
             # For Bus? Right Click -> X?
             
             sig_idx = (y - self.header_height) // self.row_height
             if 0 <= sig_idx < len(self.project.signals):
                 signal = self.project.signals[sig_idx]
                 if signal.type == SignalType.BUS:
                     cw = self.project.cycle_width
                     cycle_idx = int((x - self.signal_header_width) / cw)
                     # Overwrite 1 cycle
                     signal.set_value_at(cycle_idx, 'X')
                     self.data_changed.emit()
                     self.update()
                                
        elif event.button() == Qt.MouseButton.RightButton:
             # --- Right Click: Overwrite 5 cycles with 'X' ---
             # User requested: Click cycle -> Overwrite 5 cycles with 'X' (No boundary check)
             sig_idx = (y - self.header_height) // self.row_height
             
             if x > self.signal_header_width:
                 cw = self.project.cycle_width
                 cycle_idx = int((x - self.signal_header_width) / cw)
                 
                 if 0 <= sig_idx < len(self.project.signals):
                     signal = self.project.signals[sig_idx]
                     
                     if signal.type == SignalType.BUS:
                         # Overwrite 1 cycle starting from clicked cycle
                         start_idx = cycle_idx
                         duration = 1
                         
                         for i in range(duration):
                             target_idx = start_idx + i
                             # Auto-expand project if needed (and signal list via set_value_at logic usually handles list, but we update total_cycles)
                             if target_idx >= self.project.total_cycles:
                                 self.project.total_cycles = target_idx + 1
                                 self.cycles_changed.emit(self.project.total_cycles)
                             
                             signal.set_value_at(target_idx, 'X')
                             
                         self.data_changed.emit()
                         self.update()
                         return
                            
    def mouseReleaseEvent(self, event):
        self.long_press_timer.stop()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
        if self.is_moving_block:
            
            # Apply Previews to Real Signals
            if self.preview_signal_values:
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
            
        sig_idx, start, end = self.selected_region
        new_cycle = None
        
        if event.key() == Qt.Key.Key_Left:
            new_cycle = max(0, start - 1)
        elif event.key() == Qt.Key.Key_Right:
            new_cycle = min(self.project.total_cycles - 1, end + 1)
        
        if new_cycle is not None and new_cycle != start and new_cycle != end:
             # Find bounds for the new cycle
             signal = self.project.signals[sig_idx]
             val = signal.get_value_at(new_cycle)
             
             o_start = new_cycle
             o_end = new_cycle
             
             if signal.type == SignalType.BUS and val != 'X':
                 # Expand block
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
                        
             self.selected_region = (sig_idx, o_start, o_end)
             self.bus_selected.emit(sig_idx, new_cycle)
             self.update()
        else:
            super().keyPressEvent(event)

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
