# -*- coding: utf-8 -*-
"""把原版锡周报与 tin-insight 快照重组为与镍同结构的每周研究页面。"""
import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import build_nickel_weekly as shared

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'tin-weekly'
UPSTREAM = OUT / 'upstream.html'
CHART_JS = OUT / 'charts_full' / 'weekly_inter.js'
META = BASE / 'data' / 'tin_weekly_freshness.json'
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
SHFE_CSV = Path(r'D:/Kimi/有色截面配置_2026/_价格缓存.csv')
BALANCE_CONFIG = {
    'title': '年度平衡与2027策略：2026短暂过剩，2027重回紧平衡',
    'rows': [
        ('2026E', '38.10万吨（+2.7%）', '37.62万吨（-0.7%）', '+0.48', '小幅过剩，阶段空配'),
        ('2027E', '38.75万吨（+1.7%）', '38.90万吨（+3.4%）', '-0.15', '紧平衡，不做长期空配'),
    ],
    'regional': '2026过剩依赖缅甸缓慢复产、Bisie满产和高价抑制消费；2027需求恢复后重新小幅短缺。平衡量不足全球市场0.5%，佤邦、印尼政策或刚果金扰动都可能改变方向。',
    'source': '来源：Loyan AI 2026-06-19二次研究（综合ITA、CRU、USGS及公开数据），不是ITA官方平衡表；WBMS 2026-06单月短缺0.36万吨用于交叉验证。预测不是实际值。',
    'strategy': [
        '方向：2026小幅过剩只支持阶段空配；2027重回紧平衡，不套用其他有色的长期做空策略，回调后更应关注供给扰动带来的多头弹性。',
        '入场：空配仅限库存连续回升、LME Back走弱或转Contango、缅甸进口恢复且价格反弹衰竭时；低库存和供应扰动急涨期不追空。',
        '风控：若佤邦复产再推迟、印尼出口收紧、Bisie停产或全球显性库存重新连续下降，停止空配；锡市场小、波动大，仓位应低于铜铝。',
        '止盈/失效：阶段回落6%—10%分批兑现；若2027平衡转为明显过剩才考虑中期空配，否则回调到成本与库存支撑区后转为观察多头机会。',
    ],
    'drivers': [
        '供应恢复：缅甸佤邦缓慢复产、Alphamin Bisie满产是2026再平衡主因；恢复不及预期会立即压缩过剩。',
        '需求节奏：2026高价和光伏走弱压制消费，2027AI电子、光伏与传统电子恢复使需求重新超过供应。',
        '验证指标：缅甸矿进口、印尼出口、LME+SHFE库存、LME 0-3和焊料开工必须同向确认，不能只看年度点估计。',
    ],
}

MODULES = [
    ('sumsec', '本周总结', '总览', []),
    ('price', '价格与结构', '总览', ['价格与现货']),
    ('supply_mine', '矿端与进口', '重点关注/供给', ['供给 · 矿端', '进出口']),
    ('supply_smelt', '冶炼与精锡', '重点关注/供给', ['供给 · 冶炼']),
    ('inventory', '显性库存', '重点关注/供给', ['库存']),
    ('demand_solder', '焊料/电子/新能源', '重点关注/需求', ['需求 · 焊料', '需求 · 终端耗锡', '终端 · 电子', '终端 · 白电', '需求 · 光伏/家电/汽车/电子', '终端 · 光伏', 'AI · 半导体', '终端 · 半导体']),
    ('demand_chemical', '锡化工/镀锡板/铅酸', '重点关注/需求', ['需求 · 锡化工', '需求 · 其他下游', '终端 · 锡化工/玻璃', '终端 · 镀锡板', '需求 · 铅蓄电池', '终端 · 铅蓄电池']),
    ('cost', '成本与平衡', '平衡表', ['平衡']),
    ('balance', '年度平衡与2027策略', '平衡表', []),
    ('detailed', '详细周报', '详细周报', ['详细周报']),
    ('framework', '产业框架', '总览', []),
    ('technical', '技术分析', '宏观与策略', []),
    ('sources', '数据缺口', '总览', []),
]
NAV_TITLES = {key: value['title'] for key, value in []}


def clean(fragment):
    return re.sub(r'\s+', ' ', shared.esc(re.sub(r'<[^>]+>', '', fragment)).replace('&amp;', '&')).strip()


def text(fragment):
    import html
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', fragment))).strip()


def one(pattern, source, fallback=''):
    match = re.search(pattern, source, re.S | re.I)
    return match.group(1) if match else fallback


def shfe_values():
    import csv
    values = []
    with open(SHFE_CSV, encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            value = row.get('SN')
            if value not in (None, ''):
                values.append(float(value))
    if not values:
        raise RuntimeError('沪锡行情为空，保留上一成功版并中止年度平衡重建')
    return values


def ordinal(value):
    if value < 1900:
        return str(value)
    if value <= 2100:
        return str(int(value))
    return (datetime.date(1970, 1, 1) + datetime.timedelta(days=int(value))).isoformat()


def convert_chart(key, chart):
    kind = chart.get('type', 'line')
    if kind == 'pie':
        return {'labels': chart.get('labels') or [], 'datasets': [{
            'label': '占比', 'data': chart.get('values') or [],
            'backgroundColor': chart.get('colors') or ['#1F4E79', '#C00000', '#A6A6A6', '#8FAADC', '#C55A11'],
        }], '_type': 'pie'}
    labels = chart.get('labels')
    points = sorted({p[0] for series in chart.get('series', []) for p in (series.get('pts') or [])})
    if labels is None:
        labels = [ordinal(x) if isinstance(x, (int, float)) else str(x) for x in points]
    datasets = []
    for series in chart.get('series', []):
        if 'values' in series:
            values = series['values']
        else:
            lookup = {p[0]: p[1] for p in series.get('pts') or []}
            values = [lookup.get(p) for p in points]
        datasets.append({
            'label': series.get('name', key), 'data': values,
            'borderColor': series.get('color') or '#1F4E79',
            'backgroundColor': series.get('color') or '#1F4E79',
            'type': 'bar' if series.get('kind') == 'bar' or kind == 'cat' else 'line',
            'yAxisID': series.get('axis', 'y'), 'borderWidth': 1.6,
        })
    return {'labels': labels, 'datasets': datasets, '_type': kind}


def common_summary(source):
    table = one(r'(<table class="sum">.*?</table>)', source)
    result = {}
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(cells) >= 5 and text(cells[0]) in ('宏观', '美股·半导体 AI'):
            result[text(cells[0])] = {'datum': text(cells[1]) + ' ' + text(cells[2]), 'conclusion': text(cells[3])}
    return result


def summary_table(source):
    table = one(r'(<table class="sum">.*?</table>)', source)
    rows = ['<table class="sum"><tr><th>环节</th><th>相关数据与边际</th><th>周度结论</th><th>跟踪</th></tr>']
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(cells) < 5 or text(cells[0]) in ('宏观', '美股·半导体 AI'):
            continue
        label, datum, daily, conclusion, direction = cells[:5]
        direction_text = text(direction)
        cls = 'up' if '多' in direction_text or '利' in direction_text else ('dn' if '空' in direction_text else 'nt')
        rows.append('<tr><td class="c">%s</td><td>%s<br><span class="src-note">%s</span></td><td>%s</td><td><span class="dir %s">%s</span></td></tr>' % (
            label, datum, daily, conclusion, cls, direction))
    rows.append('</table>')
    return ''.join(rows)


def update_nonferrous_daily(common_charts, common_rows, names, asof):
    path = BASE / 'reports' / 'daily_latest.html'
    if not path.exists():
        return
    begin, end = '<!-- NONFERROUS_COMMON_BEGIN -->', '<!-- NONFERROUS_COMMON_END -->'
    sections = [
        ('宏观与跨资产', '宏观', ['c_cpi.png', 'c_us10y.png', 'c_dxy.png', 'c_wti.png', 'c_cusn.png', 'c_agsn.png'],
         '利率、美元、油价与地缘是全部有色共同的风险预算和估值约束；方向仍须回到各品种库存、升贴水和供需验证。'),
        ('美股与半导体 AI', '美股·半导体 AI', ['m_sox.png'],
         'SOX与AI财报影响电子需求预期及风险偏好：对锡焊料传导更直接，对铜铝等其他有色主要通过宏观情绪与资本开支预期传导，不等同于实际订单。'),
    ]
    payload = {}
    parts = [begin, '<div class="card" id="nonferrousCommon" style="border-left:3px solid var(--blue);margin:14px 0;">',
             '<h3 style="color:var(--blue);margin-bottom:6px;">有色共性前瞻 · 宏观与美股</h3>',
             '<p style="font-size:12px;color:var(--dim);">由锡周报迁入，作为铜/铝/锌/镍/锡/铅共用宏观层；不再占用单品种周报目录。数据截至 %s。</p>' % shared.esc(asof)]
    for title, row_key, keys, implication in sections:
        row = common_rows.get(row_key) or {}
        parts.append('<h4 style="color:var(--gold);margin:14px 0 5px;">%s</h4>' % shared.esc(title))
        if row.get('datum'):
            parts.append('<p style="font-size:12.5px;line-height:1.8;"><b>前瞻事件与事实：</b>%s</p>' % shared.esc(row['datum']))
        parts.append('<p style="font-size:12.5px;line-height:1.8;"><b>共性策略含义：</b>%s</p>' % shared.esc(implication))
        parts.append('<div class="grid2">')
        for key in keys:
            chart = common_charts.get(key)
            if not chart:
                continue
            payload[key] = chart
            point = shared.last_point(chart)
            chart_id = 'nfCommon' + str(len(payload))
            parts.append('<div class="mini"><h4>%s</h4><div id="%s" data-nf-chart="%s" style="height:220px;"></div><div style="font-size:11px;color:var(--dim);">最新 %s ｜ %s</div></div>' % (
                shared.esc(names.get(key, key)), chart_id, shared.esc(key),
                shared.esc(point[0] if point else '—'), shared.fmt(point[1]) if point else '—'))
        parts.append('</div>')
    parts.append('</div>')
    parts.append('<script>window.NF_COMMON_CHARTS=%s;(function(){const charts={};function draw(){document.querySelectorAll("[data-nf-chart]").forEach(function(el){if(!el.offsetParent)return;const c=window.NF_COMMON_CHARTS[el.dataset.nfChart];if(!c)return;const chart=charts[el.id]||(charts[el.id]=echarts.init(el));chart.setOption({animation:false,grid:{left:55,right:16,top:20,bottom:42},tooltip:{trigger:"axis"},xAxis:{type:"category",data:c.labels||[],axisLabel:{fontSize:10}},yAxis:{type:"value",scale:true},series:(c.datasets||[]).map(function(d){return{name:d.label,type:"line",data:d.data||[],showSymbol:false,connectNulls:true,lineStyle:{width:1.5}}})},true);chart.resize();});}window.addEventListener("resize",draw);document.querySelectorAll(".dtabs button").forEach(function(btn){btn.addEventListener("click",function(){setTimeout(draw,50);});});draw();})();</script>' % json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    parts.append(end)
    block = '\n'.join(parts)
    page = path.read_text(encoding='utf-8')
    pattern = re.escape(begin) + r'.*?' + re.escape(end)
    if re.search(pattern, page, re.S):
        page = re.sub(pattern, lambda _m: block, page, count=1, flags=re.S)
    else:
        anchor = '<section class="dp on" id="dp1">'
        if anchor not in page:
            raise RuntimeError('daily_latest.html 缺少总览页锚点')
        page = page.replace(anchor, anchor + '\n' + block, 1)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(page, encoding='utf-8')
    os.replace(tmp, path)


def sync_technical():
    target = OUT / 'technical.json'
    url = 'https://amiya866.github.io/tin-insight/technical.json?t=' + str(int(datetime.datetime.now().timestamp()))
    p = subprocess.run(['curl', '-fsSL', '--proxy', os.environ.get('RW_PROXY', 'http://127.0.0.1:7897'),
                        '--max-time', '45', url], capture_output=True, timeout=60, creationflags=NW)
    if p.returncode == 0:
        try:
            data = json.loads(p.stdout)
            if data.get('tech') and data.get('kline'):
                target.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                return data
        except Exception:
            pass
    if target.exists():
        return json.loads(target.read_text(encoding='utf-8'))
    fallback = Path(r'C:/Users/Yitian Shen/tin-insight-amiya866/technical.json')
    if fallback.exists():
        data = json.loads(fallback.read_text(encoding='utf-8'))
        target.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return data
    return {}


def main():
    source = UPSTREAM.read_text(encoding='utf-8')
    chart_script = CHART_JS.read_text(encoding='utf-8')
    raw_charts = json.loads(chart_script[chart_script.index('=') + 1:].rstrip().rstrip(';'))
    raw_charts = {key: value for key, value in raw_charts.items() if key != 'i_shfew.png'}
    converted = {key: convert_chart(key, value) for key, value in raw_charts.items()}
    common_keys = {key for key, value in raw_charts.items()
                   if value.get('sec') == '宏观 · 利率美元商品' or key == 'm_sox.png'}
    common_charts = {key: converted[key] for key in common_keys}
    charts = shared.seasonalize_charts({key: value for key, value in converted.items() if key not in common_keys})
    names = {key: value.get('title', key) for key, value in raw_charts.items()}
    shared.NAMES = names
    source_meta = {key: {'type': '原版锡周报', 'formula': value.get('sec', '详细周报')}
                   for key, value in raw_charts.items() if key not in common_keys}
    built = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    shared.SECTIONS = MODULES
    data = {'charts': charts, 'sourceMeta': {'charts': source_meta}, 'meta': {'builtAt': built, 'warnings': [], 'emptyCharts': []}}
    freshness = shared.build_freshness(data)
    META.write_text(json.dumps(freshness, ensure_ascii=False, indent=2), encoding='utf-8')
    technical = sync_technical()
    headline = text(one(r'<div class="tone">(.*?)</div>', source))
    asof = one(r'数据截至\s*<b>(\d{4}-\d{2}-\d{2})</b>', source, datetime.date.today().isoformat())
    update_nonferrous_daily(common_charts, common_summary(source), names, asof)
    summary = summary_table(source)
    quarter = shared.quarterly_html(OUT / 'index.html', one(r'(<details class="fold" id="q4outlook">.*?</details>)', source))
    framework = one(r'(<details class="fold" id="framework">.*?</details>)', source)
    balance = one(r'(<details class="fold" id="balance">.*?</details>)', source)
    price_values = shfe_values()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'lib').mkdir(exist_ok=True)
    for name in ('research.css', 'weekly_mobile.css', 'weekly_polish.css', 'weekly_mobile.js'):
        shutil.copyfile(BASE / 'nickel-weekly' / name, OUT / name)
    shutil.copyfile(BASE / 'nickel-weekly' / 'lib' / 'chart.min.js', OUT / 'lib' / 'chart.min.js')
    shutil.copyfile(BASE / 'scripts' / 'tin_weekly_research.js', OUT / 'research.js')
    base_css = re.search(r'<style>(.*?)</style>', source, re.S).group(1)

    parts = []
    for sid, title, trail, secs in MODULES:
        parts.append('<section class="report-page" data-page="%s" data-trail="%s"><div class="page-heading"><h2>%s</h2><span>%s</span></div><div class="page-body">' % (
            sid, shared.esc(trail), shared.esc(title), shared.esc(trail.replace('/', ' / ').upper())))
        if sid in ('sumsec', 'balance'):
            parts.append(shared.forecast_balance_html(BALANCE_CONFIG, price_values, full=(sid == 'balance')))
        if sid == 'sumsec':
            parts.append('<div class="tone"><b>%s</b></div>' % shared.esc(headline))
            parts.append('<div class="roll">策略每日滚动更新：周报为周五存档，最新决策见日报页。使用左侧目录切换研究内容。</div>')
            parts.append(quarter)
            parts.append('<div id="sumsec"><h2>总结<span class="en">SUMMARY</span></h2>%s</div>' % summary)
            parts.append('<footer>数据更新至 %s ｜ 原版周报 × 锡息相关 ｜ 仅供研究参考。</footer>' % shared.esc(asof))
        elif sid == 'framework':
            parts.append(framework)
        elif sid == 'cost':
            parts.append(balance)
            keys = [key for key, value in raw_charts.items() if value.get('sec') in secs]
            parts.append('<div class="lead">平衡图表 · 实绩与预测分列</div>')
            parts.append(shared.chart_group(charts, keys))
        elif sid == 'technical':
            parts.append('''<div class="tech-intro"><p>道氏趋势 / 均线 / MACD / 缠论简化结构 / 江恩区间</p><span class="tag" id="techUpdated">读取技术快照…</span></div><div class="tech-grid" id="techGrid"></div><div class="tech-note"><b>解释边界：</b>技术分析来自 tin-insight 静态快照，仅作研究参考，不作为确定性买卖信号。</div><div class="kline-card"><h3>沪锡主连｜日 K 价格与均线</h3><div class="meta-line" id="techMeta">MA5 / MA10 / MA20 / MA60 / MA288 · 红涨绿跌</div><div class="kline-chart"><canvas id="snKline" aria-label="沪锡主连日 K 图"></canvas></div></div>''')
        elif sid == 'sources':
            summary_counts = freshness['summary']
            parts.append('<details class="fold" id="datagap" open><summary>数据口径、缺口与新鲜度（%d项全量审计）</summary><div class="foldbody">' % summary_counts['total'])
            parts.append('<div class="fresh-grid">')
            for code, label in [('fresh', '正常'), ('watch', '关注'), ('stale', '滞后'), ('missing', '缺失'), ('review', '待核')]:
                parts.append('<button type="button" class="fresh-kpi %s" data-filter="%s"><span>%s</span><strong>%d</strong><small>点击筛选</small></button>' % (code, code, label, summary_counts[code]))
            parts.append('<button type="button" class="fresh-kpi total" data-filter="all"><span>全部指标</span><strong>%d</strong><small>重置筛选</small></button></div>' % summary_counts['total'])
            parts.append('<p>数据来源：原版锡周报 weekly_inter.js、原版正文与 tin-insight 技术快照。日度 7/14 天、周度 10/21 天、月度 45/75 天、季度 150/240 天为正常/关注阈值；分类、饼图和无法映射日期的标签进入待核，不硬猜日期。</p></div></details>')
            parts.append('<div class="fresh-legend">当前显示 <b id="freshCount">%d</b> / %d 项｜点击上方卡片筛选</div>' % (summary_counts['total'], summary_counts['total']))
            parts.append('<div class="tablewrap"><table class="bal fresh-table"><tr><th>模块/指标</th><th>来源</th><th>频率</th><th>单位</th><th>最新标签/值</th><th>新鲜度</th><th>处理</th></tr>')
            for row in freshness['rows']:
                age = '，%d天' % row['age_days'] if row['age_days'] is not None else ''
                parts.append('<tr data-fresh="%s"><td><b>%s</b><br><span class="src-note">%s｜%s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s<br><span class="src-note">%s%s</span></td><td><span class="fresh-badge %s">%s</span></td><td>%s</td></tr>' % (
                    row['status'], shared.esc(row['name']), shared.esc(row['module']), shared.esc(row['key']), shared.esc(row['source']),
                    shared.esc(row['frequency']), shared.esc(row['unit']), shared.esc(row['latest']), shared.esc(row['latest_value']), shared.esc(age),
                    row['status'], shared.esc(row['status_label']), shared.esc(row['action'])))
            parts.append('</table></div>')
        else:
            keys = [key for key, value in raw_charts.items() if value.get('sec') in secs]
            if sid == 'price' and 'm_lme3m.png' in charts:
                keys.append('m_lme3m.png')
            parts.append('<div class="lead">%s · 最新读数逐项标注日期</div>' % shared.esc(title))
            parts.append(shared.chart_group(charts, keys))
        parts.append('</div></section>')

    payload = json.dumps(charts, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    doc = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><link href="data:," rel="icon">
<title>研究周报 · 锡</title><style>__BASE_CSS__</style><link href="weekly_mobile.css" rel="stylesheet"><link href="weekly_polish.css" rel="stylesheet"><link href="research.css" rel="stylesheet"><link href="../weekly-light.css" rel="stylesheet"><style>.chart-box{height:240px;position:relative}.chart-box canvas{display:block;width:100%;height:100%}.tablewrap{overflow-x:auto}.page-body p{font-size:14.5px}.cbox .stats{line-height:1.55}.fresh-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin:12px 0}.fresh-kpi{border:1px solid var(--line);background:var(--cardbg);padding:10px;text-align:left;cursor:pointer}.fresh-kpi span,.fresh-kpi small{display:block;color:var(--faint);font-size:11px}.fresh-kpi strong{display:block;font-size:25px}.fresh-kpi.fresh strong{color:#188865}.fresh-kpi.watch strong{color:#a3760e}.fresh-kpi.stale strong,.fresh-kpi.missing strong{color:#c44b5d}.fresh-kpi.review strong{color:#7c4dff}.fresh-kpi.active{outline:2px solid var(--blue);outline-offset:1px}.fresh-legend{margin:12px 0;color:var(--grey);font-size:13px}.fresh-badge{display:inline-block;padding:1px 7px;border:1px solid var(--line);white-space:nowrap}.fresh-badge.fresh{color:#188865}.fresh-badge.watch{color:#a3760e}.fresh-badge.stale,.fresh-badge.missing{color:#c44b5d}.fresh-badge.review{color:#7c4dff}.src-note{color:var(--faint);font-size:11px}.fresh-table{min-width:1080px}.fresh-table td{vertical-align:top}@media(max-width:900px){.fresh-grid{grid-template-columns:repeat(3,1fr)}}</style></head>
<body><header class="research-topbar"><div class="research-brand"><a aria-label="返回整合研究站" class="back-home" href="../index.html">← 整合研究站</a><div class="brand-copy"><p class="research-eyebrow">COMMODITY WEEKLY RESEARCH · TIN</p><h1>研究周报 <span class="commodity-current">锡</span></h1><p>原版周报 × 锡息相关 · 供需平衡 · 技术分析 · 数据治理</p></div></div><div class="research-actions"><nav class="commodity-switch" aria-label="品种切换"><a class="active" href="#sumsec">锡</a><a href="../nickel-weekly/#sumsec">镍</a><a href="../zinc-weekly/#sumsec">锌</a><a href="../aluminum-weekly/#sumsec">铝</a><a href="../copper-weekly/#sumsec">铜</a><a href="../lead-weekly/#sumsec">铅</a></nav><a class="back-home" href="https://amiya866.github.io/tin-insight/" target="_blank" rel="noopener">锡息相关 ↗</a><span class="research-stamp">数据截至 <b>__ASOF__</b></span><button aria-pressed="false" class="view-toggle" id="viewToggle" type="button">切换手机版</button></div></header>
<div class="research-workspace"><aside class="research-sidebar top-navigation" id="researchSidebar"><button aria-controls="treeNav" aria-expanded="false" class="menu-toggle" id="menuToggle" type="button">研究目录 <span>＋</span></button><div class="sidebar-heading"><span>RESEARCH INDEX</span><b>研究目录</b></div><nav aria-label="锡研究分层目录" class="tree-nav top-nav-inner" id="treeNav"></nav></aside><div class="research-content"><div aria-live="polite" class="breadcrumb" id="breadcrumb"></div><div class="wrap" id="reportWrap">__SECTIONS__</div><section aria-live="polite" class="tool-page" hidden id="toolPage"><div class="tool-head"><div><p class="research-eyebrow">RESEARCH WORKBENCH</p><h2 id="toolTitle">研究工作台</h2></div><button id="closeTool" type="button">← 返回周报</button></div><iframe hidden id="toolFrame" title="锡研究工作台"></iframe></section></div></div>
<script src="lib/chart.min.js"></script><script>const charts=__PAYLOAD__;document.querySelectorAll('canvas[data-chart]').forEach(function(canvas){
  const c=charts[canvas.dataset.chart];if(!c)return;
  const ds=(c.datasets||[]).map(function(d){return Object.assign({borderWidth:1.5,pointRadius:0,spanGaps:true},d);});
  const cfg={
    type:c._type==='pie'?'pie':'line',
    data:{labels:c.labels||[],datasets:ds},
    options:{
      responsive:true,maintainAspectRatio:false,animation:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{position:'bottom',labels:{boxWidth:12,font:{family:'KaiTi,"楷体",serif',size:10}}}},
      scales:{x:{ticks:{maxTicksLimit:8,font:{family:'KaiTi,"楷体",serif',size:10}},grid:{color:'#e3e3e3'}},y:{ticks:{font:{family:'KaiTi,"楷体",serif',size:10}},grid:{color:'#e3e3e3'}},y2:{display:false}}
    }
  };
  new Chart(canvas,cfg);
});</script><script>window.TIN_TECHNICAL=__TECHNICAL__;</script><script src="weekly_mobile.js"></script><script src="research.js"></script><script>document.querySelectorAll('.fresh-kpi').forEach(function(btn){btn.addEventListener('click',function(){const code=btn.dataset.filter;let shown=0;document.querySelectorAll('.fresh-kpi').forEach(function(x){x.classList.toggle('active',x===btn)});document.querySelectorAll('tr[data-fresh]').forEach(function(row){const visible=code==='all'||row.dataset.fresh===code;row.hidden=!visible;if(visible)shown++});document.getElementById('freshCount').textContent=shown})});</script></body></html>'''
    technical_payload = json.dumps(technical, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    doc = doc.replace('__BASE_CSS__', base_css).replace('__ASOF__', shared.esc(asof)).replace('__SECTIONS__', ''.join(parts)).replace('__PAYLOAD__', payload).replace('__TECHNICAL__', technical_payload)
    tmp = OUT / 'index.html.tmp'
    tmp.write_text(doc, encoding='utf-8')
    os.replace(tmp, OUT / 'index.html')
    print(json.dumps({'output': str(OUT / 'index.html'), 'asof': asof, 'charts': len(charts),
                      'freshness': freshness['summary'], 'technical': technical.get('updated_at')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
