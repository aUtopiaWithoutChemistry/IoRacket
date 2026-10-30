"""BLE connection to the racket.

Bleak is asyncio-based and Qt has its own event loop, so the asyncio loop runs in a
background thread. Received packets are handed to the UI through Qt signals
(Qt queues them onto the UI thread automatically).
"""
import asyncio
import threading

from bleak import BleakClient, BleakScanner
from PySide6 import QtCore

DEVICE_NAME = "Zifan_Badminton_Sensor"
DATA_UUID = "253113ce-9a58-4847-b67d-f94b719837dc"  # notify: v2 packets


class BLEManager(QtCore.QObject):
    packet_received = QtCore.Signal(bytes)
    status_changed = QtCore.Signal(str)
    connection_changed = QtCore.Signal(bool)

    def __init__(self):
        super().__init__()
        self._client = None
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    # --- called from the UI thread ---

    def connect_device(self):
        asyncio.run_coroutine_threadsafe(self._connect(), self._loop)

    def disconnect_device(self):
        asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)

    def shutdown(self):
        """Disconnect and stop the background loop (call when the app closes)."""
        try:
            asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop).result(timeout=3)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    # --- run on the background asyncio loop ---

    async def _connect(self):
        if self._client is not None and self._client.is_connected:
            return
        self.status_changed.emit("正在扫描...")
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
        if device is None:
            self.status_changed.emit("没有找到球拍（是否已上电、正在广播？）")
            return

        self.status_changed.emit("正在连接...")
        client = BleakClient(device, disconnected_callback=self._on_disconnected)
        try:
            await client.connect()
            await client.start_notify(DATA_UUID, self._on_notify)
        except Exception as e:
            self.status_changed.emit(f"连接失败：{e}")
            await client.disconnect()
            return

        self._client = client
        self.status_changed.emit(f"已连接（MTU {client.mtu_size}）")
        self.connection_changed.emit(True)

    async def _disconnect(self):
        if self._client is not None:
            await self._client.disconnect()

    def _on_notify(self, _sender, data: bytearray):
        self.packet_received.emit(bytes(data))

    def _on_disconnected(self, _client):
        self._client = None
        self.status_changed.emit("已断开")
        self.connection_changed.emit(False)
