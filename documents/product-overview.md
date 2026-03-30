# Product overview

## What it is

A smart farming monitoring system that combines IoT hardware and software to track environmental conditions in real-time.

## Current system

**Hardware**
- ESP32-S3 microcontroller with 5 sensors: light, pH, water temperature, air temperature, humidity
- OV2640 camera for visual monitoring (640x480 MJPEG streaming)
- Raspberry Pi server for data processing and storage

**Software stack**
- MQTT for sensor data transmission (5-second intervals)
- InfluxDB for time-series data storage
- Grafana for data visualization dashboards
- PWA web app for remote monitoring
- Remote access via Tailscale VPN and ngrok

**Key features**
- Real-time sensor data collection with noise filtering
- Live camera streaming
- Historical data tracking and visualization
- Remote access from phone or PC browser
- No installation required (PWA)

## Technical status

The prototype is fully functional. All sensors are calibrated and collecting data. The data pipeline from sensors through MQTT to InfluxDB and Grafana is operational. Camera streaming works. Remote access configured.

## Planned improvements

- Enhanced Grafana dashboards
- pH 2-point calibration
- Telegram alerts for anomaly detection
- Time-lapse recording for plant growth
- Automated LED control via smart plug
- Long-term AI training data accumulation