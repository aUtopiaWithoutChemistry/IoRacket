/**
 * This is the main program of IoRacket,
 * starts the BLE service and broadcast BLE information,
 * keeping listen to the senser's data and send data to the connected bluetooth device.
 * 
 * @author Zifan Zuo
 * @date 2026-Jan-21
 */
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// include badminton data structure
#include "BadmintonData.h"

// for sensor
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

#define LED_PIN 2

// uuid for bluetooth
#define SERVICE_UUID        "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
#define CHARACTERISTIC_UUID "253113ce-9a58-4847-b67d-f94b719837dc"

// BLE characteristic
BLECharacteristic *pCharacteristic;

// MPU6050 sensor
Adafruit_MPU6050 mpu;

// flag for device connection status
bool deviceConnected = false;

// BLE server callbacks to handle device connection and disconnection events
class MyServerCallbacks: public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    Serial.println("Device connected");
  };
  
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    Serial.println("Device disconnected...");
    pServer -> getAdvertising() -> start(); // restart advertising
  }
};

void setup() {
  // 1. Setup esp32 device
  Serial.begin(115200);
  Wire.begin(21, 22);
  Serial.println("Initializing...");

  // 2. initialize BLE device
  BLEDevice::init("Zifan_Badminton_Sensor");
  BLEServer *pServer = BLEDevice::createServer();
  pServer -> setCallbacks(new MyServerCallbacks());

  // create BLE service
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // create BLE characteristic, open read, write and notify properties
  pCharacteristic = pService -> createCharacteristic(
                    CHARACTERISTIC_UUID,
                    BLECharacteristic::PROPERTY_READ |
                    BLECharacteristic::PROPERTY_WRITE |
                    BLECharacteristic::PROPERTY_NOTIFY
                  );

  // create BLE2902 descriptor for notify property
  pCharacteristic -> addDescriptor(new BLE2902());

  // start the service, and start advertising
  pService -> start();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising -> addServiceUUID(SERVICE_UUID);
  pAdvertising -> setScanResponse(true);

  // set advertising parameters
  pAdvertising -> addServiceUUID(SERVICE_UUID); // add service UUID to advertising packet
  pAdvertising -> setScanResponse(true);

  pServer -> getAdvertising() -> start();

  // 3. initialize MPU6050 sensor
  if (!mpu.begin()) {
    Serial.println("Failed to find MPU6050 chip");
    while (1) {
      delay(10);
    }
  }
  Serial.println("MPU6050 Found!");

  // set range and filter bandwidth
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
}

void loop() {
  // read sensor data
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  // using array to store data for bluetooth sending
  float data[6];

  // for bluetooth data sending
  if (deviceConnected) {
    // get sensor data
    data[0] = a.acceleration.x;
    data[1] = a.acceleration.y;
    data[2] = a.acceleration.z;
    data[3] = g.gyro.x;
    data[4] = g.gyro.y;
    data[5] = g.gyro.z;

    // pack data into badminton data structure
    BadmintonData bdData;
    bdData.timestamp = millis();
    bdData.acc[0] = data[0];
    bdData.acc[1] = data[1];
    bdData.acc[2] = data[2];
    bdData.gyro[0] = data[3];
    bdData.gyro[1] = data[4];
    bdData.gyro[2] = data[5];

    // send data via bluetooth
    pCharacteristic -> setValue((uint8_t*)&bdData, sizeof(bdData));
    pCharacteristic -> notify(); 

    // 200 Hz data sending rate
    delay(5); 
  }
}