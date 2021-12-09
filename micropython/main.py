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

        data += b'\x0d' # length (type + pack)
        data += b'\x16' # Type: Service Data - 16 bit UUID (0x16)
        data += b'\x1d\x18' # UUID 16: Weight Scale (0x181d)

        peso = 99.999
        data += b'\x20' # stabilized weight
        data += pack('H', int(peso*200)) # peso
        data += b'\x00\x00\x00\x00\x00\x00\x00\x00'

        self.ble.gap_advertise(500000, bytearray(data))

ble = BLE("ESP32")
