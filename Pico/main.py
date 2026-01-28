# main.py — Raspberry Pi Pico 2 W / MicroPython
# Smart Pot + RFID Lock with:
# - DHT11 sensor (temperature/humidity)
# - RC522 (MFRC522) RFID reader (SPI1)
# - I2C LCD 16x2
# - Servo lock
# - Wi-Fi + NTP time sync
# - MQTT telemetry + RFID events to broker
#
# Notes:
# - MicroPython has no real timezone handling; NTP sets UTC time, so we apply a fixed offset only for LCD display. [web:984]
# - network.WLAN.isconnected() is True when connected and has an IP address. [web:991]
# - MQTT client uses a persistent TCP connection to publish JSON payloads to topics. [web:1149][web:1148]

from time import sleep, time
import time as utime

from machine import Pin, PWM, I2C
import machine

import network
import ntptime
import ujson

import ubinascii
from umqtt.simple import MQTTClient  # umqtt.simple must be present on the filesystem. [web:1149]

import dht
from mfrc522 import MFRC522
from pico_i2c_lcd import I2cLcd


# ---------------- WIFI + TIME ----------------
USE_WIFI = True
WIFI_SSID = "gomodrila1337"
WIFI_PASS = "22882288"

TZ_OFFSET_H = 1  # Košice winter time (CET = UTC+1). Used only for LCD display. [web:984]


def wifi_connect(timeout_s=20):
    """Connect to Wi-Fi and return WLAN object, or None on timeout."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan

    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = time()
    while time() - t0 < timeout_s:
        if wlan.isconnected():
            return wlan
        sleep(0.25)

    return None


def ntp_sync(retries=3):
    """Sync RTC using NTP. ntptime.settime() sets UTC time (no timezone). [web:984]"""
    for _ in range(retries):
        try:
            ntptime.settime()
            return True
        except Exception:
            sleep(1)
    return False


# ---------------- MQTT CONFIG ----------------
MQTT_BROKER = "147.232.204.221"  # TODO: set to your Docker host / router IP
MQTT_PORT = 1883               # Default Mosquitto port. [web:1153]
MQTT_USER = None               # Set if auth is enabled on broker
MQTT_PASS = None

DEVICE_ID = "pico2w-01"

TOPIC_TELEMETRY = b"iot/pico2w-01/telemetry"
TOPIC_RFID = b"iot/pico2w-01/rfid"


def mqtt_connect():
    """
    Create and connect MQTT client.
    Uses a persistent TCP connection to the broker so subsequent publish() calls are fast. [web:1148]
    """
    client_id = ubinascii.hexlify(machine.unique_id())
    client = MQTTClient(
        client_id,
        MQTT_BROKER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASS,
        keepalive=60,
    )
    client.connect()
    return client


mqtt = None  # Will hold MQTTClient instance after Wi-Fi connection.


# ---------------- LCD CONFIG ----------------
LCD_ADDR = 0x27
LCD_ROWS = 2
LCD_COLS = 16

PIN_SDA = 20
PIN_SCL = 21


# ---------------- SENSOR/ACTUATOR PINS ----------------
PIN_DHT = 28
PIN_SERVO = 15

# RC522 SPI1 pins
PIN_SCK = 10
PIN_MOSI = 11
PIN_MISO = 12
PIN_CS = 13
PIN_RST = 14


# ---------------- TIMINGS ----------------
DHT_PERIOD_S = 5
MQTT_TELEMETRY_PERIOD_S = 30  # Periodic telemetry publish interval.

RFID_POLL_PERIOD_S = 0.2
RFID_POPUP_S = 3

# RFID queue: send events in the background so RFID polling is non-blocking.
RFID_PUBLISH_PERIOD_S = 2

LCD_PERIOD_S = 0.25


# ---------------- LCD SETUP ----------------
i2c = I2C(0, sda=Pin(PIN_SDA), scl=Pin(PIN_SCL), freq=100000)
sleep(0.5)
lcd = I2cLcd(i2c, LCD_ADDR, LCD_ROWS, LCD_COLS)


def lcd_line(row, text):
    """Write one line of text to LCD, padding or truncating to LCD_COLS."""
    lcd.move_to(0, row)
    lcd.putstr((text + " " * LCD_COLS)[:LCD_COLS])


def show_default_screen(temp, hum):
    """
    Show current time (with fixed timezone offset) and last temperature/humidity. [web:984]
    """
    t = utime.gmtime()  # UTC time from RTC.
    hh = (t[3] + TZ_OFFSET_H) % 24
    mm = t[4]
    ss = t[5]

    lcd_line(0, "Time {:02d}:{:02d}:{:02d}".format(hh, mm, ss))
    if temp is None or hum is None:
        lcd_line(1, "T:--C H:--%")
    else:
        lcd_line(1, "T:{}C H:{}%".format(temp, hum))


def show_rfid(uid_hex):
    """Show last scanned RFID UID on LCD (trimmed to last 16 characters)."""
    lcd_line(0, "RFID UID:")
    lcd_line(1, uid_hex[-16:])


# ---------------- DHT11 ----------------
sensor = dht.DHT11(Pin(PIN_DHT))
temp = None
hum = None


# ---------------- SERVO ----------------
servo = PWM(Pin(PIN_SERVO))
servo.freq(50)


def angle_to_u16(angle):
    """
    Convert servo angle in degrees to 16‑bit duty cycle.
    Uses 0.5–2.5 ms pulse width for 0–180° at 50 Hz. [web:1112]
    """
    pulse_ms = 0.5 + (angle / 180.0) * 2.0
    return int((pulse_ms / 20.0) * 65535)


def lock():
    """Move servo to 'locked' position."""
    servo.duty_u16(angle_to_u16(0))


def unlock_pulse():
    """Pulse servo to 'unlock' position for 1 second, then return to 'lock'."""
    servo.duty_u16(angle_to_u16(90))
    sleep(1)
    servo.duty_u16(angle_to_u16(0))


# ---------------- RFID (RC522) ----------------
reader = MFRC522(
    sck=PIN_SCK, mosi=PIN_MOSI, miso=PIN_MISO,
    cs=PIN_CS, rst=PIN_RST,
    baudrate=1_000_000,
    spi_id=1,
)


def uid_to_hex(uid):
    """Convert list/bytes UID from RC522 to uppercase hex string."""
    return "".join("{:02X}".format(x) for x in uid)


# ---------------- STATE ----------------
dht_timer = 0
telemetry_publish_timer = 0

rfid_timer = 0
rfid_publish_timer = 0

lcd_timer = 0
popup_until = 0

last_uid_hex = ""
last_uid_time = 0  # Debounce time for same card, in seconds.

rfid_queue = []  # Queued RFID events to publish without blocking RFID polling.


# ---------------- BOOT SCREEN ----------------
lcd.clear()
lcd_line(0, "Smart Pot+Lock")
lcd_line(1, "Booting...")

wlan = None
if USE_WIFI:
    lcd_line(0, "WiFi connect...")
    lcd_line(1, "")
    wlan = wifi_connect()

    if wlan:
        ip = wlan.ifconfig()[0]
        lcd_line(0, "WiFi OK")
        lcd_line(1, ip)
        sleep(1.2)

        lcd_line(0, "NTP sync...")
        lcd_line(1, "")
        ok = ntp_sync()
        lcd_line(0, "NTP OK" if ok else "NTP FAIL")
        lcd_line(1, ip)
        sleep(1.2)

        # Try to connect to MQTT broker once Wi‑Fi is up.
        try:
            mqtt = mqtt_connect()
            lcd_line(0, "MQTT OK")
        except Exception:
            mqtt = None
            lcd_line(0, "MQTT FAIL")
        sleep(1.2)
    else:
        lcd_line(0, "WiFi FAIL")
        lcd_line(1, "offline mode")
        sleep(1.2)

lock()
sleep(1)


# ---------------- MAIN LOOP ----------------
while True:
    now = time()

    # --- DHT read ---
    if now - dht_timer >= DHT_PERIOD_S:
        try:
            sensor.measure()
            temp = sensor.temperature()
            hum = sensor.humidity()
        except Exception:
            temp = None
            hum = None
        dht_timer = now

    # --- RFID poll (NO network calls here) ---
    if now - rfid_timer >= RFID_POLL_PERIOD_S:
        try:
            reader.init()
            (status, tag_type) = reader.request(reader.REQIDL)
            if status == reader.OK:
                (status, uid) = reader.SelectTagSN()
                if status == reader.OK:
                    uid_hex = uid_to_hex(uid)

                    # Debounce: ignore same UID repeatedly for 2 seconds.
                    if (uid_hex != last_uid_hex) or ((now - last_uid_time) >= 2):
                        last_uid_hex = uid_hex
                        last_uid_time = now
                        popup_until = now + RFID_POPUP_S

                        # Queue event for MQTT publish later.
                        rfid_queue.append({
                            "device_id": DEVICE_ID,
                            "ts": int(now),
                            "uid": last_uid_hex,
                            "action": "open",
                        })

                        show_rfid(last_uid_hex)
                        unlock_pulse()
        except Exception:
            pass
        rfid_timer = now

    # --- Telemetry MQTT publish (periodic) ---
    if mqtt and wlan and wlan.isconnected() and (temp is not None) and (hum is not None):
        if now - telemetry_publish_timer >= MQTT_TELEMETRY_PERIOD_S:
            payload = {
                "device_id": DEVICE_ID,
                "ts": int(now),
                "temperature": int(temp),
                "humidity": int(hum),
            }
            try:
                mqtt.publish(TOPIC_TELEMETRY, ujson.dumps(payload))
            except Exception:
                # If publish fails, try to reconnect once.
                try:
                    mqtt = mqtt_connect()
                    mqtt.publish(TOPIC_TELEMETRY, ujson.dumps(payload))
                except Exception:
                    mqtt = None
            telemetry_publish_timer = now

    # --- RFID queue MQTT publish (non-blocking for RFID poll) ---
    if mqtt and wlan and wlan.isconnected():
        if rfid_queue and (now - rfid_publish_timer >= RFID_PUBLISH_PERIOD_S):
            payload = rfid_queue.pop(0)
            try:
                mqtt.publish(TOPIC_RFID, ujson.dumps(payload))
            except Exception:
                # On failure, attempt a single reconnect and requeue the message.
                try:
                    mqtt = mqtt_connect()
                    mqtt.publish(TOPIC_RFID, ujson.dumps(payload))
                except Exception:
                    mqtt = None
                    # Put payload back to queue to try again later.
                    rfid_queue.insert(0, payload)
            rfid_publish_timer = now

    # --- LCD refresh ---
    if now - lcd_timer >= LCD_PERIOD_S:
        if now < popup_until and last_uid_hex:
            show_rfid(last_uid_hex)
        else:
            show_default_screen(temp, hum)
        lcd_timer = now

    sleep(0.05)
