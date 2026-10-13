param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
    throw "NasdaqAutoTrader executable was not found: $ExecutablePath"
}

$resolvedExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path
$matchingProcess = Get-CimInstance -ClassName Win32_Process -Filter "Name = 'NasdaqAutoTrader.exe'" |
    Where-Object {
        $_.ExecutablePath -and
        [StringComparer]::OrdinalIgnoreCase.Equals($_.ExecutablePath, $resolvedExecutable) -and
        $_.CommandLine -notmatch '(?i)(^|\s)live-canary(\s|$)'
    } |
    Select-Object -First 1

if ($null -ne $matchingProcess) {
    exit 0
}

$workingDirectory = Split-Path -Parent $resolvedExecutable
$process = Start-Process -FilePath $resolvedExecutable -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru
$runtimeDirectory = Join-Path $env:LOCALAPPDATA "NasdaqAutoTrader\runtime"
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$line = "{0} watchdog_started pid={1}" -f (Get-Date).ToString("o"), $process.Id
Add-Content -LiteralPath (Join-Path $runtimeDirectory "watchdog.log") -Value $line -Encoding UTF8
