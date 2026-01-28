from PyQt6.QtWidgets import QLabel, QFrame, QFileDialog
from PyQt6.QtCore import Qt, pyqtSignal

class DropZone(QLabel):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("DRAG & DROP\nOR CLICK TO UPLOAD")
        self.setObjectName("drop_zone")
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QLabel#drop_zone {
                border: 2px dashed #00f3ff;
                border-radius: 10px;
                background-color: rgba(0, 243, 255, 0.05);
                color: #00f3ff;
                font-weight: bold;
                font-size: 16px;
            }
            QLabel#drop_zone:hover {
                background-color: rgba(0, 243, 255, 0.1);
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.setStyleSheet("""
                QLabel#drop_zone {
                    border: 2px solid #00f3ff;
                    background-color: rgba(0, 243, 255, 0.2);
                    color: #fff;
                }
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            QLabel#drop_zone {
                border: 2px dashed #00f3ff;
                border-radius: 10px;
                background-color: rgba(0, 243, 255, 0.05);
                color: #00f3ff;
            }
        """)

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if self.is_video_file(file_path):
                files.append(file_path)
        
        if files:
            self.files_dropped.emit(files)
        
        self.dragLeaveEvent(event) # Reset style

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            files, _ = QFileDialog.getOpenFileNames(
                self, 
                "Select Video Files", 
                "", 
                "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv);;All Files (*)"
            )
            if files:
                self.files_dropped.emit(files)

    def is_video_file(self, path):
        # Basic check, can be expanded
        valid_exts = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
        return any(path.lower().endswith(ext) for ext in valid_exts)
