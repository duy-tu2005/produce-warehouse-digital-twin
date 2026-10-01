$ErrorActionPreference = 'Stop'

$pioPath = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\pio.exe'
if (-not (Test-Path -LiteralPath $pioPath)) {
    throw "PlatformIO was not found at $pioPath"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildAlias = 'D:\produce_warehouse_fw'

if (Test-Path -LiteralPath $buildAlias) {
    $existing = Get-Item -LiteralPath $buildAlias
    if ($existing.LinkType -ne 'Junction' -or $existing.Target -ne $projectRoot) {
        throw "Build alias already exists and does not point to this firmware directory: $buildAlias"
    }
} else {
    New-Item -ItemType Junction -Path $buildAlias -Target $projectRoot | Out-Null
}

Push-Location $buildAlias
try {
    & $pioPath run
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

