from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QSlider
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt

class PreviewPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)

        # Video Widget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: black; border: 1px solid #333;")
        self.layout.addWidget(self.video_widget)

        # Media Player
        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)

        # Controls (Play/Pause, Seek)
        self.controls_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶")   
        self.play_btn.setFixedSize(40, 30)
        self.play_btn.clicked.connect(self.toggle_playback)
        self.controls_layout.addWidget(self.play_btn)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.sliderMoved.connect(self.set_position)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.controls_layout.addWidget(self.seek_slider)

        self.layout.addLayout(self.controls_layout)

    def load_video(self, file_path, play_immediately=False):
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        if play_immediately:
            self.media_player.play()
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("▶")
        else:
            self.media_player.play()
            self.play_btn.setText("⏸")

    def position_changed(self, position):
        self.seek_slider.setValue(position)

    def duration_changed(self, duration):
        self.seek_slider.setRange(0, duration)

    def set_position(self, position):
        self.media_player.setPosition(position)
