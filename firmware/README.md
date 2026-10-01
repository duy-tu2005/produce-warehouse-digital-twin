# Firmware ESP32 và mô phỏng Wokwi

Mạch dùng đúng chân bắt buộc của đề bài:

| Thành phần | Chân ESP32 | Vai trò |
|---|---:|---|
| DHT22 DATA | GPIO15 | Nhiệt độ và độ ẩm không khí |
| PIR OUT | GPIO13 | Phát hiện chuyển động |
| LED qua điện trở 220 ohm | GPIO2 | Cảnh báo và actuator RPC |

## Chuẩn bị

Chạy `../thingsboard/setup.ps1` trước. Script tạo Device trên ThingsBoard và sinh
`secrets.h` cục bộ. File này bị loại khỏi Git và không được đưa vào báo cáo.

## Build và chạy

```powershell
cd firmware
.\build.ps1
```

Sau khi build thành công, mở thư mục `firmware` trong VS Code, nhấn `F1` và chạy
`Wokwi: Start Simulator`. Wokwi for VS Code dùng Private IoT Gateway; firmware
kết nối tới ThingsBoard local bằng `host.wokwi.internal:1883`.

Kết quả mong đợi trên Serial Monitor:

```text
[WIFI] connected
[MQTT] connected
[MQTT] topic=v1/devices/me/telemetry publish=OK ...
```

Trong lúc mô phỏng, bấm PIR rồi chọn **Simulate Motion** để tạo `motion=true`.
Nhấn DHT22 để thay nhiệt độ và độ ẩm.

## RPC

Firmware hỗ trợ:

- `setLed` với `params=true/false` hoặc `params={"state":true/false}`;
- `getStatus` để đọc trạng thái hiện tại;
- `setFaultMode` và `clearFaults` để demo có kiểm soát.

`setFaultMode` nhận các mode: `HIGH_TEMPERATURE`, `LOW_TEMPERATURE`,
`HIGH_HUMIDITY`, `LOW_HUMIDITY`, `TEMPERATURE_RATE_ANOMALY`,
`HUMIDITY_RATE_ANOMALY`, `SENSOR_STUCK`, `SEQUENCE_GAP`, `WEAK_SIGNAL`,
`UNEXPECTED_MOTION`, `INVALID_SENSOR`, và `NONE`.

