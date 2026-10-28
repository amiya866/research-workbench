$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $PSScriptRoot
$hidden = 'C:\Users\Yitian Shen\_task_wrappers\_hidden_run.vbs'
$python = (Get-Command pythonw.exe).Source
$script = Join-Path $base 'scripts\refresh_weekly_reports.py'
$log = Join-Path $base '_logs\weekly_sync_task.log'
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "//B `"$hidden`" `"$python`" `"$script`" `"$log`"" -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Friday,Saturday,Sunday -At '09:23'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'ResearchWeeklySync' -Action $action -Trigger $trigger -Settings $settings -Description '研究周报：每周五至周日检查更新' -Force
$quarterXml = @'
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>季度展望：每季度最后一个周五刷新</Description></RegistrationInfo>
  <Triggers><CalendarTrigger>
    <StartBoundary>2026-12-25T09:23:00</StartBoundary><Enabled>true</Enabled>
    <ScheduleByMonthDayOfWeek><DaysOfWeek><Friday /></DaysOfWeek><Weeks><Week>Last</Week></Weeks><Months><March /><June /><September /><December /></Months></ScheduleByMonthDayOfWeek>
  </CalendarTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><Enabled>true</Enabled><ExecutionTimeLimit>PT1H</ExecutionTimeLimit></Settings>
  <Actions Context="Author"><Exec><Command>wscript.exe</Command><Arguments>__ACTION_ARGS__</Arguments><WorkingDirectory>__WORK_DIR__</WorkingDirectory></Exec></Actions>
</Task>
'@
$actionArgs = "//B `"$hidden`" `"$python`" `"$script`" `"$log`""
$quarterXml = $quarterXml.Replace('__ACTION_ARGS__', [System.Security.SecurityElement]::Escape($actionArgs)).Replace('__WORK_DIR__', [System.Security.SecurityElement]::Escape($base))
$quarterXmlPath = Join-Path $env:TEMP 'research_quarterly_outlook.xml'
[System.IO.File]::WriteAllText($quarterXmlPath, $quarterXml, [System.Text.Encoding]::Unicode)
& schtasks.exe /Create /TN 'ResearchQuarterlyOutlook' /XML $quarterXmlPath /F
if ($LASTEXITCODE -ne 0) { throw "季度任务注册失败，退出码 $LASTEXITCODE" }
