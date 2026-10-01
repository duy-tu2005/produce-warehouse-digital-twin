# Máy trạng thái Digital Twin

| Trạng thái | Điều kiện chính | Chuyển tiếp |
|---|---|---|
| INIT | Chưa có lịch sử hợp lệ | Mẫu hợp lệ tiếp theo chuyển NORMAL |
| NORMAL | Không có luật bất thường kích hoạt | WARNING, ANOMALY hoặc OFFLINE |
| WARNING | Điểm bất thường từ 20 đến 49 | Ba cửa sổ sạch sang RECOVERY/NORMAL hoặc lỗi nặng sang ANOMALY |
| ANOMALY | Điểm bất thường từ 50 trở lên | Ba cửa sổ sạch qua RECOVERY; mất dữ liệu sang OFFLINE |
| OFFLINE | ThingsBoard phát `INACTIVITY_EVENT` | Có `ACTIVITY_EVENT` sang RECOVERY |
| RECOVERY | Thiết bị vừa trở lại hoặc lỗi vừa kết thúc | Ba cửa sổ sạch sang NORMAL |

OFFLINE có ưu tiên cao nhất. `recovery_clean_windows` mặc định bằng 3 để chống
dao động trạng thái. Các ngưỡng là cấu hình demo và được lưu thành server-side
attributes trên Device, không phải tiêu chuẩn bảo quản cho mọi loại rau quả.

