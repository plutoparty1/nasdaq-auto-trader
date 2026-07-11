$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
$ConfigPath = Join-Path $PSScriptRoot "config.kis.json"
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot "config.example.json"
}

python -m nasdaq_auto_trader --config $ConfigPath gui
