@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
pwsh -NoLogo -ExecutionPolicy Bypass -File "%SCRIPT_DIR%route_pc_auto.ps1" apply
pause
