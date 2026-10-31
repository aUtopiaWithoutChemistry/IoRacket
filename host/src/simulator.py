"""Simulated racket: produces v2 packets so the UI can be developed and tested without the board.

At rest: 1 g on Z plus noise and a small gyro bias (like the real IMU).
Every 3 s: a fake swing whose gyro Y peak (2500 dps) is above the +/-2000 dps range, so it
saturates on purpose and exercises the saturation counter. About 0.5% of packets are dropped
on purpose to exercise the lost-packet counter.
"""
import time

import numpy as np
from PySide6 import QtCore

from src.data_parser import encode_packet

RATE_HZ = 1000
SAMPLES_PER_PACKET = 18
DROP_PROBABILITY = 0.005
ACC_LSB_PER_G = 32768 / 16      # +/-16 g
GYRO_LSB_PER_DPS = 32768 / 2000  # +/-2000 dps


class SimulatedDevice(QtCore.QObject):
    packet_received = QtCore.Signal(bytes)
    status_changed = QtCore.Signal(str)
    connection_changed = QtCore.Signal(bool)

    def __init__(self):
        super().__init__()
        self._rng = np.random.default_rng()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._tick)
        self._index = 0
        self._t0 = 0.0

    def start(self):
        self._index = 0
        self._t0 = time.monotonic()
        self._timer.start()
        self.status_changed.emit("Simulator running · 模拟设备运行中")
        self.connection_changed.emit(True)

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
            self.status_changed.emit("Simulator stopped · 模拟设备已停止")
            self.connection_changed.emit(False)

    def _tick(self):
        # Emit as many full packets as real time says the "sensor" has produced.
        due = int((time.monotonic() - self._t0) * RATE_HZ)
        while due - self._index >= SAMPLES_PER_PACKET:
            samples = self._make_samples(self._index, SAMPLES_PER_PACKET)
            if self._rng.random() >= DROP_PROBABILITY:
                self.packet_received.emit(encode_packet(self._index, samples))
            self._index += SAMPLES_PER_PACKET

    def _make_samples(self, start: int, n: int) -> np.ndarray:
        t = (start + np.arange(n)) / RATE_HZ
        phase = (t % 3.0) - 1.5                  # swing centred in each 3 s period
        pulse = np.exp(-(phase / 0.04) ** 2)     # ~80 ms wide

        acc_g = np.column_stack([10 * pulse, 2 * pulse, 1 - 3 * pulse])
        gyro_dps = np.column_stack([300 * pulse - 8, 2500 * pulse, 500 * pulse])

        acc = acc_g * ACC_LSB_PER_G + self._rng.normal(0, 8, (n, 3))
        gyro = gyro_dps * GYRO_LSB_PER_DPS + self._rng.normal(0, 3, (n, 3))
        raw = np.hstack([acc, gyro])
        return np.clip(np.round(raw), -32768, 32767).astype(np.int16)
