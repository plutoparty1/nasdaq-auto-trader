@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage_p1_autostart.ps1" -Action Install
pause
