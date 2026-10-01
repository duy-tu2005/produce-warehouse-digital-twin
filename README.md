# Digital Twin giám sát kho bảo quản rau quả

Dự án xây dựng một Digital Twin hai chiều cho kho bảo quản rau quả bằng ESP32,
DHT22, PIR, LED, MQTT và ThingsBoard Local. Hệ thống không chỉ hiển thị số đo:
nó duy trì trạng thái kho, so sánh trạng thái kỳ vọng với trạng thái quan sát,
phát hiện bất thường, tạo/khôi phục alarm và điều khiển LED bằng RPC.

> Bản local đã kiểm thử dùng ThingsBoard CE 4.3.1.5 để không phụ thuộc license.
> Entity, Relation, telemetry, attributes, Rule Engine, Alarm, Dashboard và RPC
> tương thích với mô hình trong tài liệu Digital Twin của ThingsBoard PE. Smart
> Irrigation chỉ được dùng làm mẫu tổ chức kiến trúc, không sao chép nghiệp vụ.

## 1. Bài toán và mục tiêu

Một kho bảo quản cần biết nhiệt độ, độ ẩm, chuyển động, chất lượng kết nối và
trạng thái cơ cấu chấp hành có phù hợp với trạng thái mong muốn hay không. Mục
tiêu của dự án là:

- thu telemetry định kỳ 5 giây từ một node ESP32;
- tạo mô hình Asset–Device có relation rõ ràng;
- suy diễn sáu trạng thái `INIT`, `NORMAL`, `WARNING`, `ANOMALY`, `OFFLINE`,
  `RECOVERY`;
- phát hiện 13 nhóm bất thường nghiệp vụ/chất lượng dữ liệu, cộng lỗi mất kết
  nối theo lifecycle, và chuẩn hóa output;
- điều khiển LED từ dashboard và kiểm tra command/feedback mismatch;
- chứng minh định lượng bằng 10 lượt cho mỗi loại lỗi và một smoke test vận hành
  liên tục; script vẫn hỗ trợ chạy 30 phút nếu cần mở rộng khi nghiệm thu.

## 2. Digital Twin trong đề tài

Twin là Asset `Produce_Warehouse_01`. Device `ESP32_Env_Node_01` là đại diện
cho node vật lý/mô phỏng. Raw telemetry thuộc Device; trạng thái đã suy diễn và
lịch sử sức khỏe thuộc Asset. Relation có hướng:

```text
Produce_Warehouse_01 (Asset)
  ├── Contains ──> ESP32_Env_Node_01 (Device, nguồn dữ liệu/RPC)
  ├── Contains ──> DHT22_Storage_Racks_View (Entity View)
  ├── Contains ──> PIR_Loading_Door_View (Entity View)
  └── Contains ──> LED_GPIO2_Control_Corner_View (Entity View)

ESP32_Env_Node_01
  ├── DHT22: temperature, humidity
  ├── PIR: motion
  ├── Wi-Fi/MQTT: rssi, sequence, uptime_s
  └── LED: led_state <── RPC setLed
```

Ba Entity View là ba thành phần logic của twin và cùng đọc dữ liệu từ ESP32,
không tạo cảm biến giả và không sao chép time-series.

`expected_state` mô tả trạng thái mong muốn; `observed_state` là kết quả suy
diễn từ dữ liệu thật. `state_match` cho biết hai phía có khớp nhau hay không.

## 3. Kiến trúc

```text
Wokwi/ESP32
  -> MQTT v1/devices/me/telemetry
  -> Device Profile + Device
  -> Rule Chain (enrich -> detect -> state machine -> score)
  -> Change Originator theo relation Contains
  -> Asset twin telemetry + server attributes + alarms
  -> Dashboard / RPC LED
```

Chi tiết: [docs/architecture.md](docs/architecture.md).

## 4. Mạch

| Thành phần | ESP32 | Chức năng |
|---|---:|---|
| DHT22 DATA | GPIO15 | Nhiệt độ, độ ẩm |
| PIR OUT | GPIO13 | Chuyển động |
| LED qua 220 Ω | GPIO2 | Actuator/cảnh báo |

Sơ đồ Wokwi nằm tại [firmware/diagram.json](firmware/diagram.json). Không có cảm
biến mực nước hay độ ẩm đất; hệ thống không sinh dữ liệu phần cứng không tồn tại.

## 5. Công nghệ

- ESP32 Arduino, PubSubClient, ArduinoJson, DHT sensor library;
- Wokwi for VS Code và PlatformIO;
- MQTT Device API/RPC của ThingsBoard;
- ThingsBoard CE 4.3.1.5 + PostgreSQL 18 qua Docker Compose;
- Rule Engine JavaScript, REST API triển khai idempotent bằng Python;
- Python acceptance/stability tests.

## Quy trình chạy và build từ đầu đến cuối

Phần này dành cho thành viên mới clone project. Thực hiện đúng thứ tự, không
build firmware trước khi chạy `thingsboard/setup.ps1`, vì script này tạo Device
và sinh file credential local cho ESP32.

### Bước 1 — Cài công cụ

Cần có:

- Docker Desktop, chọn Linux containers;
- Python 3.11 trở lên;
- Git;
- VS Code;
- PlatformIO Core hoặc extension PlatformIO;
- extension Wokwi for VS Code nếu chạy mô phỏng.

Kiểm tra nhanh:

```powershell
git --version
python --version
docker version
docker info
```

Nếu chưa có PlatformIO:

```powershell
python -m pip install --upgrade platformio
```

### Bước 2 — Clone project

```powershell
git clone https://github.com/duy-tu2005/produce-warehouse-digital-twin.git
Set-Location .\produce-warehouse-digital-twin
```

### Bước 3 — Khởi động ThingsBoard local

```powershell
Set-Location .\deployment
docker compose up -d
docker compose ps
docker compose logs -f thingsboard-ce
```

Dừng xem log bằng `Ctrl+C`; không dùng `docker compose down -v` vì lệnh đó
xóa database Digital Twin. Nếu đây là database mới hoàn toàn, chạy bước cài đặt
một lần trước `up -d`:

```powershell
docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=false thingsboard-ce
docker compose up -d
```

Chỉ tiếp tục khi container ThingsBoard ở trạng thái `Up` và log có
`Started ThingsBoard`. Mở trình duyệt, tự nhập `http://localhost:8080` và đăng
nhập Tenant Administrator.

### Bước 4 — Tạo Digital Twin và sinh credential local

Từ thư mục gốc project:

```powershell
Set-Location ..
$env:TB_USERNAME = '<tenant-admin-email>'
$env:TB_PASSWORD = '<tenant-admin-password>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\thingsboard\setup.ps1
Remove-Item Env:TB_USERNAME, Env:TB_PASSWORD
```

Hoặc dùng Tenant API key:

```powershell
$env:TB_API_KEY = '<tenant-api-key>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\thingsboard\setup.ps1
Remove-Item Env:TB_API_KEY
```

Kết quả phải có các dòng tương tự:

```text
Deployed 29 rule nodes and 35 connections
Ready dashboard: Produce Warehouse - Digital Twin (9 widgets)
Deployment completed successfully
```

Script tạo Asset, Device, Entity Views, Relation, Rule Chain, Dashboard và
sinh hai file chỉ dùng ở máy local: `.env.local` và `firmware/secrets.h`. Hai
file này đã được `.gitignore`, tuyệt đối không commit lên GitHub.

### Bước 5 — Kiểm tra mô hình trên giao diện

Không cần dùng deep link; vào bằng menu:

1. `Entities` → `Assets` → `Produce_Warehouse_01`.
2. Mở `Relations`, kiểm tra quan hệ `Contains` tới `ESP32_Env_Node_01`.
3. `Entities` → `Devices`, kiểm tra `ESP32_Env_Node_01`.
4. `Rule chains`, mở `Produce Warehouse Digital Twin - Processing`.
5. `Dashboards`, mở `Produce Warehouse - Digital Twin`.

### Bước 6 — Build firmware

Từ thư mục gốc:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\build.ps1
```

Build thành công khi PlatformIO báo `SUCCESS`. Dependencies được khai báo trong
`firmware/platformio.ini` và tự tải trong lần build đầu tiên.

### Bước 7 — Chạy Wokwi và kiểm tra MQTT

Mở thư mục `firmware` bằng VS Code, sau đó chạy:

```text
F1 → Wokwi: Start Simulator
```

Serial phải có:

```text
[WIFI] connected
[MQTT] connected
[MQTT] topic=v1/devices/me/telemetry publish=OK
```

Nếu không thấy MQTT kết nối, kiểm tra `firmware/secrets.h`, broker
`host.wokwi.internal`, port `1883` và Device Token được sinh bởi bước 4.

### Bước 8 — Demo Digital Twin

- Bấm marker DHT22 để xem nhiệt độ, độ ẩm và RSSI.
- Bấm PIR và chọn `Simulate Motion` để tạo chuyển động.
- Dùng công tắc `Điều khiển đèn GPIO2` để gửi RPC `setLed`.
- Xác nhận LED trên mạch và `led_state` phản hồi về ThingsBoard.
- Cuộn cuối dashboard để xem bảng `Cảnh báo Digital Twin`.

### Bước 9 — Chạy kiểm thử

Acceptance test nhanh:

```powershell
python .\tests\integration_test.py --trials 1 --reset-test-data
```

Acceptance test đầy đủ:

```powershell
python .\tests\integration_test.py --trials 10 --settle-seconds 0.08 --reset-test-data
```

Smoke stability:

```powershell
python .\tests\stability_test.py --minutes 1 --period-seconds 5
```

Nếu cần đúng yêu cầu 30 phút:

```powershell
python .\tests\stability_test.py --minutes 30 --period-seconds 5
```

Kết quả nằm trong `tests/results/`. Không sửa tay các file JSON/CSV kết quả.

### Bước 10 — Đóng gói hoặc cập nhật project

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\package_submission.ps1
git status
git add .
git commit -m "Describe your change"
git push origin main
```

Để hiểu từng phần, xem thêm [TEAM_SETUP.md](TEAM_SETUP.md),
[docs/architecture.md](docs/architecture.md) và [docs/demo-script.md](docs/demo-script.md).

## 6. Chạy ThingsBoard Local

Yêu cầu: Docker Desktop đang chạy Linux containers, WSL2/ảo hóa hoạt động và
các cổng `8080`, `1883`, `8883` chưa bị chiếm.

```powershell
Set-Location deployment
docker compose up -d
docker compose ps
```

Lần cài cơ sở dữ liệu hoàn toàn mới cần chạy quy trình install của image
ThingsBoard theo đúng phiên bản đang dùng trước khi `up -d`. Máy đã được dựng
trước đó chỉ cần lệnh trên. Xem log:

```powershell
docker compose logs -f thingsboard-ce
```

Mở trình duyệt, tự gõ `localhost:8080`, đăng nhập Tenant Administrator.

## 7. Tạo Asset, Device, Relation và Dashboard

Lấy API key của Tenant Administrator hoặc dùng tài khoản local trong phiên
PowerShell hiện tại, sau đó chạy script idempotent:

```powershell
$env:TB_API_KEY = '<API key local>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\thingsboard\setup.ps1
Remove-Item Env:TB_API_KEY
```

Hoặc:

```powershell
$env:TB_USERNAME = '<tenant admin email>'
$env:TB_PASSWORD = '<local password>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\thingsboard\setup.ps1
Remove-Item Env:TB_USERNAME, Env:TB_PASSWORD
```

Script tạo/cập nhật: Asset Profile, Asset, Device Profile, Device, relation
`Contains`, 29-node Rule Chain, 9-widget Dashboard, thuộc tính ngưỡng, file
export đã khử bí mật, `.env.local` và `firmware/secrets.h`. Chạy lại không tạo
entity trùng.

## 8. MQTT

| Nơi chạy ESP32 | Broker host | Port |
|---|---|---:|
| Wokwi VS Code | `host.wokwi.internal` | 1883 |
| ESP32 thật cùng LAN | IP LAN của máy chạy Docker | 1883 |
| Test trên máy local | `localhost` | 1883 |

- Username MQTT: access token của Device.
- Publish: `v1/devices/me/telemetry`.
- RPC subscribe: `v1/devices/me/rpc/request/+`.
- RPC response: `v1/devices/me/rpc/response/<requestId>`.

Token chỉ nằm trong file local đã git-ignore; không đưa token vào ảnh, báo cáo
hoặc gói nộp.

## 9. Firmware và Wokwi

```powershell
Set-Location firmware
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Mở thư mục `firmware` bằng VS Code, nhấn `F1` -> `Wokwi: Start Simulator`.
Serial phải có `[WIFI] connected`, `[MQTT] connected` và `publish=OK`. Hướng dẫn
chi tiết: [firmware/README.md](firmware/README.md).

## 10. Telemetry schema

| Key | Kiểu | Ý nghĩa |
|---|---|---|
| `temperature` | number | °C từ DHT22 |
| `humidity` | number | %RH từ DHT22 |
| `motion` | boolean | PIR phát hiện chuyển động |
| `rssi` | integer | cường độ Wi-Fi dBm |
| `sequence` | integer | phát hiện mất/trùng/thứ tự gói |
| `uptime_s` | integer | phát hiện restart |
| `led_state` | boolean | phản hồi actuator |
| `sensor_valid` | boolean | chất lượng mẫu DHT22 |
| `firmware_version` | string | truy vết phiên bản |

## 11. Twin state schema

Các key chính trên Asset: `last_seen`, `expected_state`, `observed_state`,
`health_score`, `anomaly_score`, `anomaly_type`, `active_anomalies`, `anomaly`,
`severity`, `online`, `state_match`, `expected_led_state`, `led_state`,
`temperature`, `humidity`, `motion`, `rssi` và các counter chẩn đoán.

`health_score = max(0, 100 - anomaly_score)`. Các ngưỡng là ngưỡng demo có thể
đổi bằng server attributes, không phải tiêu chuẩn chung cho mọi rau quả.

## 12. State machine

```text
INIT -> NORMAL -> WARNING/ANOMALY
                 |       |
                 +-> RECOVERY -> NORMAL
mọi state -> OFFLINE -> RECOVERY
```

Ba cửa sổ sạch liên tiếp được dùng để tránh rung trạng thái. Xem
[docs/state-machine.md](docs/state-machine.md).

## 13. Luật bất thường

Hệ thống phát hiện: nhiệt độ cao/thấp, độ ẩm cao/thấp, tốc độ biến đổi nhiệt
độ/độ ẩm, sensor stuck, invalid sensor, sequence gap, device restart, weak
signal, unexpected motion, actuator mismatch và connection lost. Chi tiết điểm,
ngưỡng và ưu tiên: [docs/anomaly-rules.md](docs/anomaly-rules.md).

## 14. Dashboard

Vào `Dashboards` -> `Produce Warehouse - Digital Twin`. Dashboard có:

- sơ đồ kho bảo quản tương tác với ba marker tách biệt: DHT22 cạnh kệ hàng,
  PIR cạnh cửa nhập kho và LED tại góc điều khiển;
- bấm từng marker để xem đúng thông số của thành phần đó; marker LED phản ánh
  `led_state`, còn widget `Điều khiển đèn GPIO2` gửi RPC `setLed` tới ESP32;
- ảnh sơ đồ kho tự tối khi `led_state=false` và sáng khi `led_state=true`, với
  hiệu ứng chuyển mượt; marker và popup vẫn giữ độ tương phản để thao tác;
- cột trạng thái góc trên bên phải gồm Kết nối, Điểm sức khỏe và Trạng thái
  Digital Twin;
- hàng dưới chỉ gồm ba biểu đồ: môi trường, Wi-Fi và sức khỏe Digital Twin;
- công tắc RPC `Điều khiển đèn GPIO2` đặt cạnh ba biểu đồ.

Ảnh xác nhận cho tổng quan và cả ba popup được lưu trong `docs/screenshots/`
sau bước QA giao diện.

## 15. RPC LED

Firmware hỗ trợ `setLed`, `getLed`, `getStatus`, `setFaultMode`, `clearFaults`.
Khi dashboard gửi `setLed`, Rule Chain đồng thời ghi `expected_led_state`; các
mẫu telemetry tiếp theo xác nhận `led_state`. Ba lần không khớp tạo
`ACTUATOR_MISMATCH`.

## 16. Kiểm thử

Chạy smoke test:

```powershell
python tests\integration_test.py --trials 1 --reset-test-data
```

Chạy acceptance chính thức (10 lần cho mỗi loại, gồm mất kết nối):

```powershell
python tests\integration_test.py --trials 10 --settle-seconds 0.08 --reset-test-data
```

`--reset-test-data` chỉ xóa telemetry/alarm đã sinh cho hai entity demo trước
khi chạy tăng tốc; không xóa cấu hình, dashboard, relation hay entity.

Smoke test vận hành thời gian thật dùng cho bản nộp hiện tại:

```powershell
python tests\stability_test.py --minutes 1 --period-seconds 5
```

Để chạy đúng mốc 30 phút của đặc tả mở rộng, đổi `--minutes 1` thành
`--minutes 30`. Báo cáo không tuyên bố đã chạy 30 phút nếu chỉ có kết quả smoke
test ngắn.

Phương pháp và tiêu chí: [docs/test-plan.md](docs/test-plan.md). Kết quả máy đọc
được nằm trong [tests/results](tests/results).

## 17. Kết quả

Các chỉ số chính được sinh tự động trong `tests/results/metrics.json` và
`tests/results/stability-metrics.json`; bảng chi tiết từng lượt nằm trong CSV.
Không sửa tay các số đo trong báo cáo: báo cáo/slide đọc từ chính các file này.

Kết quả bản nộp hiện tại:

- acceptance: 14 kịch bản × 10 lượt = 140/140 ca được phát hiện và tạo alarm;
- TDR 100%, FAR 0%, continuity 100%, sequence consistency 100%;
- median latency 172 ms, p95 9.650 ms, connection-loss max 9.888 ms;
- smoke test 1 phút: 12/12 mẫu, NORMAL 100%, ONLINE 100%, max latency 146 ms.

Artifact hoàn chỉnh:

- báo cáo: `report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.docx`
  và bản PDF cùng tên;
- trình chiếu: `slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pptx`
  và bản PDF cùng tên.

## 18. Demo

Thực hiện theo [docs/demo-script.md](docs/demo-script.md): chứng minh telemetry,
NORMAL -> ANOMALY -> RECOVERY, alarm, OFFLINE/reconnect, RPC LED, PIR và một lỗi
sequence/sensor-stuck. Script có lời dẫn và checklist quay màn hình.

## 19. Bảo mật

- `.env.local` và `firmware/secrets.h` bị git-ignore;
- export trong `thingsboard/exports` không chứa access token/API key;
- không ghi token trong log kiểm thử;
- chỉ mở cổng local/LAN cần thiết; đổi mật khẩu PostgreSQL khi triển khai thật;
- thu hồi/đổi API key sau khi triển khai.

## 20. Xử lý sự cố

- Docker báo không có pipe Linux engine: mở Docker Desktop và chờ `docker info`.
- `VirtualizationFirmwareEnabled=False`: bật Intel VT-x/AMD-V trong BIOS và
  Windows Virtual Machine Platform/WSL2; lệnh PowerShell không thể đổi cờ BIOS.
- UI trắng/loading lâu: kiểm tra `docker compose logs thingsboard-ce`, chờ dòng
  `Started ThingsBoard`, rồi gõ lại `localhost:8080`.
- Wokwi MQTT `rc=3`: kiểm tra broker là `host.wokwi.internal`, port 1883 và token
  đúng Device local.
- Không có telemetry: xác nhận topic, token, relation và Device Profile.

## 21. Hạn chế

- Wokwi mô phỏng cảm biến, chưa đánh giá sai số phần cứng thật;
- ngưỡng demo chưa tối ưu theo từng loại nông sản;
- CE không có Solution Template/Calculated Fields PE nên phép tính được triển
  khai tương đương bằng Rule Engine;
- mô hình hiện có một kho và một node cảm biến.

## 22. Hướng phát triển

- nhiều zone/nhiều node và tự động khám phá quan hệ;
- cảm biến cửa, CO₂, ethylene và điện năng thực;
- lưu ngưỡng theo loại nông sản/lô hàng;
- TLS MQTT, certificate provisioning và phân quyền khách hàng;
- mô hình dự báo hỏng hàng, drift và bảo trì dự đoán;
- đóng gói thành PE Solution Template khi có license.

## Cấu trúc quan trọng

```text
deployment/       Docker Compose local
firmware/         ESP32 + Wokwi + PlatformIO
thingsboard/      setup idempotent, rule scripts, export JSON
tests/            acceptance + stability + kết quả CSV/JSON
docs/             kiến trúc, state machine, test plan, demo
report/           báo cáo DOCX/PDF và script tạo
slides/           slide PPTX và script tạo
```

Giấy phép: [MIT](LICENSE).
