"""Video player for the replay window: play/pause, slow motion, seek, frame stepping, and marking the sync taps."""
from PySide6 import QtCore, QtWidgets
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from src.recording import format_video_time

# Playback speeds. A swing lasts ~0.3 s, so slow motion is what makes it visible; 1/8 suits 240 fps footage.
SPEEDS = {"1×": 1.0, "0.5×": 0.5, "0.25×": 0.25, "0.125×": 0.125}


class VideoPanel(QtWidgets.QWidget):
    position_changed = QtCore.Signal(float)   # current video time (s), while playing and after seeks
    tap_marked = QtCore.Signal(int, float)    # (0 = start tap, 1 = end tap, video time in s)
    choose_requested = QtCore.Signal()        # the user wants to link a video file

    def __init__(self):
        super().__init__()
        self.fps = 30.0
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)       # the tap is easy to hear, which helps finding its frame
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)

        self.choose_btn = QtWidgets.QPushButton("选择视频…", clicked=self.choose_requested.emit)
        self.play_btn = QtWidgets.QPushButton("播放", clicked=self.toggle_play)
        prev_btn = QtWidgets.QPushButton("◀ 1 帧", clicked=lambda: self.step(-1))
        next_btn = QtWidgets.QPushButton("1 帧 ▶", clicked=lambda: self.step(1))
        self.speed_combo = QtWidgets.QComboBox()
        self.speed_combo.addItems(SPEEDS)
        self.speed_combo.setToolTip("播放速度(慢放)")
        self.speed_combo.currentTextChanged.connect(lambda name: self.player.setPlaybackRate(SPEEDS[name]))
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda ms: self.seek(ms / 1000))
        self.time_label = QtWidgets.QLabel("—")
        mark_start = QtWidgets.QPushButton("这一帧 = 开始敲击", clicked=lambda: self.tap_marked.emit(0, self.position()))
        mark_end = QtWidgets.QPushButton("这一帧 = 结束敲击", clicked=lambda: self.tap_marked.emit(1, self.position()))

        controls = QtWidgets.QHBoxLayout()
        for w in (self.play_btn, self.speed_combo, prev_btn, next_btn):
            controls.addWidget(w)
        controls.addWidget(self.slider, stretch=1)
        controls.addWidget(self.time_label)
        marks = QtWidgets.QHBoxLayout()
        for w in (self.choose_btn, mark_start, mark_end):
            marks.addWidget(w)
        marks.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video, stretch=1)
        layout.addLayout(controls)
        layout.addLayout(marks)

        self.player.durationChanged.connect(lambda ms: self.slider.setRange(0, ms))
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(
            lambda s: self.play_btn.setText("暂停" if s == QMediaPlayer.PlayingState else "播放"))
        self.player.metaDataChanged.connect(self._read_fps)
        # positionChanged is not frequent enough for a smooth data cursor; poll while playing
        self._timer = QtCore.QTimer(self, interval=30, timeout=lambda: self.position_changed.emit(self.position()))
        self.player.playbackStateChanged.connect(
            lambda s: self._timer.start() if s == QMediaPlayer.PlayingState else self._timer.stop())

    def load(self, path):
        self.player.setSource(QtCore.QUrl.fromLocalFile(str(path)))
        self.choose_btn.setText("更换视频…")

    def has_video(self) -> bool:
        return not self.player.source().isEmpty()

    def position(self) -> float:
        return self.player.position() / 1000

    def seek(self, seconds: float, notify: bool = True):
        self.player.setPosition(max(0, int(round(seconds * 1000))))
        if notify:
            self.position_changed.emit(self.position())

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def step(self, frames: int):
        self.player.pause()
        self.seek(self.position() + frames / self.fps)

    def _on_position(self, ms):
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_label.setText(f"{format_video_time(ms / 1000)} / {format_video_time(self.player.duration() / 1000)}"
                                f"  ({self.fps:.0f} fps)")

    def _read_fps(self):
        fps = self.player.metaData().value(QMediaMetaData.VideoFrameRate)
        if fps:
            self.fps = float(fps)
