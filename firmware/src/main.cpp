/**
 * This is the main program of IoRacket (firmware v2).
 * Streams raw 1 kHz IMU data over BLE in the v2 packet format (CLAUDE.md "BLE protocol v2").
 * Sampling runs only while a host is subscribed; otherwise the IMU sleeps and the racket
 * advertises slowly. Serial prints connection events and once-per-second counters.
 *
 * @author Zifan Zuo
 * @date 2026-Oct-29
 */
#include <Arduino.h>
#include <esp_system.h>
#include <soc/rtc_cntl_reg.h>

#include "BLEManager.h"
#include "SensorManager.h"

#ifndef IMU_SDA
#define IMU_SDA 5   // XIAO D4
#endif
#ifndef IMU_SCL
#define IMU_SCL 6   // XIAO D5
#endif

const char* DEVICE_NAME = "Zifan_Badminton_Sensor";
const int HEADER_BYTES = 6;             // uint32 first_sample_index, uint8 n_samples, uint8 ranges
const int MAX_SAMPLES_PER_PACKET = 18;  // 6 + 18 * 12 = 222 B
const int SAMPLE_BYTES = SensorManager::SAMPLE_BYTES;

SensorManager imu(IMU_SDA, IMU_SCL);
BLEManager ble;
bool imuOk = false;

// Packet being filled. Samples are read from the FIFO straight into it.
uint8_t packet[HEADER_BYTES + MAX_SAMPLES_PER_PACKET * SAMPLE_BYTES];
int packetSamples = 0;     // samples already in `packet`
int packetCapacity = 1;    // samples per packet at the current MTU
uint32_t sampleIndex = 0;  // index of the first sample in `packet`
uint32_t lastReadMs = 0;   // time of the last FIFO read that did not overflow
bool streaming = false;

uint32_t statSamples = 0, statPackets = 0, statOverflows = 0, statStart = 0, statMaxLoopMs = 0;

void sendPacket() {
    memcpy(packet, &sampleIndex, 4);  // the ESP32 is little-endian, as the protocol wants
    packet[4] = packetSamples;
    packet[5] = SensorManager::RANGES;
    ble.sendPacket(packet, HEADER_BYTES + packetSamples * SAMPLE_BYTES);
    sampleIndex += packetSamples;
    packetSamples = 0;
    packetCapacity = ble.samplesPerPacket(HEADER_BYTES, SAMPLE_BYTES, MAX_SAMPLES_PER_PACKET);
    statPackets++;
}

void startStreaming() {
    imu.wake();
    sampleIndex = 0;
    packetSamples = 0;
    packetCapacity = ble.samplesPerPacket(HEADER_BYTES, SAMPLE_BYTES, MAX_SAMPLES_PER_PACKET);
    lastReadMs = millis();
    statSamples = statPackets = statOverflows = statMaxLoopMs = 0;
    statStart = millis();
    streaming = true;
    Serial.printf("[%lu] streaming, %d samples/packet\n", millis(), packetCapacity);
}

void stopStreaming() {
    imu.sleep();
    streaming = false;
    Serial.printf("[%lu] stopped, IMU asleep\n", millis());
}

// Read everything the FIFO holds into packets, sending each one as it fills up.
void pumpFifo() {
    while (true) {
        bool overflowed = false;
        int n = imu.read(packet + HEADER_BYTES + packetSamples * SAMPLE_BYTES,
                         packetCapacity - packetSamples, &overflowed);
        if (overflowed) {
            // The FIFO contents were thrown away. Send what we already have, then move the index
            // past the lost samples (1 per ms at 1 kHz) so the host sees a gap, like a lost packet.
            if (packetSamples > 0) sendPacket();
            sampleIndex += millis() - lastReadMs;
            lastReadMs = millis();
            statOverflows++;
            continue;
        }
        lastReadMs = millis();
        if (n == 0) return;
        packetSamples += n;
        statSamples += n;
        if (packetSamples == packetCapacity) sendPacket();
    }
}

void printStats() {
    float seconds = (millis() - statStart) / 1000.0f;
    Serial.printf("[%lu] %.0f Hz read, %.1f packets/s, notify errors %lu, ovf=%lu, i2c err=%lu, max loop %lu ms\n",
                  millis(), statSamples / seconds, statPackets / seconds, ble.takeNotifyErrors(), statOverflows,
                  imu.readErrors, statMaxLoopMs);
    statSamples = statPackets = statOverflows = statMaxLoopMs = 0;
    imu.readErrors = 0;
    statStart = millis();
}

// Set the "force download boot" flag (it survives a software reset), then restart:
// the chip comes back up waiting for a firmware upload.
void rebootIntoBootloader() {
    REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
    esp_restart();
}

void setup() {
    Serial.begin(115200);
    // On battery nobody reads the USB serial. With the default 100 ms timeout a print can stall the loop
    // longer than the FIFO lasts (85 ms); with 0 the core's retry counter wraps around (uint32 0 - 1) and a
    // print blocks until USB comes back (seen: 51 s stall). 1 ms gives up quickly and is safe.
    Serial.setTxTimeoutMs(1);
    delay(500);
    Serial.println("\n=== IoRacket firmware v2 ===");
    imuOk = imu.begin();
    Serial.println(imuOk ? "IMU configured (asleep until a host subscribes)" : "IMU not found!");
    ble.begin(DEVICE_NAME);
    Serial.println("Advertising");
}

void loop() {
    if (ble.bootloaderRequested()) {
        Serial.println("Rebooting into download mode...");
        delay(200);  // let the BLE write be acknowledged first
        rebootIntoBootloader();
    }

    bool subscribed = imuOk && ble.isSubscribed();
    if (subscribed && !streaming) startStreaming();
    if (!subscribed && streaming) stopStreaming();
    if (!streaming) {
        delay(50);  // idle: nothing to do until a host subscribes
        return;
    }

    uint32_t loopStart = millis();
    pumpFifo();
    statMaxLoopMs = max(statMaxLoopMs, (uint32_t)(millis() - loopStart));
    if (millis() - statStart >= 1000) printStats();
    delay(5);  // the FIFO holds ~85 ms of samples, so short naps are safe
}
