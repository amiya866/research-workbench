$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $PSScriptRoot
$hidden = 'C:\Users\Yitian Shen\_task_wrappers\_hidden_run.vbs'
$python = (Get-Command pythonw.exe).Source
$script = Join-Path $base 'scripts\refresh_arbitrage_weekly.py'
$log = Join-Path $base '_logs\arbitrage_weekly_task.log'
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "//B `"$hidden`" `"$python`" `"$script`" `"$log`"" -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Saturday -At '10:27'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'ArbitrageWeeklySync' -Action $action -Trigger $trigger -Settings $settings -Description '有色套利周报：每周六10:27构建、健康检查并部署' -Force
