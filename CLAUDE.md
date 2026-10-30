# IoRacket — context for coding agents

Smart badminton racket, v1 prototype. A 3D-printed end cap holds an MCU, IMU and LiPo
inside the hollow grip of a Victor G5 racket. Long-term: combine IMU data with video
and coach labels into a badminton coaching system.

## Hardware (as built, Oct 2026)
- MCU: Seeed XIAO ESP32-S3 (PlatformIO board `seeed_xiao_esp32s3`)
- IMU: MPU6050 on a GY-521 breakout, I2C address 0x68
- Battery: 100 mAh 1S LiPo, soldered to the XIAO's rear BAT+/BAT- pads
- Wiring: IMU VCC -> 3V3, GND -> GND, SDA -> D4 (GPIO5), SCL -> D5 (GPIO6). INT not connected.
- Power: no switch; battery is always connected. USB-C charges it via the XIAO.
- Mounting: see `hardware/README.md`. The IMU must be rigidly fixed (no foam) or data picks up frame vibration.

## Layout
- `firmware/` PlatformIO project. `src/` = main firmware, `examples/imu_test/` = I2C bring-up test.
- `host/` Python receiver/plotter (Bleak + PySide6 + pyqtgraph). Data CSVs go in `host/data/` (git-ignored).
- `hardware/` CAD exports (STL) and fit notes. `hardware/_archive/` is local-only and git-ignored.

## Current status
- Hardware assembled and powered. IMU power LED on. I2C scan not yet confirmed on the final wiring.
- Next milestone: **IMU saturation test** — does a full smash clip the sensor?

## Next steps (in order)
1. `pio run -e imu_test -t upload` then monitor; expect `Found device 0x68 on SDA=5 SCL=6`.
2. Saturation-test firmware:
   - Set ranges to +/-2000 dps and +/-16 g. **Chip defaults are +/-250 dps / +/-2 g.**
   - Widen the DLPF (current main.cpp uses 21 Hz, which smears swing peaks; use 260 Hz).
   - Sample 500 Hz-1 kHz, I2C at 400 kHz. Prefer reading raw registers over Adafruit `getEvent` if too slow.
   - On-board: segment swings, record per-swing peak |acc| / |gyro| and whether any raw sample hit +/-32767.
   - Send only per-swing summaries over BLE (full-rate streaming likely exceeds BLE throughput).
3. Fix the host app (see known issues), then plot all 6 axes.

## Known issues
- `firmware/src/main.cpp` still inlines all BLE setup; `BLEManager` exists but is unused, `SensorManager.cpp` is empty.
- `main.cpp`: gyro range 500 dps and 21 Hz filter (see above); `addServiceUUID`/`setScanResponse` called twice; `loop()` busy-spins when no BLE client is connected.
- XIAO user LED is GPIO21 (old code used GPIO2).
- `host/main.py` imports `from ble_manager import ...` but the module is `src/ble_manager.py` -> ImportError. It also runs a scan-only `asyncio.run(main())` before opening the window.
- `host/src/ai_analyzer.py`, `data_parser.py`, `database.py` are empty placeholders.
- `host/venv` was created before the folder was renamed and may be broken; recreate it:
  `cd host && rm -rf venv && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`

## BLE protocol (current)
- Service `db87fb0a-cf98-4a2f-889b-3078ebaf19fb`, characteristic `253113ce-9a58-4847-b67d-f94b719837dc` (notify).
- Packet `BadmintonData` (packed, little-endian, 28 B): `uint32 timestamp_ms, float acc[3] (m/s^2), float gyro[3] (rad/s)`; Python: `struct.unpack('<I6f', data)`.

## Working style
- Owner is learning embedded; explain hardware-facing decisions briefly. One feature at a time, keep code readable, no over-engineering.
