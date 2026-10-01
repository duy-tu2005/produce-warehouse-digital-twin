# CHECKPOINT — Digital Twin kho bảo quản rau quả

Cập nhật cuối ngày **25/09/2026**. Khi quay lại, nhắn: **“tiếp tục theo
CHECKPOINT.md”**.

## Trạng thái hiện tại

Dự án chính: `produce-warehouse-digital-twin` trong workspace
`D:\mon_hoc\năm 4 k1\IOT\btl`.

Mô hình local đã triển khai trên ThingsBoard CE 4.3.1.5:

- Asset `Produce_Warehouse_01`;
- Device `ESP32_Env_Node_01`;
- relation `Produce_Warehouse_01 --Contains--> ESP32_Env_Node_01`;
- ba Entity View logic `DHT22_Storage_Racks_View`, `PIR_Loading_Door_View`,
  `LED_GPIO2_Control_Corner_View`, đều tham chiếu dữ liệu của ESP32;
- Rule Chain `Produce Warehouse Digital Twin - Processing`, 29 node;
- Dashboard `Produce Warehouse - Digital Twin`, 9 widget;
- state machine `INIT`, `NORMAL`, `WARNING`, `ANOMALY`, `OFFLINE`, `RECOVERY`;
- RPC LED `setLed` và feedback `led_state`.

Dashboard có sơ đồ kho tương tác với ba marker tách riêng: DHT22 ở kệ hàng,
PIR cạnh cửa nhập kho và LED tại góc điều khiển. Công tắc `Điều khiển đèn GPIO2`
gửi RPC `setLed` tới ESP32; marker LED hiển thị telemetry phản hồi `led_state`.
Góc trên bên phải chỉ giữ Kết nối, Điểm sức khỏe và Trạng thái Digital Twin;
khu vực giữa giữ ba biểu đồ và công tắc LED; cuối dashboard có bảng
`Cảnh báo Digital Twin`, hiển thị alarm active/cleared của Asset kho.
Ảnh kho tự tối/sáng theo `led_state`; đã xác nhận cả hai trạng thái bằng ảnh
`dashboard-light-off.png` và `dashboard-light-on.png`.
Các lỗi RPC target, auto-height và time-series đã được sửa. Ảnh xác nhận:

- `docs/screenshots/dashboard-overview.png`;
- `docs/screenshots/dashboard-warehouse-environment-popup.png`;
- `docs/screenshots/dashboard-warehouse-motion-popup.png`;
- `docs/screenshots/dashboard-warehouse-led-popup.png`;
- `docs/screenshots/dashboard-history.png`;
- `docs/screenshots/dashboard-lower-panel.png`.

## Kiểm thử đã hoàn thành

Acceptance end-to-end:

- 14 kịch bản × 10 lượt = 140/140 ca được phát hiện;
- 140/140 ca tạo alarm tương ứng;
- TDR 100%, FAR 0%;
- continuity 100%, sequence consistency 100%;
- median 172 ms, p95 9.650 ms;
- connection-loss max 9.888 ms, đạt ngưỡng 15 giây.

Smoke test theo phạm vi bài tập lớn:

- thời lượng 1 phút, chu kỳ 5 giây;
- 12/12 mẫu được nhận;
- NORMAL 100%, ONLINE 100%;
- max latency 146 ms, PASS.

Không tuyên bố đã chạy stability 30 phút. Script vẫn hỗ trợ chạy 30 phút nếu
giảng viên yêu cầu mở rộng.

Kết quả máy đọc:

- `tests/results/metrics.json`;
- `tests/results/anomaly_trials.csv`;
- `tests/results/acceptance-summary.md`;
- `tests/results/stability-metrics.json`;
- `tests/results/stability-samples.csv`.

## Firmware

- ESP32 DevKit V1, DHT22 GPIO15, PIR GPIO13, LED GPIO2.
- Build PlatformIO gần nhất: **SUCCESS**, RAM 13.7%, Flash 58.1%.
- Không có cảm biến mực nước/độ ẩm đất và dashboard không hiển thị dữ liệu giả.
- Token chỉ nằm trong `.env.local` và `firmware/secrets.h`, đều git-ignore.

Phần Wokwi live cuối cùng vẫn là thao tác demo thủ công: mở `firmware`, chạy
`Wokwi: Start Simulator`, xác nhận Serial có Wi-Fi/MQTT/publish OK và thử switch
LED trên dashboard. Không ghi “đã xác nhận live Wokwi” nếu chưa tự thực hiện bước
này.

## Artifact đã hoàn thành

Báo cáo đã render và kiểm tra đủ 19 trang:

- `report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.docx`;
- `report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf`.

Trình chiếu đã render và kiểm tra đủ 16 slide:

- `slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pptx`;
- `slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf`;
- source sinh slide: `slides/build_slides.ps1`.

Video demo chưa được quay; lời dẫn/checklist nằm trong `docs/demo-script.md`.

## Việc còn lại khi tiếp tục

1. Chạy thử live Wokwi và RPC LED nếu cần bằng chứng demo trực tiếp.
2. Quay video theo `docs/demo-script.md` nếu giảng viên yêu cầu nộp video.
3. Nếu sửa code/tài liệu, build lại và tạo lại ZIP sạch; không đưa secret,
   `.pio`, runtime, render trung gian hoặc log vào gói.

## Lệnh chạy nhanh

```powershell
Set-Location 'D:\mon_hoc\năm 4 k1\IOT\btl\produce-warehouse-digital-twin'

# ThingsBoard local
docker compose -f C:\thingsboard\docker-compose.yml up -d

# Build firmware
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\firmware\build.ps1

# Acceptance đầy đủ
python .\tests\integration_test.py --trials 10 --settle-seconds 0.08 --reset-test-data

# Smoke test ngắn
python .\tests\stability_test.py --minutes 1 --period-seconds 5
```

Không chạy lại marker tạo DOCX/PPTX: cả hai marker đã được chạy đúng một lần.
