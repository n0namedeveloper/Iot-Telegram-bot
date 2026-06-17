# IoT Telegram Bot

Real-time IoT monitoring and remote control system built on **Raspberry Pi Pico W** with Telegram bot interface and n8n automation.

## Overview

This project connects a Raspberry Pi Pico W microcontroller to the internet and allows remote monitoring and control via a Telegram bot. Sensor data is collected on the device, sent to a server, and processed through an n8n automation workflow that triggers Telegram notifications and handles commands.

## Architecture

```
Raspberry Pi Pico W
  └── Sensors (temperature, humidity, etc.)
  └── MicroPython firmware
  └── HTTP/MQTT → Server
            └── n8n Workflow
                  └── Telegram Bot API
                        └── User (remote alerts & commands)
```

## Tech Stack

| Component | Technology |
|---|---|
| Microcontroller | Raspberry Pi Pico W |
| Firmware | MicroPython |
| Automation | n8n |
| Notifications | Telegram Bot API |
| Server | Python / FastAPI |

## Features

- Real-time sensor data collection and transmission
- Telegram bot for remote monitoring and control
- Automated alerts via n8n workflows when thresholds are exceeded
- Low-power IoT-friendly communication

## Project Structure

```
/Pico       - MicroPython firmware for Raspberry Pi Pico W
/Server     - Backend server for receiving sensor data
```

## Quick Start

1. Flash MicroPython to your Raspberry Pi Pico W
2. Configure Wi-Fi credentials and server URL in `/Pico/config.py`
3. Deploy the server from `/Server`
4. Import the n8n workflow and configure your Telegram bot token
5. Power on the Pico W and send `/start` to your Telegram bot

## License

MIT
