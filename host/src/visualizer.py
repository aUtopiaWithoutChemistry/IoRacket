"""Main window: connection controls, live 6-axis plots, link statistics, CSV recording."""
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtWidgets

from src.data_parser import INT16_MAX, INT16_MIN, parse_packet
from src.recording import finalize_recording
from src.plots import SixAxisPlot
from src.replay import ReplayWindow

RATE_HZ = 1000            # nominal sample rate; packets don't carry the rate yet
WINDOW_S = 5              # seconds shown in the plots
BUFFER_LEN = WINDOW_S * RATE_HZ
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, ble, simulator):
        super().__init__()
        self.ble = ble
        self.sim = simulator
        self.setWindowTitle("IoRacket 实时数据")
        self.resize(1100, 750)

        self._build_ui()
        for source in (ble, simulator):
            source.packet_received.connect(self.on_packet)
            source.status_changed.connect(self.conn_label.setText)
            source.connection_changed.connect(self.on_connection_changed)

        # Rolling buffers for the plots (physical units)
        self._t = np.full(BUFFER_LEN, np.nan)
        self._acc = np.full((BUFFER_LEN, 3), np.nan)
        self._gyro = np.full((BUFFER_LEN, 3), np.nan)
        self._sat = np.zeros((BUFFER_LEN, 6), dtype=bool)
        self._replay_windows = []

        self._reset_stats()
        self._record_file = None

        self._plot_timer = QtCore.QTimer(self, interval=30, timeout=self.update_plots)
        self._plot_timer.start()
        self._stats_timer = QtCore.QTimer(self, interval=1000, timeout=self.update_stats)
        self._stats_timer.start()

    # ---------- UI ----------

    def _build_ui(self):
        self.connect_btn = QtWidgets.QPushButton("连接球拍", clicked=self.ble.connect_device)
        self.disconnect_btn = QtWidgets.QPushButton("断开", clicked=self.ble.disconnect_device)
        self.sim_check = QtWidgets.QCheckBox("模拟设备", toggled=self.on_sim_toggled)
        self.record_btn = QtWidgets.QPushButton("开始录制", clicked=self.toggle_recording)
        self.autoscale_check = QtWidgets.QCheckBox("自动缩放")
        self.replay_btn = QtWidgets.QPushButton("回放录音…", clicked=self.open_replay)
        self.conn_label = QtWidgets.QLabel("未连接")

        controls = QtWidgets.QHBoxLayout()
        for w in (self.connect_btn, self.disconnect_btn, self.sim_check, self.record_btn, self.autoscale_check):
            controls.addWidget(w)
        controls.addSpacing(20)
        controls.addWidget(self.conn_label, stretch=1)
        controls.addWidget(self.replay_btn)

        self.plots = SixAxisPlot()
        self.autoscale_check.toggled.connect(self.plots.set_autoscale)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.plots, stretch=1)
        self.setCentralWidget(central)

        self.stats_label = QtWidgets.QLabel()
        self.record_label = QtWidgets.QLabel()
        self.statusBar().addWidget(self.stats_label, 1)
        self.statusBar().addPermanentWidget(self.record_label)

    # ---------- data sources ----------

    def on_sim_toggled(self, checked):
        self.connect_btn.setEnabled(not checked)
        self.disconnect_btn.setEnabled(not checked)
        if checked:
            self.ble.disconnect_device()
            self.sim.start()
        else:
            self.sim.stop()

    def on_connection_changed(self, connected):
        if connected:
            self._reset_stats()

    def on_packet(self, data: bytes):
        self._window_bytes += len(data)
        try:
            pkt = parse_packet(data)
        except ValueError as e:
            self._bad_packets += 1
            print(f"bad packet: {e}")
            return

        n = len(pkt.samples)
        if self._next_index is not None and pkt.first_index != self._next_index:
            missing = pkt.first_index - self._next_index
            if missing > 0:
                self._lost_samples += missing
                self._lost_packets += max(1, round(missing / n))
            # missing < 0: the index went backwards, i.e. the device restarted; just resync
        self._next_index = pkt.first_index + n

        self._window_samples += n
        self._saturated += pkt.saturated_count()

        acc, gyro = pkt.to_physical()
        t = (pkt.first_index + np.arange(n)) / RATE_HZ
        self._t = np.concatenate([self._t[n:], t])
        self._acc = np.concatenate([self._acc[n:], acc])
        self._gyro = np.concatenate([self._gyro[n:], gyro])
        sat = (pkt.samples == INT16_MAX) | (pkt.samples == INT16_MIN)
        self._sat = np.concatenate([self._sat[n:], sat])

        if self._record_file is not None:
            self._write_rows(pkt)

    # ---------- display ----------

    def update_plots(self):
        if np.isnan(self._t[-1]):
            return
        self.plots.set_data(self._t, self._acc, self._gyro, self._sat)
        self.plots.set_x_range(self._t[-1] - WINDOW_S, self._t[-1])

    def _reset_stats(self):
        self._next_index = None
        self._lost_samples = self._lost_packets = 0
        self._saturated = 0
        self._bad_packets = 0
        self._window_samples = self._window_bytes = 0
        self._window_start = QtCore.QElapsedTimer()
        self._window_start.start()

    def update_stats(self):
        seconds = self._window_start.restart() / 1000.0
        rate = self._window_samples / seconds
        kbps = self._window_bytes / seconds / 1000
        self._window_samples = self._window_bytes = 0
        text = (f"采样率 {rate:5.0f} Hz   |   丢包 {self._lost_packets}（{self._lost_samples} 个样本）"
                f"   |   饱和样本 {self._saturated}   |   {kbps:5.1f} kB/s")
        if self._bad_packets:
            text += f"   |   格式错误包 {self._bad_packets}"
        self.stats_label.setText(text)

    # ---------- recording ----------

    def toggle_recording(self):
        if self._record_file is None:
            DATA_DIR.mkdir(exist_ok=True)
            path = DATA_DIR / f"racket_{datetime.now():%Y%m%d_%H%M%S}.csv"
            self._record_file = open(path, "w", newline="")
            self._record_path = path
            self._record_rows = 0
            self._record_ranges = None   # header is written with the first packet
            self.record_btn.setText("停止录制")
            self.record_label.setText(f"录制中：{path.name}")
        else:
            self._stop_recording(ask_name=True)

    def _stop_recording(self, ask_name: bool):
        self._record_file.close()
        self._record_file = None
        self.record_btn.setText("开始录制")
        path = self._record_path
        if ask_name:
            dialog = SaveDialog(self, path)
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                path = finalize_recording(path, dialog.name_edit.text(), dialog.note_edit.toPlainText())
        self.record_label.setText(f"已保存 {self._record_rows} 行 → {path}")

    def _write_rows(self, pkt):
        ranges = (pkt.accel_range_g, pkt.gyro_range_dps)
        if self._record_ranges is None:
            self._record_file.write(
                "# IoRacket raw IMU data (BLE protocol v2)\n"
                f"# accel_range_g={ranges[0]} gyro_range_dps={ranges[1]} nominal_rate_hz={RATE_HZ}\n"
                "# values are raw int16: physical = raw * range / 32768; gaps in sample_index = lost packets\n"
                "sample_index,ax,ay,az,gx,gy,gz\n")
        elif ranges != self._record_ranges:
            self._record_file.write(f"# ranges changed: accel_range_g={ranges[0]} gyro_range_dps={ranges[1]}\n")
        self._record_ranges = ranges

        index = pkt.first_index + np.arange(len(pkt.samples))
        np.savetxt(self._record_file, np.column_stack([index, pkt.samples]), fmt="%d", delimiter=",")
        self._record_rows += len(pkt.samples)

    def open_replay(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择录音", str(DATA_DIR), "CSV (*.csv)")
        if path:
            window = ReplayWindow(path)
            window.show()
            self._replay_windows.append(window)  # keep a reference so it is not garbage-collected

    def closeEvent(self, event):
        if self._record_file is not None:
            self._stop_recording(ask_name=False)   # closing the app: keep the date/time name
        self.sim.stop()
        self.ble.shutdown()
        super().closeEvent(event)


class SaveDialog(QtWidgets.QDialog):
    """Shown when recording stops: name the file and add a note (written into the CSV header)."""

    def __init__(self, parent, path):
        super().__init__(parent)
        self.setWindowTitle("保存录音")
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如 smash_practice(留空则保留时间名)")
        self.note_edit = QtWidgets.QPlainTextEdit()
        self.note_edit.setPlaceholderText("例如 杀球练习,室内,右手")
        self.note_edit.setFixedHeight(70)
        stamp = path.stem.removeprefix("racket_")
        form = QtWidgets.QFormLayout(self)
        form.addRow(QtWidgets.QLabel(f"文件名会保存为 <名字>_{stamp}.csv"))
        form.addRow("名字", self.name_edit)
        form.addRow("备注", self.note_edit)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Save).setText("保存")
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText("保留时间名")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
