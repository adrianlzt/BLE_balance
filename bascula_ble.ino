/*
 * Bascula que expone los datos mediante BLE
 * Podemos usar la app https://play.google.com/store/apps/details?id=com.mightyit.gops.bleterminal&hl=en_US&gl=US para leer los datos
 * IMPORTANTE: recordar desconectar la app del móvil tras leer los datos
 *
 * Se calcula el peso de gas y porcentaje de llenado (respecto al 80% máximo de la botella) asumiendo que los valores void_tank y tank_capacity son correctos
 */

#include <stdio.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "HX711.h"

// Initialize our HX711 interface
HX711 scale;
const int LOADCELL_DOUT_PIN = 18;
const int LOADCELL_SCK_PIN = 21;
const int LOADCELL_OFFSET = -153322;
//const int LOADCELL_OFFSET = -151562; // -80gr
//const int LOADCELL_OFFSET = -149802;
const int LOADCELL_SCALE = 22;

// Peso del tanque de gas en vacío, en gramos
const int void_tank = 12400;
// capacidad del tanque, en gramos
const int tank_capacity = 11760;

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
      char txString[50];
      char tank_weight_str[12];
      char gas_weight_str[12];
      char gas_pct_str[12];

      // peso total del tanque
      long tank_weight = scale.get_units(10);
      dtostrf(tank_weight, 1, 0, tank_weight_str);

      sprintf(txString, "tank  %s gr\n", tank_weight_str);
      pCharacteristic->setValue(txString);
      pCharacteristic->notify(); // send the value to the app!

      // peso del gas almacenado en el tanque
      long gas_weight = tank_weight - void_tank;
      dtostrf(gas_weight, 1, 0, gas_weight_str);

      sprintf(txString, "gas   %s gr\n", gas_weight_str);
      pCharacteristic->setValue(txString);
      pCharacteristic->notify(); // send the value to the app!

      // porcentaje de llenado (100% es que el tanque está a su máximo de 80%, el 20% restante es de seguridad)
      long gas_pct = gas_weight * 100 / tank_capacity;
      dtostrf(gas_pct, 1, 1, gas_pct_str);

      sprintf(txString, "pct    %s %%\n---\n", gas_pct_str);
      pCharacteristic->setValue(txString);
      pCharacteristic->notify(); // Send the value to the app!

      Serial.print("tank=");
      Serial.print(tank_weight);
      Serial.print(" gr  ");
      Serial.print("gas=");
      Serial.print(gas_weight);
      Serial.print(" gr  ");
      Serial.print("pct=");
      Serial.print(gas_pct);
      Serial.print(" %  ");
    } else {
      pCharacteristic->setValue("no data\n");
      pCharacteristic->notify(); // Send the value to the app!
      Serial.print("no data");
    }
    Serial.print("\n");
  }

  delay(5000);
}
