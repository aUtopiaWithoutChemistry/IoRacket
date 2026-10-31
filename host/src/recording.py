"""A recorded CSV (raw int16 IMU data) plus its optional sidecar file <csv>.sync.json, which holds
the linked video (a copy stored next to the CSV) and the video sync."""
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

NOMINAL_RATE_HZ = 1000


@dataclass
class Recording:
    path: Path
    index: np.ndarray        # sample_index, shape (n,)
    raw: np.ndarray          # ax ay az gx gy gz raw int16 values, shape (n, 6)
    accel_range_g: int
    gyro_range_dps: int
    note: str = ""

    @property
    def acc(self) -> np.ndarray:
        """Acceleration in g, shape (n, 3)."""
        return self.raw[:, :3] * (self.accel_range_g / 32768.0)

    @property
    def gyro(self) -> np.ndarray:
        """Angular velocity in deg/s, shape (n, 3)."""
        return self.raw[:, 3:] * (self.gyro_range_dps / 32768.0)

    @property
    def t(self) -> np.ndarray:
        """Time in seconds from the sample index at the nominal rate."""
        return self.index / NOMINAL_RATE_HZ

    @property
    def saturated(self) -> np.ndarray:
        """Boolean mask, shape (n, 6): sample sits at the int16 limit."""
        return (self.raw >= 32767) | (self.raw <= -32768)

    @property
    def sync_path(self) -> Path:
        return self.path.with_suffix(".sync.json")


def load_recording(path) -> Recording:
    path = Path(path)
    accel_range, gyro_range, note = 16, 2000, ""
    header_rows = 0  # comment lines + the column-name line, all skipped by loadtxt
    with open(path) as f:
        for line in f:
            header_rows += 1
            m = re.search(r"accel_range_g=(\d+) gyro_range_dps=(\d+)", line)
            if m:
                accel_range, gyro_range = int(m.group(1)), int(m.group(2))
            if line.startswith("# note="):
                note = line[len("# note="):].strip()
            if line.startswith("sample_index"):
                break
    if path.stat().st_size == 0 or header_rows == 0:
        raise ValueError("no data")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # loadtxt warns on a file with a header but no rows
        data = np.loadtxt(path, delimiter=",", comments="#", skiprows=header_rows, dtype=np.int64, ndmin=2)
    if len(data) == 0:
        raise ValueError("no data")
    return Recording(path, data[:, 0], data[:, 1:7], accel_range, gyro_range, note)


@dataclass
class VideoSync:
    """Maps sample index <-> video time using two taps seen in both the IMU data and the video."""
    tap_index: tuple       # (i1, i2) sample indices of the two taps
    video_time_s: tuple    # (v1, v2) times of the same taps in the video

    @property
    def rate_hz(self) -> float:
        """True IMU sample rate implied by the two taps."""
        return (self.tap_index[1] - self.tap_index[0]) / (self.video_time_s[1] - self.video_time_s[0])

    def to_video_time(self, index):
        return self.video_time_s[0] + (np.asarray(index) - self.tap_index[0]) / self.rate_hz

    def to_index(self, video_time_s):
        return self.tap_index[0] + (np.asarray(video_time_s) - self.video_time_s[0]) * self.rate_hz


def load_sidecar(rec: Recording):
    """(video file name or None, VideoSync or None)"""
    if not rec.sync_path.exists():
        return None, None
    d = json.loads(rec.sync_path.read_text())
    sync = VideoSync(tuple(d["tap_index"]), tuple(d["video_time_s"])) if "tap_index" in d else None
    return d.get("video"), sync


def save_sidecar(rec: Recording, video, sync):
    d = {}
    if video:
        d["video"] = video  # file name in the same folder as the CSV
    if sync:
        d["tap_index"] = [int(i) for i in sync.tap_index]
        d["video_time_s"] = [float(v) for v in sync.video_time_s]
    rec.sync_path.write_text(json.dumps(d, indent=2, ensure_ascii=False))


def finalize_recording(path: Path, name: str, note: str) -> Path:
    """After recording stops: add the note to the CSV header and rename the file to <name>_<date_time>.csv.
    Returns the final path."""
    note = " ".join(note.split())  # one line
    if note and path.stat().st_size > 0:
        lines = path.read_text().splitlines(keepends=True)
        lines.insert(1, f"# note={note}\n")
        path.write_text("".join(lines))
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")
    if not name:
        return path
    stamp = path.stem.removeprefix("racket_")   # keep the date/time so names never collide
    new_path = path.with_name(f"{name}_{stamp}.csv")
    path.rename(new_path)
    return new_path


def format_video_time(seconds: float) -> str:
    """83.456 -> '1:23.456'"""
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"


def parse_video_time(text: str) -> float:
    """'1:23.456' or '83.456' -> 83.456"""
    parts = text.strip().split(":")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    return seconds
