# Регистрация ежедневной Windows-задачи дрейф-контроля sync_check
# (PHASE 16 №67: §8.2 «запуск по требованию/cron» → закрыто).
#
# Использование:
#   .\tools\setup_sync_task.ps1                        # задача на 09:30
#   .\tools\setup_sync_task.ps1 -At 21:00              # своё время
#   .\tools\setup_sync_task.ps1 -SshPass '1234'        # сохранить SSH-пароль
#
# Пароль хранится ТОЛЬКО локально: %LOCALAPPDATA%\lan-discovery\ssh_pass.txt
# (вне репозитория, в git не попадает). Лог сверки:
# %LOCALAPPDATA%\lan-discovery\sync_check.log
param(
    [string]$At = '09:30',
    [string]$SshPass
)
$ErrorActionPreference = 'Stop'

$dir = Join-Path $env:LOCALAPPDATA 'lan-discovery'
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$passFile = Join-Path $dir 'ssh_pass.txt'
if ($SshPass) {
    Set-Content -Path $passFile -Value $SshPass -NoNewline -Encoding ASCII
    Write-Host "SSH-пароль сохранён: $passFile (вне репо)"
} elseif (-not (Test-Path $passFile)) {
    Write-Warning "Нет $passFile — запуск уйдёт в интерактивный ввод пароля и в задаче упадёт. Перезапустите с -SshPass."
}

$cmd = Join-Path $PSScriptRoot 'sync_check_daily.cmd'
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Parse($At))
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName 'LanDiscovery-SyncCheck' `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Дрейф-контроль repo (Lan-discovery-1.1) vs 192.168.3.243, ежедневно' `
    -Force | Out-Null

Write-Host "Задача LanDiscovery-SyncCheck зарегистрирована (ежедневно в $At, лог: $dir\sync_check.log)"
Write-Host "Запуск сразу: Start-ScheduledTask LanDiscovery-SyncCheck"
