#pragma once

// Copy this file to secrets.h manually, or run thingsboard/setup.ps1 to
// generate secrets.h from the actual local ThingsBoard device credential.
// Never commit secrets.h.

constexpr char WIFI_SSID[] = "Wokwi-GUEST";
constexpr char WIFI_PASSWORD[] = "";

// Wokwi for VS Code reaches services on the host through this hostname when
// the Private IoT Gateway is enabled. For a physical ESP32, use the LAN IP of
// the computer running ThingsBoard instead.
constexpr char TB_MQTT_HOST[] = "host.wokwi.internal";
constexpr uint16_t TB_MQTT_PORT = 1883;
constexpr char TB_DEVICE_TOKEN[] = "YOUR_DEVICE_ACCESS_TOKEN";

