from machine import SPI, Pin
from time import sleep_ms

class MFRC522:
    def __init__(self, sck, mosi, miso, cs, rst):
        # Правильный синтаксис для Pico
        self.spi = SPI(0, baudrate=100000, polarity=1, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self.cs = Pin(cs, Pin.OUT)
        self.rst = Pin(rst, Pin.OUT)
        self.cs.value(1)
        self.init()

    def init(self):
        self.rst.value(0)
        sleep_ms(50)
        self.rst.value(1)
        sleep_ms(50)
        
        self.write(0x01, 0x0F)
        self.write(0x2A, 0x80)
        self.write(0x2B, 0xA9)
        self.write(0x2C, 0x03)
        self.write(0x2D, 0xE8)
        self.write(0x26, 0x4F)
        self.write(0x0C, 0x03)

    def write(self, reg, val):
        self.cs.value(0)
        self.spi.write(bytes([((reg << 1) | 0x80), val]))
        self.cs.value(1)

    def read(self, reg):
        self.cs.value(0)
        self.spi.write(bytes([(reg << 1) & 0x7E]))
        data = self.spi.read(1)[0]
        self.cs.value(1)
        return data

    def request(self):
        """Ищет карту"""
        self.write(0x0D, 0x07)
        self.write(0x01, 0x0C)
        self.write(0x0D, 0x80)
        
        for _ in range(2000):
            if self.read(0x04) & 0x30:
                break
        
        return (self.read(0x01) & 0x40) == 0

    def get_uid(self):
        """Читает UID карты"""
        self.write(0x0D, 0x00)
        self.write(0x01, 0x0C)
        self.write(0x0D, 0x80)
        
        for _ in range(2000):
            if self.read(0x04) & 0x30:
                break
        
        uid = []
        for i in range(5):
            uid.append(self.read(0x09))
        
        return uid
