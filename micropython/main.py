import esp32
import random
import ubluetooth
from machine import Pin, Timer
from time import sleep_ms
from struct import pack

class BLE():
    def __init__(self, name):
        self.name = name
        self.ble = ubluetooth.BLE()
        self.ble.active(True)

        self.led = Pin(2, Pin.OUT)
        self.timer1 = Timer(0)
        self.timer2 = Timer(1)
        self.timer3 = Timer(2)

        # Modificamos el advertiser cada segundo
        self.timer3.init(period=1000, mode=Timer.PERIODIC, callback=lambda _: self.advertiser())

        self.disconnected()
        self.advertiser()

    def connected(self):
        self.timer1.deinit()
        self.timer2.deinit()

    def disconnected(self):
        self.timer1.init(period=1000, mode=Timer.PERIODIC, callback=lambda _: self.led(1))
        sleep_ms(200)
        self.timer2.init(period=1000, mode=Timer.PERIODIC, callback=lambda _: self.led(0))

    def advertiser(self):
        data = b'\x02\x01\x06' # flags: BR/EDR Not Supported + LE General Discoverable Mode

        # Hacer que flapee entre uno y otro
        # TODO el problema es que el módulo de HA parece que espera o una cosa o la otra
        r = random.getrandbits(1)
        r = 0

        if r == 0:
            # simular bascula
            data += b'\x0d' # length (type + pack)
            data += b'\x16' # Type: Service Data - 16 bit UUID (0x16)
            data += b'\x1d\x18' # UUID 16: Weight Scale (0x181d)

            peso = (random.getrandbits(14)/1000)
            data += b'\x20' # stabilized weight
            data += pack('H', int(peso*200)) # peso
            data += b'\x00\x00\x00\x00\x00\x00\x00\x00'

        else:
            # Simular ser un termómetro

            # adstruct
            data += b'\x15' # length (type + pack)
            data += b'\x16' # Type: Service Data - 16 bit UUID (0x16)
            data += b'\x95\xfe' # UUID Xiaomi
            data += b'\x50\x20' # [4,5] frctrl
            data += b'\xaa\x01' # [6,7] device id
            data += b'\xda' # [8] packet id
            data += b'\xe2\x5d\x00\x98\x83\x30' # [9,10,11,12,13,14] mac reversed

            # payload
            data += b'\x0d\x10' # obj_typecode (reversed, 0x100d)
            data += b'\x04' # length

            temp = esp32.raw_temperature()
            # Convert farhenheit to celcius
            temp = (temp - 32) * 5/9

            #data += b'\xfe\x00' # temperature, reversed, multiplicada por 10 (0x00fe = 254 -> 25.4C)
            data += pack('<h', int(temp*10)) # temperature, reversed, multiplicada por 10 (0x00fe = 254 -> 25.4C)

            data += b'\x48\x02' # humedad, reversed, multiplicada por 10

            data += b'\xc4'


        #print(f"gap_advertise: {bytearray(data)}")
        self.ble.gap_advertise(500000, bytearray(data))

ble = BLE("ESP32")
