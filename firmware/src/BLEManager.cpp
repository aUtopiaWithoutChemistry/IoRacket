#include "../include/BLEManager.h"

// uuid for bluetooth
#define SERVICE_UUID        "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
#define CHARACTERISTIC_UUID "253113ce-9a58-4847-b67d-f94b719837dc"

BLEManager::BLEManager() {
    Serial.begin(115200);
    BLEDevice::init("Zifan_Badminton_Sensor");
    pServer = BLEDevice::createServer();
    pService = pServer->createService(SERVICE_UUID);
    pCharacteristic = pService -> createCharacteristic(
                    CHARACTERISTIC_UUID,
                    BLECharacteristic::PROPERTY_READ |
                    BLECharacteristic::PROPERTY_WRITE |
                    BLECharacteristic::PROPERTY_NOTIFY
                  );
    pCharacteristic -> addDescriptor(new BLE2902());
    pService -> start();
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising -> addServiceUUID(SERVICE_UUID);
    pAdvertising -> setScanResponse(true);
    pAdvertising -> addServiceUUID(SERVICE_UUID); // add service UUID to advertising packet
    pAdvertising -> setScanResponse(true);
    pServer -> getAdvertising() -> start();
}

void BLEManager::initBLE() {
    
}

void BLEManager::sendData(uint8_t* data, size_t length) {
    pCharacteristic -> setValue(data, length);
    pCharacteristic -> notify(); 
}