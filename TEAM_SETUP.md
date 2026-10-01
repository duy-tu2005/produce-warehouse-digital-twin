# Hướng dẫn thành viên nhóm chạy và tìm hiểu project

## 1. Project này làm gì?

Đây là Digital Twin của kho bảo quản rau quả:

```text
DHT22 + PIR + LED
        ↓
ESP32 → MQTT → ThingsBoard Device
                  ↓
              Rule Chain
                  ↓
       Asset Produce_Warehouse_01
                  ↓
              Dashboard
```

- DHT22 GPIO15: nhiệt độ, độ ẩm.
- PIR GPIO13: chuyển động gần cửa kho.
- LED GPIO2: actuator/cảnh báo, điều khiển bằng RPC.
- Device `ESP32_Env_Node_01`: nhận raw telemetry.
- Asset `Produce_Warehouse_01`: Digital Twin cấp kho.

## 2. Chuẩn bị môi trường

- Windows 10/11.
- Docker Desktop chạy Linux containers.
- WSL2/ảo hóa đã bật.
- Python 3.11 trở lên.
- Git.
- VS Code; Wokwi hoặc PlatformIO nếu chạy mô phỏng/build firmware.

## 3. Clone và chạy ThingsBoard local

```powershell
git clone <URL_REPOSITORY>
cd produce-warehouse-digital-twin
cd deployment
docker compose up -d
docker compose ps
```

Mở trình duyệt và tự nhập:

```text
http://localhost:8080
```

Đăng nhập Tenant Administrator của ThingsBoard local.

## 4. Tạo mô hình Digital Twin

Quay về thư mục project và chạy:

```powershell
cd ..
$env:TB_USERNAME = '<tenant-admin-email>'
$env:TB_PASSWORD = '<tenant-admin-password>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\thingsboard\setup.ps1
Remove-Item Env:TB_USERNAME, Env:TB_PASSWORD
```

Script tự tạo/cập nhật:

- Asset Profile, Asset, Device Profile và Device.
- Quan hệ `Produce_Warehouse_01 --Contains--> ESP32_Env_Node_01`.
- Ba Entity View cho DHT22, PIR và LED.
- Rule Chain 29 node.
- Dashboard 9 widget.
- `firmware/secrets.h` và `.env.local` ở máy local.

Hai file chứa credential này đã bị `.gitignore`; không commit và không gửi lên nhóm.

## 5. Build và chạy firmware

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\build.ps1
```

Nếu dùng Wokwi trong VS Code:

1. Mở thư mục `firmware`.
2. Mở `diagram.json`.
3. Chọn **Wokwi: Start Simulator**.
4. Kiểm tra Serial có `[WIFI] connected`, `[MQTT] connected` và `publish=OK`.

Không tự đổi GPIO hoặc token trong source. Token local được sinh sau khi chạy `setup.ps1`.

## 6. Kiểm tra dashboard

Vào:

```text
Dashboards → Produce Warehouse - Digital Twin
```

Dashboard gồm:

- Sơ đồ kho với marker DHT22, PIR và LED tách riêng.
- Kết nối, điểm sức khỏe và trạng thái Digital Twin.
- Ba biểu đồ nhiệt độ/độ ẩm, RSSI và sức khỏe/anomaly.
- Công tắc bật/tắt LED bằng RPC `setLed`.
- Bảng `Cảnh báo Digital Twin` ở cuối dashboard.

## 7. Kiểm tra lỗi và alarm

Các loại lỗi chính:

```text
HIGH_TEMPERATURE
HIGH_HUMIDITY
SENSOR_STUCK
SEQUENCE_GAP
DEVICE_RESTART
WEAK_SIGNAL
CONNECTION_LOST
UNEXPECTED_MOTION
```

Luồng xử lý nằm ở:

- `thingsboard/rule-scripts/process-telemetry.js`: phát hiện lỗi và tính điểm.
- `thingsboard/rule-scripts/build-twin-payload.js`: tạo trạng thái Asset.
- `thingsboard/rule-scripts/offline-state.js`: xử lý mất kết nối.
- `thingsboard/setup.py`: triển khai Rule Chain và Dashboard.

## 8. Chạy kiểm thử

```powershell
python .\tests\integration_test.py --trials 10 --settle-seconds 0.08 --reset-test-data
python .\tests\stability_test.py --minutes 1 --period-seconds 5
```

Nếu giảng viên yêu cầu đúng 30 phút:

```powershell
python .\tests\stability_test.py --minutes 30 --period-seconds 5
```

Kết quả nằm trong `tests/results/`. Không sửa tay các số liệu kiểm thử.

## 9. Phân công nhanh

- Thành viên 1: `firmware/`, mạch, Wokwi, MQTT và RPC.
- Thành viên 2: `thingsboard/`, Asset/Device/Relation, Rule Chain, anomaly và alarm.
- Thành viên 3: Dashboard, biểu đồ, marker, giao diện và điều khiển LED.
- Thành viên 4: `tests/`, báo cáo, slide, video và đóng gói.

Mỗi thành viên vẫn phải hiểu toàn bộ luồng Sensor → MQTT → Device → Rule Chain → Asset → Dashboard.

## 10. Không đưa lên GitHub

- `.env.local`
- `firmware/secrets.h`
- API key, Device Access Token, mật khẩu
- thư mục `.pio`, `__pycache__`, `.runtime`, `.rendered`
