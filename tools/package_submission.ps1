param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputPath = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'Nop_bai_Digital_Twin_Kho_Bao_Quan_Rau_Qua.zip')
)

$ErrorActionPreference = 'Stop'

$root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$output = [System.IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw "Project root does not exist: $root"
}

$forbiddenExact = @(
    '.env.local',
    'firmware/secrets.h',
    'thingsboard/.env.local'
)

$files = Get-ChildItem -LiteralPath $root -File -Recurse | Where-Object {
    $relative = $_.FullName.Substring($root.Length + 1).Replace('\', '/')
    $partsExcluded = $relative -match '(^|/)(\.git|\.pio|\.runtime|\.rendered|rendered|__pycache__|node_modules)(/|$)'
    $nameExcluded = $forbiddenExact -contains $relative
    $extensionExcluded = $_.Extension -in @('.log', '.tmp', '.bak', '.pyc')
    $selfExcluded = [System.IO.Path]::GetFullPath($_.FullName) -eq $output
    -not ($partsExcluded -or $nameExcluded -or $extensionExcluded -or $selfExcluded)
} | Sort-Object FullName

if ($files.Count -lt 20) {
    throw "Unexpectedly small package input: $($files.Count) files"
}

$required = @(
    'README.md',
    'firmware/sketch.ino',
    'thingsboard/setup.py',
    'tests/results/metrics.json',
    'tests/results/stability-metrics.json',
    'report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.docx',
    'report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf',
    'slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pptx',
    'slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf'
)

$relativeFiles = $files | ForEach-Object { $_.FullName.Substring($root.Length + 1).Replace('\', '/') }
foreach ($item in $required) {
    if ($relativeFiles -notcontains $item) {
        throw "Required submission file is missing: $item"
    }
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$outputDir = Split-Path -Parent $output
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$stream = [System.IO.File]::Open($output, [System.IO.FileMode]::Create, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
try {
    $archive = New-Object System.IO.Compression.ZipArchive($stream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($root.Length + 1).Replace('\', '/')
            $entryName = "produce-warehouse-digital-twin/$relative"
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $entryStream = $entry.Open()
            $sourceStream = [System.IO.File]::OpenRead($file.FullName)
            try {
                $sourceStream.CopyTo($entryStream)
            } finally {
                $sourceStream.Dispose()
                $entryStream.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
    }
} finally {
    $stream.Dispose()
}

$zipInfo = Get-Item -LiteralPath $output
Write-Host "Package created: $($zipInfo.FullName)"
Write-Host "Included files: $($files.Count)"
Write-Host "ZIP size: $([math]::Round($zipInfo.Length / 1MB, 2)) MB"

