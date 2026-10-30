/**
 * Reads the MPU6050 through its FIFO at 1 kHz using raw registers.
 * Fixed settings (CLAUDE.md design decisions): +/-16 g, +/-2000 dps, DLPF 260 Hz, I2C 400 kHz.
 * A sample is 12 bytes: ax ay az gx gy gz as int16 big-endian, exactly as the chip sends them.
 *
 * @author Zifan Zuo
 * @date 2026-Oct-29
 */

#pragma once

#include <Arduino.h>

class SensorManager {
public:
    static const int SAMPLE_BYTES = 12;

    /** Ranges byte for the BLE packet: gyro FS_SEL << 4 | accel AFS_SEL (3 = 2000 dps, 3 = 16 g). */
    static const uint8_t RANGES = (3 << 4) | 3;

    SensorManager(int sdaPin, int sclPin);

    /** Recover the I2C bus, configure the IMU and leave it asleep. False if the IMU does not answer. */
    bool begin();

    /** Wake the IMU and start sampling into an empty FIFO. */
    void wake();

    /** Put the IMU to sleep (a few uA instead of a few mA). */
    void sleep();

    /**
     * Copy up to maxSamples complete samples from the FIFO into buf and return how many were copied.
     * If the FIFO overflowed since the last call, its contents are discarded (they are no longer
     * aligned to 12-byte samples), 0 is returned and *overflowed is set to true.
     */
    int read(uint8_t* buf, int maxSamples, bool* overflowed);

    uint32_t readErrors = 0;

private:
    int sda, scl;

    void recoverBus();
    void resetFifo();
    void writeReg(uint8_t reg, uint8_t value);
    bool readRegs(uint8_t reg, uint8_t* buf, size_t len);
};
