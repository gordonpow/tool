import sys
from PyQt6.QtWidgets import QApplication
from ui.mainwindow import MainWindow
from core.models import Signal, SignalType

def test_pinning():
    app = QApplication(sys.argv)
    window = MainWindow()
    
    # 增加大量信號以測試捲動
    for i in range(50):
        sig = Signal(name=f"Sig_{i}", type=SignalType.INPUT)
        if i % 10 == 0:
            sig.pinned = True # 應該儲存/預設出現
            sig.color = "#ff00ff"
        if i % 5 == 0:
            sig.sticky = True # 應該在捲動時置頂
            sig.color = "#00ff00"
        window.project.add_signal(sig)
    
    window.refresh_list()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    test_pinning()
