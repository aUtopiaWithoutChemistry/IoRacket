#include "BLEManager.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define SERVICE_UUID "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
#define DATA_UUID    "253113ce-9a58-4847-b67d-f94b719837dc"  // notify: v2 packets
#define CONTROL_UUID "c0a1b2d3-4e5f-4a6b-8c7d-9e0f1a2b3c4d"  // write: command byte

static const uint8_t CMD_BOOTLOADER = 0x01;

// Advertising interval in 0.625 ms units: 400-500 ms. Slow, to save power while nobody is connected;
// the laptop still finds the racket within about a second.
static const uint16_t ADV_MIN_INTERVAL = 640;
static const uint16_t ADV_MAX_INTERVAL = 800;

// State shared with the BLE stack's callbacks, which run on the BLE task.
static BLECharacteristic* dataChar = nullptr;
static BLE2902* dataCccd = nullptr;  // the client's "notifications on/off" switch
static volatile bool connected = false;
static volatile uint16_t mtu = 23;   // BLE default until the client negotiates a bigger one
static volatile bool bootloader = false;
static volatile uint32_t notifyErrors = 0;

class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer*, esp_ble_gatts_cb_param_t* param) override {
        connected = true;
        Serial.printf("[%lu] connected, interval %.2f ms\n", millis(), param->connect.conn_params.interval * 1.25f);
    }

    void onDisconnect(BLEServer* server, esp_ble_gatts_cb_param_t* param) override {
        connected = false;
        mtu = 23;
        // The library keeps the client's "notifications on" flag after a disconnect. Without this reset,
        // the next connection starts streaming before the host has subscribed or negotiated the MTU
        // (1 sample per 23 B packet, 1000 notifications/s), which floods the link and the connect fails.
        dataCccd->setNotifications(false);
        // Reason codes: 0x08 supervision timeout (radio), 0x13 host closed, 0x16 we closed
        Serial.printf("[%lu] disconnected, reason 0x%02X\n", millis(), param->disconnect.reason);
        server->startAdvertising();  // advertising stops on connect; make the racket findable again
    }

    void onMtuChanged(BLEServer*, esp_ble_gatts_cb_param_t* param) override {
        mtu = param->mtu.mtu;
        Serial.printf("[%lu] MTU %u\n", millis(), mtu);
    }
};

class DataCallbacks : public BLECharacteristicCallbacks {
    void onStatus(BLECharacteristic*, Status s, uint32_t) override {
        if (s == ERROR_GATT) notifyErrors++;
    }
};

class ControlCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* c) override {
        if (c->getLength() >= 1 && c->getData()[0] == CMD_BOOTLOADER) bootloader = true;
    }
};

void BLEManager::begin(const char* deviceName) {
    BLEDevice::init(deviceName);
    BLEDevice::setMTU(247);  // our side allows up to 247; the laptop decides the final value

    BLEServer* server = BLEDevice::createServer();
    server->setCallbacks(new ServerCallbacks());
    BLEService* service = server->createService(SERVICE_UUID);

    dataChar = service->createCharacteristic(DATA_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    dataCccd = new BLE2902();
    dataChar->addDescriptor(dataCccd);
    dataChar->setCallbacks(new DataCallbacks());

    BLECharacteristic* control = service->createCharacteristic(CONTROL_UUID, BLECharacteristic::PROPERTY_WRITE);
    control->setCallbacks(new ControlCallbacks());

    service->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(SERVICE_UUID);
    adv->setScanResponse(true);
    adv->setMinInterval(ADV_MIN_INTERVAL);
    adv->setMaxInterval(ADV_MAX_INTERVAL);
    adv->start();
}

bool BLEManager::isSubscribed() const {
    return connected && dataCccd->getNotifications();
}

// A notification can carry at most MTU - 3 bytes; anything longer is silently cut off.
int BLEManager::samplesPerPacket(int headerBytes, int sampleBytes, int maxSamples) const {
    return constrain((mtu - 3 - headerBytes) / sampleBytes, 1, maxSamples);
}

void BLEManager::sendPacket(uint8_t* data, size_t length) {
    dataChar->setValue(data, length);
    dataChar->notify();
}

bool BLEManager::bootloaderRequested() const {
    return bootloader;
}

uint32_t BLEManager::takeNotifyErrors() {
    uint32_t n = notifyErrors;
    notifyErrors = 0;
    return n;
}
