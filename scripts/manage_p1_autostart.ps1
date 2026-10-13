param([ValidateSet('Install','Remove','Status')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$TaskName = 'NasdaqAutoTrader-P1-Local-Startup-v1'
$TaskExecutable = Join-Path $PSHOME 'powershell.exe'
$Launcher = Join-Path $PSScriptRoot 'start_p1_trader.ps1'
$TaskArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '"'
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing -and (($Existing.Actions | Measure-Object).Count -ne 1 -or $Existing.Actions[0].Arguments -ne $TaskArguments -or $Existing.Actions[0].Execute -ne $TaskExecutable)) {
    throw 'Same-name task has different executable or arguments; it will not be replaced or removed.'
}
if ($Action -eq 'Status') {
    if ($Existing) { Write-Output 'P1 local startup registered. Live startup is not configured.' }
    else { Write-Output 'P1 startup is not registered.' }
    exit 0
}
if ($Action -eq 'Remove') {
    if ($Existing) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    Write-Output 'P1 startup removed; running programs and broker orders are not stopped.'
    exit 0
}
if ($Existing) { Write-Output 'P1 local startup already registered.'; exit 0 }
$UserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$TaskAction = New-ScheduledTaskAction -Execute $TaskExecutable -Argument $TaskArguments
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserName
$Principal = New-ScheduledTaskPrincipal -UserId $UserName -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'P1 local simulation dashboard only; never auto-starts KIS or live mode.' | Out-Null
Write-Output 'Registered for next logon only. Nothing was started now.'
