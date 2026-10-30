"""BLE packet format v2 (see CLAUDE.md "BLE protocol v2").

One notification:
    uint32 first_sample_index   little-endian
    uint8  n_samples
    uint8  ranges               low 4 bits: accel full-scale code, high 4 bits: gyro full-scale code
    n_samples x 12 bytes        ax ay az gx gy gz, int16 big-endian, copied verbatim from the MPU6050 FIFO
"""
import struct
from dataclasses import dataclass

import numpy as np

HEADER = struct.Struct("<IBB")
SAMPLE_BYTES = 12
SAMPLE_DTYPE = np.dtype(">i2")  # big-endian int16, as the MPU6050 sends it

# MPU6050 full-scale codes (AFS_SEL / FS_SEL register values 0..3)
ACCEL_RANGE_G = [2, 4, 8, 16]
GYRO_RANGE_DPS = [250, 500, 1000, 2000]

INT16_MIN, INT16_MAX = -32768, 32767


@dataclass
class Packet:
    first_index: int
    accel_code: int
    gyro_code: int
    samples: np.ndarray  # shape (n, 6), int16 raw: ax ay az gx gy gz

    @property
    def accel_range_g(self) -> int:
        return ACCEL_RANGE_G[self.accel_code]

    @property
    def gyro_range_dps(self) -> int:
        return GYRO_RANGE_DPS[self.gyro_code]

    def to_physical(self):
        """Return (acc in g, gyro in dps), each shape (n, 3) float."""
        acc = self.samples[:, :3] * (self.accel_range_g / 32768.0)
        gyro = self.samples[:, 3:] * (self.gyro_range_dps / 32768.0)
        return acc, gyro

    def saturated_count(self) -> int:
        """Number of samples where any axis sits at the int16 limit."""
        at_limit = (self.samples == INT16_MAX) | (self.samples == INT16_MIN)
        return int(at_limit.any(axis=1).sum())


def parse_packet(data: bytes) -> Packet:
    if len(data) < HEADER.size:
        raise ValueError(f"packet too short: {len(data)} B")
    first_index, n, ranges = HEADER.unpack_from(data)
    expected = HEADER.size + n * SAMPLE_BYTES
    if len(data) != expected:
        raise ValueError(f"packet length {len(data)} B, header says {n} samples ({expected} B)")
    samples = np.frombuffer(data, dtype=SAMPLE_DTYPE, offset=HEADER.size).reshape(n, 6).astype(np.int16)
    return Packet(first_index, ranges & 0x0F, ranges >> 4, samples)


def encode_packet(first_index: int, samples: np.ndarray, accel_code: int = 3, gyro_code: int = 3) -> bytes:
    """Build a packet the same way the firmware does (used by the simulated device)."""
    header = HEADER.pack(first_index, len(samples), (gyro_code << 4) | accel_code)
    return header + np.asarray(samples, dtype=SAMPLE_DTYPE).tobytes()
