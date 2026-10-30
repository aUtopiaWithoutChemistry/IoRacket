#include "SensorManager.h"

#include <Wire.h>

// MPU6050 registers (see the MPU-6000/6050 register map)
static const uint8_t MPU_ADDR         = 0x68;
static const uint8_t REG_SMPLRT_DIV   = 0x19;
static const uint8_t REG_CONFIG       = 0x1A;
static const uint8_t REG_GYRO_CONFIG  = 0x1B;
static const uint8_t REG_ACCEL_CONFIG = 0x1C;
static const uint8_t REG_FIFO_EN      = 0x23;
static const uint8_t REG_INT_ENABLE   = 0x38;
static const uint8_t REG_INT_STATUS   = 0x3A;
static const uint8_t REG_USER_CTRL    = 0x6A;
static const uint8_t REG_PWR_MGMT_1   = 0x6B;
static const uint8_t REG_FIFO_COUNT_H = 0x72;
static const uint8_t REG_FIFO_R_W     = 0x74;
static const uint8_t REG_WHO_AM_I     = 0x75;

static const uint8_t PWR_AWAKE  = 0x01;  // clock from gyro X PLL (more accurate than the internal RC)
static const uint8_t PWR_ASLEEP = 0x41;  // same clock setting + SLEEP bit

static const int MAX_BURST_SAMPLES = 10;  // 120 B per I2C read; the ESP32 Wire buffer is 128 B

SensorManager::SensorManager(int sdaPin, int sclPin) : sda(sdaPin), scl(sclPin) {}

bool SensorManager::begin() {
    recoverBus();
    Wire.begin(sda, scl, 400000);

    uint8_t who = 0;
    if (!readRegs(REG_WHO_AM_I, &who, 1) || who != 0x68) return false;

    writeReg(REG_PWR_MGMT_1, 0x80);    // full reset
    delay(100);
    writeReg(REG_PWR_MGMT_1, PWR_AWAKE);
    delay(10);
    writeReg(REG_CONFIG, 0x00);        // DLPF widest: accel 260 Hz / gyro 256 Hz; gyro runs at 8 kHz
    writeReg(REG_SMPLRT_DIV, 7);       // sample rate = 8 kHz / (1 + 7) = 1 kHz
    writeReg(REG_GYRO_CONFIG, 0x18);   // FS_SEL 3: +/-2000 dps
    writeReg(REG_ACCEL_CONFIG, 0x18);  // AFS_SEL 3: +/-16 g
    writeReg(REG_INT_ENABLE, 0x10);    // latch FIFO overflow in INT_STATUS (the INT pin is not wired)
    writeReg(REG_FIFO_EN, 0x78);       // accel + gyro x/y/z into the FIFO, no temperature
    sleep();
    return true;
}

void SensorManager::wake() {
    writeReg(REG_PWR_MGMT_1, PWR_AWAKE);
    delay(50);  // let the gyro start up (datasheet: ~30 ms) before collecting samples
    resetFifo();
}

void SensorManager::sleep() {
    writeReg(REG_PWR_MGMT_1, PWR_ASLEEP);
}

int SensorManager::read(uint8_t* buf, int maxSamples, bool* overflowed) {
    *overflowed = false;
    uint8_t status = 0;
    if (readRegs(REG_INT_STATUS, &status, 1) && (status & 0x10)) {
        resetFifo();
        *overflowed = true;
        return 0;
    }

    uint8_t c[2];
    if (!readRegs(REG_FIFO_COUNT_H, c, 2)) { readErrors++; return 0; }
    int available = ((c[0] << 8) | c[1]) / SAMPLE_BYTES;
    int total = min(available, maxSamples);

    int done = 0;
    while (done < total) {
        int n = min(total - done, MAX_BURST_SAMPLES);
        if (!readRegs(REG_FIFO_R_W, buf + done * SAMPLE_BYTES, n * SAMPLE_BYTES)) { readErrors++; break; }
        done += n;
    }
    return done;
}

// If the MCU was reset in the middle of an I2C read (e.g. opening the serial port resets it), the IMU,
// which stays powered, can be left holding SDA low. Clocking SCL up to 9 times lets it finish the byte
// and release SDA; a STOP condition then returns the bus to idle.
void SensorManager::recoverBus() {
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, OUTPUT_OPEN_DRAIN);
    digitalWrite(scl, HIGH);
    delayMicroseconds(10);
    for (int i = 0; i < 9 && digitalRead(sda) == LOW; i++) {
        digitalWrite(scl, LOW);  delayMicroseconds(5);
        digitalWrite(scl, HIGH); delayMicroseconds(5);
    }
    // STOP: SDA goes low -> high while SCL is high
    pinMode(sda, OUTPUT_OPEN_DRAIN);
    digitalWrite(sda, LOW);  delayMicroseconds(5);
    digitalWrite(scl, HIGH); delayMicroseconds(5);
    digitalWrite(sda, HIGH); delayMicroseconds(5);
}

void SensorManager::resetFifo() {
    uint8_t status;
    readRegs(REG_INT_STATUS, &status, 1);  // reading clears a stale overflow flag
    writeReg(REG_USER_CTRL, 0x04);         // FIFO_RESET (also turns the FIFO off)
    writeReg(REG_USER_CTRL, 0x40);         // FIFO_EN on again
}

void SensorManager::writeReg(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(value);
    Wire.endTransmission();
}

bool SensorManager::readRegs(uint8_t reg, uint8_t* buf, size_t len) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom((uint16_t)MPU_ADDR, len) != len) return false;
    for (size_t i = 0; i < len; i++) buf[i] = Wire.read();
    return true;
}
