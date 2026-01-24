from dataclasses import dataclass

@dataclass
class BadmintonData:
    timestamp: float
    acc_x: float; acc_y: float; acc_z: float
    gyro_x: float; gyro_y: float; gyro_z: float

# 1. Create a Bluetooth Low Energy(BLE) connection to the MCU
import asyncio
import struct
from bleak import BleakScanner, BleakClient

SERVICE_UUID =          "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
CHARACTERISTIC_UUID =   "253113ce-9a58-4847-b67d-f94b719837dc"

async def main():
    print("正在搜索 Zifan 的羽毛球拍...")

    # 2. 定义过滤逻辑：检查广播数据中的 UUID 列表
    def filter_func(device, advertising_data):
        # 打印一下扫描到的设备，方便调试
        print(f"发现设备: {device.name}, UUIDs: {advertising_data.service_uuids}")
        return SERVICE_UUID in [uuid.lower() for uuid in advertising_data.service_uuids]

    # 3. 使用过滤器寻找设备
    device = await BleakScanner.find_device_by_filter(filter_func, timeout=10.0)

    if not device:
        print("超时：未能找到匹配该 Service UUID 的设备。")
        print("请检查：1. ESP32 是否在运行？ 2. UUID 是否填错？")
        return

    print(f"匹配成功！设备地址: {device.address}")

    async with BleakClient(device) as client:
        print(f"已连接！正在通过 {device.address} 接收数据...")

        # 3. 定义“翻译官”：当收到字节流时，怎么处理它
        def notification_handler(sender, data):
            # '6f' 的意思是：把这串字节按“6个小端序浮点数”来解析
            # 这对应了你 C++ 里的 float mockData[6]
            values = struct.unpack('<6f', data) 
            
            acc = values[:3]  # 前三个是加速度
            gyro = values[3:] # 后三个是角速度
            print(f"收到数据 -> 加速度: {acc[0]:.2f}, {acc[1]:.2f}, {acc[2]:.2f}")
            print(f"          角速度: {gyro[0]:.2f}, {gyro[1]:.2f}, {gyro[2]:.2f}")

        # 4. 告诉 ESP32：开启数据推送模式 (这会激活 BLE2902)
        await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
        
        # 让程序运行 10 秒钟，观察数据
        await asyncio.sleep(10)
        await client.stop_notify(CHARACTERISTIC_UUID)

# 2. Receiving real-time sensor data from the MCU

# 3. Write the received data into a CVS file or a database

# 4. Transfer the sensor data to meaningful badminton metrics

# 5. Implement data visualization to show real-time sensor data in 3D graphs

# 6. AI analysing

if __name__ == "__main__":
    asyncio.run(main())