param(
    [switch]$IncludeEnv
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if ($IncludeEnv) {
    throw "-IncludeEnv is disabled: private credentials must not be packaged."
}

python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not available."
}

$UniverseSource = Join-Path $ProjectRoot "nasdaq_auto_trader\quant_data\defaults\nasdaq_100_universe.json"
$UniverseTarget = "nasdaq_auto_trader\quant_data\defaults"
if (-not (Test-Path $UniverseSource)) {
    throw "Bundled universe resource is missing: $UniverseSource"
}
$SpecText = Get-Content -LiteralPath (Join-Path $ProjectRoot "NasdaqAutoTrader.spec") -Raw
if (-not $SpecText.Contains("nasdaq_100_universe.json") -or -not $SpecText.Contains("quant_data")) {
    throw "NasdaqAutoTrader.spec does not include the universe resource contract."
}

python -m PyInstaller --noconfirm --clean NasdaqAutoTrader.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$DistRoot = Join-Path $ProjectRoot "dist"
$DistDir = Join-Path $ProjectRoot "dist\NasdaqAutoTrader"
$LegacyFiles = @(
    "NasdaqAutoTrader.exe",
    "config.kis.json",
    "config.example.json",
    "trading_config.json",
    ".env.example"
)
foreach ($File in $LegacyFiles) {
    $LegacyPath = Join-Path $DistRoot $File
    if (Test-Path $LegacyPath) {
        Remove-Item -LiteralPath $LegacyPath -Force
    }
}
$StaleToken = Join-Path $DistDir ".kis_token.json"
if (Test-Path $StaleToken) {
    Remove-Item -LiteralPath $StaleToken -Force
    Write-Host "Removed stale KIS token cache from dist."
}
$StaleTraderLog = Join-Path $DistDir "logs\trader.log"
if (Test-Path $StaleTraderLog) {
    Remove-Item -LiteralPath $StaleTraderLog -Force
    Write-Host "Removed stale GUI trader log from dist."
}
$StaleTradingConfig = Join-Path $DistDir "trading_config.json"
if (Test-Path $StaleTradingConfig) {
    Remove-Item -LiteralPath $StaleTradingConfig -Force
    Write-Host "Removed stale GUI trading settings from dist."
}
$LogsDir = Join-Path $DistDir "logs"
if ((Test-Path $LogsDir) -and -not (Get-ChildItem -LiteralPath $LogsDir -Force)) {
    Remove-Item -LiteralPath $LogsDir -Force
}
$DistEnv = Join-Path $DistDir ".env"
if (-not $IncludeEnv -and (Test-Path $DistEnv)) {
    Remove-Item -LiteralPath $DistEnv -Force
    Write-Host "Removed dist .env because -IncludeEnv was not used."
}

$FilesToCopy = @("config.kis.json", "config.example.json")
foreach ($File in $FilesToCopy) {
    $Source = Join-Path $ProjectRoot $File
    if (Test-Path $Source) {
        Copy-Item -LiteralPath $Source -Destination $DistDir -Force
    }
}

$OperationsDir = Join-Path $DistDir "operations"
New-Item -ItemType Directory -Path $OperationsDir -Force | Out-Null
$OperationalScripts = @(
    "ensure_unattended_running.ps1",
    "install_unattended_task.ps1"
)
foreach ($File in $OperationalScripts) {
    $Source = Join-Path $PSScriptRoot $File
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Operational script is missing: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination $OperationsDir -Force
}

$EnvExample = Join-Path $DistDir ".env.example"
@"
# Copy this template to %LOCALAPPDATA%\NasdaqAutoTrader\.env.
# Keep that file private. It can contain real broker API credentials.
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=
KIS_ACCOUNT_PRODUCT_CODE=01
KIS_ORDER_EXCHANGE_CODE=NASD
KIS_PRICE_EXCHANGE_CODE=NAS
KIS_CURRENCY=USD
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_DATA_FEED=iex
NASDAQ_AUTO_TRADER_ALLOW_LIVE=NO
"@ | Set-Content -LiteralPath $EnvExample -Encoding UTF8

$ProjectEnv = Join-Path $ProjectRoot ".env"
if (Test-Path $ProjectEnv) {
    Write-Host "Project .env was not copied. Put private credentials in %LOCALAPPDATA%\NasdaqAutoTrader\.env only when needed."
}

python -m nasdaq_auto_trader.package_audit $DistRoot
if ($LASTEXITCODE -ne 0) {
    throw "Private runtime artifacts were found in dist."
}

Write-Host "Built: $(Join-Path $DistDir 'NasdaqAutoTrader.exe')"
Write-Host "Copied editable broker/example config files to: $DistDir"
Write-Host "GUI settings are stored outside the exe folder: %LOCALAPPDATA%\NasdaqAutoTrader\trading_config.json"
