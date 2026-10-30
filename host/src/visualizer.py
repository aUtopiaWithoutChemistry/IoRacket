"""Main window: connection controls, live 6-axis plots, link statistics, CSV recording."""
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from src.data_parser import parse_packet

RATE_HZ = 1000            # nominal sample rate; packets don't carry the rate yet
WINDOW_S = 5              # seconds shown in the plots
BUFFER_LEN = WINDOW_S * RATE_HZ
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AXIS_PENS = ["r", "g", "b"]


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
        self.conn_label = QtWidgets.QLabel("未连接")

        controls = QtWidgets.QHBoxLayout()
        for w in (self.connect_btn, self.disconnect_btn, self.sim_check, self.record_btn):
            controls.addWidget(w)
        controls.addSpacing(20)
        controls.addWidget(self.conn_label, stretch=1)

        plots = pg.GraphicsLayoutWidget()
        self.acc_plot = plots.addPlot(row=0, col=0, title="加速度")
        self.gyro_plot = plots.addPlot(row=1, col=0, title="角速度")
        self.gyro_plot.setXLink(self.acc_plot)
        self.acc_plot.setLabel("left", "g")
        self.gyro_plot.setLabel("left", "°/s")
        self.gyro_plot.setLabel("bottom", "时间", units="s")
        self.acc_curves, self.gyro_curves = [], []
        for plot, curves in ((self.acc_plot, self.acc_curves), (self.gyro_plot, self.gyro_curves)):
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.addLegend(offset=(10, 10))
            for axis, pen in zip("xyz", AXIS_PENS):
                curves.append(plot.plot(pen=pen, name=axis, connect="finite"))

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(plots, stretch=1)
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

        if self._record_file is not None:
            self._write_rows(pkt)

    # ---------- display ----------

    def update_plots(self):
        if np.isnan(self._t[-1]):
            return
        for i in range(3):
            self.acc_curves[i].setData(self._t, self._acc[:, i])
            self.gyro_curves[i].setData(self._t, self._gyro[:, i])
        self.acc_plot.setXRange(self._t[-1] - WINDOW_S, self._t[-1], padding=0)

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
            self._record_file.close()
            self._record_file = None
            self.record_btn.setText("开始录制")
            self.record_label.setText(f"已保存 {self._record_rows} 行 → {self._record_path}")

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

    def closeEvent(self, event):
        if self._record_file is not None:
            self.toggle_recording()
        self.sim.stop()
        self.ble.shutdown()
        super().closeEvent(event)
