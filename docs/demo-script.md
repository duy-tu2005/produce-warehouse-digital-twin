# Kịch bản video demo (7–9 phút)

## Chuẩn bị trước khi quay

- Docker/ThingsBoard đã chạy, dashboard mở bằng menu.
- Wokwi mở ở mạch ESP32; terminal thấy MQTT connected.
- Dashboard ở time window “last 30 minutes”.
- Không để lộ API key, device token, mật khẩu hoặc `secrets.h`.
- Tắt notification cá nhân và phóng trình duyệt 90–100%.

## Storyboard

| Thời gian | Hình ảnh/thao tác | Lời dẫn ngắn |
|---|---|---|
| 0:00–0:30 | Slide tên đề tài | Nêu bài toán và đối tượng twin |
| 0:30–1:10 | Wokwi circuit | DHT22 GPIO15, PIR GPIO13, LED GPIO2 |
| 1:10–1:40 | Serial monitor | Wi-Fi, MQTT và publish telemetry thành công |
| 1:40–2:20 | Asset/Device/Relation | Asset kho Contains node ESP32 |
| 2:20–3:00 | Sơ đồ kho; bấm lần lượt DHT22, PIR và LED | DHT22 nằm ở kệ hàng, PIR cạnh cửa nhập kho, LED tại góc điều khiển; mỗi popup chỉ hiện dữ liệu đúng chức năng |
| 3:00–3:50 | Inject high temperature | State sang ANOMALY, alarm xuất hiện, health giảm |
| 3:50–4:20 | Clear fault | RECOVERY qua ba mẫu sạch rồi NORMAL |
| 4:20–5:10 | Dừng mô phỏng/MQTT | Trong dưới 15 s twin sang OFFLINE, CONNECTION_LOST |
| 5:10–5:40 | Chạy lại | ACTIVITY/reconnect, RECOVERY rồi NORMAL |
| 5:40–6:20 | Widget `Điều khiển đèn GPIO2` | RPC `setLed` bật/tắt LED; marker phản hồi `led_state`, đồng thời ảnh kho tối khi OFF và sáng khi ON |
| 6:20–6:55 | PIR Simulate Motion | Khi ARMED, `UNEXPECTED_MOTION` và alarm |
| 6:55–7:30 | Fault sequence/stuck | Chứng minh sequence gap hoặc sensor stuck |
| 7:30–8:10 | Kết quả test | 10 lượt/loại, latency, TDR, FAR và smoke stability |
| 8:10–8:40 | Kết luận | Kết quả, hạn chế CE/Wokwi và hướng phát triển |

## Checklist bằng chứng

- [ ] ESP32 boot và MQTT connect.
- [ ] ThingsBoard nhận telemetry realtime.
- [ ] NORMAL -> ANOMALY -> RECOVERY -> NORMAL.
- [ ] Alarm đúng loại và clear.
- [ ] OFFLINE/reconnect trong ngưỡng.
- [ ] RPC LED hai chiều.
- [ ] PIR và ít nhất một lỗi chất lượng dữ liệu.
- [ ] Trang kết quả test, không chỉ nói miệng.

Video là bước quay màn hình cuối cùng do người nộp thực hiện; dự án cung cấp
đầy đủ storyboard và dữ liệu để quay, nhưng không tự nhận là đã có video nếu
chưa tạo file video thực tế.
