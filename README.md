# IoRacket

A smart badminton racket: a 3D-printed end cap puts an ESP32-S3 and a 6-axis IMU inside the racket grip, streams raw motion data at 1 kHz over Bluetooth LE, and a desktop app shows it live and replays it in sync with video.

**Status:** v1 working end to end: racket -> BLE -> live plots -> recording -> replay synced with video.

<!-- Demo GIF goes here: screen recording of the replay window (video on the left, synced 6-axis data on the right). -->

## What v1 does
- **Firmware:** reads the IMU through its hardware FIFO at **1000 Hz** (+/-16 g, +/-2000 deg/s, raw int16) and streams it over BLE in batched packets (18 samples, 222 B). Tested with 0 lost samples on USB power and on battery. Sampling starts when the app subscribes and the IMU sleeps otherwise.
- **Live view:** 6 axes in separate plots with the sensor limits drawn in, saturated samples marked; sample rate, lost packets and saturation counters.
- **Recording:** raw data to CSV (lossless, every gap in `sample_index` = lost data); on stop, name the file and add a note.
- **Replay:**
  - overview of the whole session with automatically detected swings
  - swing list: peak angular velocity, peak acceleration, estimated racket-head speed (km/h), clipping
  - one swing in detail, or all swings overlaid at their peak
- **Video sync:** link a phone video to a recording, mark the two sync taps frame by frame, then play video and data together, with slow motion (down to 1/8 speed for 240 fps footage). Clicking a swing or the overview jumps the video there.

## Recording a session with video
1. Start the phone video (120/240 fps if possible), then **tap the racket frame once** against your palm.
2. Put the racket down still for 1-2 s (used to estimate the gyro offset).
3. Play your strokes.
4. **Tap the frame once more**, then stop the video.

In the replay window, **Link video…** attaches the video (it is copied next to the CSV). Step to each tap with the frame buttons and press **This frame = start tap** / **This frame = end tap**; the sync dialog then opens pre-filled. The two taps give both the time offset and the IMU's true sample rate.

## First finding: a full swing clips the MPU6050
In the first saturation test, every hard swing exceeded the gyro range (+/-2000 deg/s per axis) for 30-80 ms, and the hardest ones also hit +/-16 g. Fitting the clipped peaks suggests roughly 3000-3500 deg/s and 20-23 g (rough, likely higher). The next hardware revision needs a +/-4000 deg/s, >= +/-32 g IMU; until then, peak values of hard swings are lower bounds (marked "≥" in the app).

## Hardware
- Seeed XIAO ESP32-S3 + MPU6050 (GY-521) + 100 mAh LiPo
- Custom parametric end cap (Autodesk Fusion), printed in PLA+, ~5 g
- **Attach the U.FL antenna** to the XIAO; without it the BLE link drops within a second.
- Details, measurements and wiring: [`hardware/README.md`](hardware/README.md)

## Repository layout
| Folder | What |
|---|---|
| `firmware/` | PlatformIO firmware for the XIAO ESP32-S3 (`src/` = main firmware, `examples/` = bring-up and test programs) |
| `host/` | Python desktop app (PySide6 + pyqtgraph + Bleak): live view, recording, replay, video sync |
| `hardware/` | End cap CAD exports and build notes |

## Quick start
```bash
# firmware (hold B, tap R, release B to enter download mode before each upload)
cd firmware
pio run -e imu_test -t upload && pio device monitor   # check the IMU is found
pio run -e xiao -t upload                              # main firmware

# host app
cd host
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py        # tick "Simulator" to try it without the racket
```

## Roadmap
- [x] End cap design and fit iterations (v1 -> v3)
- [x] Assembly and wiring
- [x] 1 kHz raw streaming over BLE, live view, recording
- [x] IMU saturation test (yes, a full swing clips +/-2000 deg/s and +/-16 g)
- [x] Swing segmentation, per-swing metrics, replay
- [x] Video sync (two frame taps) with slow-motion playback
- [ ] v2: data analysis: racket orientation reconstruction, 3D swing replay, forehand/backhand
- [ ] Higher-range IMU (custom PCBA)
- [ ] v3: live phone camera stream recorded together with the IMU data
- [ ] Coach labels -> badminton coaching feedback
