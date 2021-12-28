#
# Reporta mediante mensajes BLE advertisment y el UUID de scale el valor
# de lectura de la báscula hecha con el sensor HX711.
# Para ahorrar batería usamos deep sleep.
# También expone por BLE el servicio UART para poder configurar el offset
# y scale de la báscúla. Estos valores perduran los reinicios
# Los comandos son:
# offset?
#   obtiene el offset de la báscula
# scale?
#   obtiene el scale de la báscula
# deepsleep?
#   obtiene el tiempo de deep sleep
# awake?
#   obtiene el tiempo de awake
# advertisment?
#   obtiene el tiempo de advertisment
# interval?
#   obtiene el tiempo entre nuevas mediciones
# offset=<valor>
#   establece el offset de la báscula
# scale=<valor>
#   establece el scale de la báscula
# deepsleep=<valor>
#   establece el tiempo de deep sleep (ms)
# awake=<valor>
#   establece el tiempo de awake (ms)
# advertisment=<valor>
#   establece el tiempo entre envíos de advertisment (us)
# interval=<valor>
#   establece el tiempo entre mediciones (ms)

import esp32
import random
import ubluetooth
import json

import machine
from machine import Pin, Timer, deepsleep
from time import sleep_ms
from struct import pack

from hx711_gpio import HX711

LOADCELL_DOUT_PIN = 18;
LOADCELL_SCK_PIN = 21;

OFFSET = 'offset'
SCALE = 'scale'
DEEPSLEEP_MS = 'deepsleep_ms'
AWAKE_MS = 'awake_ms'
ADVERTISMENT_US = 'advertisment_us'
INTERVAL_MS = 'interval_ms'

# Si el peso obtenido no está en estos márgenes, volver a tomar otra medida
# tras un segundo
MIN_ALLOWED_WEIGHT = 5
MAX_ALLOWED_WEIGHT = 30

# Cuantas medidas obtenemos para calcular el valor
NUMBER_OF_SAMPLES = 5

# Cuantas veces intentar tomar las medidas antes de desistir
MAX_NUMBER_OF_RETRIES = 3

# Cual es el máximo error entre las medidas permitido.
# Si el error es mayor, volver a tomar otra serie de medidas.
# La unidad es la original que se obtiene de hx711.read()
MAX_ALLOWED_ERROR = 1/200


# Cargar la configuración
CONFIG_FILE = 'config.json'
# Ejemplo del formato de configuración
config = {
    OFFSET: 0,
    SCALE: 1.0,
    # Cuanto tiempo pasa en el deep sleep (sin emitir nada por BLE)
    DEEPSLEEP_MS: 1000,
    # Cuanto tiempo pasa despierto
    AWAKE_MS: 1000,
    # Cada cuanto se envia un advertisment BLE
    ADVERTISMENT_US: 500*1000,
    # Cada cuanto se hace una medida
    INTERVAL_MS: 1000
}


# Cargar la configuración
with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)


def save_config():
    """Guarda el fichero de configuración"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)


class BLE():
    def __init__(self, name):
        self.name = name
        self.ble = ubluetooth.BLE()
        self.ble.active(True)

        pin_OUT = Pin(LOADCELL_DOUT_PIN, Pin.IN, pull=Pin.PULL_DOWN)
        pin_SCK = Pin(LOADCELL_SCK_PIN, Pin.OUT)
        self.hx711 = HX711(pin_SCK, pin_OUT)
        self.hx711.set_scale(config[SCALE])
        self.hx711.set_offset(config[OFFSET])

        self.timer3 = Timer(2)

        # Modificamos el advertiser cada cierto tiempo
        self.timer3.init(
            period=config[INTERVAL_MS],
            mode=Timer.PERIODIC,
            callback=lambda _: self.advertiser(),
        )

        self.disconnected()
        self.ble.irq(self.ble_irq)
        self.register()
        self.advertiser()

    def connected(self):
        print("Connected")

    def disconnected(self):
        print("Disconnected")

    def advertiser(self):
        """
        Cada vez que llamamos a esta función realizamos una lectura
        y configuramos BLE para exportarla por el service y advertisment
        """
        data = b'\x02\x01\x06' # flags: BR/EDR Not Supported + LE General Discoverable Mode

        # simular bascula
        data += b'\x0d' # length (type + pack)
        data += b'\x16' # Type: Service Data - 16 bit UUID (0x16)
        data += b'\x1d\x18' # UUID 16: Weight Scale (0x181d)

        data_weight = b'\x20' # mark as stabilized weight
        data_weight += pack('H', self.get_weight_kg()) # weight in kilograms
        data_weight += b'\x00\x00\x00\x00\x00\x00\x00\x00'

        self.ble.gatts_write(self.scale_ble, data_weight, True) # el True es para notificar a clientes subscritos

        data += data_weight
        self.ble.gap_advertise(config[ADVERTISMENT_US], bytearray(data))

        #print(f"Advertiser: {weight_kg} kg")


    def get_weight_kg(self):
        """Obtiene el peso en kg.

        Si el peso obtenido no está en estos márgenes, volver a tomar otra medida.
        Se tomas varias medidas y se descarta si ambas no tienen unos valores similares.
        Si tras MAX_NUMBER_OF_RETRIES no se consigue una medida, se devuelve 0.
        """
        # Si el peso obtenido no está en estos márgenes, volver a tomar otra medida
        weight_kg = 0
        for _ in range(MAX_NUMBER_OF_RETRIES):
            measures = []
            for _ in range(NUMBER_OF_SAMPLES):
                measures.append(self.hx711.read())

            if max(measures) - min(measures) > MAX_ALLOWED_ERROR:
                print(f"Error: las medidas no tienen unos valores similares: {measures}")
                continue

            weight = sum(measures) / len(measures)
            weight_kg = int(weight * 200)

            # Si el peso obtenido está en unos márgenes permitidos, retornar el valor
            if weight_kg > MIN_ALLOWED_WEIGHT or weight_kg < MAX_ALLOWED_WEIGHT:
                return weight_kg

            sleep_ms(1000)

        return 0


    def register(self):
        # Nordic UART Service (NUS)
        SCALE_UUID = ubluetooth.UUID(0x181D)
        SCALE_CHAR = (ubluetooth.UUID(0x2A9D), ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,)
        SCALE_SERVICE = (SCALE_UUID, (SCALE_CHAR,),)

        UART_UUID = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
        UART_TX = (ubluetooth.UUID('6E400003-B5A3-F393-E0A9-E50E24DCCA9E'), ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,)
        UART_RX = (ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'), ubluetooth.FLAG_WRITE,)
        UART_SERVICE = (UART_UUID, (UART_TX, UART_RX,),)
        SERVICES = (SCALE_SERVICE, UART_SERVICE,)
        ( (self.scale_ble,), (self.tx, self.rx,), ) = self.ble.gatts_register_services(SERVICES)


    def ble_irq(self, event, data):
        print(f"BLE IRQ, event: {event}, data: {data}")

        if event == 1:
            '''Central disconnected'''
            self.connected()

        elif event == 2:
            '''Central disconnected'''
            self.advertiser()
            self.disconnected()

        elif event == 3:
            '''New message received'''
            buffer = self.ble.gatts_read(self.rx)
            message = buffer.decode('UTF-8').strip()
            print(message)

            if message.startswith('?'):
                print(f"config: {config}")
                self.ble.gatts_notify(0, self.tx, f"offset: {config}\n")

            elif message.startswith('offset?'):
                print(f"get offset: {config[OFFSET]}")
                self.ble.gatts_notify(0, self.tx, f"offset: {config[OFFSET]}\n")

            elif message.startswith('scale?'):
                print(f"get scale: {config[SCALE]}")
                self.ble.gatts_notify(0, self.tx, f"scale: {config[SCALE]}\n")

            elif message.startswith('deepsleep?'):
                print(f"get scale: {config[DEEPSLEEP_MS]}")
                self.ble.gatts_notify(0, self.tx, f"deepsleep: {config[DEEPSLEEP_MS]}\n")

            elif message.startswith('awake?'):
                print(f"get scale: {config[AWAKE_MS]}")
                self.ble.gatts_notify(0, self.tx, f"awake: {config[AWAKE_MS]}\n")

            elif message.startswith('interval?'):
                print(f"get interval: {config[INTERVAL_MS]}")
                self.ble.gatts_notify(0, self.tx, f"interval: {config[INTERVAL_MS]}\n")

            elif message.startswith('advertisment?'):
                print(f"get advertisment: {config[ADVERTISMENT_US]}")
                self.ble.gatts_notify(0, self.tx, f"advertisment: {config[ADVERTISMENT_US]}\n")

            elif message.startswith('offset='):
                config[OFFSET] = float(message.split('=')[1])
                print(f"set offset to: {config[OFFSET]}")
                self.ble.gatts_notify(0, self.tx, "OK\n")
                self.hx711.set_offset(config[OFFSET])
                save_config()

            elif message.startswith('scale='):
                config[SCALE] = float(message.split('=')[1])
                print(f"set scale to: {config[SCALE]}")
                self.ble.gatts_notify(0, self.tx, "OK\n")
                self.hx711.set_scale(config[SCALE])
                save_config()

            elif message.startswith('deepsleep='):
                config[DEEPSLEEP_MS] = int(message.split('=')[1])
                print(f"set deepsleep to: {config[DEEPSLEEP_MS]}")
                self.ble.gatts_notify(0, self.tx, "OK\n")
                save_config()

            elif message.startswith('awake='):
                config[AWAKE_MS] = int(message.split('=')[1])
                print(f"set awake to: {config[AWAKE_MS]}")
                self.ble.gatts_notify(0, self.tx, "OK\n")
                save_config()

            elif message.startswith('interval='):
                config[INTERVAL_MS] = int(message.split('=')[1])
                print(f"set interval to: {config[INTERVAL_MS]}")
                self.ble.gatts_notify(0, self.tx, "OK\n")
                save_config()

            elif message.startswith('advertisment='):
                config[ADVERTISMENT_US] = int(message.split('=')[1])
                print(f"set advertisment to: {config[ADVERTISMENT_US]}")
                self.ble.gatts_notify(0, self.tx, "OK\n")
                save_config()


def dslep():
    """Manda el ESP32 a dormir durante el tiempo especificado en el fichero"""
    print("Deep sleep")
    deepsleep(config[DEEPSLEEP_MS])


if machine.reset_cause() == machine.DEEPSLEEP_RESET:
    print('woke from a deep sleep')

print("Starting BLE")
ble = BLE("ESP32")

# Setting timer for deep sleep
timer2 = Timer(3)
timer2.init(period=config[AWAKE_MS], mode=Timer.ONE_SHOT, callback=lambda _: dslep())
