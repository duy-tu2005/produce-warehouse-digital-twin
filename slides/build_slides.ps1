param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$outputDir = Join-Path $PSScriptRoot 'output'
$renderDir = Join-Path $PSScriptRoot 'rendered'
New-Item -ItemType Directory -Force -Path $outputDir, $renderDir | Out-Null

$pptxPath = Join-Path $outputDir 'Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pptx'
$pdfPath = Join-Path $outputDir 'Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf'

function Get-Rgb([int]$r, [int]$g, [int]$b) {
    return $r + ($g * 256) + ($b * 65536)
}

$C = @{
    Ink      = Get-Rgb 20 30 48
    Slate    = Get-Rgb 73 88 105
    Muted    = Get-Rgb 112 128 144
    Teal     = Get-Rgb 0 121 107
    TealDark = Get-Rgb 0 77 70
    TealSoft = Get-Rgb 227 242 240
    Blue     = Get-Rgb 47 107 255
    BlueSoft = Get-Rgb 235 241 255
    Green    = Get-Rgb 20 145 83
    Red      = Get-Rgb 220 53 69
    Amber    = Get-Rgb 244 166 33
    White    = Get-Rgb 255 255 255
    Cloud    = Get-Rgb 246 248 250
    Line     = Get-Rgb 220 226 232
}

$ppLayoutBlank = 12
$ppSaveAsOpenXMLPresentation = 24
$ppSaveAsPDF = 32
$msoTextOrientationHorizontal = 1
$msoFalse = 0
$msoTrue = -1
$msoShapeRectangle = 1
$msoShapeRoundedRectangle = 5
$msoShapeOval = 9
$msoShapeChevron = 52
$msoShapeRightArrow = 33
$msoShapeHexagon = 10

function Add-Text {
    param(
        $Slide,
        [string]$Text,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [double]$Size = 20,
        [int]$Color = $C.Ink,
        [bool]$Bold = $false,
        [int]$Align = 1,
        [string]$Font = 'Arial',
        [bool]$AutoFit = $false
    )
    $shape = $Slide.Shapes.AddTextBox($msoTextOrientationHorizontal, $Left, $Top, $Width, $Height)
    $shape.TextFrame.TextRange.Text = $Text
    $shape.TextFrame.TextRange.Font.Name = $Font
    $shape.TextFrame.TextRange.Font.Size = $Size
    $shape.TextFrame.TextRange.Font.Color.RGB = $Color
    $shape.TextFrame.TextRange.Font.Bold = if ($Bold) { $msoTrue } else { $msoFalse }
    $shape.TextFrame.TextRange.ParagraphFormat.Alignment = $Align
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $shape.TextFrame.WordWrap = $msoTrue
    if ($AutoFit) { $shape.TextFrame.AutoSize = 2 }
    return $shape
}

function Add-Box {
    param(
        $Slide,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [int]$Fill = $C.White,
        [int]$Line = $C.Line,
        [double]$Radius = 0,
        [double]$Transparency = 0
    )
    $shapeType = if ($Radius -gt 0) { $msoShapeRoundedRectangle } else { $msoShapeRectangle }
    $shape = $Slide.Shapes.AddShape($shapeType, $Left, $Top, $Width, $Height)
    $shape.Fill.ForeColor.RGB = $Fill
    $shape.Fill.Transparency = $Transparency
    if ($Line -lt 0) {
        $shape.Line.Visible = $msoFalse
    } else {
        $shape.Line.ForeColor.RGB = $Line
        $shape.Line.Weight = 1
    }
    return $shape
}

function Add-PictureFit {
    param(
        $Slide,
        [string]$Path,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [bool]$Crop = $false
    )
    $resolved = (Resolve-Path $Path).Path
    Add-Type -AssemblyName System.Drawing
    $img = [System.Drawing.Image]::FromFile($resolved)
    try {
        $imageRatio = $img.Width / $img.Height
    } finally {
        $img.Dispose()
    }
    $boxRatio = $Width / $Height
    if ($Crop) {
        if ($imageRatio -gt $boxRatio) {
            $h = $Height
            $w = $h * $imageRatio
        } else {
            $w = $Width
            $h = $w / $imageRatio
        }
    } else {
        if ($imageRatio -gt $boxRatio) {
            $w = $Width
            $h = $w / $imageRatio
        } else {
            $h = $Height
            $w = $h * $imageRatio
        }
    }
    $x = $Left + (($Width - $w) / 2)
    $y = $Top + (($Height - $h) / 2)
    return $Slide.Shapes.AddPicture($resolved, $msoFalse, $msoTrue, $x, $y, $w, $h)
}

function Add-SlideBase {
    param($Presentation, [string]$Title, [string]$Kicker, [int]$Number)
    $slide = $Presentation.Slides.Add($Presentation.Slides.Count + 1, $ppLayoutBlank)
    $bg = Add-Box $slide 0 0 960 540 $C.White -1
    $bg.ZOrder(1)
    Add-Box $slide 0 0 960 8 $C.Teal -1 | Out-Null
    Add-Text $slide $Kicker 48 27 650 20 10 $C.Teal $true | Out-Null
    Add-Text $slide $Title 48 49 850 48 28 $C.Ink $true | Out-Null
    Add-Box $slide 48 513 864 1 $C.Line -1 | Out-Null
    Add-Text $slide 'DIGITAL TWIN KHO BẢO QUẢN RAU QUẢ' 48 518 540 14 8 $C.Muted $true | Out-Null
    Add-Text $slide ([string]$Number).PadLeft(2, '0') 870 516 42 16 9 $C.Teal $true 3 | Out-Null
    return $slide
}

function Add-BulletList {
    param(
        $Slide,
        [string[]]$Items,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$LineHeight = 49,
        [double]$FontSize = 18,
        [int]$DotColor = $C.Teal,
        [int]$TextColor = $C.Ink
    )
    for ($i = 0; $i -lt $Items.Count; $i++) {
        $y = $Top + ($i * $LineHeight)
        $dot = $Slide.Shapes.AddShape($msoShapeOval, $Left, $y + 7, 9, 9)
        $dot.Fill.ForeColor.RGB = $DotColor
        $dot.Line.Visible = $msoFalse
        Add-Text $Slide $Items[$i] ($Left + 20) $y ($Width - 20) ($LineHeight - 2) $FontSize $TextColor $false | Out-Null
    }
}

function Add-MetricCard {
    param($Slide, [double]$Left, [double]$Top, [double]$Width, [string]$Value, [string]$Label, [int]$Accent = $C.Teal)
    Add-Box $Slide $Left $Top $Width 92 $C.White $C.Line 8 | Out-Null
    Add-Box $Slide $Left $Top 7 92 $Accent -1 8 | Out-Null
    Add-Text $Slide $Value ($Left + 19) ($Top + 13) ($Width - 30) 36 27 $Accent $true | Out-Null
    Add-Text $Slide $Label ($Left + 19) ($Top + 56) ($Width - 30) 23 11 $C.Slate $false | Out-Null
}

function Add-Notes {
    param($Slide, [string]$Text)
    try {
        $placeholder = $Slide.NotesPage.Shapes.Placeholders.Item(2)
        $placeholder.TextFrame.TextRange.Text = $Text
    } catch {
        # Notes are helpful but not required for a valid deck.
    }
}

function Add-FlowStep {
    param($Slide, [double]$Left, [double]$Top, [double]$Width, [string]$Number, [string]$Title, [string]$Body, [int]$Fill)
    Add-Box $Slide $Left $Top $Width 132 $Fill -1 10 | Out-Null
    $badge = $Slide.Shapes.AddShape($msoShapeOval, ($Left + 16), ($Top + 16), 30, 30)
    $badge.Fill.ForeColor.RGB = $C.White
    $badge.Line.Visible = $msoFalse
    Add-Text $Slide $Number ($Left + 16) ($Top + 22) 30 18 11 $C.TealDark $true 2 | Out-Null
    Add-Text $Slide $Title ($Left + 56) ($Top + 17) ($Width - 70) 30 16 $C.White $true | Out-Null
    Add-Text $Slide $Body ($Left + 16) ($Top + 58) ($Width - 32) 60 12 $C.White $false | Out-Null
}

$powerPoint = $null
$presentation = $null
try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    $powerPoint.Visible = $msoTrue
    $presentation = $powerPoint.Presentations.Add()
    $presentation.PageSetup.SlideWidth = 960
    $presentation.PageSetup.SlideHeight = 540

    $architecture = Join-Path $ProjectRoot 'report\assets\architecture.png'
    $entityModel = Join-Path $ProjectRoot 'report\assets\entity-model.png'
    $circuit = Join-Path $ProjectRoot 'report\assets\circuit.png'
    $stateMachine = Join-Path $ProjectRoot 'report\assets\state-machine.png'
    $ruleChain = Join-Path $ProjectRoot 'report\assets\rule-chain.png'
    $acceptance = Join-Path $ProjectRoot 'report\assets\acceptance-results.png'
    $dashOverview = Join-Path $ProjectRoot 'docs\screenshots\dashboard-overview.png'
    $dashHistory = Join-Path $ProjectRoot 'docs\screenshots\dashboard-history.png'
    $dashAlarms = Join-Path $ProjectRoot 'docs\screenshots\dashboard-alarms.png'

    # 1 — Title
    $slide = $presentation.Slides.Add(1, $ppLayoutBlank)
    Add-Box $slide 0 0 960 540 $C.Ink -1 | Out-Null
    Add-Box $slide 0 0 18 540 $C.Teal -1 | Out-Null
    Add-Text $slide 'BÀI TẬP LỚN · INTERNET OF THINGS' 62 50 700 24 12 $C.TealSoft $true | Out-Null
    Add-Text $slide "DIGITAL TWIN GIÁM SÁT`nKHO BẢO QUẢN RAU QUẢ" 62 93 690 112 38 $C.White $true | Out-Null
    Add-Text $slide 'Giám sát trạng thái · phát hiện bất thường · cảnh báo · điều khiển LED hai chiều' 65 224 740 54 18 (Get-Rgb 202 216 226) $false | Out-Null
    Add-Box $slide 63 316 834 146 (Get-Rgb 26 43 60) -1 10 | Out-Null
    Add-Text $slide 'THINGSBOARD LOCAL 4.3.1.5' 92 344 250 20 11 $C.TealSoft $true | Out-Null
    Add-Text $slide 'ESP32 · DHT22 · PIR · LED' 92 376 300 30 20 $C.White $true | Out-Null
    Add-Text $slide 'Asset ↔ Device ↔ Rule Engine ↔ Dashboard' 92 414 380 22 13 (Get-Rgb 190 205 218) $false | Out-Null
    $hex = $slide.Shapes.AddShape($msoShapeHexagon, 685, 326, 150, 122)
    $hex.Fill.ForeColor.RGB = $C.Teal
    $hex.Line.Visible = $msoFalse
    Add-Text $slide 'TWIN' 685 359 150 35 26 $C.White $true 2 | Out-Null
    Add-Text $slide '2026' 685 397 150 18 11 $C.TealSoft $true 2 | Out-Null
    Add-Notes $slide 'Mở đầu: đề tài xây dựng một Digital Twin vận hành được trên ThingsBoard Local, bám đúng mạch ESP32 mô phỏng và có kiểm thử định lượng.'

    # 2 — Problem and scope
    $slide = Add-SlideBase $presentation 'Bài toán và phạm vi' '01 · ĐẶT VẤN ĐỀ' 2
    Add-Box $slide 48 118 412 342 $C.Cloud -1 10 | Out-Null
    Add-Text $slide 'Vấn đề' 72 142 180 30 20 $C.TealDark $true | Out-Null
    Add-BulletList $slide @(
        'Nhiệt độ, độ ẩm và chuyển động cần được theo dõi theo thời gian thực.',
        'Dashboard cảm biến đơn thuần chưa thể hiện trạng thái, quan hệ và vòng phản hồi.',
        'Cần cảnh báo đúng loại và truy vết được bằng dữ liệu lịch sử.'
    ) 72 188 354 67 16
    Add-Box $slide 482 118 430 342 $C.TealSoft -1 10 | Out-Null
    Add-Text $slide 'Mục tiêu đầu ra' 506 142 250 30 20 $C.TealDark $true | Out-Null
    Add-BulletList $slide @(
        'Twin cấp kho gồm Asset, Device và relation Contains.',
        'State machine NORMAL / WARNING / CRITICAL / OFFLINE.',
        '13 nhóm nghiệp vụ/dữ liệu + connection lost; dashboard 19 widget.',
        'RPC bật/tắt LED có command và feedback thực tế.'
    ) 506 188 374 55 16 $C.Blue
    Add-Notes $slide 'Phạm vi bài tập lớn: một kho và một node cảm biến. Trọng tâm là luồng Digital Twin hoàn chỉnh, không phải mô phỏng quy mô sản xuất.'

    # 3 — What makes it a Digital Twin
    $slide = Add-SlideBase $presentation 'Vì sao đây là Digital Twin?' '02 · KHÁI NIỆM ÁP DỤNG' 3
    Add-FlowStep $slide 48 134 196 '1' 'IDENTITY' 'Asset kho và Device ESP32 có định danh riêng.' $C.Teal
    Add-FlowStep $slide 260 134 196 '2' 'STATE' 'Trạng thái hiện tại, lịch sử và health score.' (Get-Rgb 0 137 123)
    Add-FlowStep $slide 472 134 196 '3' 'BEHAVIOR' 'State machine và luật phát hiện bất thường.' (Get-Rgb 32 119 179)
    Add-FlowStep $slide 684 134 228 '4' 'FEEDBACK' 'RPC LED: expected state được đối chiếu observed state.' $C.Blue
    Add-Box $slide 48 298 864 150 $C.Cloud -1 10 | Out-Null
    Add-Text $slide 'Không chỉ là biểu đồ cảm biến' 78 322 355 30 21 $C.Ink $true | Out-Null
    Add-Text $slide 'Twin tổng hợp dữ liệu vật lý → ngữ cảnh entity/relation → trạng thái nghiệp vụ → alarm → hành động điều khiển → telemetry xác nhận.' 78 365 750 60 18 $C.Slate $false | Out-Null
    Add-Notes $slide 'Nguồn tham chiếu: https://thingsboard.io/docs/pe/concepts/digital-twin-model/ và https://thingsboard.io/docs/pe/user-guide/digital-twins/entities/'

    # 4 — Architecture
    $slide = Add-SlideBase $presentation 'Kiến trúc tổng thể' '03 · KIẾN TRÚC' 4
    Add-Box $slide 48 112 864 374 $C.Cloud -1 10 | Out-Null
    Add-PictureFit $slide $architecture 65 126 830 338 | Out-Null
    Add-Notes $slide 'Luồng chính: cảm biến Wokwi gửi MQTT tới ThingsBoard; Rule Engine chuẩn hóa, cập nhật Asset twin, tạo alarm; dashboard hiển thị và gửi RPC ngược về ESP32.'

    # 5 — Circuit
    $slide = Add-SlideBase $presentation 'Node vật lý / mô phỏng' '04 · PHẦN CỨNG' 5
    Add-Box $slide 48 116 580 354 $C.Cloud -1 10 | Out-Null
    Add-PictureFit $slide $circuit 62 131 552 322 | Out-Null
    Add-Box $slide 650 116 262 354 $C.White $C.Line 10 | Out-Null
    Add-Text $slide 'ESP32 DevKit V1' 676 142 210 30 20 $C.TealDark $true | Out-Null
    Add-BulletList $slide @(
        'DHT22: nhiệt độ, độ ẩm',
        'PIR: phát hiện chuyển động',
        'LED GPIO2: actuator',
        'Wi-Fi + MQTT Device API',
        'Wokwi for VS Code'
    ) 676 190 205 48 15
    Add-Text $slide 'Không tạo dữ liệu “mực nước” hay cảm biến ngoài mạch.' 676 415 205 40 12 $C.Red $true | Out-Null
    Add-Notes $slide 'Mạch chỉ đo nhiệt độ, độ ẩm và chuyển động; LED là cơ cấu chấp hành. Dashboard đã được sửa để không hiển thị dữ liệu giả ngoài khả năng mạch.'

    # 6 — Telemetry
    $slide = Add-SlideBase $presentation 'Dữ liệu và giao tiếp MQTT' '05 · TELEMETRY' 6
    Add-Box $slide 48 121 410 334 $C.Ink -1 10 | Out-Null
    Add-Text $slide 'v1/devices/me/telemetry' 73 145 340 26 17 $C.TealSoft $true '1' 'Consolas' | Out-Null
    $telemetryJson = @'
{
  "temperature": 22.4,
  "humidity": 65.2,
  "motion": false,
  "rssi": -57,
  "sequence": 1042,
  "led_state": true
}
'@
    Add-Text $slide $telemetryJson 75 188 330 220 16 $C.White $false '1' 'Consolas' | Out-Null
    Add-Box $slide 486 121 426 334 $C.Cloud -1 10 | Out-Null
    Add-Text $slide 'Nguyên tắc dữ liệu' 514 148 260 28 20 $C.TealDark $true | Out-Null
    Add-BulletList $slide @(
        'Giữ raw telemetry trên Device.',
        'Asset nhận state tổng hợp và anomaly context.',
        'sequence / uptime hỗ trợ phát hiện gap và restart.',
        'last_seen + activity tạo ONLINE / OFFLINE.'
    ) 514 198 360 55 16
    Add-Notes $slide 'Nguồn API: https://thingsboard.io/docs/reference/mqtt-api/. Token thiết bị chỉ nằm trong tệp bí mật, không nằm trong export hoặc slide.'

    # 7 — Entity model
    $slide = Add-SlideBase $presentation 'Mô hình Entity và Relation' '06 · DIGITAL TWIN MODEL' 7
    Add-Box $slide 48 119 864 287 $C.Cloud -1 10 | Out-Null
    Add-PictureFit $slide $entityModel 70 137 820 245 | Out-Null
    Add-MetricCard $slide 48 414 265 'WAREHOUSE' 'Asset · Produce_Warehouse_01 · state' $C.Teal
    Add-MetricCard $slide 338 414 284 'CONTAINS' 'Relation · cấu trúc và ngữ cảnh' $C.Blue
    Add-MetricCard $slide 647 414 265 'DEVICE: ESP32' 'ESP32_Env_Node_01 · raw data / RPC' $C.Green
    Add-Notes $slide 'Nguồn tham chiếu: https://thingsboard.io/docs/pe/user-guide/digital-twins/relations/. Relation Contains nối Warehouse Asset với ESP32 Device.'

    # 8 — State machine
    $slide = Add-SlideBase $presentation 'Trạng thái tổng hợp của Twin' '07 · STATE MACHINE' 8
    Add-Box $slide 48 116 602 362 $C.Cloud -1 10 | Out-Null
    Add-PictureFit $slide $stateMachine 66 133 566 325 | Out-Null
    Add-Box $slide 674 116 238 362 $C.White $C.Line 10 | Out-Null
    Add-Text $slide 'Ưu tiên trạng thái' 696 142 190 30 18 $C.TealDark $true | Out-Null
    Add-Text $slide 'OFFLINE' 696 194 170 28 20 $C.Red $true | Out-Null
    Add-Text $slide 'CRITICAL' 696 240 170 28 20 (Get-Rgb 230 96 30) $true | Out-Null
    Add-Text $slide 'WARNING' 696 286 170 28 20 $C.Amber $true | Out-Null
    Add-Text $slide 'NORMAL' 696 332 170 28 20 $C.Green $true | Out-Null
    Add-Text $slide 'Alarm và health score được suy ra từ cùng một ngữ cảnh.' 696 387 180 58 13 $C.Slate $false | Out-Null
    Add-Notes $slide 'OFFLINE có ưu tiên cao nhất; sau đó là CRITICAL, WARNING và NORMAL. Mỗi lần cập nhật đều lưu current_state, observed_state, anomaly_type và health_score trên Asset.'

    # 9 — Anomalies
    $slide = Add-SlideBase $presentation 'Phát hiện bất thường' '08 · ANOMALY DETECTION' 9
    $groups = @(
        @{x=48; title='MÔI TRƯỜNG'; color=$C.Teal; items="HIGH_TEMPERATURE`nLOW_TEMPERATURE`nHIGH_HUMIDITY`nLOW_HUMIDITY`nTEMPERATURE_RATE`nHUMIDITY_RATE"},
        @{x=338; title='CHẤT LƯỢNG DỮ LIỆU'; color=$C.Blue; items="INVALID_SENSOR`nSENSOR_STUCK`nSEQUENCE_GAP`nDEVICE_RESTART"},
        @{x=628; title='VẬN HÀNH'; color=$C.Red; items="WEAK_SIGNAL`nUNEXPECTED_MOTION`nACTUATOR_MISMATCH`nCONNECTION_LOST"}
    )
    foreach ($g in $groups) {
        Add-Box $slide $g.x 126 264 318 $C.White $C.Line 10 | Out-Null
        Add-Box $slide $g.x 126 264 48 $g.color -1 10 | Out-Null
        Add-Text $slide $g.title ($g.x + 18) 142 228 20 13 $C.White $true 2 | Out-Null
        Add-Text $slide $g.items ($g.x + 23) 203 218 164 13 $C.Ink $true 2 | Out-Null
        Add-Text $slide "Ngưỡng + rate + lịch sử`n→ anomaly_type`n→ severity / score" ($g.x + 28) 371 208 56 12 $C.Slate $false 2 | Out-Null
    }
    Add-Notes $slide 'Có 14 kịch bản được kiểm thử: 13 loại nghiệp vụ/chất lượng dữ liệu và CONNECTION_LOST theo lifecycle timeout.'

    # 10 — Rule chain
    $slide = Add-SlideBase $presentation 'Xử lý trong Rule Engine' '09 · RULE CHAIN' 10
    Add-Box $slide 48 116 864 320 $C.Cloud -1 10 | Out-Null
    Add-PictureFit $slide $ruleChain 64 132 832 286 | Out-Null
    Add-Text $slide 'Một payload đi qua cùng pipeline: enrich → validate → detect → update twin → alarm → dashboard.' 76 452 808 28 16 $C.Slate $false 2 | Out-Null
    Add-Notes $slide 'ThingsBoard CE dùng Rule Engine và script nodes để triển khai logic tương đương mô hình twin; PE có thêm Digital Twin/Calculated Fields và Solution Template đóng gói sẵn.'

    # 11 — Dashboard
    $slide = Add-SlideBase $presentation 'Dashboard vận hành' '10 · DIGITAL TWIN UI' 11
    Add-Box $slide 48 115 864 356 $C.Ink -1 8 | Out-Null
    Add-PictureFit $slide $dashOverview 55 122 850 342 | Out-Null
    Add-Box $slide 61 420 838 37 $C.Ink -1 6 0.14 | Out-Null
    Add-Text $slide '19 widget · trạng thái hiện tại · gauges · lịch sử · alarm · RPC LED' 80 430 800 19 13 $C.White $true 2 | Out-Null
    Add-Notes $slide 'Dashboard tổ chức theo tư duy template Smart Irrigation: overview, health/state, history, alarms và control; nhưng trường dữ liệu được thay bằng đúng mạch kho rau quả. Nguồn tham khảo: https://thingsboard.io/iot-hub/solution-templates/smart-irrigation/'

    # 12 — History and alarms
    $slide = Add-SlideBase $presentation 'Lịch sử và cảnh báo có thể truy vết' '11 · OBSERVABILITY' 12
    Add-Box $slide 48 119 413 326 $C.Cloud -1 8 | Out-Null
    Add-PictureFit $slide $dashHistory 56 127 397 310 | Out-Null
    Add-Box $slide 499 119 413 326 $C.Cloud -1 8 | Out-Null
    Add-PictureFit $slide $dashAlarms 507 127 397 310 | Out-Null
    Add-Text $slide 'HISTORY' 72 458 370 20 12 $C.Teal $true 2 | Out-Null
    Add-Text $slide 'ALARMS' 522 458 370 20 12 $C.Red $true 2 | Out-Null
    Add-Notes $slide 'Người vận hành có thể đối chiếu diễn biến telemetry với alarm, severity và trạng thái của Asset thay vì chỉ nhìn số tức thời.'

    # 13 — RPC LED
    $slide = Add-SlideBase $presentation 'Vòng điều khiển hai chiều: LED' '12 · RPC FEEDBACK' 13
    $steps = @(
        @{x=48; n='1'; t='Dashboard'; b='Người dùng đổi switch LED.'; c=$C.Teal},
        @{x=254; n='2'; t='Server-side RPC'; b='ThingsBoard gửi setLed.'; c=(Get-Rgb 0 137 123)},
        @{x=460; n='3'; t='ESP32'; b='Firmware đổi GPIO2.'; c=$C.Blue},
        @{x=666; n='4'; t='Feedback'; b='Publish led_state; Twin đối chiếu.'; c=$C.Green}
    )
    foreach ($s in $steps) { Add-FlowStep $slide $s.x 148 184 $s.n $s.t $s.b $s.c }
    for ($i=0; $i -lt 3; $i++) {
        $arrow = $slide.Shapes.AddShape($msoShapeChevron, (232 + $i*206), 194, 22, 36)
        $arrow.Fill.ForeColor.RGB = $C.Line
        $arrow.Line.Visible = $msoFalse
    }
    Add-Box $slide 48 320 802 116 $C.TealSoft -1 10 | Out-Null
    Add-Text $slide 'Expected = observed' 76 343 300 32 24 $C.TealDark $true | Out-Null
    Add-Text $slide 'Nếu khác nhau trong 3 mẫu liên tiếp → ACTUATOR_MISMATCH.' 76 385 650 28 17 $C.Ink $false | Out-Null
    $loop = $slide.Shapes.AddShape($msoShapeRightArrow, 803, 344, 75, 52)
    $loop.Fill.ForeColor.RGB = $C.Teal
    $loop.Line.Visible = $msoFalse
    Add-Notes $slide 'Đây là khác biệt quan trọng giữa dashboard hiển thị và Digital Twin có vòng phản hồi: lệnh điều khiển phải được xác nhận bằng trạng thái quan sát thực tế.'

    # 14 — Tests
    $slide = Add-SlideBase $presentation 'Kiểm thử end-to-end' '13 · VERIFICATION' 14
    Add-Box $slide 48 120 405 337 $C.Cloud -1 10 | Out-Null
    Add-Text $slide 'Acceptance test' 76 148 250 30 20 $C.TealDark $true | Out-Null
    Add-BulletList $slide @(
        '14 kịch bản × 10 lượt = 140 ca; baseline kiểm tra FAR riêng',
        'Payload đi qua Device API và Rule Engine thật',
        'Đối chiếu Asset state, Alarm và latency',
        'Ngưỡng: TDR ≥90%, FAR ≤5%, latency ≤15s'
    ) 76 198 345 55 15
    Add-Box $slide 477 120 435 337 $C.TealSoft -1 10 | Out-Null
    Add-Text $slide 'Smoke test vận hành' 505 148 300 30 20 $C.TealDark $true | Out-Null
    Add-BulletList $slide @(
        'Thời lượng 1 phút, chu kỳ 5 giây',
        '12 mẫu kỳ vọng / 12 mẫu nhận',
        'NORMAL và ONLINE đạt 100%',
        'Dùng đúng phạm vi bài tập lớn; không tuyên bố độ bền dài hạn'
    ) 505 198 365 55 15 $C.Blue
    Add-Notes $slide 'Người thực hiện chủ động dùng smoke test ngắn theo phạm vi bài tập lớn. Kiểm thử 30 phút được giữ là tùy chọn, không được tuyên bố là đã chạy.'

    # 15 — Results
    $slide = Add-SlideBase $presentation 'Kết quả định lượng' '14 · RESULTS' 15
    Add-MetricCard $slide 48 119 196 '100%' 'True Detection Rate' $C.Green
    Add-MetricCard $slide 268 119 196 '0%' 'False Alarm Rate' $C.Teal
    Add-MetricCard $slide 488 119 196 '100%' 'Data continuity' $C.Blue
    Add-MetricCard $slide 708 119 204 '172 ms' 'Median latency' $C.Amber
    Add-Box $slide 48 232 864 235 $C.Cloud -1 10 | Out-Null
    Add-PictureFit $slide $acceptance 70 244 820 208 | Out-Null
    Add-Text $slide 'P95 9.65 s do CONNECTION_LOST chờ inactivity timeout; vẫn dưới ngưỡng 15 s.' 80 448 800 18 11 $C.Slate $false 2 | Out-Null
    Add-Notes $slide 'Kết quả: 140/140 lượt được phát hiện và tạo alarm đúng; continuity 100%; sequence consistency 100%; connection-loss tối đa 9.888 giây.'

    # 16 — Conclusion
    $slide = Add-SlideBase $presentation 'Kết luận và demo' '15 · HANDOFF' 16
    Add-Box $slide 48 120 526 340 $C.Ink -1 10 | Out-Null
    Add-Text $slide 'Đã hoàn thành' 78 148 280 34 22 $C.TealSoft $true | Out-Null
    Add-BulletList $slide @(
        'Digital Twin Asset–Device–Relation chạy local',
        'State machine, anomaly, alarm và 19 widget',
        'RPC LED hai chiều với telemetry feedback',
        'Bộ test, báo cáo và source có thể tái tạo'
    ) 78 204 448 54 16 $C.Teal $C.White
    Add-Box $slide 600 120 312 340 $C.TealSoft -1 10 | Out-Null
    Add-Text $slide 'Demo 4 bước' 626 148 220 30 20 $C.TealDark $true | Out-Null
    Add-Text $slide "01  Khởi động Docker`n02  Chạy Wokwi`n03  Xem Dashboard / Alarm`n04  Bật tắt LED bằng RPC" 626 208 240 155 18 $C.Ink $true | Out-Null
    Add-Text $slide 'Q & A' 626 392 240 35 27 $C.Teal $true | Out-Null
    Add-Notes $slide 'Kết thúc bằng demo trực tiếp. Nếu không có Wokwi live, có thể dùng publisher/test harness để chứng minh pipeline server; không thay thế phần xác nhận LED vật lý trong demo cuối.'

    if (Test-Path $pptxPath) { Remove-Item -LiteralPath $pptxPath -Force }
    if (Test-Path $pdfPath) { Remove-Item -LiteralPath $pdfPath -Force }
    $presentation.SaveAs($pptxPath, $ppSaveAsOpenXMLPresentation)
    $presentation.SaveAs($pdfPath, $ppSaveAsPDF)

    Get-ChildItem -LiteralPath $renderDir -Filter '*.png' -ErrorAction SilentlyContinue | Remove-Item -Force
    $presentation.Export($renderDir, 'PNG', 1600, 900)
    Get-ChildItem -LiteralPath $renderDir -Filter '*.png' | ForEach-Object {
        $match = [regex]::Match($_.BaseName, '(\d+)$')
        if ($match.Success) {
            $newName = 'slide-{0:D2}.png' -f [int]$match.Groups[1].Value
            Rename-Item -LiteralPath $_.FullName -NewName $newName
        }
    }

    Write-Host "Created: $pptxPath"
    Write-Host "Created: $pdfPath"
    Write-Host "Rendered slides: $renderDir"
} finally {
    if ($presentation -ne $null) {
        try { $presentation.Close() } catch {}
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    }
    if ($powerPoint -ne $null) {
        try { $powerPoint.Quit() } catch {}
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
