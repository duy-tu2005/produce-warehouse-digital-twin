# Luật phát hiện bất thường

| Mã | Logic mặc định | Điểm |
|---|---|---:|
| HIGH_TEMPERATURE | Trên 26 °C cảnh báo, trên 30 °C nghiêm trọng | 40 hoặc 90 |
| LOW_TEMPERATURE | Dưới 18 °C cảnh báo, dưới 15 °C nghiêm trọng | 40 hoặc 90 |
| HIGH_HUMIDITY | Trên 75 % cảnh báo, trên 85 % nghiêm trọng | 40 hoặc 90 |
| LOW_HUMIDITY | Dưới 55 % cảnh báo, dưới 45 % nghiêm trọng | 40 hoặc 90 |
| TEMPERATURE_RATE_ANOMALY | Tốc độ tuyệt đối lớn hơn 2 °C/phút | 70 hoặc 85 |
| HUMIDITY_RATE_ANOMALY | Tốc độ tuyệt đối lớn hơn 10 %RH/phút | 70 hoặc 85 |
| SENSOR_STUCK | Nhiệt độ và độ ẩm đổi dưới epsilon trong 12 mẫu | 70 |
| SEQUENCE_GAP | Trùng, giảm hoặc nhảy sequence | 45 đến 80 |
| DEVICE_RESTART | `uptime_s` nhỏ hơn mẫu trước | 65 |
| WEAK_SIGNAL | RSSI không lớn hơn -80/-90 dBm | 35 hoặc 80 |
| UNEXPECTED_MOTION | `security_mode=ARMED` và `motion=true` | 70 |
| INVALID_SENSOR | Ba mẫu liên tiếp thiếu hoặc ngoài miền DHT22 | 60 |
| CONNECTION_LOST | ThingsBoard phát inactivity event | 100 |

Khi nhiều luật cùng kích hoạt, Rule Engine chọn luật có điểm cao nhất làm
`anomaly_type`, đồng thời lưu toàn bộ danh sách vào `active_anomalies`.
`health_score = max(0, 100 - anomaly_score)`.

