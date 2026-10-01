#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHTesp.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "config.h"
#include "secrets.h"

namespace {

constexpr char TELEMETRY_TOPIC[] = "v1/devices/me/telemetry";
constexpr char ATTRIBUTES_TOPIC[] = "v1/devices/me/attributes";
constexpr char RPC_REQUEST_TOPIC[] = "v1/devices/me/rpc/request/+";
constexpr char RPC_REQUEST_PREFIX[] = "v1/devices/me/rpc/request/";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
DHTesp dht;

unsigned long lastSampleMs = 0;
unsigned long nextWifiAttemptMs = 0;
unsigned long nextMqttAttemptMs = 0;
unsigned long wifiBackoffMs = WIFI_BACKOFF_MIN_MS;
unsigned long mqttBackoffMs = MQTT_BACKOFF_MIN_MS;
uint32_t sequenceNo = 0;
uint32_t bootId = 0;

bool ledState = false;
String faultMode = "NONE";
float lastValidTemperature = NAN;
float lastValidHumidity = NAN;
float stuckTemperature = NAN;
float stuckHumidity = NAN;

bool timeReached(unsigned long now, unsigned long target) {
  return static_cast<long>(now - target) >= 0;
}

void setLed(bool state) {
  ledState = state;
  digitalWrite(GPIO_LED, ledState ? HIGH : LOW);
}

void publishJson(const char* topic, JsonDocument& document) {
  char buffer[MQTT_BUFFER_SIZE];
  const size_t length = serializeJson(document, buffer, sizeof(buffer));
  if (length == 0 || length >= sizeof(buffer)) {
    Serial.printf("[ERROR] JSON payload too large for topic %s\n", topic);
    return;
  }
  const bool ok = mqttClient.publish(topic, reinterpret_cast<uint8_t*>(buffer), length, false);
  Serial.printf("[MQTT] topic=%s publish=%s payload=%s\n", topic, ok ? "OK" : "FAILED", buffer);
}

void publishDeviceAttributes() {
  StaticJsonDocument<384> attributes;
  attributes["device_id"] = DEVICE_ID;
  attributes["fw_version"] = FIRMWARE_VERSION;
  attributes["firmware_version"] = FIRMWARE_VERSION;
  attributes["sample_period_s"] = SAMPLE_PERIOD_MS / 1000UL;
  attributes["gpio_dht"] = GPIO_DHT;
  attributes["gpio_pir"] = GPIO_PIR;
  attributes["gpio_led"] = GPIO_LED;
  attributes["mqtt_connected"] = true;
  attributes["boot_id"] = bootId;
  publishJson(ATTRIBUTES_TOPIC, attributes);
}

void publishRpcResponse(const String& requestId, JsonDocument& response) {
  const String responseTopic = String("v1/devices/me/rpc/response/") + requestId;
  publishJson(responseTopic.c_str(), response);
}

bool readBooleanParam(JsonVariantConst params, bool& value) {
  if (params.is<bool>()) {
    value = params.as<bool>();
    return true;
  }
  if (params.is<JsonObjectConst>()) {
    JsonObjectConst object = params.as<JsonObjectConst>();
    if (object["state"].is<bool>()) {
      value = object["state"].as<bool>();
      return true;
    }
    if (object["value"].is<bool>()) {
      value = object["value"].as<bool>();
      return true;
    }
  }
  return false;
}

String readFaultMode(JsonVariantConst params) {
  if (params.is<const char*>()) {
    return String(params.as<const char*>());
  }
  if (params.is<JsonObjectConst>()) {
    JsonObjectConst object = params.as<JsonObjectConst>();
    if (object["mode"].is<const char*>()) {
      return String(object["mode"].as<const char*>());
    }
  }
  return String();
}

void handleRpc(char* topic, byte* payload, unsigned int length) {
  String topicName(topic);
  if (!topicName.startsWith(RPC_REQUEST_PREFIX)) {
    return;
  }
  const String requestId = topicName.substring(strlen(RPC_REQUEST_PREFIX));

  StaticJsonDocument<512> request;
  const DeserializationError error = deserializeJson(request, payload, length);
  if (error) {
    StaticJsonDocument<192> response;
    response["success"] = false;
    response["message"] = "Invalid RPC JSON";
    publishRpcResponse(requestId, response);
    Serial.printf("[RPC] invalid JSON: %s\n", error.c_str());
    return;
  }

  const String method = request["method"] | "";
  JsonVariantConst params = request["params"];

  if (method == "setLed" || method == "setState") {
    bool requestedState = false;
    if (!readBooleanParam(params, requestedState)) {
      StaticJsonDocument<192> response;
      response["success"] = false;
      response["message"] = "params must be boolean or {state:boolean}";
      publishRpcResponse(requestId, response);
      return;
    }
    setLed(requestedState);
    StaticJsonDocument<256> response;
    response["success"] = true;
    response["value"] = ledState;
    response["led_state"] = ledState;
    response["sequence"] = sequenceNo;
    response["message"] = "LED updated";
    publishRpcResponse(requestId, response);
    Serial.printf("[RPC] setLed=%s\n", ledState ? "true" : "false");
    return;
  }

  if (method == "getLed" || method == "getState" || method == "getStatus") {
    StaticJsonDocument<256> response;
    response["success"] = true;
    // The built-in ThingsBoard switch widget reads `value`; `led_state` is
    // kept as a descriptive field for manual RPC tests and API clients.
    response["value"] = ledState;
    response["led_state"] = ledState;
    response["sequence"] = sequenceNo;
    response["uptime_s"] = millis() / 1000UL;
    response["rssi"] = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : -127;
    response["fault_mode"] = faultMode;
    publishRpcResponse(requestId, response);
    Serial.println("[RPC] getStatus");
    return;
  }

  if (method == "setFaultMode") {
    String requestedMode = readFaultMode(params);
    requestedMode.toUpperCase();
    if (requestedMode.length() == 0) {
      StaticJsonDocument<192> response;
      response["success"] = false;
      response["message"] = "params must be a mode string or {mode:string}";
      publishRpcResponse(requestId, response);
      return;
    }
    faultMode = requestedMode;
    if (faultMode == "SENSOR_STUCK") {
      stuckTemperature = lastValidTemperature;
      stuckHumidity = lastValidHumidity;
    }
    StaticJsonDocument<192> response;
    response["success"] = true;
    response["fault_mode"] = faultMode;
    publishRpcResponse(requestId, response);
    Serial.printf("[RPC] fault_mode=%s\n", faultMode.c_str());
    return;
  }

  if (method == "clearFaults") {
    faultMode = "NONE";
    StaticJsonDocument<128> response;
    response["success"] = true;
    response["fault_mode"] = faultMode;
    publishRpcResponse(requestId, response);
    Serial.println("[RPC] faults cleared");
    return;
  }

  StaticJsonDocument<192> response;
  response["success"] = false;
  response["message"] = "Unsupported RPC method";
  response["method"] = method;
  publishRpcResponse(requestId, response);
}

void maintainWiFi(unsigned long now) {
  if (WiFi.status() == WL_CONNECTED) {
    wifiBackoffMs = WIFI_BACKOFF_MIN_MS;
    return;
  }
  if (!timeReached(now, nextWifiAttemptMs)) {
    return;
  }

  Serial.printf("[WIFI] connecting to %s, retry in %lu ms if needed\n", WIFI_SSID, wifiBackoffMs);
  WiFi.disconnect(false, false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  nextWifiAttemptMs = now + wifiBackoffMs;
  wifiBackoffMs = min(wifiBackoffMs * 2UL, WIFI_BACKOFF_MAX_MS);
}

void maintainMqtt(unsigned long now) {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    if (mqttClient.connected()) {
      mqttBackoffMs = MQTT_BACKOFF_MIN_MS;
    }
    return;
  }
  if (!timeReached(now, nextMqttAttemptMs)) {
    return;
  }

  const String clientId = String("ESP32-Env-") + String(static_cast<uint32_t>(ESP.getEfuseMac()), HEX);
  const char* willPayload = "{\"mqtt_connected\":false}";
  Serial.printf("[MQTT] connecting to %s:%u\n", TB_MQTT_HOST, TB_MQTT_PORT);
  const bool connected = mqttClient.connect(
      clientId.c_str(), TB_DEVICE_TOKEN, "", ATTRIBUTES_TOPIC, 1, false, willPayload);

  if (connected) {
    Serial.println("[MQTT] connected");
    mqttClient.subscribe(RPC_REQUEST_TOPIC, 1);
    publishDeviceAttributes();
    mqttBackoffMs = MQTT_BACKOFF_MIN_MS;
    nextMqttAttemptMs = now;
  } else {
    Serial.printf("[MQTT] failed rc=%d, retry in %lu ms\n", mqttClient.state(), mqttBackoffMs);
    nextMqttAttemptMs = now + mqttBackoffMs;
    mqttBackoffMs = min(mqttBackoffMs * 2UL, MQTT_BACKOFF_MAX_MS);
  }
}

void applyFaultMode(float& temperature, float& humidity, bool& motion, int& rssi, bool& sensorValid) {
  if (faultMode == "HIGH_TEMPERATURE") {
    temperature = 42.0f;
  } else if (faultMode == "LOW_TEMPERATURE") {
    temperature = 8.0f;
  } else if (faultMode == "HIGH_HUMIDITY") {
    humidity = 95.0f;
  } else if (faultMode == "LOW_HUMIDITY") {
    humidity = 20.0f;
  } else if (faultMode == "TEMPERATURE_RATE_ANOMALY") {
    temperature = (sequenceNo % 2 == 0) ? 25.0f : 29.5f;
  } else if (faultMode == "HUMIDITY_RATE_ANOMALY") {
    humidity = (sequenceNo % 2 == 0) ? 65.0f : 79.0f;
  } else if (faultMode == "SENSOR_STUCK") {
    if (isfinite(stuckTemperature) && isfinite(stuckHumidity)) {
      temperature = stuckTemperature;
      humidity = stuckHumidity;
    }
  } else if (faultMode == "WEAK_SIGNAL") {
    rssi = -95;
  } else if (faultMode == "UNEXPECTED_MOTION") {
    motion = true;
  } else if (faultMode == "INVALID_SENSOR") {
    temperature = 999.0f;
    humidity = 999.0f;
    sensorValid = false;
  }
}

void publishTelemetry(unsigned long now) {
  TempAndHumidity reading = dht.getTempAndHumidity();
  float temperature = reading.temperature;
  float humidity = reading.humidity;
  bool sensorValid = isfinite(temperature) && isfinite(humidity) &&
                     temperature >= -40.0f && temperature <= 80.0f &&
                     humidity >= 0.0f && humidity <= 100.0f;
  bool motion = digitalRead(GPIO_PIR) == HIGH;
  int rssi = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : -127;

  if (sensorValid && ENABLE_WOKWI_BASELINE_JITTER && faultMode == "NONE") {
    const int jitterStep = static_cast<int>((sequenceNo + 1U) % 5U) - 2;
    temperature += static_cast<float>(jitterStep) * 0.02f;
    humidity -= static_cast<float>(jitterStep) * 0.03f;
  }

  applyFaultMode(temperature, humidity, motion, rssi, sensorValid);

  if (faultMode == "SEQUENCE_GAP") {
    sequenceNo += 3U;
  }
  sequenceNo++;

  StaticJsonDocument<768> telemetry;
  telemetry["device_id"] = DEVICE_ID;
  telemetry["sequence"] = sequenceNo;
  telemetry["uptime_s"] = now / 1000UL;
  telemetry["motion"] = motion;
  telemetry["rssi"] = rssi;
  telemetry["led_state"] = ledState;
  telemetry["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  telemetry["firmware_version"] = FIRMWARE_VERSION;
  telemetry["boot_id"] = bootId;
  telemetry["sensor_valid"] = sensorValid;
  telemetry["fault_mode"] = faultMode;

  if (sensorValid || faultMode == "INVALID_SENSOR") {
    telemetry["temperature"] = roundf(temperature * 100.0f) / 100.0f;
    telemetry["humidity"] = roundf(humidity * 100.0f) / 100.0f;
  }

  publishJson(TELEMETRY_TOPIC, telemetry);

  if (sensorValid) {
    lastValidTemperature = temperature;
    lastValidHumidity = humidity;
  } else {
    Serial.println("[SENSOR] invalid DHT22 data; environmental values omitted unless fault injection is active");
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(GPIO_PIR, INPUT);
  pinMode(GPIO_LED, OUTPUT);
  setLed(false);

  dht.setup(GPIO_DHT, DHTesp::DHT22);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);

  mqttClient.setServer(TB_MQTT_HOST, TB_MQTT_PORT);
  mqttClient.setCallback(handleRpc);
  mqttClient.setBufferSize(MQTT_BUFFER_SIZE);
  mqttClient.setKeepAlive(MQTT_KEEP_ALIVE_S);
  mqttClient.setSocketTimeout(5);

  bootId = static_cast<uint32_t>(ESP.getEfuseMac()) ^ micros();
  nextWifiAttemptMs = 0;
  nextMqttAttemptMs = 0;

  Serial.printf("[BOOT] device=%s firmware=%s boot_id=%lu\n", DEVICE_ID, FIRMWARE_VERSION, bootId);
  Serial.printf("[GPIO] DHT=%u PIR=%u LED=%u\n", GPIO_DHT, GPIO_PIR, GPIO_LED);
}

void loop() {
  const unsigned long now = millis();
  maintainWiFi(now);
  maintainMqtt(now);

  if (mqttClient.connected()) {
    mqttClient.loop();
    if (now - lastSampleMs >= SAMPLE_PERIOD_MS) {
      lastSampleMs = now;
      publishTelemetry(now);
    }
  }

  delay(2);
}
