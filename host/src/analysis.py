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
TAP_GROUP_MS = 300         # impact peaks closer than this are one tap (bounces)


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
    """Rows of sync taps: the frame hits the palm, so |a| spikes and the racket's rotation stops at once.

    Rule (rev 4, 2026-10-31):
    - a candidate is an impact peak with |a| - 1 > 2.5 g. There is no length limit any more: the motion
      towards the palm can itself reach ~2.4 g, so the spike above 1.5 g lasted 43 ms
      (10-31-test1, 13.88 s) and the old "<= 40 ms" rule missed it.
    - the impact must stop the rotation: the minimum |gyro| in the 20 ms after the peak is under half the
      maximum in the 30 ms before it (seen: 384 -> 50, 366 -> 118, 375 -> 45 dps). Arm movements and
      bumps without a sudden stop (a false tap at 46.3 s in 10-31-test1: 2.6 g, gyro 175 -> 150) fail this.
    - the frame often bounces off the palm (2nd spike ~200 ms later), so peaks closer than TAP_GROUP_MS
      are one tap, timed at the first peak = the first contact seen in the video.
    - the racket is not swinging: |gyro| < 300 dps in the 300 ms before and after the group, skipping
      50 ms next to it (the impact jolts the gyro for a few ms)."""
    acc_mag = np.linalg.norm(rec.acc, axis=1)
    gyro_mag = np.linalg.norm(rec.gyro, axis=1)
    peaks = [s + int(np.argmax(acc_mag[s:e + 1])) for s, e in runs(acc_mag - 1 > 2.5, merge_gap=20)]

    groups = []
    for p in peaks:
        if groups and p - groups[-1][-1] < TAP_GROUP_MS:
            groups[-1].append(p)
        else:
            groups.append([p])

    taps = []
    for g in groups:
        first, last = g[0], g[-1]
        before = gyro_mag[max(0, first - 300):max(0, first - 50)]
        after = gyro_mag[last + 50:last + 300]
        if max(before.max(initial=0), after.max(initial=0)) > 300:   # part of a swing, not a deliberate tap
            continue
        if gyro_mag[first:first + 20].min() < 0.5 * gyro_mag[max(0, first - 30):first + 1].max():
            taps.append(first)
    return taps
