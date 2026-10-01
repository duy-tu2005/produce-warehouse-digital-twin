# Kế hoạch kiểm thử và tiêu chí chấp nhận

## Phạm vi

Acceptance test gửi qua HTTP Device API nhưng đi qua đúng Device Profile, Rule
Engine, relation, Asset, alarm và dashboard như telemetry MQTT. Wokwi được kiểm
tra riêng để chứng minh mạch, Wi-Fi, MQTT và RPC vật lý/mô phỏng.

## Chỉ số

- Detection latency: từ khi gửi mẫu gây lỗi đến khi Asset có `anomaly_type`.
- TDR: số lượt phát hiện đúng / tổng lượt fault injection.
- Alarm rate: số lượt có active alarm đúng loại / tổng lượt.
- FAR: số cửa sổ baseline bình thường bị gắn bất thường / tổng cửa sổ baseline.
- Continuity: POST thành công / POST đã thử.
- Sequence consistency: số bước sequence bình thường đúng / tổng bước bình thường.

## Tiêu chí

| Tiêu chí | Ngưỡng PASS |
|---|---:|
| True Detection Rate | >= 90% |
| False Alarm Rate | <= 5% |
| Connection lost latency | <= 15 s |
| Data continuity | >= 95% |
| Sequence consistency | >= 99% |
| Smoke stability | 2 phút, chu kỳ 5 s, >=95% NORMAL/continuity |

## Ma trận fault injection

Mỗi loại chạy 10 lượt: `HIGH_TEMPERATURE`, `LOW_TEMPERATURE`,
`HIGH_HUMIDITY`, `LOW_HUMIDITY`, `TEMPERATURE_RATE_ANOMALY`,
`HUMIDITY_RATE_ANOMALY`, `WEAK_SIGNAL`, `SEQUENCE_GAP`, `DEVICE_RESTART`,
`UNEXPECTED_MOTION`, `INVALID_SENSOR`, `SENSOR_STUCK`, `ACTUATOR_MISMATCH`,
`CONNECTION_LOST`.

## Tái lập

```powershell
python tests\integration_test.py --trials 10 --settle-seconds 0.08 --reset-test-data
python tests\stability_test.py --minutes 2 --period-seconds 5
```

Test tăng tốc dùng logical timestamp nằm trong quá khứ để không tạo alarm có
thời gian tương lai. Stability test dùng timestamp đồng hồ thật. File JSON/CSV
trong `tests/results` là bằng chứng nguồn cho báo cáo và slide. Mốc 30 phút trong
MASTER PROMPT được giữ như một test mở rộng có thể chạy bằng cách đổi tham số;
bản nộp hiện tại dùng smoke test ngắn theo phạm vi bài tập đã thống nhất.
