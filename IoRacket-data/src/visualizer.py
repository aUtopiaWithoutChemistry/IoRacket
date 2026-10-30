from collections import deque
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg
import struct

MAX_POINTS = 500  # 屏幕上显示的波形点数

class BadmintonRealTimePlot(QtWidgets.QMainWindow):
    # constructor
    def __init__(self):
        super().__init__()
        self.view = pg.PlotWidget(title="羽毛球拍实时 6 轴数据")
        self.setCentralWidget(self.view)
        
        # create data buffers
        self.time_data = deque(maxlen=MAX_POINTS)
        self.acc_x_data = deque(maxlen=MAX_POINTS)
        self.start_time = None

        # create plot curves
        self.curve_ax = self.view.plot(pen='r', name="Acc X")
        self.view.addLegend()
        self.view.showGrid(x=True, y=True)
        self.view.setLabel('left', '加速度', units='m/s^2')
        self.view.setLabel('bottom', '时间', units='s')

        # setup a timer to update the plot
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(30)

    def update_plot(self):
        # 将 deque 转换为 numpy 数组进行快速绘图
        if len(self.time_data) > 0:
            self.curve_ax.setData(list(self.time_data), list(self.acc_x_data))

    def handle_ble_data(self, sender, data):
        # 2. 解析从 ESP32 传来的数据包
        # 格式: <I (uint32_t 时间戳), 6f (6个 float)
        try:
            unpacked = struct.unpack('<I6f', data)
            raw_ms = unpacked[0]
            ax = unpacked[1]
            
            # 计算相对时间
            if self.start_time is None: self.start_time = raw_ms
            rel_time = (raw_ms - self.start_time) / 1000.0

            # 存入缓冲区
            self.time_data.append(rel_time)
            self.acc_x_data.append(ax)
        except Exception as e:
            print(f"解析错误: {e}")

