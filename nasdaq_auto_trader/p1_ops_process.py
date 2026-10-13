"""Cooperative shared locks plus a read-only legacy executable presence check."""
from __future__ import annotations

import os
import subprocess


def assert_no_legacy_process() -> None:
    if os.name != 'nt':
        return
    script = "$ErrorActionPreference='Stop'; $n=0; Get-CimInstance Win32_Process | ForEach-Object { if ($_.ProcessId -ne " + str(os.getpid()) + r") { if ($_.Name -like '*Nasdaq*Trader*.exe' -or ($_.Name -like 'python*' -and $_.CommandLine -match '(?i)(-m\s+nasdaq_auto_trader|live.canary.runner|run_trader_gui)')) { $n++ } } }; Write-Output $n"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    value = result.stdout.strip()
    if result.returncode or not value.isdecimal():
        raise ValueError('legacy_process_inspection_unavailable')
    if int(value):
        raise ValueError('legacy_trader_process_running_close_it_first')
