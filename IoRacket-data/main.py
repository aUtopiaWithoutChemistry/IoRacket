import sys
import asyncio
import struct
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets
from bleak import BleakScanner, BleakClient
from collections import deque
from dataclasses import dataclass


SERVICE_UUID =          "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
CHARACTERISTIC_UUID =   "253113ce-9a58-4847-b67d-f94b719837dc"
MAX_POINTS = 500  # 屏幕上显示的波形点数


@dataclass
class BadmintonData:
    timestamp: float
    acc_x: float; acc_y: float; acc_z: float
    gyro_x: float; gyro_y: float; gyro_z: float


class BadmintonRealTimePlot(QtWidgets.QMainWindow):
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


async def run_ble(app_window):
    print("搜索设备...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: SERVICE_UUID.lower() in [u.lower() for u in ad.service_uuids]
    )
    
    if device:
        async with BleakClient(device) as client:
            print(f"已连接: {device.address}")
            # 开启订阅
            await client.start_notify(CHARACTERISTIC_UUID, app_window.handle_ble_data)
            while True:
                await asyncio.sleep(1) # 保持连接


async def main():
    # 1. Create a Bluetooth Low Energy(BLE) connection to the MCU
    def filter_func(device, advertising_data):
        print(f"Find device: {device.name}, UUIDs: {advertising_data.service_uuids}")
        return SERVICE_UUID in [uuid.lower() for uuid in advertising_data.service_uuids]

    # find the device
    device = await BleakScanner.find_device_by_filter(filter_func, timeout=10.0)

    if not device:
        print("failed to find the device.")
        return
    print(f"Success! Device address: {device.address}")

    # data_list = []

    # # 2. Receiving real-time sensor data from the MCU
    # async with BleakClient(device) as client:
    #     print(f"Connected to {device.address}, getting data ...")

    #     # define notification handler
    #     def notification_handler(sender, data):
    #         # data is a bytearray, unpack it into 6 floats
    #         values = struct.unpack('<I6f', data) 
    #         row = BadmintonData(
    #             timestamp=values[0],
    #             acc_x=values[1], acc_y=values[2], acc_z=values[3],
    #             gyro_x=values[4], gyro_y=values[5], gyro_z=values[6]
    #         )
    #         data_list.append(row)

    #     # turn on notifications on the ESP32 characteristic
    #     await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
        
    #     # keep the program running to receive notifications
    #     await asyncio.sleep(10)
    #     await client.stop_notify(CHARACTERISTIC_UUID)

    # # 3. Write the received data into a CVS file or a database
    # with open("sensor_data.csv", "w") as f:
    #     f.write("timestamp,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n")
    #     for row in data_list:
    #         f.write(f"{row.timestamp},{row.acc_x},{row.acc_y},{row.acc_z},{row.gyro_x},{row.gyro_y},{row.gyro_z}\n")

    # 4. Transfer the sensor data to meaningful badminton metrics

    # 5. Implement data visualization to show real-time sensor data in 3D graphs

    # 6. AI analysing


if __name__ == "__main__":
    asyncio.run(main())
    app = QtWidgets.QApplication(sys.argv)
    window = BadmintonRealTimePlot()
    window.show()

    # 在 Qt 事件循环中启动异步蓝牙任务
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # 这种方式可以让 Qt 和 asyncio 共存
    def ble_thread_start():
        loop.run_until_complete(run_ble(window))

    import threading
    threading.Thread(target=ble_thread_start, daemon=True).start()

    sys.exit(app.exec())