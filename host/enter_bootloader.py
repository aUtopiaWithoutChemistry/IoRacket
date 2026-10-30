"""Tell the racket to reboot into download mode over BLE, so it can be re-flashed without B+R.

Usage: python enter_bootloader.py
Then: ~/.platformio/penv/bin/pio run -e <env> -t upload   (from firmware/)
"""
import asyncio
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "Zifan_Badminton_Sensor"
CONTROL_UUID = "c0a1b2d3-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
CMD_BOOTLOADER = b"\x01"


async def main():
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
    if device is None:
        print(f"{DEVICE_NAME} not found. Is it powered and running a firmware with the control characteristic?")
        return
    print(f"Found {device.address}, sending bootloader command...")
    try:
        async with BleakClient(device) as client:
            await client.write_gatt_char(CONTROL_UUID, CMD_BOOTLOADER, response=True)
    except Exception as e:
        # The board resets right after the write, so a dropped connection here is expected.
        print(f"(connection ended: {e})")
    print("Done. The board should now be in download mode; run the upload.")


asyncio.run(main())
