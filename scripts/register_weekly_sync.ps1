$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $PSScriptRoot
$hidden = 'C:\Users\Yitian Shen\_task_wrappers\_hidden_run.vbs'
$python = (Get-Command pythonw.exe).Source
$script = Join-Path $base 'scripts\refresh_weekly_reports.py'
$log = Join-Path $base '_logs\weekly_sync_task.log'
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "//B `"$hidden`" `"$python`" `"$script`" `"$log`"" -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -Daily -At '09:23'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'ResearchWeeklySync' -Action $action -Trigger $trigger -Settings $settings -Description '研究周报独立更新：锡同步、镍重建、日报与部署' -Force
