#pragma once

#include <Arduino.h>

// Hardware required by the assignment.
constexpr uint8_t GPIO_DHT = 15;
constexpr uint8_t GPIO_PIR = 13;
constexpr uint8_t GPIO_LED = 2;

constexpr unsigned long SAMPLE_PERIOD_MS = 5000UL;
constexpr unsigned long WIFI_BACKOFF_MIN_MS = 1000UL;
constexpr unsigned long WIFI_BACKOFF_MAX_MS = 60000UL;
constexpr unsigned long MQTT_BACKOFF_MIN_MS = 1000UL;
constexpr unsigned long MQTT_BACKOFF_MAX_MS = 60000UL;

constexpr uint16_t MQTT_KEEP_ALIVE_S = 30;
constexpr uint16_t MQTT_BUFFER_SIZE = 1024;

constexpr char DEVICE_ID[] = "esp32-dt-01";
constexpr char FIRMWARE_VERSION[] = "2.0.0";

// Wokwi's DHT22 stays perfectly constant until the slider is moved. A tiny,
// deterministic jitter keeps normal simulation data from looking like a
// frozen sensor. Set this to false for a physical ESP32.
constexpr bool ENABLE_WOKWI_BASELINE_JITTER = true;

