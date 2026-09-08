param(
    [string]$ExecutablePath = "",
    [string]$ConfigPath = "",
    [string]$TaskName = "NasdaqAutoTrader-LiveCanary",
    [switch]$DescribeOnly
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
    $ExecutablePath = Join-Path (Split-Path -Parent $PSScriptRoot) "NasdaqAutoTrader.exe"
}
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path (Split-Path -Parent $PSScriptRoot) "config.kis.json"
}
$ExecutablePath = [IO.Path]::GetFullPath($ExecutablePath)
$ConfigPath = [IO.Path]::GetFullPath($ConfigPath)
$WatchdogPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "ensure_live_canary_running.ps1")
)
$PowerShellPath = Join-Path $PSHOME "powershell.exe"
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$ActionArguments = (
    "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass " +
    "-File `"$WatchdogPath`" -ExecutablePath `"$ExecutablePath`" " +
    "-ConfigPath `"$ConfigPath`""
)

$Descriptor = [ordered]@{
    task_name = $TaskName
    action = [ordered]@{
        executable = $PowerShellPath
        arguments = $ActionArguments
    }
    triggers = @("AtLogOn", "Daily/PT5M")
    principal = [ordered]@{
        user_id = $CurrentUser
        logon_type = "InteractiveToken"
        run_level = "Limited"
    }
    settings = [ordered]@{
        multiple_instances = "IgnoreNew"
        start_when_available = $true
        execution_time_limit_minutes = 2
    }
}

if ($DescribeOnly) {
    $Descriptor | ConvertTo-Json -Depth 4
    exit 0
}

if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
    throw "NasdaqAutoTrader executable was not found: $ExecutablePath"
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "NasdaqAutoTrader config was not found: $ConfigPath"
}
if (-not (Test-Path -LiteralPath $WatchdogPath -PathType Leaf)) {
    throw "Live canary watchdog was not found: $WatchdogPath"
}

$AppDataRoot = Join-Path $env:LOCALAPPDATA "NasdaqAutoTrader"
New-Item -ItemType Directory -Path $AppDataRoot -Force | Out-Null
& icacls.exe $AppDataRoot /inheritance:r /grant:r "${CurrentUser}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to apply private NasdaqAutoTrader ACL."
}
& icacls.exe (Join-Path $AppDataRoot "*") /reset /T | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to reset descendant NasdaqAutoTrader ACLs."
}

$XmlUser = [Security.SecurityElement]::Escape($CurrentUser)
$XmlCommand = [Security.SecurityElement]::Escape($PowerShellPath)
$XmlArguments = [Security.SecurityElement]::Escape($ActionArguments)
$StartBoundary = (Get-Date).Date.ToString("yyyy-MM-dd'T'HH:mm:ss")
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>One-day bounded KIS live canary watchdog</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>$XmlUser</UserId></LogonTrigger>
    <CalendarTrigger>
      <Repetition><Interval>PT5M</Interval><Duration>P1D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>$StartBoundary</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>$XmlUser</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled><Hidden>false</Hidden><ExecutionTimeLimit>PT2M</ExecutionTimeLimit><Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>$XmlCommand</Command><Arguments>$XmlArguments</Arguments></Exec></Actions>
</Task>
"@
Register-ScheduledTask -TaskName $TaskName -Xml $TaskXml -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

$Registered = Get-ScheduledTask -TaskName $TaskName
[ordered]@{
    task_name = $Registered.TaskName
    state = $Registered.State.ToString()
    executable = $ExecutablePath
    config = $ConfigPath
    watchdog = $WatchdogPath
} | ConvertTo-Json -Depth 3
