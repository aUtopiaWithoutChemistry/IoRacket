from dataclasses import dataclass

@dataclass
class BadmintonData:
    timestamp: float
    acc_x: float; acc_y: float; acc_z: float
    gyro_x: float; gyro_y: float; gyro_z: float

import asyncio
import struct
from bleak import BleakScanner, BleakClient

SERVICE_UUID =          "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
CHARACTERISTIC_UUID =   "253113ce-9a58-4847-b67d-f94b719837dc"

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

    data_list = []

    # 2. Receiving real-time sensor data from the MCU
    async with BleakClient(device) as client:
        print(f"Connected to {device.address}, getting data ...")

        # define notification handler
        def notification_handler(sender, data):
            # data is a bytearray, unpack it into 6 floats
            values = struct.unpack('<I6f', data) 
            row = BadmintonData(
                timestamp=values[0],
                acc_x=values[1], acc_y=values[2], acc_z=values[3],
                gyro_x=values[4], gyro_y=values[5], gyro_z=values[6]
            )
            data_list.append(row)

        # turn on notifications on the ESP32 characteristic
        await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
        
        # keep the program running to receive notifications
        await asyncio.sleep(10)
        await client.stop_notify(CHARACTERISTIC_UUID)

    # 3. Write the received data into a CVS file or a database
    with open("sensor_data.csv", "w") as f:
        f.write("timestamp,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n")
        for row in data_list:
            f.write(f"{row.timestamp},{row.acc_x},{row.acc_y},{row.acc_z},{row.gyro_x},{row.gyro_y},{row.gyro_z}\n")

    # 4. Transfer the sensor data to meaningful badminton metrics

    # 5. Implement data visualization to show real-time sensor data in 3D graphs

    # 6. AI analysing

if __name__ == "__main__":
    asyncio.run(main())