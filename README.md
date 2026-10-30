# IoRacket

A smart badminton racket: a 3D-printed end cap puts an ESP32-S3 and a 6-axis IMU inside the racket grip and streams swing data over Bluetooth LE.

**Status:** v1 prototype — hardware assembled, firmware bring-up in progress.

## Hardware
- Seeed XIAO ESP32-S3 + MPU6050 (GY-521) + 100 mAh LiPo
- Custom parametric end cap (Autodesk Fusion), printed in PLA+, ~5 g
- Details, measurements and wiring: [`hardware/README.md`](hardware/README.md)

## Repository layout
| Folder | What |
|---|---|
| `firmware/` | PlatformIO firmware for the XIAO ESP32-S3 |
| `host/` | Python app that receives and plots BLE data |
| `hardware/` | End cap CAD exports and build notes |

## Quick start
```bash
# firmware
cd firmware
pio run -e imu_test -t upload && pio device monitor   # check the IMU is found
pio run -e xiao -t upload                              # main firmware

# host
cd host
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Roadmap
- [x] End cap design and fit iterations (v1 -> v3)
- [x] Assembly and wiring
- [ ] IMU saturation test (does a full smash clip +/-16 g / +/-2000 dps?)
- [ ] Swing segmentation and per-swing metrics
- [ ] Video sync + coach labels -> badminton coaching feedback
