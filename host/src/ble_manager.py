import asyncio
from bleak import BleakScanner, BleakClient

SERVICE_UUID =          "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
CHARACTERISTIC_UUID =   "253113ce-9a58-4847-b67d-f94b719837dc"

class BLEManager():
    def __init__(self):
        self.device = None
    
    async def connect_to_device(self):
        self.device = await BleakScanner.find_device_by_filter(
            lambda d, ad: SERVICE_UUID.lower() in [u.lower() for u in ad.service_uuids]
        )

    def disconnect_from_device(self, device):
        # Code to disconnect from a specific BLE device
        pass

    def get_connected_devices(self):
        # Code to return a list of currently connected devices
        return self.device
    
    async def run_ble(self, app_window):
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

    def filter_func(self, device, advertising_data):
        print(f"Find device: {device.name}, UUIDs: {advertising_data.service_uuids}")
        return SERVICE_UUID in [uuid.lower() for uuid in advertising_data.service_uuids]
