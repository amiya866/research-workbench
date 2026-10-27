# -*- coding: utf-8 -*-
"""由 nickel-panel/data.json 生成与锡周报同版式的镍周报、摘要 JSON 和日报卡片。"""
import datetime
import html
import json
import os
import re
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE = Path(r'D:/Kimi/nickel-panel/data.json')
OUT = BASE / 'nickel-weekly'
META = BASE / 'data' / 'nickel_weekly.json'
DAILY = BASE / 'reports' / 'daily_latest.html'
BEGIN = '<!-- NICKEL_WEEKLY_CARD_BEGIN -->'
END = '<!-- NICKEL_WEEKLY_CARD_END -->'

SECTIONS = [
    ('sumsec', '本周总结', '总览', []),
    ('price', '价格、升贴水与结构', '宏观与策略', ['overview_shfe', 'overview_ss', 'overview_lme', 'premium', 'ratio_ni_ss', 'lme03', 'import_profit', 'npi_price', 'ni_curve', 'ss_curve', 'lme_curve', 'ratio_ni_copper', 'ratio_npi_refined', 'premium_russia', 'premium_jinchuan', 'premium_bean']),
    ('supply', '纯镍与印尼供应', '重点关注/供给', ['supply_refined_cn', 'supply_refined_id', 'supply_npi_cn', 'supply_npi_id', 'supply_npi_stock', 'supply_nickel_sulfate', 'supply_sulfate_rate', 'supply_matte', 'supply_mhp', 'overview_trade_net']),
    ('demand', '不锈钢与新能源需求', '重点关注/需求', ['demand_ss_cn', 'demand_ss_id', 'demand_battery_ternary', 'demand_battery_lfp', 'demand_install_ternary', 'demand_install_lfp', 'demand_ss_import', 'demand_ss_export']),
    ('inventory', '库存与仓单', '重点关注/供给', ['overview_global_stock', 'inventory_shfe', 'inventory_lme', 'inventory_social', 'inventory_plate', 'inventory_bean', 'inventory_ss300', 'inventory_ss_cold', 'inventory_ss_hot', 'lme_region']),
    ('cost', '成本与利润', '重点关注/供给', ['cost_npi_profit', 'cost_ss_profit', 'cost_chrome', 'cost_chromium', 'supply_chrome', 'supply_chrome_import']),
    ('framework', '产业框架', '总览', []),
    ('balance', '平衡表与财报项目', '平衡表', []),
    ('sources', '数据源与缺口', '总览', []),
]
NAMES = {
    'overview_shfe': '沪镍主连', 'overview_ss': '不锈钢主连', 'overview_lme': 'LME镍3M',
    'overview_global_stock': '全球显性库存', 'premium': '不同镍产品折镍价', 'ratio_ni_ss': '镍/不锈钢比价',
    'lme03': 'LME镍0-3升贴水', 'import_profit': '精炼镍进口盈亏', 'npi_price': '镍铁价格',
    'ni_curve': '沪镍月间结构', 'ss_curve': '不锈钢月间结构', 'lme_curve': '伦镍月间结构',
    'ratio_ni_copper': '镍/铜比价', 'ratio_npi_refined': '镍铁/纯镍比价',
    'supply_refined_cn': '中国精炼镍产量', 'supply_refined_id': '印尼精炼镍产量',
    'supply_npi_cn': '中国镍铁产量', 'supply_npi_id': '印尼镍铁产量', 'supply_npi_stock': '镍铁库存',
    'supply_nickel_sulfate': '中国硫酸镍产量', 'supply_sulfate_rate': '硫酸镍企业开工率',
    'supply_matte': '印尼高冰镍项目产量', 'supply_mhp': '印尼MHP项目产量', 'overview_trade_net': '中国电解镍净进口量',
    'demand_ss_cn': '中国300系不锈钢产量', 'demand_ss_id': '印尼300系不锈钢产量',
    'demand_battery_ternary': '三元动力电池产量', 'demand_battery_lfp': '磷酸铁锂电池产量',
    'demand_install_ternary': '三元电池装车量', 'demand_install_lfp': '磷酸铁锂电池装车量',
    'demand_ss_import': '不锈钢进口量', 'demand_ss_export': '不锈钢出口量',
    'inventory_shfe': 'SHFE镍仓单', 'inventory_lme': 'LME镍库存', 'inventory_social': '镍社会库存',
    'inventory_plate': '镍板库存', 'inventory_bean': '镍豆库存', 'inventory_ss300': '300系不锈钢库存',
    'inventory_ss_cold': '300系冷轧库存', 'inventory_ss_hot': '300系热轧库存', 'lme_region': 'LME镍库存分地区',
    'cost_npi_profit': '镍铁价格与理论利润', 'cost_ss_profit': '不锈钢成本与利润',
    'cost_chrome': '铬矿价格', 'cost_chromium': '高碳铬铁价格', 'supply_chrome': '中国高碳铬铁产量',
    'supply_chrome_import': '高碳铬铁进口量', 'premium_russia': '俄镍升贴水',
    'premium_jinchuan': '金川镍升贴水', 'premium_bean': '镍豆升贴水',
}
KPI = [('shfe', '沪镍主连', '元/吨'), ('ss', '不锈钢主连', '元/吨'), ('lme', 'LME镍3M', '美元/吨'),
       ('global_stock', '全球显性库存', '吨'), ('social_stock', '镍社会库存', '吨'), ('npi_price', '镍铁价格', '元/镍点')]


def esc(value):
    return html.escape(str(value if value is not None else '—'))


def fmt(value):
    if value is None:
        return '—'
    value = float(value)
    if abs(value) >= 1000:
        return format(round(value), ',d')
    if abs(value) >= 100:
        return format(value, ',.1f')
    return format(value, ',.2f').rstrip('0').rstrip('.')


def pct(value):
    return '—' if value is None else '%+.1f%%' % (value * 100)


def last_point(chart):
    labels = chart.get('labels') or []
    datasets = chart.get('datasets') or []
    if not labels or not datasets:
        return None
    candidates = [d for d in datasets if '2026' in str(d.get('label', ''))] or datasets
    for ds in reversed(candidates):
        values = ds.get('data') or []
        for i in range(min(len(labels), len(values)) - 1, -1, -1):
            if values[i] is not None:
                return labels[i], values[i], ds.get('label', '')
    return None


def change(chart, periods=5):
    datasets = chart.get('datasets') or []
    if not datasets:
        return None
    ds = ([d for d in datasets if '2026' in str(d.get('label', ''))] or datasets)[-1]
    values = [v for v in (ds.get('data') or []) if v is not None]
    if len(values) <= periods or not values[-periods - 1]:
        return None
    return values[-1] / values[-periods - 1] - 1


def card_html(meta):
    metrics = ''.join('<li><b>%s</b>　%s</li>' % (esc(m['name']), esc(m['value'])) for m in meta['metrics'][:4])
    return '''%s
<div class="card" id="nickelWeeklyCard" style="border-left:3px solid var(--gold);margin:14px 0;">
  <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;">
    <h3 style="margin:0;color:var(--gold);">研究周报 · 镍与不锈钢</h3>
    <a href="../nickel-weekly/#sumsec" style="font-weight:700;">打开完整镍周报 ↗</a>
  </div>
  <p style="margin-top:8px;">%s</p>
  <ul style="margin:8px 0 0 18px;font-size:12px;color:var(--dim);">%s</ul>
  <p style="font-size:11px;color:var(--dim);margin-top:8px;">数据截至 %s · 本地生成，随镍数据管线自动更新 · <a href="https://amiya866.github.io/nickel-panel/" target="_blank" rel="noopener">镍市瞭望</a></p>
</div>
%s''' % (BEGIN, esc(meta['headline']), metrics, esc(meta['asof']), END)


def update_daily(meta):
    page = DAILY.read_text(encoding='utf-8')
    card = card_html(meta)
    pattern = re.escape(BEGIN) + r'.*?' + re.escape(END)
    if re.search(pattern, page, re.S):
        page = re.sub(pattern, lambda _m: card, page, count=1, flags=re.S)
    else:
        tin_end = '<!-- TIN_WEEKLY_CARD_END -->'
        anchor = tin_end if tin_end in page else '<section class="dp on" id="dp1">'
        page = page.replace(anchor, anchor + '\n' + card, 1)
    DAILY.write_text(page, encoding='utf-8')


def chart_group(charts, keys):
    parts = ['<div class="charts3">']
    for key in keys:
        point = last_point(charts.get(key, {}))
        parts.append('<div class="cbox%s">' % (' ec' if point else ''))
        if point:
            parts.append('<div class="echart"><div class="chart-box"><canvas data-chart="%s"></canvas></div></div>' % esc(key))
            parts.append('<div class="cap">%s</div><div class="stats">最新标签 %s ｜ 最新值 %s ｜ %s</div>' % (
                esc(NAMES.get(key, key)), esc(point[0]), fmt(point[1]), esc(point[2])))
        else:
            parts.append('<div class="cap">%s</div><div class="stats">本期无有效数据，保留空态不补零。</div>' % esc(NAMES.get(key, key)))
        parts.append('</div>')
    parts.append('</div>')
    return ''.join(parts)


def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    charts = data['charts']
    latest = data['latest']
    asof = max(str(v[0]) for v in latest.values() if v and v[0] and re.match(r'^\d{4}-\d{2}-\d{2}$', str(v[0])))
    shfe_chg = change(charts['overview_shfe'])
    lme_chg = change(charts['inventory_lme'])
    npi = last_point(charts['supply_npi_id'])
    ss300 = last_point(charts['demand_ss_cn'])
    price_word = '走强' if (shfe_chg or 0) > 0.01 else ('走弱' if (shfe_chg or 0) < -0.01 else '震荡')
    stock_word = '累库' if (lme_chg or 0) > 0 else '去库'
    headline = ('本周定调：价格%s与海外%s并存，边际仍看印尼 —— 沪镍近5个交易日%s，LME镍库存近5个交易日%s；'
                '印尼NPI最新读数 %s 万金属吨（标签%s），中国300系不锈钢产量最新读数 %s 万吨（标签%s）。'
                '近端重点跟踪印尼供应兑现、300系排产和库存变化能否同向验证；⚙️规则摘要，不构成投资建议。') % (
        price_word, stock_word, pct(shfe_chg), pct(lme_chg), fmt(npi[1]) if npi else '—', npi[0] if npi else '—',
        fmt(ss300[1]) if ss300 else '—', ss300[0] if ss300 else '—')
    metrics = []
    for key, name, unit in KPI:
        date, value = latest.get(key) or [None, None]
        metrics.append({'name': name, 'value': '%s %s（%s）' % (fmt(value), unit, date or '—')})
    meta = {'title': '研究周报 · 镍与不锈钢', 'asof': asof, 'headline': headline, 'metrics': metrics,
            'built_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'local_url': 'nickel-weekly/#sumsec', 'source_url': 'https://amiya866.github.io/nickel-panel/',
            'warnings': data.get('meta', {}).get('warnings', []), 'sync_status': 'ok'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'lib').mkdir(exist_ok=True)
    for name in ('research.css', 'weekly_mobile.css', 'weekly_polish.css', 'weekly_mobile.js'):
        shutil.copyfile(BASE / 'tin-weekly' / name, OUT / name)
    shutil.copyfile(BASE / 'tin-weekly' / 'lib' / 'chart.min.js', OUT / 'lib' / 'chart.min.js')
    shutil.copyfile(BASE / 'scripts' / 'nickel_weekly_research.js', OUT / 'research.js')
    tin_html = (BASE / 'tin-weekly' / 'index.html').read_text(encoding='utf-8')
    base_css = re.search(r'<style>(.*?)</style>', tin_html, re.S).group(1)

    parts = []
    for sid, title, trail, keys in SECTIONS:
        parts.append('<section class="report-page" data-page="%s" data-trail="%s"><div class="page-heading"><h2>%s</h2><span>%s</span></div><div class="page-body">' % (
            sid, esc(trail), esc(title), esc(trail.replace('/', ' / ').upper())))
        if sid == 'sumsec':
            parts.append('<div class="tone"><b>%s</b></div>' % esc(headline))
            parts.append('<div class="roll">策略每日滚动更新：周报为周五存档，最新决策见日报页。使用左侧目录切换研究内容。</div>')
            parts.append('''<details class="fold" id="q4outlook"><summary>后续观察与证伪条件（点击展开/折叠）</summary><div class="foldbody"><ul class="sq"><li>印尼供应：跟踪NPI、MHP、高冰镍和精炼镍产量兑现，不将项目规划直接当作当期供应。</li><li>库存验证：LME、SHFE、社库需同向变化，单一日度去库不直接外推趋势。</li><li>需求验证：300系排产、三元电池装车与硫酸镍开工需共同确认。</li><li>观点边界：⚙️规则摘要只整理当前数据，不沿用旧周报方向，不构成投资建议。</li></ul></div></details>''')
            parts.append('<div id="sumsec"><h2>总结<span class="en">SUMMARY</span></h2><table class="sum"><tr><th>环节</th><th>相关数据</th><th>周度结论</th><th>跟踪</th></tr>')
            shfe = latest.get('shfe') or [None, None]
            ss = latest.get('ss') or [None, None]
            lm = latest.get('lme_stock') or [None, None]
            social = latest.get('social_stock') or [None, None]
            rows = [
                ('价格', '沪镍 %s 元/吨（%s）｜不锈钢 %s 元/吨（%s）' % (fmt(shfe[1]), shfe[0], fmt(ss[1]), ss[0]), '沪镍近5个交易日 %s，价格%s' % (pct(shfe_chg), price_word), price_word, 'nt'),
                ('海外库存', 'LME镍库存 %s 吨（%s）' % (fmt(lm[1]), lm[0]), '近5个交易日 %s，海外%s' % (pct(lme_chg), stock_word), stock_word, 'up' if stock_word == '去库' else 'dn'),
                ('国内库存', '镍社会库存 %s 吨（%s）' % (fmt(social[1]), social[0]), '与海外仓单共同验证，不用单一口库存代全部供需', '跟踪', 'nt'),
                ('供应·印尼', 'NPI %s 万金属吨（标签%s）' % (fmt(npi[1]) if npi else '—', npi[0] if npi else '—'), '边际供应核心在印尼，跟踪NPI/MHP/高冰镍/精炼镍四条线', '重点', 'nt'),
                ('需求·不锈钢', '中国300系 %s 万吨（标签%s）' % (fmt(ss300[1]) if ss300 else '—', ss300[0] if ss300 else '—'), '排产、库存和镍铁采购共同验证，不单独以产量判断需求', '跟踪', 'nt'),
                ('策略观察', '价格、库存、排产三线交叉验证', '信号未同向前不作单边外推；优先看印尼供应与库存趋势是否持续', '观望', 'nt'),
            ]
            for label, datum, conclusion, status, cls in rows:
                parts.append('<tr><td class="c">%s</td><td>%s</td><td>%s</td><td><span class="dir %s">%s</span></td></tr>' % (
                    esc(label), esc(datum), esc(conclusion), cls, esc(status)))
            parts.append('</table></div>')
        if sid == 'framework':
            parts.append('''<details class="fold" id="framework" open><summary>镍与不锈钢产业研究框架（三条产品线）</summary><div class="foldbody"><div class="lead">不锈钢线：红土镍矿 → NPI/镍铁 → 300系不锈钢</div><p>镍需求基本盘。跟踪印尼NPI、钢厂排产、镍铁利润与300系库存，避免把镍价与不锈钢需求简单一一对应。</p><div class="lead">新能源线：HPAL/RKEF → MHP/高冰镍 → 硫酸镍 → 三元电池</div><p>重点看印尼中间品投产、折扣系数和三元相对磷酸铁锂的份额。</p><div class="lead">精炼镍线：硫化矿/镍锍 → 一级镍 → 电镀/合金/特钢</div><p>重点看纯镍产量、进口盈亏、LME/SHFE仓单与镍板库存。</p><p><a href="https://amiya866.github.io/nickel-panel/framework.html">打开原13模块研究框架 ↗</a> · <a href="https://amiya866.github.io/nickel-panel/sources.html">68个图表槽位溯源 ↗</a></p></div></details>''')
        if sid == 'balance':
            parts.append('<details class="fold" id="balance" open><summary>NPI与精炼镍月度平衡（实际与预测分列）</summary><div class="foldbody">')
            for key, bal in (data.get('monthlyBalance') or {}).items():
                if not bal.get('labels'):
                    continue
                parts.append('<div class="lead">%s月度平衡</div><div class="tablewrap"><table class="bal"><tr><th>期间</th><th>供应</th><th>需求</th><th>平衡</th><th>累计</th></tr>' % ('NPI' if key == 'mineral' else '精炼镍'))
                for i in range(max(0, len(bal['labels']) - 10), len(bal['labels'])):
                    vals = [(bal.get(k) or [None] * len(bal['labels']))[i] for k in ('supply', 'demand', 'balance', 'cumulative')]
                    parts.append('<tr><td>%s</td>%s</tr>' % (esc(bal['labels'][i]), ''.join('<td class="num">%s</td>' % fmt(v) for v in vals)))
                parts.append('</table></div>')
            parts.append('</div></details>')
            parts.append('<div class="lead">印尼项目与全球财报</div><p>核心原则：边际看印尼。项目增量采用已披露财报口径，金属量与实物量不混用。</p><div class="tablewrap"><table class="bal"><tr><th>项目</th><th>公司</th><th>2026E增量</th><th>2027E增量</th><th>确定性</th></tr>')
            for p in data.get('projects', []):
                parts.append('<tr><td>%s</td><td>%s</td><td class="num">%s</td><td class="num">%s</td><td>%s</td></tr>' % (
                    esc(p.get('project')), esc(p.get('company')), fmt(p.get('inc26')), fmt(p.get('inc27')), esc(p.get('certainty'))))
            parts.append('</table></div>')
        if sid == 'sources':
            warnings = data.get('meta', {}).get('warnings') or []
            parts.append('<details class="fold" id="datagap" open><summary>数据口径、缺口与新鲜度</summary><div class="foldbody"><p>构建时间 %s ｜ 空图：%s ｜ 构建警告：%s</p><p>优先使用本地镜像和人工核定 Excel 原生图绑定；预测与实际分列，NPI 与精炼镍不混算，未核实数据不补零。</p></div></details>' % (
                esc(data.get('meta', {}).get('builtAt')), esc('、'.join(data.get('meta', {}).get('emptyCharts') or []) or '无'), esc('；'.join(warnings) or '无')))
            parts.append('<div class="tablewrap"><table class="bal"><tr><th>图表键</th><th>来源</th><th>定位/公式</th><th>最新标签</th></tr>')
            sm = data.get('sourceMeta', {}).get('charts', {})
            for key in sorted(k for keys in SECTIONS for k in keys[3]):
                source = sm.get(key, {})
                detail = source.get('formula') or '/'.join(str(source.get(k, '')) for k in ('slot', 'sheet', 'position') if source.get(k)) or source.get('type', '—')
                point = last_point(charts.get(key, {}))
                parts.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (esc(key), esc(source.get('type', '—')), esc(detail), esc(point[0] if point else '—')))
            parts.append('</table></div>')
        if keys:
            parts.append('<div class="lead">%s · 最新读数逐项标注日期</div>' % esc(title))
            parts.append(chart_group(charts, keys))
        if sid == 'sumsec':
            parts.append('<footer>数据更新至 %s ｜ 镍与不锈钢研究周报 ｜ ⚙️自动构建，仅供研究参考，不构成投资建议。</footer>' % esc(asof))
        parts.append('</div></section>')

    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    doc = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><link href="data:," rel="icon">
<title>研究周报 · 镍与不锈钢</title><style>__BASE_CSS__</style><link href="weekly_mobile.css" rel="stylesheet"><link href="weekly_polish.css" rel="stylesheet"><link href="research.css" rel="stylesheet"><link href="../weekly-light.css" rel="stylesheet"><style>.chart-box{height:240px;position:relative}.chart-box canvas{display:block;width:100%;height:100%}.tablewrap{overflow-x:auto}.page-body p{font-size:14.5px}.cbox .stats{line-height:1.55}</style></head>
<body><header class="research-topbar"><div class="research-brand"><a aria-label="返回整合研究站" class="back-home" href="../index.html">← 整合研究站</a><div class="brand-copy"><p class="research-eyebrow">COMMODITY WEEKLY RESEARCH · NICKEL</p><h1>研究周报 <span class="commodity-current">镍</span></h1><p>镍 × 不锈钢 · 周度研究 · 印尼供应 · 库存 · 成本平衡</p></div></div><div class="research-actions"><nav class="commodity-switch" aria-label="品种切换"><a href="../tin-weekly/#sumsec">锡</a><a class="active" href="#sumsec">镍</a></nav><a class="back-home" href="https://amiya866.github.io/nickel-panel/" target="_blank" rel="noopener">镍市瞭望 ↗</a><span class="research-stamp">数据截至 <b>__ASOF__</b></span><button aria-pressed="false" class="view-toggle" id="viewToggle" type="button">切换手机版</button></div></header>
<div class="research-workspace"><aside class="research-sidebar" id="researchSidebar"><button aria-controls="treeNav" aria-expanded="false" class="menu-toggle" id="menuToggle" type="button">研究目录 <span>＋</span></button><div class="sidebar-heading"><span>RESEARCH INDEX</span><b>研究目录</b></div><nav aria-label="镍研究分层目录" class="tree-nav" id="treeNav"></nav></aside><div class="research-content"><div aria-live="polite" class="breadcrumb" id="breadcrumb"></div><div class="wrap" id="reportWrap">__SECTIONS__</div><section aria-live="polite" class="tool-page" hidden id="toolPage"><div class="tool-head"><div><p class="research-eyebrow">RESEARCH WORKBENCH</p><h2 id="toolTitle">研究工作台</h2></div><button id="closeTool" type="button">← 返回周报</button></div><iframe hidden id="toolFrame" title="镍研究工作台"></iframe></section></div></div>
<script src="lib/chart.min.js"></script><script>const DATA=__PAYLOAD__;const charts=DATA.charts;document.querySelectorAll('canvas[data-chart]').forEach(function(canvas){const c=charts[canvas.dataset.chart];if(!c)return;const ds=(c.datasets||[]).map(function(d){return Object.assign({borderWidth:1.5,pointRadius:0,spanGaps:true},d);});new Chart(canvas,{type:'line',data:{labels:c.labels||[],datasets:ds},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{boxWidth:12,font:{family:'KaiTi,"楷体",serif',size:10}}}},scales:{x:{ticks:{maxTicksLimit:8,font:{family:'KaiTi,"楷体",serif',size:10}},grid:{color:'#e3e3e3'}},y:{ticks:{font:{family:'KaiTi,"楷体",serif',size:10}},grid:{color:'#e3e3e3'}}}}});});</script><script src="weekly_mobile.js"></script><script src="research.js"></script></body></html>'''
    doc = doc.replace('__BASE_CSS__', base_css).replace('__ASOF__', esc(asof)).replace('__SECTIONS__', ''.join(parts)).replace('__PAYLOAD__', payload)
    tmp = OUT / 'index.html.tmp'
    tmp.write_text(doc, encoding='utf-8')
    os.replace(tmp, OUT / 'index.html')
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    update_daily(meta)
    print(json.dumps({'output': str(OUT / 'index.html'), 'asof': asof, 'charts': sum(len(s[3]) for s in SECTIONS),
                      'projects': len(data.get('projects', [])), 'warnings': meta['warnings'], 'layout': 'tin-compatible'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
