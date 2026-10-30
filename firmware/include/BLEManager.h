/**
 * This class is to handle BLE service initialization 
 * and data sending.
 * 
 * @author Zifan Zuo
 * @date 2026-Jan-26
 */

#pragma once

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BadmintonData.h>

class BLEManager {
private:
    BLECharacteristic* pCharacteristic;
    BLEAdvertising* pAdvertising;
    BLEServer* pServer;
    BLEService* pService;
    BLEDevice* pDevice;
    BadmintonData bdData;

public:
    /**
     * Setup BLE service and start advertising
     */
    BLEManager();

    /**
     * Destructor
     */
    ~BLEManager();

    /**
     * Initialize BLE service
     */
    void initBLE();

    /**
     * Send data via BLE notification
     * 
     * @param data Pointer to the data to send
     * @param length Length of the data
     */
    void sendData(uint8_t* data, size_t length);
};