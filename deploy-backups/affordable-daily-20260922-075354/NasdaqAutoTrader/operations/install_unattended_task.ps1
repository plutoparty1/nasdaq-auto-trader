param(
    [string]$ExecutablePath = "",
    [string]$TaskName = "NasdaqAutoTrader-Unattended",
    [switch]$DescribeOnly
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
    $ExecutablePath = Join-Path (Split-Path -Parent $PSScriptRoot) "NasdaqAutoTrader.exe"
}
$ExecutablePath = [IO.Path]::GetFullPath($ExecutablePath)
$WatchdogPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "ensure_unattended_running.ps1")
)
$HiddenLauncherPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "run_hidden.vbs")
)
$PowerShellPath = Join-Path $PSHOME "powershell.exe"
$WScriptPath = Join-Path $env:SystemRoot "System32\wscript.exe"
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$ActionArguments = (
    "//B //NoLogo `"$HiddenLauncherPath`" `"$PowerShellPath`" " +
    "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass " +
    "-File `"$WatchdogPath`" -ExecutablePath `"$ExecutablePath`""
)

$Descriptor = [ordered]@{
    task_name = $TaskName
    action = [ordered]@{
        executable = $WScriptPath
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
if (-not (Test-Path -LiteralPath $WatchdogPath -PathType Leaf)) {
    throw "Watchdog script was not found: $WatchdogPath"
}
if (-not (Test-Path -LiteralPath $HiddenLauncherPath -PathType Leaf)) {
    throw "Hidden launcher was not found: $HiddenLauncherPath"
}
if (-not (Test-Path -LiteralPath $WScriptPath -PathType Leaf)) {
    throw "Windows Script Host was not found: $WScriptPath"
}

$XmlUser = [Security.SecurityElement]::Escape($CurrentUser)
$XmlCommand = [Security.SecurityElement]::Escape($WScriptPath)
$XmlArguments = [Security.SecurityElement]::Escape($ActionArguments)
$StartBoundary = (Get-Date).Date.ToString("yyyy-MM-dd'T'HH:mm:ss")
$TaskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>NASDAQ market-aware unattended learning, trading, and reporting watchdog</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$XmlUser</UserId>
    </LogonTrigger>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <Duration>P1D</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$StartBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$XmlUser</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$XmlCommand</Command>
      <Arguments>$XmlArguments</Arguments>
    </Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskName $TaskName -Xml $TaskXml -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

$Registered = Get-ScheduledTask -TaskName $TaskName
[ordered]@{
    task_name = $Registered.TaskName
    state = $Registered.State.ToString()
    executable = $ExecutablePath
    watchdog = $WatchdogPath
} | ConvertTo-Json -Depth 3
