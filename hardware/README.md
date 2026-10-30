# Hardware

## End cap (v3, current)
Designed in Autodesk Fusion (document "IoRacket endcap v1", parametric user parameters).
- `cad/endcap_v3.stl` — end cap + sled that slides into the hollow grip.
- `cad/fit_gauge.stl` — 4 short plugs to test grip fit. Notch count 1-4 = long side 21.0 / 21.2 / 21.4 / 21.6 mm. v3 matches plug #2.

v3 fit result: snug at the cap end, slightly loose further in; shimmed with Kapton when taping the IMU down.

### Grip measurements (Victor G5, measured 2026-10-22, includes old grip glue)
| | mm |
|---|---|
| Outer long side | 23.5 |
| Outer short side | 20.0 |
| Outer across diagonal flats | 23.0 |
| Wall | ~1.25 |
| Cavity depth | ~60 |

### Key parameters
| Parameter | Value | Note |
|---|---|---|
| `fit` | -0.1 mm | negative = sled larger than computed cavity (true wall is thinner under the glue) |
| `crush` | 0.25 mm | guide rib tip beyond cavity wall |
| `cap_h` | 6 mm | tapered cap height; top is flush with the grip |
| `bottom_t` | 1.5 mm | floor under the XIAO; USB-C hole 11 x 6.5 mm |
| `pk` | 0.2 mm | board pocket clearance per side |
| IMU pins | dia 2.6 mm, h 2 mm | **positions estimated from product photo — measure the IMU holes and update** |

Print settings used: Prusa MK4, PLA+, 0.20 mm STRUCTURAL, 3 perimeters, 20% infill, no supports, brim. ~5 g, ~35 min.

## Layout inside the sled (USB end down)
- Top deck: XIAO ESP32-S3 (component side up, USB-C through the cap floor), then wire bay, then MPU6050 on a light frame with two locating pins.
- Lower deck: 100 mAh LiPo (18 x 14 x 7 mm), wire exit toward the cap, wires pass up through the slot under the XIAO.
- The IMU's pin row sits over a solder-relief groove; mounting holes go over the locating pins.

## Wiring
| IMU | XIAO | Wire |
|---|---|---|
| VCC | 3V3 | red |
| GND | GND | black |
| SCL | D5 (GPIO6) | green |
| SDA | D4 (GPIO5) | yellow |
| Battery red (+) | BAT+ (rear pad, farther from USB) | via 40 mm extension |
| Battery black (-) | BAT- (rear pad, nearer USB) | via 40 mm extension |

Notes: 5V/VUSB, GND and 3V3 are adjacent on the XIAO edge — check for solder bridges with a continuity test before plugging in USB.
