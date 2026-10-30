// v2 step A: read the MPU6050 through its FIFO at 1 kHz using raw registers.
// Prints one line per second over USB serial:
//   samples received (expect ~1000), FIFO overflows (expect 0),
//   saturated samples (any axis at the int16 limit), and per-axis peak |value|.
#include <Arduino.h>
#include <Wire.h>

#ifndef IMU_SDA
#define IMU_SDA 5   // XIAO D4
#endif
#ifndef IMU_SCL
#define IMU_SCL 6   // XIAO D5
#endif

const uint8_t MPU_ADDR = 0x68;

// MPU6050 registers (see the MPU-6000/6050 register map)
const uint8_t REG_SMPLRT_DIV   = 0x19;
const uint8_t REG_CONFIG       = 0x1A;
const uint8_t REG_GYRO_CONFIG  = 0x1B;
const uint8_t REG_ACCEL_CONFIG = 0x1C;
const uint8_t REG_FIFO_EN      = 0x23;
const uint8_t REG_INT_ENABLE   = 0x38;
const uint8_t REG_INT_STATUS   = 0x3A;
const uint8_t REG_USER_CTRL    = 0x6A;
const uint8_t REG_PWR_MGMT_1   = 0x6B;
const uint8_t REG_FIFO_COUNT_H = 0x72;
const uint8_t REG_FIFO_R_W     = 0x74;
const uint8_t REG_WHO_AM_I     = 0x75;

const int SAMPLE_BYTES = 12;            // accel x,y,z + gyro x,y,z, each int16 big-endian
const int MAX_BURST_SAMPLES = 10;       // 120 B per read; ESP32 Wire buffer is 128 B

// Scale factors for the chosen ranges
const float ACC_LSB_PER_G     = 2048.0f;  // +/-16 g
const float GYRO_LSB_PER_DPS  = 16.4f;    // +/-2000 dps

void writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool readRegs(uint8_t reg, uint8_t* buf, size_t len) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint16_t)MPU_ADDR, len) != len) return false;
  for (size_t i = 0; i < len; i++) buf[i] = Wire.read();
  return true;
}

void resetFifo() {
  writeReg(REG_USER_CTRL, 0x04);  // FIFO_RESET (also turns FIFO off)
  writeReg(REG_USER_CTRL, 0x40);  // FIFO_EN on again
}

// If the MCU was reset in the middle of an I2C read, the IMU (which stays powered) can still be
// holding SDA low, waiting to send the rest of a byte. Clocking SCL up to 9 times lets it finish
// and release SDA; then a STOP condition returns the bus to idle.
// Returns true if SDA was stuck low at boot.
bool recoverBus() {
  pinMode(IMU_SDA, INPUT_PULLUP);
  pinMode(IMU_SCL, OUTPUT_OPEN_DRAIN);
  digitalWrite(IMU_SCL, HIGH);
  delayMicroseconds(10);
  bool stuck = digitalRead(IMU_SDA) == LOW;
  for (int i = 0; i < 9 && digitalRead(IMU_SDA) == LOW; i++) {
    digitalWrite(IMU_SCL, LOW);  delayMicroseconds(5);
    digitalWrite(IMU_SCL, HIGH); delayMicroseconds(5);
  }
  // STOP: SDA goes low -> high while SCL is high
  pinMode(IMU_SDA, OUTPUT_OPEN_DRAIN);
  digitalWrite(IMU_SDA, LOW);  delayMicroseconds(5);
  digitalWrite(IMU_SCL, HIGH); delayMicroseconds(5);
  digitalWrite(IMU_SDA, HIGH); delayMicroseconds(5);
  return stuck;
}

// Try I2C clocks from fastest to slowest; return the first one where all WHO_AM_I reads succeed, or 0.
uint32_t pickI2cClock() {
  const uint32_t clocks[] = {400000, 200000, 100000};
  for (uint32_t hz : clocks) {
    Wire.end();
    Wire.begin(IMU_SDA, IMU_SCL, hz);
    delay(10);
    int ok = 0;
    for (int i = 0; i < 100; i++) {
      uint8_t who = 0;
      if (readRegs(REG_WHO_AM_I, &who, 1) && who == 0x68) ok++;
    }
    Serial.printf("I2C %lu kHz: WHO_AM_I ok %d/100\n", hz / 1000, ok);
    if (ok == 100) return hz;
  }
  return 0;
}

bool setupImu() {
  writeReg(REG_PWR_MGMT_1, 0x80);    // full reset
  delay(100);
  writeReg(REG_PWR_MGMT_1, 0x01);    // wake up, clock from gyro X PLL (more accurate than internal RC)
  delay(10);
  writeReg(REG_CONFIG, 0x00);        // DLPF widest: accel 260 Hz / gyro 256 Hz; gyro runs at 8 kHz
  writeReg(REG_SMPLRT_DIV, 7);       // sample rate = 8 kHz / (1 + 7) = 1 kHz
  writeReg(REG_GYRO_CONFIG, 0x18);   // +/-2000 dps
  writeReg(REG_ACCEL_CONFIG, 0x18);  // +/-16 g
  writeReg(REG_INT_ENABLE, 0x10);    // latch FIFO overflow in INT_STATUS (INT pin is not wired)
  writeReg(REG_FIFO_EN, 0x78);       // put accel + gyro x/y/z into the FIFO (no temperature)
  resetFifo();
  return true;
}

// Stats for the current one-second window
uint32_t samples = 0, overflows = 0, saturated = 0, readErrors = 0;
int16_t peak[6] = {0};               // max |raw| per axis: ax ay az gx gy gz
uint32_t windowStart = 0;

void processSample(const uint8_t* p) {
  bool sat = false;
  for (int i = 0; i < 6; i++) {
    int16_t v = (int16_t)((p[2 * i] << 8) | p[2 * i + 1]);
    if (v == 32767 || v == -32768) sat = true;
    int16_t mag = (v == -32768) ? 32767 : abs(v);
    if (mag > peak[i]) peak[i] = mag;
  }
  if (sat) saturated++;
  samples++;
}

void printStats() {
  uint32_t now = millis();
  float seconds = (now - windowStart) / 1000.0f;
  Serial.printf("%.0f Hz (n=%lu) ovf=%lu sat=%lu err=%lu | peak acc g: %5.2f %5.2f %5.2f | peak gyro dps: %7.1f %7.1f %7.1f\n",
                samples / seconds, samples, overflows, saturated, readErrors,
                peak[0] / ACC_LSB_PER_G, peak[1] / ACC_LSB_PER_G, peak[2] / ACC_LSB_PER_G,
                peak[3] / GYRO_LSB_PER_DPS, peak[4] / GYRO_LSB_PER_DPS, peak[5] / GYRO_LSB_PER_DPS);
  samples = overflows = saturated = readErrors = 0;
  for (int i = 0; i < 6; i++) peak[i] = 0;
  windowStart = now;
}

bool imuOk = false;

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\n=== FIFO test: 1 kHz, +/-16 g, +/-2000 dps, DLPF 260 Hz ===");
  Serial.println(recoverBus() ? "SDA was stuck low at boot -> bus recovered" : "SDA idle at boot (bus OK)");
  uint32_t hz = pickI2cClock();
  if (hz == 0) {
    Serial.println("No I2C clock works. Check SDA/SCL wiring and solder joints.");
    return;
  }
  imuOk = setupImu();
  Serial.printf(imuOk ? "IMU configured, I2C at %lu kHz\n" : "IMU setup failed\n", hz / 1000);
  windowStart = millis();
}

void loop() {
  if (!imuOk) { delay(1000); return; }

  uint8_t status = 0;
  if (readRegs(REG_INT_STATUS, &status, 1) && (status & 0x10)) {
    // FIFO filled up before we read it: data is no longer aligned to 12-byte samples, start over.
    overflows++;
    resetFifo();
  }

  uint8_t c[2];
  if (!readRegs(REG_FIFO_COUNT_H, c, 2)) { readErrors++; return; }
  int available = ((c[0] << 8) | c[1]) / SAMPLE_BYTES;

  uint8_t buf[MAX_BURST_SAMPLES * SAMPLE_BYTES];
  while (available > 0) {
    int n = min(available, MAX_BURST_SAMPLES);
    if (!readRegs(REG_FIFO_R_W, buf, n * SAMPLE_BYTES)) { readErrors++; break; }
    for (int i = 0; i < n; i++) processSample(buf + i * SAMPLE_BYTES);
    available -= n;
  }

  if (millis() - windowStart >= 1000) printStats();
  delay(10);  // FIFO holds ~85 samples (85 ms at 1 kHz), so 10 ms polling leaves plenty of margin
}
