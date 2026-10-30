// v2 step B: stream the 1 kHz FIFO data over BLE in the v2 packet format (CLAUDE.md "BLE protocol v2").
// Watch it with the host UI (host/main.py). Serial prints the board-side counters once per second,
// so losses can be split into "lost on the board" (FIFO overflow) vs "lost over BLE" (host sees gaps).
#include <Arduino.h>
#include <Wire.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#ifndef IMU_SDA
#define IMU_SDA 5   // XIAO D4
#endif
#ifndef IMU_SCL
#define IMU_SCL 6   // XIAO D5
#endif

// ---------------- IMU (same as examples/fifo_test) ----------------

const uint8_t MPU_ADDR = 0x68;
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

const int SAMPLE_BYTES = 12;       // ax ay az gx gy gz, int16 big-endian
const int MAX_BURST_SAMPLES = 10;  // 120 B per I2C read; ESP32 Wire buffer is 128 B

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

// An MCU reset in the middle of an I2C read can leave the IMU holding SDA low (seen in fifo_test).
// Clock SCL until it lets go, then send a STOP.
void recoverBus() {
  pinMode(IMU_SDA, INPUT_PULLUP);
  pinMode(IMU_SCL, OUTPUT_OPEN_DRAIN);
  digitalWrite(IMU_SCL, HIGH);
  delayMicroseconds(10);
  for (int i = 0; i < 9 && digitalRead(IMU_SDA) == LOW; i++) {
    digitalWrite(IMU_SCL, LOW);  delayMicroseconds(5);
    digitalWrite(IMU_SCL, HIGH); delayMicroseconds(5);
  }
  pinMode(IMU_SDA, OUTPUT_OPEN_DRAIN);
  digitalWrite(IMU_SDA, LOW);  delayMicroseconds(5);
  digitalWrite(IMU_SCL, HIGH); delayMicroseconds(5);
  digitalWrite(IMU_SDA, HIGH); delayMicroseconds(5);
}

void resetFifo() {
  uint8_t status;
  readRegs(REG_INT_STATUS, &status, 1);  // clear a stale overflow flag
  writeReg(REG_USER_CTRL, 0x04);         // FIFO_RESET
  writeReg(REG_USER_CTRL, 0x40);         // FIFO_EN
}

bool setupImu() {
  uint8_t who = 0;
  if (!readRegs(REG_WHO_AM_I, &who, 1) || who != 0x68) return false;
  writeReg(REG_PWR_MGMT_1, 0x80);    // full reset
  delay(100);
  writeReg(REG_PWR_MGMT_1, 0x01);    // wake up, clock from gyro X PLL
  delay(10);
  writeReg(REG_CONFIG, 0x00);        // DLPF widest (260 Hz), gyro output 8 kHz
  writeReg(REG_SMPLRT_DIV, 7);       // 8 kHz / (1 + 7) = 1 kHz
  writeReg(REG_GYRO_CONFIG, 0x18);   // FS_SEL 3: +/-2000 dps
  writeReg(REG_ACCEL_CONFIG, 0x18);  // AFS_SEL 3: +/-16 g
  writeReg(REG_INT_ENABLE, 0x10);    // latch FIFO overflow in INT_STATUS
  writeReg(REG_FIFO_EN, 0x78);       // accel + gyro into the FIFO
  return true;
}

// ---------------- BLE ----------------

#define SERVICE_UUID "db87fb0a-cf98-4a2f-889b-3078ebaf19fb"
#define DATA_UUID    "253113ce-9a58-4847-b67d-f94b719837dc"

const int HEADER_BYTES = 6;                   // uint32 first_sample_index, uint8 n_samples, uint8 ranges
const int MAX_SAMPLES_PER_PACKET = 18;        // 6 + 18 * 12 = 222 B
const uint8_t RANGES = (3 << 4) | 3;          // gyro FS_SEL 3 (2000 dps) | accel AFS_SEL 3 (16 g)

BLECharacteristic* dataChar;
BLE2902* dataCccd;                            // the client's "notifications on/off" switch
volatile bool connected = false;
volatile uint16_t mtu = 23;                   // BLE default until the client negotiates a bigger one

// Diagnostics: connection events are printed with millis() so they can be lined up with the host log.
class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer*, esp_ble_gatts_cb_param_t* param) override {
    connected = true;
    Serial.printf("[%lu] connected, interval %.2f ms, latency %u, timeout %u ms\n", millis(),
                  param->connect.conn_params.interval * 1.25f, param->connect.conn_params.latency,
                  param->connect.conn_params.timeout * 10);
  }
  void onDisconnect(BLEServer* server, esp_ble_gatts_cb_param_t* param) override {
    connected = false;
    mtu = 23;
    // The library keeps the client's "notifications on" flag after a disconnect. Without this reset,
    // the next connection starts streaming before the host has subscribed or negotiated the MTU
    // (1 sample per 23 B packet, 1000 notifications/s), which floods the link and the connect fails.
    dataCccd->setNotifications(false);
    // Reason codes: 0x08 supervision timeout, 0x13 remote side closed, 0x16 we closed, 0x3E failed to establish
    Serial.printf("[%lu] disconnected, reason 0x%02X\n", millis(), param->disconnect.reason);
    server->startAdvertising();  // advertising stops on connect; make the racket findable again
  }
  void onMtuChanged(BLEServer*, esp_ble_gatts_cb_param_t* param) override {
    mtu = param->mtu.mtu;
    Serial.printf("[%lu] MTU %u\n", millis(), mtu);
  }
};

// Connection-interval changes requested by the laptop arrive as GAP events.
void gapHandler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t* param) {
  if (event == ESP_GAP_BLE_UPDATE_CONN_PARAMS_EVT) {
    Serial.printf("[%lu] conn params updated: status %d, interval %.2f ms, latency %u, timeout %u ms\n",
                  millis(), param->update_conn_params.status, param->update_conn_params.conn_int * 1.25f,
                  param->update_conn_params.latency, param->update_conn_params.timeout * 10);
  }
}

volatile uint32_t statNotifyErrors = 0;

class DataCallbacks : public BLECharacteristicCallbacks {
  void onStatus(BLECharacteristic*, Status s, uint32_t) override {
    if (s == ERROR_GATT) statNotifyErrors++;
  }
};

// A notification can carry at most MTU - 3 bytes; anything longer is silently cut off.
int samplesPerPacket() {
  return constrain((mtu - 3 - HEADER_BYTES) / SAMPLE_BYTES, 1, MAX_SAMPLES_PER_PACKET);
}

// ---------------- streaming ----------------

uint8_t packet[HEADER_BYTES + MAX_SAMPLES_PER_PACKET * SAMPLE_BYTES];
int packetSamples = 0;       // samples already in `packet`
int packetCapacity = 1;      // samples per packet for this connection
uint32_t sampleIndex = 0;    // index of the first sample in `packet`
bool streaming = false;

uint32_t statSamples = 0, statPackets = 0, statOverflows = 0, statReadErrors = 0, statStart = 0;
uint32_t statMaxLoopMs = 0;  // longest single loop() pass: shows if something blocks the loop

void sendPacket() {
  memcpy(packet, &sampleIndex, 4);  // ESP32 is little-endian, as the protocol wants
  packet[4] = packetSamples;
  packet[5] = RANGES;
  dataChar->setValue(packet, HEADER_BYTES + packetSamples * SAMPLE_BYTES);
  dataChar->notify();
  sampleIndex += packetSamples;
  packetSamples = 0;
  statPackets++;
}

void startStreaming() {
  packetCapacity = samplesPerPacket();
  sampleIndex = 0;
  packetSamples = 0;
  resetFifo();
  streaming = true;
  statSamples = statPackets = statOverflows = statReadErrors = statMaxLoopMs = 0;
  statNotifyErrors = 0;
  statStart = millis();
  Serial.printf("[%lu] Streaming: MTU %u -> %d samples/packet (%d B)\n",
                millis(), mtu, packetCapacity, HEADER_BYTES + packetCapacity * SAMPLE_BYTES);
}

void printStats() {
  float seconds = (millis() - statStart) / 1000.0f;
  Serial.printf("[%lu] %.0f Hz read, %.1f packets/s, notify errors %lu, ovf=%lu, i2c err=%lu, max loop %lu ms\n",
                millis(), statSamples / seconds, statPackets / seconds, statNotifyErrors, statOverflows,
                statReadErrors, statMaxLoopMs);
  statSamples = statPackets = statOverflows = statReadErrors = statMaxLoopMs = 0;
  statNotifyErrors = 0;
  statStart = millis();
}

bool imuOk = false;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== BLE stream test: 1 kHz, v2 packets ===");
  recoverBus();
  Wire.begin(IMU_SDA, IMU_SCL, 400000);
  imuOk = setupImu();
  Serial.println(imuOk ? "IMU configured" : "IMU setup failed");

  BLEDevice::init("Zifan_Badminton_Sensor");
  BLEDevice::setCustomGapHandler(gapHandler);
  BLEDevice::setMTU(247);  // our side allows up to 247; the laptop decides the final value
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService* service = server->createService(SERVICE_UUID);
  dataChar = service->createCharacteristic(DATA_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  dataCccd = new BLE2902();
  dataChar->addDescriptor(dataCccd);
  dataChar->setCallbacks(new DataCallbacks());
  service->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  adv->start();
  Serial.println("Advertising, waiting for the host to subscribe...");
}

void loop() {
  bool subscribed = connected && dataCccd->getNotifications();
  if (!imuOk || !subscribed) {
    if (streaming) {
      streaming = false;
      Serial.printf("[%lu] host unsubscribed/disconnected, streaming stopped\n", millis());
    }
    delay(50);
    return;
  }
  if (!streaming) startStreaming();
  uint32_t loopStart = millis();

  uint8_t status = 0;
  if (readRegs(REG_INT_STATUS, &status, 1) && (status & 0x10)) {
    // We fell behind and the FIFO overflowed; its contents are no longer sample-aligned.
    // How many samples were lost is unknown, so this shows up only in the serial counters.
    statOverflows++;
    resetFifo();
    packetSamples = 0;
  }

  uint8_t c[2];
  if (!readRegs(REG_FIFO_COUNT_H, c, 2)) { statReadErrors++; return; }
  int available = ((c[0] << 8) | c[1]) / SAMPLE_BYTES;

  uint8_t buf[MAX_BURST_SAMPLES * SAMPLE_BYTES];
  while (available > 0) {
    int n = min(available, MAX_BURST_SAMPLES);
    if (!readRegs(REG_FIFO_R_W, buf, n * SAMPLE_BYTES)) { statReadErrors++; break; }
    for (int i = 0; i < n; i++) {
      // copy the sample verbatim (big-endian, as the chip sends it)
      memcpy(packet + HEADER_BYTES + packetSamples * SAMPLE_BYTES, buf + i * SAMPLE_BYTES, SAMPLE_BYTES);
      if (++packetSamples == packetCapacity) sendPacket();
    }
    statSamples += n;
    available -= n;
  }

  statMaxLoopMs = max(statMaxLoopMs, (uint32_t)(millis() - loopStart));
  if (millis() - statStart >= 1000) printStats();
  delay(5);
}
