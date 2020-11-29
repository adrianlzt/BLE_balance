/*
 * Bascula que expone los datos mediante BLE
 */

#include <string.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "HX711.h"

// Initialize our HX711 interface
HX711 scale;
const int LOADCELL_DOUT_PIN = 18;
const int LOADCELL_SCK_PIN = 21;
const int LOADCELL_OFFSET = -151562;
const int LOADCELL_SCALE = 22;

BLECharacteristic *pCharacteristic;
bool deviceConnected = false;

#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E" // UART service UUID
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.print("Connected\n");
      scale.power_up();
    };

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      Serial.print("Disconnected\n");
      scale.power_down();
    }
};

void setup() {
  Serial.begin(9600);
  setCpuFrequencyMhz(80);

  scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
  scale.set_offset(LOADCELL_OFFSET);
  scale.set_scale(LOADCELL_SCALE);

  // Create the BLE Device
  BLEDevice::init("Bascula BLE");

  // Give it a name
  // Create the BLE Server
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  // Create the BLE Service
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // Create a BLE Characteristic
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID_TX,
                      BLECharacteristic::PROPERTY_NOTIFY
                    );

  pCharacteristic->addDescriptor(new BLE2902());

  // La app movil no muestra datos si no tenemos esta línea, no he investigado por que.
  // btgatt-client si muestra notificationes sin esta linea
  BLECharacteristic *pCharacteristic = pService->createCharacteristic(
                                         CHARACTERISTIC_UUID_RX,
                                         BLECharacteristic::PROPERTY_WRITE
                                       );

  // Start the service
  pService->start();

  // Start advertising
  pServer->getAdvertising()->start();
  Serial.println("Waiting a client connection to notify...\n");
}

void loop() {
  if (deviceConnected) {
    Serial.print("Sent Value: ");

    if (scale.is_ready()) {
      char txString[8];
      long reading = scale.get_units(10);

      dtostrf(reading, 1, 0, txString); // float_val, min_width, digits_after_decimal, char_buffer
      strcat(txString, "\n");
      pCharacteristic->setValue(txString);
      pCharacteristic->notify(); // Send the value to the app!
      Serial.print(reading);
    } else {
      pCharacteristic->setValue("no data\n");
      Serial.print("no data");
    }
    Serial.print("\n");
  }

  delay(5000);
}
