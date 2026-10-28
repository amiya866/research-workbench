# -*- coding: utf-8 -*-
"""生成日报/周报更新健康检查页。"""
import datetime
import html
import json
import os
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
OUT = BASE / 'reports' / 'update_health.html'
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def load(name, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding='utf-8'))
    except Exception:
        return default


def esc(value):
    return html.escape(str(value if value not in (None, '') else '—'))


def first_date(value):
    match = re.search(r'20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?', str(value or ''))
    return match.group(0).replace('T', ' ') if match else ''


def age_hours(value):
    stamp = first_date(value)
    if not stamp:
        return None
    try:
        parsed = datetime.datetime.strptime(stamp, '%Y-%m-%d %H:%M')
    except ValueError:
        parsed = datetime.datetime.strptime(stamp, '%Y-%m-%d')
    return (datetime.datetime.now() - parsed).total_seconds() / 3600


def task_status():
    if os.name != 'nt':
        return []
    command = '''$rows=foreach($n in @("RwBenchDaily","RwBenchQuick","RWXsAlignDaily","ResearchWeeklySync","ResearchQuarterlyOutlook")){
      $t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
      if($t){$i=$t|Get-ScheduledTaskInfo; [pscustomobject]@{name=$n;state=[string]$t.State;last=$i.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss");next=$i.NextRunTime.ToString("yyyy-MM-dd HH:mm:ss");result=$i.LastTaskResult}}
      else{[pscustomobject]@{name=$n;state="MISSING";last="";next="";result=-1}}
    }; $rows|ConvertTo-Json -Compress'''
    try:
        result = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=30, creationflags=NW)
        rows = json.loads(result.stdout)
        return rows if isinstance(rows, list) else [rows]
    except Exception:
        return []


def source_row(label, file, field='asof', limit=None, note=''):
    data = load(file, {})
    value = data.get(field, '') if isinstance(data, dict) else ''
    age = age_hours(value)
    status = 'ok'
    if not value:
        status = 'bad'
    elif limit is not None and age is not None and age > limit:
        status = 'warn'
    return {'label': label, 'value': value or '未读取', 'status': status,
            'note': note or (('距抓取 %.1f 小时' % age) if age is not None else '按发布频率更新')}


def main():
    rows = [
        source_row('实时行情', 'live_quotes.json', limit=4, note='RwBenchQuick 每2小时；页面打开时再拉取'),
        source_row('快讯消息', 'news_latest.json', limit=4, note='金十/CS/东财/新浪/LME；内嵌兜底同步刷新'),
        source_row('宏观序列与图表', 'macro_series.json', 'updated', 36, 'RwBenchDaily 全链'),
        source_row('美元流动性', 'liquidity.json', 'updated', 36, 'FRED/央行公开数据，按各自发布频率'),
        source_row('FedWatch', 'fedwatch.json', limit=36, note='CME官方条件概率表'),
        source_row('经济日历', 'econ_calendar.json', 'updated', 36, '公开日历与发布计划'),
        source_row('共识日历', 'calendar_consensus.json', limit=36, note='投行/机构一致预期'),
        source_row('CFTC持仓', 'cftc.json', 'updated', 36, '周度持仓，抓取时间不等于报告期'),
        source_row('新出数据', 'releases_recent.json', 'updated', 4, '快讯中识别的官方发布'),
        source_row('知识星球雷达', 'zsxq_radar.json', limit=4, note='方向/研报/观点快照'),
        source_row('预测市场', 'polymarket.json', 'fetched_at', 36, 'Polymarket公开行情'),
    ]
    downstream = load('downstream.json', {})
    hvac = downstream.get('hvac', {})
    rows.append({'label': '白电排产', 'value': hvac.get('period', '未读取'),
                 'status': 'ok' if hvac.get('period') else 'bad',
                 'note': '产业在线/Mysteel月度自动更新；内外销拆分与地产等L3腿仍是人工快照'})
    geo = load('geopolitics.json', {})
    geo_dates = [event[0] for line in geo.get('lines', []) for event in line.get('events', []) if event]
    latest_geo = max(geo_dates) if geo_dates else ''
    geo_age = age_hours(latest_geo)
    rows.append({'label': '地缘事件链', 'value': latest_geo or '未读取',
                 'status': 'ok' if geo_age is not None and geo_age <= 24 * 31 else 'warn',
                 'note': '全链扫描快讯标题自动追加；无新事件时不强行填日期'})
    release = load('release_panels.json', {})
    blocks = release.get('blocks', {})
    stale = [key for key, value in blocks.items() if isinstance(value, dict) and value.get('stale')]
    periods = {key: value.get('period') for key, value in blocks.items()
               if isinstance(value, dict) and value.get('period')}
    rows.append({'label': '官方发布分项', 'value': '；'.join('%s=%s' % item for item in periods.items()),
                 'status': 'bad' if stale else 'ok',
                 'note': ('旧值块：' + ','.join(stale)) if stale else 'BLS/BEA/CME 本次全部成功；月份不同是自然披露节奏'})
    for key, label in [('tin', '锡研究周报'), ('nickel', '镍研究周报'), ('zinc', '锌研究周报'), ('aluminum', '铝研究周报')]:
        data = load(key + '_weekly.json', {})
        rows.append({'label': label, 'value': data.get('asof', '未读取'),
                     'status': 'ok' if data.get('sync_status') == 'ok' else 'warn',
                     'note': '周五/六/日检查；季度展望仅季度最后一周刷新'})
    tasks = task_status()
    overall = '正常' if all(row['status'] == 'ok' for row in rows) else '有需要检查项'
    built = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    payload = {'built_at': built, 'overall': overall, 'rows': rows, 'tasks': tasks}
    (DATA / 'update_health.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    task_descriptions = {
        'RwBenchQuick': '每2小时：行情→快讯→新出数据→星球雷达；不生成报告、不部署',
        'RwBenchDaily': '每天07:40/20:40：完整宏观链→日报→品种点评→健康检查→部署',
        'RWXsAlignDaily': '交易日15:52：截面信号对齐→日报→部署',
        'ResearchWeeklySync': '周五/六/日09:23：锡→镍→锌→铝→日报→点评→健康检查→部署',
        'ResearchQuarterlyOutlook': '3/6/9/12月最后一个周五09:23：同周报链，允许刷新季度展望',
    }
    task_html = ''.join('<tr><td><b>%s</b><br><span class="muted">%s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        esc(task.get('name')), esc(task_descriptions.get(task.get('name'), '')), esc(task.get('state')),
        esc(task.get('last')), esc(task.get('next')), esc(task.get('result'))) for task in tasks)
    source_html = ''.join('<tr><td><b>%s</b><br><span class="muted">%s</span></td><td>%s</td><td><span class="badge %s">%s</span></td></tr>' % (
        esc(row['label']), esc(row['note']), esc(row['value']), row['status'],
        {'ok': '正常', 'warn': '关注', 'bad': '检查'}[row['status']]) for row in rows)
    page = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>研究站更新状态</title><style>
:root{--bg:#f2efeb;--card:#fff;--ink:#292c31;--muted:#73777f;--line:#ded9d2;--gold:#9b6a24}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 "Microsoft YaHei",sans-serif}.wrap{max-width:1180px;margin:auto;padding:28px 20px 60px}h1{margin:0;font-size:26px}h2{font-size:17px;margin:28px 0 10px}.muted{color:var(--muted);font-size:12px}.top{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0}.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.flow .card{margin:0}.flow b{color:var(--gold)}table{width:100%;border-collapse:collapse;background:var(--card);font-size:12px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#e9e4de}.badge{padding:2px 8px;border-radius:10px;white-space:nowrap}.ok{background:#e2f0e6;color:#267343}.warn{background:#fff0cf;color:#8a5c00}.bad{background:#fbe1df;color:#a52b25}a{color:#245e91}code{background:#e9e4de;padding:1px 5px;border-radius:4px}@media(max-width:760px){table{display:block;overflow-x:auto}.wrap{padding:18px 10px}}
</style></head><body><div class="wrap"><div class="top"><div><h1>研究站更新状态</h1><div class="muted">生成于 __BUILT__ · 总结：__OVERALL__</div></div><a href="daily_latest.html">← 返回宏观研究日报</a></div>
<div class="card"><b>你在日报看到的数据分三层：</b>①每2小时刷新的行情/快讯；②每天早晚两次刷新的宏观、日历、流动性与官方分项；③周五至周日检查的四品种周报。月度/季度指标显示上月或上季是披露节奏，不等于断更。</div>
<h2>一、自动更新流程</h2><div class="flow"><div class="card"><b>快刷链</b><br><code>scripts/fetch_live.py</code><br>→ 快讯/新出数据/星球雷达<br><span class="muted">只更新数据快照，不部署报告。</span></div><div class="card"><b>完整日更链</b><br><code>_refresh_all.py</code><br>→ 宏观/日历/官方分项<br>→ <code>_daily_report.py</code> + <code>_variety_review.py</code><br>→ 健康检查 → <code>_deploy_git.py</code></div><div class="card"><b>周报链</b><br><code>scripts/refresh_weekly_reports.py</code><br>→ 锡/镍/锌/铝 → 日报卡片<br>→ 健康检查 → 部署<br><span class="muted">周一至周四，全链自动跳过周报。</span></div></div>
<h2>二、数据新鲜度</h2><table><tr><th>模块 / 口径</th><th>最新数据时间或期间</th><th>状态</th></tr>__ROWS__</table>
<h2>三、Windows 定时任务</h2><table><tr><th>任务 / 职责</th><th>状态</th><th>最近运行</th><th>下次运行</th><th>最近返回码</th></tr>__TASKS__</table>
<h2>四、日志与排错</h2><div class="card">全链摘要：<code>_logs/last_run.txt</code>；全链明细：<code>_logs/refresh_*.log</code>；定时任务控制台：<code>_logs/daily_sync_task.log</code>；周报：<code>_logs/weekly_sync_task.log</code>。<br>页面数据文件：<code>data/update_health.json</code>。本页由 <code>scripts/build_update_health.py</code> 自动生成。</div>
<h2>五、哪些是历史快照，不是断更</h2><div class="card"><code>cs_snapshot.json</code>（2026-08-24 第三方EDB人工截面）与 <code>live_snapshot.js</code>（2026-09-02 手工快照）只作网络失败时的兜底/历史存档，页面已有标注。快讯内嵌兜底现已随每次快讯链更新，不再停在9月。</div>
</div></body></html>'''
    page = page.replace('__BUILT__', esc(built)).replace('__OVERALL__', esc(overall)).replace('__ROWS__', source_html).replace('__TASKS__', task_html)
    OUT.write_text(page, encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'overall': overall, 'sources': len(rows), 'tasks': len(tasks)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
