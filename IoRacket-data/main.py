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
    # Scan for the device advertising the specific service UUID
    def filter_func(device, advertising_data):
        print(f"发现设备: {device.name}, UUIDs: {advertising_data.service_uuids}")
        return SERVICE_UUID in [uuid.lower() for uuid in advertising_data.service_uuids]

    # find the device
    device = await BleakScanner.find_device_by_filter(filter_func, timeout=10.0)

    if not device:
        print("failed to find the device.")
        return
    print(f"Success! Device address: {device.address}")

    async with BleakClient(device) as client:
        print(f"已连接！正在通过 {device.address} 接收数据...")

        # define notification handler
        def notification_handler(sender, data):
            # data is a bytearray, unpack it into 6 floats
            values = struct.unpack('<6f', data) 
            
            acc = values[:3]  # first three are acceleration
            gyro = values[3:] # last three are angular velocity

        # turn on notifications on the ESP32 characteristic
        await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
        
        # keep the program running to receive notifications
        await asyncio.sleep(10)
        await client.stop_notify(CHARACTERISTIC_UUID)

# 2. Receiving real-time sensor data from the MCU

# 3. Write the received data into a CVS file or a database

# 4. Transfer the sensor data to meaningful badminton metrics

# 5. Implement data visualization to show real-time sensor data in 3D graphs

# 6. AI analysing

if __name__ == "__main__":
    asyncio.run(main())