// Minimal bring-up test: find the IMU on I2C, then print readings.
// If the default pins find nothing, scan GPIO pairs to discover the wiring.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>

#ifndef IMU_SDA
#define IMU_SDA 5   // XIAO D4
#endif
#ifndef IMU_SCL
#define IMU_SCL 6   // XIAO D5
#endif

Adafruit_MPU6050 mpu;

// Returns the first responding I2C address on the given pins, or 0.
uint8_t scanPins(int sda, int scl) {
  Wire.end();
  if (!Wire.begin(sda, scl, 100000)) return 0;
  for (uint8_t addr = 0x08; addr < 0x78; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) return addr;
  }
  return 0;
}

void discoverPins() {
  // GPIOs that are safe on ESP32-S3 (skip flash/PSRAM 26-37, USB 19/20, strapping 0/3/45/46)
  const int pins[] = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 38, 39, 40, 41, 42, 47, 48};
  for (int sda : pins)
    for (int scl : pins) {
      if (sda == scl) continue;
      uint8_t addr = scanPins(sda, scl);
      if (addr) {
        Serial.printf("Found device 0x%02X with SDA=%d SCL=%d\n", addr, sda, scl);
        return;
      }
    }
  Serial.println("No I2C device found on any pin pair. Check soldering / power (3V3, GND).");
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\n=== IMU bring-up test ===");

  uint8_t addr = scanPins(IMU_SDA, IMU_SCL);
  if (addr) {
    Serial.printf("Found device 0x%02X on SDA=%d SCL=%d\n", addr, IMU_SDA, IMU_SCL);
  } else {
    Serial.printf("Nothing on SDA=%d SCL=%d, scanning other pin pairs...\n", IMU_SDA, IMU_SCL);
    discoverPins();
    return;
  }

  if (!mpu.begin(addr)) {
    Serial.println("Device responded but is not a recognised MPU6050 (check chip model).");
    return;
  }
  Serial.println("MPU6050 OK");
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last < 200) return;
  last = millis();

  sensors_event_t a, g, t;
  if (!mpu.getEvent(&a, &g, &t)) return;
  Serial.printf("acc[m/s2] %6.2f %6.2f %6.2f | gyro[rad/s] %6.2f %6.2f %6.2f | %.1fC\n",
                a.acceleration.x, a.acceleration.y, a.acceleration.z,
                g.gyro.x, g.gyro.y, g.gyro.z, t.temperature);
}
