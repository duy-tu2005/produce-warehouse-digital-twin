[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://localhost:8080',
    [string]$ApiKey = $env:TB_API_KEY,
    [string]$Username = $env:TB_USERNAME,
    [string]$Password = $env:TB_PASSWORD,
    [string]$MqttHost = 'host.wokwi.internal'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SetupScript = Join-Path $PSScriptRoot 'setup.py'

$arguments = @($SetupScript, '--base-url', $BaseUrl, '--mqtt-host', $MqttHost)
if (-not [string]::IsNullOrWhiteSpace($ApiKey)) {
    $arguments += @('--api-key', $ApiKey)
} elseif (-not [string]::IsNullOrWhiteSpace($Username)) {
    $arguments += @('--username', $Username, '--password', $Password)
}

Push-Location $ProjectRoot
try {
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "ThingsBoard deployment failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

