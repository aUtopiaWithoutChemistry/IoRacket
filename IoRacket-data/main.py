import sys
import asyncio
import struct
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets
from bleak import BleakScanner, BleakClient
from dataclasses import dataclass


from ble_manager import BLEManager
from src.visualizer import BadmintonRealTimePlot


SERVICE_UUID =          "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
CHARACTERISTIC_UUID =   "253113ce-9a58-4847-b67d-f94b719837dc"


@dataclass
class BadmintonData:
    timestamp: float
    acc_x: float; acc_y: float; acc_z: float
    gyro_x: float; gyro_y: float; gyro_z: float


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


if __name__ == "__main__":
    asyncio.run(main())
    ble_manager = BLEManager()

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