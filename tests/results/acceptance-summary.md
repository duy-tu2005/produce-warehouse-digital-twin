# Kết quả kiểm thử chấp nhận

- Số ca thử bất thường: **140**
- Tỷ lệ phát hiện đúng (TDR): **100.00%**
- Tỷ lệ tạo alarm tương ứng: **100.00%**
- Tỷ lệ cảnh báo giả trên cửa sổ baseline (FAR): **0.00%**
- Độ liên tục gửi dữ liệu: **100.00%**
- Nhất quán sequence ở luồng bình thường: **100.00%**
- Độ trễ p95: **9650 ms**
- Độ trễ mất kết nối lớn nhất: **9888 ms**

## Đối chiếu tiêu chí

- PASS — `tdr_at_least_90`
- PASS — `far_at_most_5`
- PASS — `connection_at_most_15s`
- PASS — `continuity_at_least_95`
- PASS — `sequence_at_least_99`

> Các ca trên dùng HTTP Device API nhưng đi qua đúng Device Profile và Rule Engine như ESP32/MQTT. Kiểm tra Wokwi vật lý được thực hiện riêng theo checklist demo.
