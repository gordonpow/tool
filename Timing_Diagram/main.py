import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QFile, QTextStream

from ui.mainwindow import MainWindow

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Force Fusion style for consistent cross-platform look
    
    # Load Stylesheet
    style_path = resource_path("styles/tech_theme.qss")
    style_file = QFile(style_path)
    
    if style_file.open(QFile.OpenModeFlag.ReadOnly | QFile.OpenModeFlag.Text):
        stream = QTextStream(style_file)
        app.setStyleSheet(stream.readAll())
    else:
        print(f"Warning: Could not load stylesheet from {style_path}")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
