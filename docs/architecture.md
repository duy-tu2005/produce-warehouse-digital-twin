# Kiến trúc Digital Twin kho bảo quản rau quả

Đối tượng Digital Twin cấp cao là Asset `Produce_Warehouse_01`. Node vật lý hoặc
mô phỏng là Device `ESP32_Env_Node_01` và được liên kết bằng quan hệ có hướng
`Contains`.

```text
Produce_Warehouse_01 (Asset)
        |
        | Contains
        v
ESP32_Env_Node_01 (Device)
        |
        +-- DHT22 GPIO15: temperature, humidity
        +-- PIR GPIO13: motion
        +-- LED GPIO2: led_state và RPC setLed
        +-- Wi-Fi/MQTT: rssi, sequence, uptime_s
```

## Luồng xử lý

```text
Wokwi/ESP32
  -> MQTT v1/devices/me/telemetry
  -> Device ESP32_Env_Node_01
  -> Rule Chain Warehouse Digital Twin Processing
  -> kiểm tra schema, threshold, rate, stuck, sequence, restart và RSSI
  -> state machine INIT/NORMAL/WARNING/ANOMALY/OFFLINE/RECOVERY
  -> Change Originator theo relation TO/Contains
  -> Asset Produce_Warehouse_01
  -> Twin telemetry + server attributes + alarms
  -> Dashboard Produce Warehouse Digital Twin
```

Raw telemetry được lưu tại Device. Trạng thái tổng hợp của Twin được lưu đồng
thời dưới hai dạng trên Asset:

- server attributes cho trạng thái mới nhất;
- time-series cho lịch sử `health_score`, `anomaly_score` và state.

ThingsBoard local hiện là Community Edition 4.3.1.5. Phần logic được triển khai
bằng Rule Engine để tương thích CE; mô hình Entity, Relation, telemetry,
attributes, alarms, dashboard và RPC vẫn giữ nguyên khi chuyển sang PE.

