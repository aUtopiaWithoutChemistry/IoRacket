"""Replay window for a recorded CSV: overview, linked video, swing list, single-swing 6-axis view,
swings overlaid at their peak, and video sync from two frame taps.

Once a video is linked and synced, playing or seeking the video moves the data cursor, and
selecting a swing or clicking the overview seeks the video.
"""
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from src.analysis import find_swings, find_taps, gyro_bias, head_speed_ms
from src.plots import SixAxisPlot
from src.recording import (VideoSync, format_video_time, load_recording, load_sidecar, parse_video_time,
                           save_sidecar)
from src.video_panel import VideoPanel

SWING_VIEW_S = (-0.5, 0.5)      # single-swing view, seconds around the peak
FOLLOW_VIEW_S = 1.0             # while following the video: seconds shown on each side of the cursor
SEEK_LEAD_S = 0.5               # selecting a swing seeks the video this long before its peak
OVERLAY_MS = (-300, 300)        # overlay window, ms around the peak
OVERLAY_QUANTITIES = {
    "角速度合成 (°/s)": lambda gyro, acc: np.linalg.norm(gyro, axis=1),
    "拍头速度 (km/h)": lambda gyro, acc: head_speed_ms(gyro) * 3.6,
    "加速度合成 (g)": lambda gyro, acc: np.linalg.norm(acc, axis=1),
}
COLUMNS = ["#", "时间(s)", "视频时间", "时长(ms)", "角速度(°/s)", "加速度(g)", "拍头(km/h)", "饱和(ms)"]
VIDEO_FILTER = "视频 (*.mp4 *.mov *.m4v *.avi *.mkv)"


class ReplayWindow(QtWidgets.QMainWindow):
    def __init__(self, path):
        super().__init__()
        self.rec = load_recording(path)
        self.bias = gyro_bias(self.rec)
        self.gyro = self.rec.gyro - self.bias      # bias-corrected, used for all analysis and plots
        self.acc = self.rec.acc
        self.t = self.rec.t
        self.swings = find_swings(self.rec, self.bias)
        self.taps = find_taps(self.rec)
        self.video_name, self.sync = load_sidecar(self.rec)
        self.marked = [None, None]                 # video times of the start/end taps marked in the player
        self.selected = None

        self.setWindowTitle(f"回放 - {self.rec.path.name}")
        self.resize(1400, 950)
        self._build_ui()
        self._fill_overview()
        self._fill_table()
        self._fill_overlay()
        if self.video_name:
            video_path = self.rec.path.parent / self.video_name
            if video_path.exists():
                self.video.load(video_path)
            else:
                self.statusBar().showMessage(f"找不到关联的视频 {video_path},可以重新选择。")
        if self.swings:
            self.table.selectRow(0)

    # ---------- layout ----------

    def _build_ui(self):
        sync_btn = QtWidgets.QPushButton("视频对时…", clicked=self.open_sync_dialog)
        self.autoscale_check = QtWidgets.QCheckBox("自动缩放")
        self.info_label = QtWidgets.QLabel()
        self.info_label.setWordWrap(True)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.info_label, stretch=1)
        top.addWidget(self.autoscale_check)
        top.addWidget(sync_btn)

        self.overview = pg.PlotWidget(title="整段总览:角速度合成(浅色块 = 挥拍,橙线 = 疑似敲击,点击可跳转)")
        self.overview.setLabel("left", "°/s")
        self.overview.setLabel("bottom", "时间", units="s")
        self.overview.showGrid(x=True, y=True, alpha=0.25)
        self.overview.setMouseEnabled(y=False)
        self.overview.scene().sigMouseClicked.connect(self.on_overview_clicked)

        self.video = VideoPanel()
        self.video.choose_requested.connect(self.choose_video)
        self.video.position_changed.connect(self.on_video_position)
        self.video.tap_marked.connect(self.on_tap_marked)

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.on_swing_selected)

        left = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        left.addWidget(self.video)
        left.addWidget(self.table)
        left.setSizes([420, 380])

        self.swing_plot = SixAxisPlot(self.rec.accel_range_g, self.rec.gyro_range_dps)
        self.autoscale_check.toggled.connect(self.swing_plot.set_autoscale)

        self.overlay_plot = pg.PlotWidget()
        self.overlay_plot.setLabel("bottom", "相对峰值的时间", units="ms")
        self.overlay_plot.showGrid(x=True, y=True, alpha=0.25)
        self.overlay_combo = QtWidgets.QComboBox()
        self.overlay_combo.addItems(OVERLAY_QUANTITIES)
        self.overlay_combo.currentIndexChanged.connect(self._fill_overlay)
        overlay_tab = QtWidgets.QWidget()
        ol = QtWidgets.QVBoxLayout(overlay_tab)
        ol.addWidget(self.overlay_combo, alignment=QtCore.Qt.AlignLeft)
        ol.addWidget(self.overlay_plot)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.swing_plot, "6 轴数据")
        self.tabs.addTab(overlay_tab, "叠加对比")

        bottom = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        bottom.addWidget(left)
        bottom.addWidget(self.tabs)
        bottom.setSizes([620, 780])

        split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        split.addWidget(self.overview)
        split.addWidget(bottom)
        split.setSizes([200, 750])

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(split, stretch=1)
        self.setCentralWidget(central)

    # ---------- content ----------

    def _fill_overview(self):
        p = self.overview
        p.clear()
        p.plot(self.t, np.linalg.norm(self.gyro, axis=1), pen=pg.mkPen("#555", width=1))
        for sw in self.swings:
            region = pg.LinearRegionItem((self.t[sw.start], self.t[sw.end]), movable=False,
                                         brush=pg.mkBrush(46, 134, 222, 50), pen=pg.mkPen(None))
            p.addItem(region)
        for row in self.taps:
            p.addItem(pg.InfiniteLine(self.t[row], pen=pg.mkPen("#e67e22", width=2)))
        self.overview_cursor = pg.InfiniteLine(pen=pg.mkPen("#c0392b", width=1.5))
        p.addItem(self.overview_cursor)

        parts = [f"{len(self.rec.index)} 个样本({self.t[-1] - self.t[0]:.1f} s)",
                 f"挥拍 {len(self.swings)} 次,其中 {sum(1 for s in self.swings if s.saturated_ms)} 次饱和",
                 f"疑似敲击 {len(self.taps)} 次"]
        if self.bias.any():
            parts.append(f"陀螺仪零偏 {self.bias[0]:+.1f} / {self.bias[1]:+.1f} / {self.bias[2]:+.1f} °/s(已扣除)")
        else:
            parts.append("没有静止时段,零偏未扣除(敲击后把拍子放下静止 1-2 s 即可)")
        parts.append(f"已对时,真实采样率 {self.sync.rate_hz:.1f} Hz" if self.sync else "未对时")
        if self.rec.note:
            parts.append(f"备注:{self.rec.note}")
        self.info_label.setText("  |  ".join(parts))

    def _fill_table(self):
        self.table.setRowCount(len(self.swings))
        for r, sw in enumerate(self.swings):
            g = "≥ " if sw.gyro_clipped else ""   # clipped data: the true peak is higher
            a = "≥ " if sw.acc_clipped else ""
            video = format_video_time(float(self.sync.to_video_time(self.rec.index[sw.peak]))) if self.sync else ""
            values = [str(r + 1), f"{self.t[sw.peak]:.2f}", video, str(sw.end - sw.start + 1),
                      f"{g}{sw.peak_gyro_dps:.0f}", f"{a}{sw.peak_acc_g:.1f}", f"{g}{sw.head_speed_kmh:.0f}",
                      str(sw.saturated_ms) if sw.saturated_ms else ""]
            for c, v in enumerate(values):
                item = QtWidgets.QTableWidgetItem(v)
                item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()

    def _fill_overlay(self):
        p = self.overlay_plot
        p.clear()
        name = self.overlay_combo.currentText()
        values = OVERLAY_QUANTITIES[name](self.gyro, self.acc)
        p.setLabel("left", name)
        lo, hi = OVERLAY_MS
        for i, sw in enumerate(self.swings):
            a, b = max(0, sw.peak + lo), min(len(values), sw.peak + hi)
            selected = i == self.selected
            pen = pg.mkPen("#e67e22", width=3) if selected else pg.mkPen((46, 134, 222, 90), width=1)
            curve = p.plot(np.arange(a, b) - sw.peak, values[a:b], pen=pen)
            curve.setZValue(10 if selected else 0)

    def _show_window(self, row_from, row_to, t0=0.0, cursor_t=None):
        """Show rows [row_from, row_to) in the 6-axis plot, with time shifted by t0."""
        a, b = max(0, row_from), min(len(self.t), row_to)
        if b - a < 2:
            return
        t = self.t[a:b] - t0
        self.swing_plot.set_data(t, self.acc[a:b], self.gyro[a:b], self.rec.saturated[a:b])
        self.swing_plot.set_x_range(t[0], t[-1])
        self.swing_plot.set_cursor(cursor_t)

    def _row_of_index(self, sample_index) -> int:
        return int(np.clip(np.searchsorted(self.rec.index, sample_index), 0, len(self.t) - 1))

    # ---------- interaction ----------

    def on_swing_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        self.selected = rows[0].row()
        sw = self.swings[self.selected]
        lo, hi = SWING_VIEW_S
        self._show_window(sw.peak + int(lo * 1000), sw.peak + int(hi * 1000), t0=self.t[sw.peak])
        self.overview_cursor.setPos(self.t[sw.peak])
        self.tabs.setCurrentWidget(self.swing_plot)
        self._fill_overlay()
        if self.sync and self.video.has_video():
            self.video.seek(float(self.sync.to_video_time(self.rec.index[sw.peak])) - SEEK_LEAD_S, notify=False)

    def on_video_position(self, video_t):
        """Video moved (playing or seeking): follow it with the data cursor."""
        if not self.sync:
            return
        row = self._row_of_index(self.sync.to_index(video_t))
        half = int(FOLLOW_VIEW_S * 1000)
        self._show_window(row - half, row + half, cursor_t=self.t[row])
        self.overview_cursor.setPos(self.t[row])

    def on_overview_clicked(self, event):
        vb = self.overview.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(event.scenePos()):
            return
        t = vb.mapSceneToView(event.scenePos()).x()
        row = self._row_of_index(t * 1000)     # t is sample_index / 1000
        if self.sync and self.video.has_video():
            self.video.seek(float(self.sync.to_video_time(self.rec.index[row])))  # also moves the data view
        else:
            half = int(FOLLOW_VIEW_S * 1000)
            self._show_window(row - half, row + half, cursor_t=self.t[row])
            self.overview_cursor.setPos(self.t[row])

    def choose_video(self):
        src, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择这段录音对应的视频", str(Path.home()), VIDEO_FILTER)
        if not src:
            return
        src = Path(src)
        dest = self.rec.path.with_suffix(src.suffix.lower())   # racket_xxx.csv -> racket_xxx.mp4
        if src.resolve() != dest.resolve() and not copy_with_progress(self, src, dest):
            return
        self.video_name = dest.name
        save_sidecar(self.rec, self.video_name, self.sync)
        self.video.load(dest)
        self.statusBar().showMessage(f"已关联视频 {dest.name}" + ("" if self.sync else
                                     ",接下来逐帧找到两次敲击,点“这一帧 = 开始/结束敲击”完成对时"))

    def on_tap_marked(self, which, video_t):
        self.marked[which] = video_t
        names = ("开始", "结束")
        self.statusBar().showMessage(f"{names[which]}敲击 = 视频 {format_video_time(video_t)}")
        if all(m is not None for m in self.marked):
            self.open_sync_dialog()

    def open_sync_dialog(self):
        if len(self.taps) < 2:
            QtWidgets.QMessageBox.information(
                self, "视频对时", f"只找到 {len(self.taps)} 次敲击,至少需要 2 次(录像开始后和结束前各敲一下拍框)。")
            return
        if all(m is not None for m in self.marked):
            prefill = tuple(self.marked)
        else:
            prefill = self.sync.video_time_s if self.sync else (None, None)
        dialog = SyncDialog(self, [self.t[r] for r in self.taps], prefill)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        (i1, v1), (i2, v2) = dialog.result_pairs()
        sync = VideoSync((int(self.rec.index[self.taps[i1]]), int(self.rec.index[self.taps[i2]])), (v1, v2))
        if not 900 < sync.rate_hz < 1100:
            QtWidgets.QMessageBox.warning(
                self, "视频对时", f"算出的采样率是 {sync.rate_hz:.1f} Hz,和 1000 Hz 差太多,"
                                 "可能选错了敲击或输错了视频时间。没有保存。")
            return
        self.sync = sync
        self.marked = [None, None]
        save_sidecar(self.rec, self.video_name, self.sync)
        self._fill_overview()
        self._fill_table()
        self.statusBar().showMessage(f"对时完成,真实采样率 {sync.rate_hz:.1f} Hz")

    def closeEvent(self, event):
        self.video.player.stop()
        super().closeEvent(event)


class SyncDialog(QtWidgets.QDialog):
    """Pick which detected taps are the start/end taps and give their times in the video."""

    def __init__(self, parent, tap_times, prefill):
        super().__init__(parent)
        self.setWindowTitle("视频对时")
        labels = [f"第 {i + 1} 次敲击  @ {t:.3f} s" for i, t in enumerate(tap_times)]
        self.first_combo, self.last_combo = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for combo in (self.first_combo, self.last_combo):
            combo.addItems(labels)
        self.last_combo.setCurrentIndex(len(labels) - 1)
        self.first_edit, self.last_edit = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        for edit, value in zip((self.first_edit, self.last_edit), prefill):
            edit.setPlaceholderText("视频里的时间,如 0:03.250 或 3.25")
            if value is not None:
                edit.setText(format_video_time(value))

        form = QtWidgets.QFormLayout(self)
        form.addRow(QtWidgets.QLabel("数据里的两次敲击对应视频里的哪两个时刻?\n"
                                     "(在视频面板里逐帧找到敲击,点“这一帧 = …”会自动填入)"))
        form.addRow("开始敲击(数据)", self.first_combo)
        form.addRow("开始敲击(视频时间)", self.first_edit)
        form.addRow("结束敲击(数据)", self.last_combo)
        form.addRow("结束敲击(视频时间)", self.last_edit)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        try:
            self._pairs = [(self.first_combo.currentIndex(), parse_video_time(self.first_edit.text())),
                           (self.last_combo.currentIndex(), parse_video_time(self.last_edit.text()))]
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "视频对时", "视频时间格式不对,应为 0:03.250 或 3.25")
            return
        if self._pairs[0][0] == self._pairs[1][0]:
            QtWidgets.QMessageBox.warning(self, "视频对时", "开始和结束要选两次不同的敲击。")
            return
        self.accept()

    def result_pairs(self):
        return self._pairs


def copy_with_progress(parent, src: Path, dest: Path, chunk=8 * 1024 * 1024) -> bool:
    """Copy a (possibly large) file in chunks with a cancellable progress dialog. False if cancelled."""
    total = src.stat().st_size
    progress = QtWidgets.QProgressDialog(f"正在复制视频到 {dest.name}…", "取消", 0, 100, parent)
    progress.setWindowModality(QtCore.Qt.WindowModal)
    progress.setMinimumDuration(300)
    done = 0
    with open(src, "rb") as fin, open(dest, "wb") as fout:
        while block := fin.read(chunk):
            fout.write(block)
            done += len(block)
            progress.setValue(int(done * 100 / max(total, 1)))
            QtWidgets.QApplication.processEvents()
            if progress.wasCanceled():
                break
    if progress.wasCanceled():
        dest.unlink(missing_ok=True)
        return False
    progress.setValue(100)
    return True
