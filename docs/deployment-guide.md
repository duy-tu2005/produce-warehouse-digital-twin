# Hướng dẫn triển khai local từ đầu

## 1. Kiểm tra môi trường

```powershell
docker version
docker info
python --version
Test-NetConnection localhost -Port 8080
Test-NetConnection localhost -Port 1883
```

Nếu Docker Linux Engine chưa sẵn sàng, mở Docker Desktop. Cờ
`VirtualizationFirmwareEnabled` phải được bật từ BIOS/UEFI; không có lệnh
PowerShell an toàn nào biến `False` thành `True` khi firmware đang tắt.

## 2. Khởi động ThingsBoard

```powershell
Set-Location deployment
docker compose up -d
docker compose ps
docker compose logs -f thingsboard-ce
```

Chỉ tiếp tục khi log có `Started ThingsBoard`. Dữ liệu PostgreSQL nằm trong
named volume `postgres-data`, nên restart container/máy không làm mất mô hình.

## 3. Triển khai mô hình

Tại thư mục gốc dự án, đưa API key hoặc thông tin Tenant Administrator vào biến
môi trường của đúng phiên PowerShell, rồi chạy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\thingsboard\setup.ps1
```

Kết quả phải báo 29 rule nodes, 35 connections, 18 dashboard widgets và không
in token. Script có thể chạy lại sau khi đổi Rule Chain/Dashboard.

## 4. Xác nhận bằng menu, không dùng deep link

1. Gõ `localhost:8080` trong thanh địa chỉ và đăng nhập.
2. `Entities` -> `Assets` -> mở `Produce_Warehouse_01`.
3. Tab `Relations`: kiểm tra `Contains` tới `ESP32_Env_Node_01`.
4. `Entities` -> `Devices`: kiểm tra device profile.
5. `Rule chains`: mở `Produce Warehouse Digital Twin - Processing`.
6. `Dashboards`: mở `Produce Warehouse - Digital Twin`.

## 5. Build và chạy Wokwi

```powershell
Set-Location firmware
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Mở chính thư mục `firmware` trong VS Code, chạy `Wokwi: Start Simulator`. Với
Wokwi VS Code, broker phải là `host.wokwi.internal`; ESP32 thật dùng IP LAN của
máy Docker.

## 6. Dừng/khởi động lại

```powershell
Set-Location deployment
docker compose stop
docker compose start
```

`docker compose down` vẫn giữ named volume nếu không thêm `-v`. Không dùng
`down -v` trừ khi chủ động muốn xóa toàn bộ database.
