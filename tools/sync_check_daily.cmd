@echo off
REM Ежедневный дрейф-контроль: репозиторий (Lan-discovery-1.1) ^<-> X96.
REM Регистрация задачи: tools\setup_sync_task.ps1
REM Лог: %LOCALAPPDATA%\lan-discovery\sync_check.log
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "LOGDIR=%LOCALAPPDATA%\lan-discovery"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "PASSFILE=%LOGDIR%\ssh_pass.txt"
if exist "%PASSFILE%" set /p LAN_SSH_PASS=<"%PASSFILE%"
echo ==== %date% %time% ==== >> "%LOGDIR%\sync_check.log"
python -X utf8 "tools\sync_check.py" >> "%LOGDIR%\sync_check.log" 2>&1
echo exit=%errorlevel% >> "%LOGDIR%\sync_check.log"
