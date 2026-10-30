/**
 * This class is to handle the BLE link: advertising, the data characteristic (v2 packets,
 * notify) and the control characteristic (commands written by the host).
 *
 * @author Zifan Zuo
 * @date 2026-Oct-29
 */

#pragma once

#include <Arduino.h>

class BLEManager {
public:
    /** Start BLE, create the service and start (slow) advertising. */
    void begin(const char* deviceName);

    /** True while a host is connected and has turned notifications on for the data characteristic. */
    bool isSubscribed() const;

    /** How many samples fit in one notification at the current MTU (at most maxSamples). */
    int samplesPerPacket(int headerBytes, int sampleBytes, int maxSamples) const;

    /** Send one packet as a notification. */
    void sendPacket(uint8_t* data, size_t length);

    /** True once the host has written the "reboot into download mode" command. */
    bool bootloaderRequested() const;

    /** Notifications the BLE stack refused since the last call (e.g. its send queue was full). */
    uint32_t takeNotifyErrors();
};
