import sys
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent

# Add project root to path
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.models import Project, Signal, SignalType
from ui.canvas import WaveformCanvas

class TestResizeLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create App instance
        cls.app = QApplication(sys.argv)

    def setUp(self):
        self.project = Project()
        # Create a signal
        self.signal = Signal(name="TestSig", type=SignalType.INPUT)
        self.project.add_signal(self.signal)
        self.project.total_cycles = 20
        self.project.cycle_width = 20 # 20px per cycle
        
        # Setup Block [5, 10] (Value '1')
        for t in range(5, 11):
            self.signal.set_value_at(t, '1')
            
        self.canvas = WaveformCanvas(self.project)
        self.canvas.resize(800, 600)
        self.canvas.show()
        
        # Geometry constants
        self.header_w = self.canvas.signal_header_width
        self.row_h = self.canvas.row_height
        self.header_h = self.canvas.header_height
        self.cw = self.project.cycle_width

    def get_pos_at_cycle(self, cycle_idx):
        # Center of cycle
        x = self.header_w + cycle_idx * self.cw + self.cw // 2
        y = self.header_h + 0 * self.row_h + self.row_h // 2
        return QPoint(int(x), int(y))

    def test_drag_left_moves_start(self):
        """Click Middle, Drag Left -> Should move Start Left (Extend)"""
        # Block is [5, 10]. Middle is ~7.
        # Click at 7
        start_pos = self.get_pos_at_cycle(7)
        
        # Press
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(start_pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.canvas.mousePressEvent(event)
        
        self.assertTrue(self.canvas.is_editing_duration)
        self.assertIsNone(self.canvas.edit_mode)
        
        # Drag Left to 6 (Diff -20px)
        target_pos = self.get_pos_at_cycle(6)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(target_pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.canvas.mouseMoveEvent(event)
        
        # Check Mode
        self.assertEqual(self.canvas.edit_mode, 'START')
        
        # Check Result: Start should move from 5 to 4?
        # Delta = 6 - 7 = -1. New Start = 5 + (-1) = 4.
        val_at_4 = self.signal.get_value_at(4)
        self.assertEqual(val_at_4, '1')
        val_at_10 = self.signal.get_value_at(10) # End unchanged
        self.assertEqual(val_at_10, '1')

    def test_drag_right_moves_end(self):
        """Click Middle, Drag Right -> Should move End Right (Extend)"""
        # Block is [5, 10]. Middle is ~7.
        # Click at 7
        start_pos = self.get_pos_at_cycle(7)
        
        # Press
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(start_pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.canvas.mousePressEvent(event)
        
        # Drag Right to 8 (Diff +20px)
        target_pos = self.get_pos_at_cycle(8)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(target_pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.canvas.mouseMoveEvent(event)
        
        # Check Mode
        self.assertEqual(self.canvas.edit_mode, 'END')
        
        # Check Result: End should move from 10 to 11?
        # Delta = 8 - 7 = +1. New End = 10 + 1 = 11.
        val_at_11 = self.signal.get_value_at(11)
        self.assertEqual(val_at_11, '1')
        val_at_5 = self.signal.get_value_at(5) # Start unchanged
        self.assertEqual(val_at_5, '1')

if __name__ == '__main__':
    unittest.main()
