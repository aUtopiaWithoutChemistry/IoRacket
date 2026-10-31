"""Analysis of a recording: gyro bias, swing segmentation, head speed, sync-tap detection."""
from dataclasses import dataclass

import numpy as np

from src.recording import Recording

# The IMU axis along the handle. Inferred from rest data (the handle is ~horizontal whenever the racket
# lies still, and acc Y is always ~0 then). Verify once by standing the racket upright: |acc Y| should be ~1 g.
HANDLE_AXIS = 1           # 0 = x, 1 = y, 2 = z
HEAD_DISTANCE_M = 0.635   # IMU to racket head centre (measured by the owner)

SWING_THRESHOLD_DPS = 500  # |gyro| above this counts as swinging
SWING_MERGE_GAP_MS = 300   # active stretches closer than this belong to the same swing


@dataclass
class Swing:
    start: int             # row numbers in the recording (not sample_index)
    end: int
    peak: int              # row of the largest |gyro|
    peak_gyro_dps: float
    peak_acc_g: float
    head_speed_kmh: float
    saturated_ms: int      # samples (= ms) with any axis at the limit
    acc_clipped: bool      # an accel axis hit the limit: peak_acc_g is a lower bound
    gyro_clipped: bool     # a gyro axis hit the limit: peak_gyro_dps and head_speed_kmh are lower bounds


def runs(mask: np.ndarray, merge_gap: int = 0):
    """(start, end) inclusive row ranges where mask is True; runs separated by < merge_gap rows are joined."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0] - 1
    out = []
    for s, e in zip(starts, ends):
        if out and s - out[-1][1] <= merge_gap:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def gyro_bias(rec: Recording, block: int = 250) -> np.ndarray:
    """Zero-rate offset (deg/s per axis), from 250 ms blocks where the racket is clearly still."""
    gyro, acc = rec.gyro, rec.acc
    still = []
    for i in range(0, len(gyro) - block, block):
        g, a = gyro[i:i + block], acc[i:i + block]
        if np.abs(g - np.median(g, axis=0)).max() < 3 and np.abs(np.linalg.norm(a, axis=1) - 1).max() < 0.1:
            still.append(np.median(g, axis=0))
    return np.median(still, axis=0) if still else np.zeros(3)


def head_speed_ms(gyro_dps: np.ndarray) -> np.ndarray:
    """Head speed from rotation only: |gyro perpendicular to the handle| x distance (m/s).
    Ignores the hand's own linear motion, so the real head speed is somewhat higher."""
    perp = np.delete(gyro_dps, HANDLE_AXIS, axis=1)
    return np.radians(np.linalg.norm(perp, axis=1)) * HEAD_DISTANCE_M


def find_swings(rec: Recording, bias: np.ndarray) -> list:
    gyro = rec.gyro - bias
    gyro_mag = np.linalg.norm(gyro, axis=1)
    acc_mag = np.linalg.norm(rec.acc, axis=1)
    head = head_speed_ms(gyro)
    sat = rec.saturated
    swings = []
    for s, e in runs(gyro_mag > SWING_THRESHOLD_DPS, SWING_MERGE_GAP_MS):
        peak = s + int(np.argmax(gyro_mag[s:e + 1]))
        swings.append(Swing(s, e, peak, float(gyro_mag[peak]), float(acc_mag[s:e + 1].max()),
                            float(head[s:e + 1].max() * 3.6), int(sat[s:e + 1].any(axis=1).sum()),
                            bool(sat[s:e + 1, :3].any()), bool(sat[s:e + 1, 3:].any())))
    return swings


def find_taps(rec: Recording) -> list:
    """Rows of sync taps: a short, sharp acceleration spike while the racket is otherwise not swinging."""
    acc_mag = np.linalg.norm(rec.acc, axis=1)
    gyro_mag = np.linalg.norm(rec.gyro, axis=1)
    taps = []
    for s, e in runs(np.abs(acc_mag - 1) > 1.5, merge_gap=20):
        if e - s > 40:                      # longer than 40 ms: a movement, not a tap
            continue
        # The impact itself jolts the gyro for a few ms (seen: 450-490 dps on real taps), so judge
        # "the racket is otherwise still" on the 300 ms before and after, skipping 50 ms around the spike.
        before = gyro_mag[max(0, s - 300):max(0, s - 50)]
        after = gyro_mag[e + 50:e + 300]
        if max(before.max(initial=0), after.max(initial=0)) > 300:   # part of a swing, not a deliberate tap
            continue
        peak = s + int(np.argmax(acc_mag[s:e + 1]))
        if acc_mag[peak] - 1 > 2.5:
            taps.append(peak)
    return taps
