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
    ('price', '价格与结构', '总览', ['overview_shfe', 'overview_ss', 'overview_lme', 'premium', 'ratio_ni_ss', 'lme03', 'import_profit', 'npi_price', 'ni_curve', 'ss_curve', 'lme_curve', 'ratio_ni_copper', 'ratio_npi_refined', 'premium_russia', 'premium_jinchuan', 'premium_bean']),
    ('supply', '纯镍与印尼供应', '重点关注/供给', ['supply_refined_cn', 'supply_refined_id', 'supply_npi_cn', 'supply_npi_id', 'supply_npi_stock', 'supply_nickel_sulfate', 'supply_sulfate_rate', 'supply_matte', 'supply_mhp', 'overview_trade_net']),
    ('demand', '不锈钢与新能源需求', '重点关注/需求', ['demand_ss_cn', 'demand_ss_id', 'demand_battery_ternary', 'demand_battery_lfp', 'demand_install_ternary', 'demand_install_lfp', 'demand_ss_import', 'demand_ss_export']),
    ('inventory', '库存与仓单', '重点关注/供给', ['overview_global_stock', 'inventory_shfe', 'inventory_lme', 'inventory_social', 'inventory_plate', 'inventory_bean', 'inventory_ss300', 'inventory_ss_cold', 'inventory_ss_hot', 'lme_region']),
    ('cost', '成本与利润', '重点关注/供给', ['cost_npi_profit', 'cost_ss_profit', 'cost_chrome', 'cost_chromium', 'supply_chrome', 'supply_chrome_import']),
    ('framework', '产业框架', '总览', []),
    ('balance', '年度平衡与2027策略', '平衡表', []),
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
BALANCE_CONFIG = {
    'title': '年度平衡与2027策略：过剩重新扩大，空配等待近端扰动落地',
    'rows': [
        ('2025实际', '供应过剩', '需求扩张', '+28.3', '高库存起点'),
        ('2026E', '387万吨', '385万吨', '+1.9', '接近平衡，近端扰动仍可反弹'),
        ('2027E', '407万吨（+5.2%）', '400万吨（+3.9%）', '+7.0', '过剩扩大，中期空配'),
    ],
    'regional': '印尼供给决定边际。2026仅小幅过剩，干旱、RKAB与HPAL扰动能制造阶段紧张；2027新增NPI/HPAL/精炼镍兑现后，供应增速再次超过需求。',
    'source': '来源：INSG 2026-10-13预测（2025过剩为INSG历史口径）；Nickel Industries项目进度用于滚动验证。预测值不是实际值。',
    'strategy': [
        '方向：中期仍以2027远月反弹空为主，但不把2026小过剩当作随时可空；近端干旱、配额或库存连续下降时先等待。',
        '入场：远月反弹且LME Contango不再收窄、国内社库止降、印尼产量恢复时分批空；避免在消息驱动的急涨首日追空。',
        '风控：若RKAB进一步削减实际产量、干旱令RKEF长期低于铭牌、或国内外库存连续两个月同降，停止加空并降低仓位。',
        '止盈/失效：远月回落5%—10%分批兑现；若2027过剩预测被下修至平衡或短缺，年度空配退出。每月复核印尼项目与INSG平衡。',
    ],
    'drivers': [
        '增量：ENC HPAL 7.2万吨/年、HNC高负荷、印尼NPI与精炼镍新线；2027首个完整年贡献更明显。',
        '扰动：2026-10干旱使RKEF约75%负荷，Weda Bay 9月恢复采矿，方向相反，不能只看项目名义产能。',
        '需求：300系不锈钢是底座，三元受磷酸铁锂挤压；若不锈钢排产强于预期，过剩下修。',
    ],
}


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


def period_return(chart, start, end):
    labels = chart.get('labels') or []
    values = (chart.get('datasets') or [{}])[0].get('data') or []
    points = [(str(label)[:10], value) for label, value in zip(labels, values)
              if start <= str(label)[:10] <= end and value is not None]
    if len(points) < 2 or not points[0][1]:
        return None
    return points[-1][1] / points[0][1] - 1


def quarterly_html(path, new_html):
    today = datetime.date.today()
    end_month = ((today.month - 1) // 3 + 1) * 3
    next_quarter = datetime.date(today.year + (end_month == 12), end_month % 12 + 1, 1)
    if (next_quarter - today).days <= 7:
        return new_html
    if path.exists():
        match = re.search(r'<details class="fold" id="q4outlook">.*?</details>', path.read_text(encoding='utf-8'), re.S)
        if match:
            return match.group(0)
    return new_html


SEASON_COLORS = ['#1F4E79', '#C00000', '#2E7D32', '#7B1FA2', '#E65100', '#00838F', '#8C564B', '#C2185B', '#546E7A', '#7A8800']


def tint(color, factor):
    color = color.lstrip('#')
    parts = [int(color[i:i + 2], 16) for i in (0, 2, 4)]
    if factor >= 1:
        parts = [min(255, round(v + (255 - v) * (factor - 1))) for v in parts]
    else:
        parts = [round(v * factor) for v in parts]
    return '#%02X%02X%02X' % tuple(parts)


def seasonalize_charts(charts):
    converted = {}
    for key, chart in charts.items():
        labels = chart.get('labels') or []
        if len(labels) < 40 or not all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(x)) for x in labels):
            converted[key] = chart
            continue
        years = sorted({str(x)[:4] for x in labels})
        month_days = sorted({str(x)[5:] for x in labels})
        sources = chart.get('datasets') or []
        datasets = []
        for source_index, source in enumerate(sources):
            base = SEASON_COLORS[source_index % len(SEASON_COLORS)]
            for year_index, year in enumerate(years):
                lookup = {str(label)[5:]: value for label, value in zip(labels, source.get('data') or []) if str(label).startswith(year)}
                if len(sources) > 1:
                    depth = 0.45 + 0.55 * (year_index / max(1, len(years) - 1))
                    color = tint(base, depth)
                else:
                    color = SEASON_COLORS[year_index % len(SEASON_COLORS)]
                datasets.append(dict(source, label='%s年｜%s' % (year, source.get('label', key)),
                                     data=[lookup.get(md) for md in month_days],
                                     borderColor=color, backgroundColor=color))
        converted[key] = dict(chart, labels=month_days, datasets=datasets, _seasonal=True)
    return converted


def marginal_block(items):
    """items=(标签, 证据, 判断, 分数)；输出“相关边际”，证据同向才给明确方向。"""
    bull = sum(1 for item in items if (item[3] or 0) > 0)
    bear = sum(1 for item in items if (item[3] or 0) < 0)
    net = sum(item[3] or 0 for item in items)
    if bull >= 3 and bull - bear >= 2:
        direction = '基准方向：偏多（价格、结构、库存/供需中多项同向，方向相对明确）'
    elif bear >= 3 and bear - bull >= 2:
        direction = '基准方向：偏空（价格、结构、库存/供需中多项同向，方向相对明确）'
    elif net > 0 and bull > bear:
        direction = '基准方向：偏多但证据不够齐，作为偏强观察而非单边确认'
    elif net < 0 and bear > bull:
        direction = '基准方向：偏空但证据不够齐，作为偏弱观察而非单边确认'
    else:
        direction = '基准方向：震荡/分化，暂不作单边外推，继续跟踪'
    parts = ['<div class="lead">相关边际</div><ul class="sq">']
    for label, evidence, judgment, _score in items:
        parts.append('<li><b>%s</b>：%s → %s</li>' % (esc(label), esc(evidence), esc(judgment)))
    parts.append('<li><b>%s</b>；⚙️规则摘要，不构成投资建议。</li>' % esc(direction))
    parts.append('</ul>')
    return ''.join(parts)


def weekly_outlook_html(near, medium, strategy, invalidation):
    rows = [('近端 · 1—4周', near), ('中长期 · 季度至明年', medium),
            ('策略建议', strategy), ('验证与失效', invalidation)]
    body = ''.join('<li><b>%s</b>：%s</li>' % (esc(label), esc(value)) for label, value in rows)
    return ('<details class="fold" id="weeklyoutlook" open><summary>本周展望与策略（近端 × 中长期）</summary>'
            '<div class="foldbody"><ul class="sq">%s</ul>'
            '<p class="src-note">近端由最新价格、结构和库存驱动；中长期为产业格局基准，须由后续数据持续验证，不构成投资建议。</p>'
            '</div></details>' % body)


def forecast_balance_html(config, shfe_values, full=False):
    window = shfe_values[-120:]
    low, high, current = min(window), max(window), shfe_values[-1]
    position = (current - low) / (high - low) if high > low else 0.5
    rows = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td class="num">%s</td><td>%s</td></tr>' % row
                   for row in config['rows'])
    parts = ['<details class="fold" id="annualbalance%s" open><summary>%s</summary><div class="foldbody">' % ('Full' if full else '', esc(config['title'])),
             '<div class="tablewrap"><table class="bal"><tr><th>年份</th><th>供应</th><th>需求</th><th>平衡（万吨）</th><th>交易含义</th></tr>',
             rows, '</table></div><p><b>结构判断：</b>%s</p>' % esc(config['regional']),
             '<p class="src-note">%s</p>' % esc(config['source']),
             '<div class="lead">年度策略与执行边界</div><ul class="sq">']
    parts += ['<li><b>%s</b></li>' % esc(item) for item in config['strategy']]
    parts.append('<li><b>价格位置：</b>当前主连 %s，近120日区间 %s—%s，位置 %s；入场看对应远月合约，不能只按主连机械下单。</li>' % (
        fmt(current), fmt(low), fmt(high), pct(position)))
    parts.append('</ul>')
    if full:
        parts.append('<div class="lead">供应增量与证伪路径</div><ul class="sq">')
        parts += ['<li>%s</li>' % esc(item) for item in config['drivers']]
        parts.append('</ul>')
    parts.append('</div></details>')
    return ''.join(parts)


FRESHNESS_FILE = BASE / 'data' / 'nickel_weekly_freshness.json'
UNITS = {
    'overview_shfe': '元/吨', 'overview_ss': '元/吨', 'overview_lme': '美元/吨',
    'overview_global_stock': '吨', 'premium': '元/吨', 'ratio_ni_ss': '比值',
    'lme03': '美元/吨', 'import_profit': '元/吨', 'npi_price': '元/镍点',
    'ni_curve': '元/吨', 'ss_curve': '元/吨', 'lme_curve': '美元/吨',
    'ratio_ni_copper': '比值', 'ratio_npi_refined': '比值',
    'supply_refined_cn': '金属吨', 'supply_refined_id': '金属吨',
    'supply_npi_cn': '万金属吨', 'supply_npi_id': '万金属吨', 'supply_npi_stock': '万金属吨',
    'supply_nickel_sulfate': '金属吨', 'supply_sulfate_rate': '%',
    'supply_matte': '吨镍', 'supply_mhp': '吨镍', 'overview_trade_net': '万金属吨',
    'demand_ss_cn': '万吨', 'demand_ss_id': '万吨',
    'demand_battery_ternary': 'MWh', 'demand_battery_lfp': 'MWh',
    'demand_install_ternary': 'MWh', 'demand_install_lfp': 'MWh',
    'demand_ss_import': '万吨', 'demand_ss_export': '万吨',
    'inventory_shfe': '吨', 'inventory_lme': '吨', 'inventory_social': '吨',
    'inventory_plate': '吨', 'inventory_bean': '吨', 'inventory_ss300': '吨',
    'inventory_ss_cold': '吨', 'inventory_ss_hot': '吨', 'lme_region': '吨',
    'cost_npi_profit': '元/镍点', 'cost_ss_profit': '%',
    'cost_chrome': '元/干吨度', 'cost_chromium': '元/50基吨',
    'supply_chrome': '万吨', 'supply_chrome_import': '万吨',
    'premium_russia': '元/吨', 'premium_jinchuan': '元/吨', 'premium_bean': '元/吨',
}


def source_detail(source):
    if not source:
        return '未找到可靠同口径源'
    kind = source.get('type', '—')
    if kind == 'excel-native':
        return '%s %s!%s（%s）' % (source.get('workbook'), source.get('sheet'), source.get('position'), source.get('slot'))
    if kind == 'zhiji':
        return 'zhiji ' + '/'.join(source.get('indicators') or [source.get('indicator', '—')])
    if kind == 'zhiji-guan':
        return '知几行情 ' + str(source.get('symbol', '—'))
    if kind == 'derived':
        return '衍生计算：' + str(source.get('formula', '—'))
    if kind == 'financial':
        return '全球镍企财报真源（%s）' % source.get('period', '—')
    if kind == 'B01':
        return 'B01 %s：%s' % (source.get('sheet', '—'), source.get('formula') or source.get('columns', '—'))
    if kind == 'sina-contracts':
        return '新浪期货逐合约日K'
    if kind == 'mysteel-mirror':
        return 'Mysteel镜像 ' + str(source.get('chart_code') or source.get('indicator') or source.get('code') or '—')
    return kind + ' ' + str(source.get('formula') or source.get('sheet') or source.get('indicator') or '')


def infer_frequency(chart):
    labels = [str(x) for x in (chart.get('labels') or [])]
    if any('Q' in x for x in labels):
        return '季度'
    dates = []
    for x in labels:
        try:
            dates.append(datetime.date.fromisoformat(x[:10]))
        except ValueError:
            pass
    if len(dates) >= 3:
        dates = sorted(set(dates))
        gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
        median = gaps[len(gaps) // 2]
        if median <= 3:
            return '日度'
        if median <= 10:
            return '周度'
        if median <= 45:
            return '月度'
        return '低频'
    if labels and all(re.fullmatch(r'\d{1,2}(?:-\d{2})?', x) for x in labels):
        return '月度/季节图'
    return '标签型'


def point_date(point):
    if not point:
        return None
    label = str(point[0])
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', label):
        return datetime.date.fromisoformat(label)
    if re.fullmatch(r'\d{4}-\d{2}', label):
        return datetime.date.fromisoformat(label + '-01')
    quarter = re.fullmatch(r'(\d{4})Q([1-4])', label)
    if quarter:
        year, q = int(quarter.group(1)), int(quarter.group(2))
        return datetime.date(year, q * 3, [31, 30, 30, 31][q - 1])
    year_match = re.search(r'20\d{2}', str(point[2]))
    year = int(year_match.group()) if year_match else datetime.date.today().year
    if re.fullmatch(r'\d{1,2}', label) and 1 <= int(label) <= 12:
        return datetime.date(year, int(label), 1)
    short = re.fullmatch(r'(\d{1,2})-(\d{2})', label)
    if short and 1 <= int(short.group(1)) <= 12:
        return datetime.date(year, int(short.group(1)), int(short.group(2)))
    return None


def build_freshness(data):
    today = datetime.date.today()
    limits = {'日度': (7, 14), '周度': (10, 21), '月度': (45, 75), '月度/季节图': (45, 75), '季度': (150, 240), '低频': (150, 240), '标签型': (45, 75)}
    modules = {key: title for _sid, title, _trail, keys in SECTIONS for key in keys}
    rows = []
    for key, chart in data['charts'].items():
        source = data.get('sourceMeta', {}).get('charts', {}).get(key) or {}
        point = last_point(chart)
        frequency = infer_frequency(chart)
        latest_date = point_date(point)
        age = (today - latest_date).days if latest_date else None
        if not point:
            status, label = 'missing', '缺失'
            action = '未找到可靠同口径源；保留空态，不补0、不用其他指标硬替。'
            if key == 'overview_trade':
                action = '贸易商同业/下游成交缺少可靠源；保留空缺，待人工提供周报口径数据。'
        elif latest_date is None:
            status, label = 'review', '待核'
            action = '最新标签无法映射确切日期，需人工核对原表口径。'
        elif age < 0:
            status, label = 'review', '待核'
            action = '最新标签晚于当前日，需核对是否为预测、排产或未来占位。'
        else:
            fresh, watch = limits[frequency]
            if age <= fresh:
                status, label = 'fresh', '正常'
                action = '按源口径使用，随自动链更新。'
            elif age <= watch:
                status, label = 'watch', '关注'
                action = '接近滞后期，保留使用并加强观察。'
            else:
                status, label = 'stale', '滞后'
                action = '保留最后真实值并标注日期；等待源端更新，不补0，不作为本周新增证据。'
        source_text = source_detail(source)
        if source.get('recoveredFrom'):
            source_text += '（失败刷新保留自 %s）' % source['recoveredFrom']
        rows.append({'key': key, 'name': NAMES.get(key, key), 'module': modules.get(key, '其他'),
                     'source': source_text, 'frequency': frequency,
                     'unit': source.get('unit') or UNITS.get(key, '—'),
                     'latest': str(point[0]) if point else '—', 'latest_value': fmt(point[1]) if point else '—',
                     'latest_iso': latest_date.isoformat() if latest_date else '', 'age_days': age,
                     'status': status, 'status_label': label, 'action': action})
    order = {'missing': 0, 'stale': 1, 'review': 2, 'watch': 3, 'fresh': 4}
    rows.sort(key=lambda row: (order[row['status']], row['module'], row['key']))
    summary = {code: sum(row['status'] == code for row in rows) for code in ('fresh', 'watch', 'stale', 'missing', 'review')}
    summary['total'] = len(rows)
    return {'asof': today.isoformat(), 'built_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'thresholds': limits, 'summary': summary, 'rows': rows}


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
    lme03 = last_point(charts['lme03'])
    jinchuan = last_point(charts['premium_jinchuan'])
    price_word = '走强' if (shfe_chg or 0) > 0.01 else ('走弱' if (shfe_chg or 0) < -0.01 else '震荡')
    stock_word = '累库' if (lme_chg or 0) > 0 else '去库'
    lme_structure = 'Back' if lme03 and lme03[1] > 0 else ('Contango' if lme03 and lme03[1] < 0 else '持平')
    domestic_structure = '升水' if jinchuan and jinchuan[1] > 0 else ('贴水' if jinchuan and jinchuan[1] < 0 else '持平')
    structure_desc = 'LME镍0-3 %s 美元/吨（%s），金川镍升贴水%s %s 元/吨（%s）' % (
        fmt(lme03[1]) if lme03 else '—', lme03[0] if lme03 else '—', domestic_structure,
        fmt(jinchuan[1]) if jinchuan else '—', jinchuan[0] if jinchuan else '—')
    headline = ('本周定调：价格%s与海外%s并存，结构%s，边际仍看印尼 —— 沪镍近5个交易日%s，LME镍库存近5个交易日%s；'
                '印尼NPI最新读数 %s 万金属吨（标签%s），中国300系不锈钢产量最新读数 %s 万吨（标签%s）；结构：%s。'
                '近端重点跟踪价格、结构、印尼供应兑现、300系排产和库存变化能否同向验证；⚙️规则摘要，不构成投资建议。') % (
        price_word, stock_word, lme_structure, pct(shfe_chg), pct(lme_chg), fmt(npi[1]) if npi else '—', npi[0] if npi else '—',
        fmt(ss300[1]) if ss300 else '—', ss300[0] if ss300 else '—', structure_desc)
    metrics = []
    for key, name, unit in KPI:
        date, value = latest.get(key) or [None, None]
        metrics.append({'name': name, 'value': '%s %s（%s）' % (fmt(value), unit, date or '—')})
    q3 = period_return(charts['overview_shfe'], '2026-07-01', '2026-09-30')
    q4 = period_return(charts['overview_shfe'], '2026-10-01', asof)
    refined = last_point(charts['supply_refined_cn'])
    lfp = last_point(charts['demand_battery_lfp'])
    q4_html = '''<details class="fold" id="q4outlook"><summary>季度展望：Q3复盘与Q4展望（点击展开/折叠）</summary><div class="foldbody">
<div class="lead">一、三季度复盘与四季度展望</div><ul class="sq">
<li>Q3沪镍价格变动 %s。供应端印尼中间品和精炼镍继续放量，需求端不锈钢与新能源未能完全消化增量，LME及国内库存高位，价格主要受现实供应压力约束。</li>
<li>进入Q4，核心不是单纯判断印尼增产还是减产，而是验证新增供应能否被不锈钢和三元需求吸收。当前LME镍库存 %s 吨、国内社库 %s 吨，库存仍是判断价格弹性的第一约束。</li>
<li>结构定位：LME镍0-3 %s 美元/吨（%s），金川镍升贴水 %s 元/吨（%s）；期现结构必须与库存去化方向一致才有效。</li>
<li>基准判断维持“高库存压制与印尼政策/成本支撑并存”。若库存不能连续下降，反弹不宜直接理解为趋势反转；若印尼供应扰动与去库共振，再上调近月弹性。</li></ul>
<div class="lead">二、供应：印尼增量仍是主线</div><ul class="sq">
<li>印尼NPI最新 %s 万金属吨（标签%s），NPI、MHP、高冰镍和精炼镍多条产品线共同决定边际供应，不能只看单一项目或单一政策。</li>
<li>中国精炼镍最新 %s（%s）。国内高产量与印尼增量叠加，Q4需重点核查实际开工、出口和仓单交付，而非只看规划产能。</li>
<li>印尼RKAB、园区检修和天气是潜在扰动项，但只有转化为产量、出口或库存变化，才作为方向性证据。</li></ul>
<div class="lead">三、需求与库存：不锈钢托底，新能源分化</div><ul class="sq">
<li>中国300系不锈钢最新 %s 万吨（标签%s），排产和镍铁采购决定NPI需求底座，需同时观察钢厂利润与300系库存。</li>
<li>新能源内部三元与磷酸铁锂继续分化，磷酸铁锂最新产量 %s MWh（标签%s），三元需求不能简单用动力电池总量替代。</li>
<li>若LME、SHFE和社库不能同向去化，高库存将继续压制反弹高度；若仓单持续下降且不锈钢排产稳定，才支持近月结构改善。</li></ul>
<div class="lead">四、策略与验证点</div><ul class="sq">
<li>不追高库存环境下的单边反弹，优先观察库存、升贴水和近月结构是否同步改善。</li>
<li>上修条件：印尼供应扰动兑现＋连续去库＋不锈钢排产稳定；下修条件：印尼增量超预期＋终端排产走弱＋仓单继续增加。</li>
<li>本段为数据驱动的研究框架，不构成投资建议。</li></ul></div></details>''' % (
        pct(q3), fmt(latest.get('lme_stock')[1]), fmt(latest.get('social_stock')[1]),
        fmt(lme03[1]) if lme03 else '—', lme03[0] if lme03 else '—',
        fmt(jinchuan[1]) if jinchuan else '—', jinchuan[0] if jinchuan else '—',
        fmt(npi[1]) if npi else '—', npi[0] if npi else '—',
        fmt(refined[1]) if refined else '—', refined[0] if refined else '—',
        fmt(ss300[1]) if ss300 else '—', ss300[0] if ss300 else '—',
        fmt(lfp[1]) if lfp else '—', lfp[0] if lfp else '—')
    q4_html = quarterly_html(OUT / 'index.html', q4_html)

    def _sign(x):
        return 1 if (x or 0) > 0 else (-1 if (x or 0) < 0 else 0)
    global20 = change(charts['overview_global_stock'], 20)
    social20 = change(charts['inventory_social'], 20)
    npi_chg = change(charts['supply_npi_id'], 20)
    refined_chg = change(charts['supply_refined_cn'], 20)
    ss_chg = change(charts['demand_ss_cn'], 20)
    lme03_trend = change(charts['lme03'], 20)
    domestic_trend = change(charts['premium_jinchuan'], 20)
    lme_s = _sign(lme03[1] if lme03 else 0); dom_s = _sign(jinchuan[1] if jinchuan else 0)
    if lme_s and dom_s and lme_s == dom_s:
        structure_score = lme_s * 2; structure_judge = '内外结构同向支撑（方向较明确）' if structure_score > 0 else '内外结构同向偏弱（方向较明确）'
    elif lme_s or dom_s:
        structure_score = lme_s or dom_s; structure_judge = '单边结构成立，仍需另一边确认'
    else:
        structure_score = 0; structure_judge = '结构数据不足，跟踪'
    if global20 is not None and social20 is not None and _sign(global20) == _sign(social20):
        inventory_score = -_sign(global20); inventory_judge = '内外库存同向去化，近月有支撑' if inventory_score > 0 else '内外库存同向累积，近月承压'
    else:
        inventory_score = 0; inventory_judge = '库存信号分化，跟踪'
    if npi_chg is not None and refined_chg is not None and _sign(npi_chg) == _sign(refined_chg):
        supply_score = -_sign(npi_chg); supply_judge = '印尼与国内供应同向收缩，供应端有支撑' if supply_score > 0 else '印尼与国内供应同向增加，供应端施压'
    else:
        supply_score = 0; supply_judge = '供应线信号分化，跟踪印尼兑现'
    demand_score = 1 if (ss_chg or 0) > 0.02 else (-1 if (ss_chg or 0) < -0.02 else 0)
    demand_judge = '300系排产改善，需求端有支撑' if demand_score > 0 else ('300系排产走弱，需求端承压' if demand_score < 0 else '需求变化不足，跟踪')
    marginal_items = [
        ('价格', '沪镍近5个交易日 %s' % pct(shfe_chg), '价格上行，偏多证据' if (shfe_chg or 0) > 0 else ('价格下行，偏空证据' if (shfe_chg or 0) < 0 else '价格震荡，等待方向'), _sign(shfe_chg)),
        ('结构', structure_desc, structure_judge, structure_score),
        ('库存', '全球显性库存20日 %s，镍社库20日 %s' % (pct(global20), pct(social20)), inventory_judge, inventory_score),
        ('供应', '印尼NPI近20日 %s，中国精炼镍近20日 %s' % (pct(npi_chg), pct(refined_chg)), supply_judge, supply_score),
        ('需求', '中国300系不锈钢近20日 %s' % pct(ss_chg), demand_judge, demand_score),
    ]
    marginal_html = marginal_block(marginal_items)
    weekly_html = weekly_outlook_html(
        '沪镍近5个交易日%s，%s；全球显性库存20日%s、国内社库20日%s。近端仍以库存和升贴水确认反弹持续性，不把单日上涨当反转。' % (pct(shfe_chg), structure_desc, pct(global20), pct(social20)),
        '2027年基准格局仍是印尼NPI、MHP、高冰镍与精炼镍多线供给具备增长潜力，不锈钢和三元需求能否吸收增量是平衡关键；高库存与Contango未根本改变前，中期估值上方受约束。',
        '近端不追反弹，优先等去库、现货升水和Contango收窄共振；中期以反弹后的风险对冲/偏空观察为主。若印尼政策或减产兑现并带来连续去库，再转为回调做多，而非提前押注。',
        '上修：印尼实际产量/出口下降＋国内外连续去库＋300系排产稳定。下修：印尼增量兑现＋社库与仓单上升＋不锈钢或三元需求走弱。')
    meta = {'title': '研究周报 · 镍与不锈钢', 'asof': asof, 'headline': headline, 'metrics': metrics,
            'built_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'local_url': 'nickel-weekly/#sumsec', 'source_url': 'https://amiya866.github.io/nickel-panel/',
            'warnings': data.get('meta', {}).get('warnings', []), 'sync_status': 'ok'}
    charts = seasonalize_charts(charts)
    freshness = build_freshness(data)
    FRESHNESS_FILE.write_text(json.dumps(freshness, ensure_ascii=False, indent=2), encoding='utf-8')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'lib').mkdir(exist_ok=True)
    for name in ('research.css', 'weekly_mobile.css', 'weekly_polish.css', 'weekly_mobile.js'):
        shutil.copyfile(BASE / 'tin-weekly' / name, OUT / name)
    shutil.copyfile(BASE / 'tin-weekly' / 'lib' / 'chart.min.js', OUT / 'lib' / 'chart.min.js')
    shutil.copyfile(BASE / 'scripts' / 'nickel_weekly_research.js', OUT / 'research.js')
    tin_html = (BASE / 'tin-weekly' / 'index.html').read_text(encoding='utf-8')
    base_css = re.search(r'<style>(.*?)</style>', tin_html, re.S).group(1)

    shfe_values = [v for v in charts['overview_shfe']['datasets'][0]['data'] if v is not None]
    parts = []
    for sid, title, trail, keys in SECTIONS:
        parts.append('<section class="report-page" data-page="%s" data-trail="%s"><div class="page-heading"><h2>%s</h2><span>%s</span></div><div class="page-body">' % (
            sid, esc(trail), esc(title), esc(trail.replace('/', ' / ').upper())))
        if sid in ('sumsec', 'balance'):
            parts.append(forecast_balance_html(BALANCE_CONFIG, shfe_values, full=(sid == 'balance')))
        if sid == 'sumsec':
            parts.append('<div class="tone"><b>%s</b></div>' % esc(headline))
            parts.append('<div class="roll">策略每日滚动更新：周报为周五存档，最新决策见日报页。使用左侧目录切换研究内容。</div>')
            parts.append(weekly_html)
            parts.append(q4_html)
            parts.append('<div id="sumsec"><h2>总结<span class="en">SUMMARY</span></h2><table class="sum"><tr><th>环节</th><th>相关数据</th><th>周度结论</th><th>跟踪</th></tr>')
            shfe = latest.get('shfe') or [None, None]
            ss = latest.get('ss') or [None, None]
            lm = latest.get('lme_stock') or [None, None]
            social = latest.get('social_stock') or [None, None]
            def _cls(score):
                return 'up' if (score or 0) > 0 else ('down' if (score or 0) < 0 else 'nt')
            score_map = {item[0]: item[3] for item in marginal_items}
            lme_value = lme03[1] if lme03 else None
            dom_value = jinchuan[1] if jinchuan else None
            if lme_value is not None and lme_value > 0:
                lme_status, lme_cls = 'Back偏多', 'up'
                lme_conclusion = 'Back结构支撑近月' if (lme03_trend or 0) >= 0 else 'Back仍在但20日走弱，跟踪是否转弱'
            elif lme_value is not None and lme_value < 0:
                lme_status, lme_cls = 'Contango偏空', 'down'
                lme_conclusion = 'Contango扩大，海外结构走弱' if (lme03_trend or 0) < 0 else 'Contango收窄，海外结构边际改善，仍需确认'
            else:
                lme_status, lme_cls, lme_conclusion = '中性', 'nt', '海外结构数据不足'
            if dom_value is not None and dom_value > 0:
                domestic_status, domestic_cls = ('升水走弱，关注', 'nt') if (domestic_trend or 0) < 0 else ('升水偏多', 'up')
                domestic_conclusion = '金川镍升水但20日走弱，跟踪是否转弱' if (domestic_trend or 0) < 0 else '金川镍升水，国内结构仍有支撑'
            elif dom_value is not None and dom_value < 0:
                domestic_status, domestic_cls = ('贴水扩大，偏空', 'down') if (domestic_trend or 0) < 0 else ('贴水收窄，关注', 'nt')
                domestic_conclusion = '金川镍贴水扩大，国内结构走弱' if (domestic_trend or 0) < 0 else '金川镍贴水收窄，国内结构边际改善，仍需确认'
            else:
                domestic_status, domestic_cls, domestic_conclusion = '中性', 'nt', '国内升贴水数据不足'
            if social20 is not None:
                social_status = '去库偏多' if social20 < 0 else '累库偏空'; social_cls = 'up' if social20 < 0 else 'down'
                social_conclusion = '镍社库20日 %s，%s' % (pct(social20), '去库支撑近月' if social20 < 0 else '累库压制近月')
            else:
                social_status, social_cls, social_conclusion = '跟踪', 'nt', '社库趋势暂不可得，继续跟踪'
            rows = [
                ('价格', '沪镍 %s 元/吨（%s）｜不锈钢 %s 元/吨（%s）' % (fmt(shfe[1]), shfe[0], fmt(ss[1]), ss[0]), '沪镍近5个交易日 %s，价格%s' % (pct(shfe_chg), price_word), price_word, _cls(shfe_chg)),
                ('结构·LME', 'LME镍0-3 %s 美元/吨（%s，20日 %s）' % (fmt(lme_value) if lme_value is not None else '—', lme03[0] if lme03 else '—', pct(lme03_trend)), lme_conclusion, lme_status, lme_cls),
                ('结构·国内', '金川镍升贴水 %s 元/吨（%s，20日 %s）' % (fmt(dom_value) if dom_value is not None else '—', jinchuan[0] if jinchuan else '—', pct(domestic_trend)), domestic_conclusion, domestic_status, domestic_cls),
                ('海外库存', 'LME镍库存 %s 吨（%s）' % (fmt(lm[1]), lm[0]), '近5个交易日 %s，海外%s' % (pct(lme_chg), stock_word), '%s%s' % (stock_word, '偏多' if stock_word == '去库' else '偏空'), 'up' if stock_word == '去库' else 'dn'),
                ('国内库存', '镍社会库存 %s 吨（%s）' % (fmt(social[1]), social[0]), social_conclusion, social_status, social_cls),
                ('供应·印尼', 'NPI %s 万金属吨（标签%s，近20日 %s）' % (fmt(npi[1]) if npi else '—', npi[0] if npi else '—', pct(npi_chg)), '印尼供应与精炼镍同向才确认，分化则跟踪', '偏多' if score_map['供应'] > 0 else ('偏空' if score_map['供应'] < 0 else '跟踪'), _cls(score_map['供应'])),
                ('需求·不锈钢', '中国300系 %s 万吨（标签%s，近20日 %s）' % (fmt(ss300[1]) if ss300 else '—', ss300[0] if ss300 else '—', pct(ss_chg)), '排产、库存和镍铁采购共同验证', '偏多' if score_map['需求'] > 0 else ('偏空' if score_map['需求'] < 0 else '跟踪'), _cls(score_map['需求'])),
                ('策略观察', '价格、LME结构、国内升贴水、库存、印尼供应和300系排产交叉验证', '信号未同向前不作单边外推；国内升贴水走弱时下调近月判断', '跟踪', 'nt'),
            ]
            for label, datum, conclusion, status, cls in rows:
                parts.append('<tr><td class="c">%s</td><td>%s</td><td>%s</td><td><span class="dir %s">%s</span></td></tr>' % (
                    esc(label), esc(datum), esc(conclusion), cls, esc(status)))
            parts.append('</table></div>')
            parts.append(marginal_html)
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
            summary = freshness['summary']
            parts.append('<details class="fold" id="datagap" open><summary>数据口径、缺口与新鲜度（51项全量审计）</summary><div class="foldbody">')
            parts.append('<div class="fresh-grid">')
            for code, label in [('fresh', '正常'), ('watch', '关注'), ('stale', '滞后'), ('missing', '缺失'), ('review', '待核')]:
                parts.append('<button type="button" class="fresh-kpi %s" data-filter="%s"><span>%s</span><strong>%d</strong><small>点击筛选</small></button>' % (code, code, label, summary[code]))
            parts.append('<button type="button" class="fresh-kpi total" data-filter="all"><span>全部指标</span><strong>%d</strong><small>重置筛选</small></button></div>' % summary['total'])
            parts.append('<p>分级阈值：日度 7/14 天、周度 10/21 天、月度 45/75 天、季度 150/240 天（正常/关注上限，超过关注即滞后）。月度标签只对应月份，不虚构具体发布日；预测或未来占位进入待核，不按正常数据处理。</p>')
            parts.append('<p>处理纪律：优先本地镜像和人工核定 Excel 原生图绑定；NPI 与精炼镍不混算，金属量与实物量不混用；缺失和滞后均保留真实状态，不补零、不以旧值冒充最新。</p></div></details>')
            parts.append('<div class="fresh-legend">当前显示 <b id="freshCount">%d</b> / %d 项｜点击上方卡片筛选</div>' % (summary['total'], summary['total']))
            parts.append('<div class="tablewrap"><table class="bal fresh-table"><tr><th>模块/指标</th><th>来源与定位</th><th>频率</th><th>单位</th><th>最新标签/值</th><th>新鲜度</th><th>缺口原因与处理</th></tr>')
            for row in freshness['rows']:
                age = '，%d天' % row['age_days'] if row['age_days'] is not None else ''
                parts.append('<tr data-fresh="%s"><td><b>%s</b><br><span class="src-note">%s｜%s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s<br><span class="src-note">%s%s</span></td><td><span class="fresh-badge %s">%s</span></td><td>%s</td></tr>' % (
                    row['status'], esc(row['name']), esc(row['module']), esc(row['key']), esc(row['source']),
                    esc(row['frequency']), esc(row['unit']), esc(row['latest']), esc(row['latest_value']), esc(age),
                    row['status'], esc(row['status_label']), esc(row['action'])))
            parts.append('</table></div>')
        if keys:
            parts.append('<div class="lead">%s · 最新读数逐项标注日期</div>' % esc(title))
            parts.append(chart_group(charts, keys))
        if sid == 'sumsec':
            parts.append('<footer>数据更新至 %s ｜ 镍与不锈钢研究周报 ｜ ⚙️自动构建，仅供研究参考，不构成投资建议。</footer>' % esc(asof))
        parts.append('</div></section>')

    payload = json.dumps({'charts': charts}, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    doc = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><link href="data:," rel="icon">
<title>研究周报 · 镍与不锈钢</title><style>__BASE_CSS__</style><link href="weekly_mobile.css" rel="stylesheet"><link href="weekly_polish.css" rel="stylesheet"><link href="research.css" rel="stylesheet"><link href="../weekly-light.css" rel="stylesheet"><style>.chart-box{height:240px;position:relative}.chart-box canvas{display:block;width:100%;height:100%}.tablewrap{overflow-x:auto}.page-body p{font-size:14.5px}.cbox .stats{line-height:1.55}.fresh-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin:12px 0}.fresh-kpi{border:1px solid var(--line);background:var(--cardbg);padding:10px;text-align:left;cursor:pointer}.fresh-kpi span,.fresh-kpi small{display:block;color:var(--faint);font-size:11px}.fresh-kpi strong{display:block;font-size:25px}.fresh-kpi.fresh strong{color:#188865}.fresh-kpi.watch strong{color:#a3760e}.fresh-kpi.stale strong,.fresh-kpi.missing strong{color:#c44b5d}.fresh-kpi.review strong{color:#7c4dff}.fresh-kpi.active{outline:2px solid var(--blue);outline-offset:1px}.fresh-legend{margin:12px 0;color:var(--grey);font-size:13px}.fresh-badge{display:inline-block;padding:1px 7px;border:1px solid var(--line);white-space:nowrap}.fresh-badge.fresh{color:#188865}.fresh-badge.watch{color:#a3760e}.fresh-badge.stale,.fresh-badge.missing{color:#c44b5d}.fresh-badge.review{color:#7c4dff}.src-note{color:var(--faint);font-size:11px}.fresh-table{min-width:1080px}.fresh-table td{vertical-align:top}@media(max-width:900px){.fresh-grid{grid-template-columns:repeat(3,1fr)}}</style></head>
<body><header class="research-topbar"><div class="research-brand"><a aria-label="返回整合研究站" class="back-home" href="../index.html">← 整合研究站</a><div class="brand-copy"><p class="research-eyebrow">COMMODITY WEEKLY RESEARCH · NICKEL</p><h1>研究周报 <span class="commodity-current">镍</span></h1><p>镍 × 不锈钢 · 周度研究 · 印尼供应 · 库存 · 成本平衡</p></div></div><div class="research-actions"><nav class="commodity-switch" aria-label="品种切换"><a href="../tin-weekly/#sumsec">锡</a><a class="active" href="#sumsec">镍</a><a href="../zinc-weekly/#sumsec">锌</a><a href="../aluminum-weekly/#sumsec">铝</a><a href="../copper-weekly/#sumsec">铜</a><a href="../lead-weekly/#sumsec">铅</a></nav><a class="back-home" href="https://amiya866.github.io/nickel-panel/" target="_blank" rel="noopener">镍市瞭望 ↗</a><span class="research-stamp">数据截至 <b>__ASOF__</b></span><button aria-pressed="false" class="view-toggle" id="viewToggle" type="button">切换手机版</button></div></header>
<div class="research-workspace"><aside class="research-sidebar top-navigation" id="researchSidebar"><button aria-controls="treeNav" aria-expanded="false" class="menu-toggle" id="menuToggle" type="button">研究目录 <span>＋</span></button><div class="sidebar-heading"><span>RESEARCH INDEX</span><b>研究目录</b></div><nav aria-label="镍研究分层目录" class="tree-nav top-nav-inner" id="treeNav"></nav></aside><div class="research-content"><div aria-live="polite" class="breadcrumb" id="breadcrumb"></div><div class="wrap" id="reportWrap">__SECTIONS__</div><section aria-live="polite" class="tool-page" hidden id="toolPage"><div class="tool-head"><div><p class="research-eyebrow">RESEARCH WORKBENCH</p><h2 id="toolTitle">研究工作台</h2></div><button id="closeTool" type="button">← 返回周报</button></div><iframe hidden id="toolFrame" title="镍研究工作台"></iframe></section></div></div>
<script src="lib/chart.min.js"></script><script>const DATA=__PAYLOAD__;const charts=DATA.charts;document.querySelectorAll('canvas[data-chart]').forEach(function(canvas){const c=charts[canvas.dataset.chart];if(!c)return;const ds=(c.datasets||[]).map(function(d){return Object.assign({borderWidth:1.5,pointRadius:0,spanGaps:true},d);});new Chart(canvas,{type:'line',data:{labels:c.labels||[],datasets:ds},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{boxWidth:12,font:{family:'KaiTi,"楷体",serif',size:10}}}},scales:{x:{ticks:{maxTicksLimit:8,font:{family:'KaiTi,"楷体",serif',size:10}},grid:{color:'#e3e3e3'}},y:{ticks:{font:{family:'KaiTi,"楷体",serif',size:10}},grid:{color:'#e3e3e3'}}}}});});</script><script src="weekly_mobile.js"></script><script src="research.js"></script><script>document.querySelectorAll('.fresh-kpi').forEach(function(btn){btn.addEventListener('click',function(){const code=btn.dataset.filter;let shown=0;document.querySelectorAll('.fresh-kpi').forEach(function(x){x.classList.toggle('active',x===btn)});document.querySelectorAll('tr[data-fresh]').forEach(function(row){const visible=code==='all'||row.dataset.fresh===code;row.hidden=!visible;if(visible)shown++});document.getElementById('freshCount').textContent=shown})});</script></body></html>'''
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
