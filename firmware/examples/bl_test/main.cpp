// Reboot-to-bootloader test: lets the laptop put the board into download mode over BLE,
// so re-flashing does not need the (hard to reach) B and R buttons.
//
// Flash this once with B+R. After that, run `host/enter_bootloader.py`, then
// `pio run -e bl_test -t upload` should work with no button presses.
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <esp_system.h>
#include <soc/rtc_cntl_reg.h>

#define SERVICE_UUID "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
#define CONTROL_UUID "c0a1b2d3-4e5f-4a6b-8c7d-9e0f1a2b3c4d"  // write-only command byte
#define CMD_BOOTLOADER 0x01

volatile bool bootloaderRequested = false;

class ControlCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* c) override {
    if (c->getLength() >= 1 && c->getData()[0] == CMD_BOOTLOADER) {
      bootloaderRequested = true;  // act in loop(), after the BLE write has been acknowledged
    }
  }
};

void rebootIntoBootloader() {
  // Set the "force download boot" flag; it survives a software reset, so the
  // chip comes back up in download mode (same trick the Arduino core uses).
  REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
  esp_restart();
}

void setup() {
  Serial.begin(115200);
  BLEDevice::init("Zifan_Badminton_Sensor");
  BLEServer* server = BLEDevice::createServer();
  BLEService* service = server->createService(SERVICE_UUID);
  BLECharacteristic* control = service->createCharacteristic(CONTROL_UUID, BLECharacteristic::PROPERTY_WRITE);
  control->setCallbacks(new ControlCallbacks());
  service->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  adv->start();
  Serial.println("bl_test ready: write 0x01 to the control characteristic to enter download mode");
}

void loop() {
  if (bootloaderRequested) {
    Serial.println("Rebooting into download mode...");
    delay(200);
    rebootIntoBootloader();
  }
  delay(20);  // don't busy-spin
}
