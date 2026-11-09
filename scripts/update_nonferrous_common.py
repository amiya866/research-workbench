#!/usr/bin/env python3
import html
import json
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
PAGE = BASE / 'reports' / 'daily_latest.html'
BEGIN = '<!-- NONFERROUS_COMMON_BEGIN -->'
END = '<!-- NONFERROUS_COMMON_END -->'


def esc(value):
    return html.escape(str(value), quote=True)


def load_series():
    text = (DATA / 'chart_series.js').read_text(encoding='utf-8')
    return json.loads(text[text.index('{'):text.rindex('}') + 1])


def futures_close(symbol):
    url = ('https://stock2.finance.sina.com.cn/futures/api/jsonp.php/x/'
           'InnerFuturesNewService.getDailyKLine?symbol=' + symbol)
    raw = subprocess.run(['curl', '-s', '--max-time', '25', url], capture_output=True,
                         timeout=35, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    text = raw.stdout.decode('utf-8', 'replace')
    match = re.search(r'\((\[.*\])\)', text, re.S)
    if not match:
        raise RuntimeError('新浪期货日线无有效数据: ' + symbol)
    rows = json.loads(match.group(1))
    return {row['d']: float(row['c']) for row in rows if row.get('d') and row.get('c')}


def line_chart(label, points):
    points = [[d, v] for d, v in points if d and v is not None]
    if len(points) < 2:
        raise RuntimeError('图表有效数据不足: ' + label)
    return {'labels': [p[0] for p in points],
            'datasets': [{'label': label, 'data': [p[1] for p in points]}]}


def relative_chart(label, numerator, denominator):
    dates = sorted(d for d in numerator.keys() & denominator.keys() if d >= '2024-01-02')
    if len(dates) < 100:
        raise RuntimeError('期货共同交易日不足: ' + label)
    ratios = [(d, numerator[d] / denominator[d]) for d in dates]
    base = ratios[0][1]
    return line_chart(label, [[d, round(value / base, 4)] for d, value in ratios])


def last(chart):
    return chart['labels'][-1], chart['datasets'][0]['data'][-1]


def fmt_date(date):
    return '%d/%d' % (int(date[5:7]), int(date[8:10]))


def pct_change(values, periods):
    if len(values) <= periods:
        return None
    return (values[-1] / values[-1 - periods] - 1) * 100


def pct_text(value):
    return '—' if value is None else ('%+.2f%%' % value)


def render(charts, cpi_period):
    us10y = charts['c_us10y.png']['datasets'][0]['data']
    us10y_dates = charts['c_us10y.png']['labels']
    dxy = charts['c_dxy.png']['datasets'][0]['data']
    wti = charts['c_wti.png']['datasets'][0]['data']
    sox = charts['m_sox.png']['datasets'][0]['data']
    sox_dates = charts['m_sox.png']['labels']
    us10y_bp = (us10y[-1] - us10y[-21]) * 100 if len(us10y) > 20 else None
    macro_facts = (
        '美债10Y %s 为 %.2f%%，近20交易日 %s；广义美元指数最新 %.4f；WTI最新 %.2f 美元/桶。'
        '核心CPI为BLS官方非季调同比，%s 为 %.2f%%。'
        % (fmt_date(us10y_dates[-1]), us10y[-1],
           '—' if us10y_bp is None else '%+.0f bp' % us10y_bp,
           dxy[-1], wti[-1], cpi_period, charts['c_cpi.png']['datasets'][0]['data'][-1]))
    sox_facts = ('SOX %s 收 %.2f 点，近5交易日 %s、近20交易日 %s。'
                 '本段按每日行情自动生成，不再沿用上期周报点位或财报日历。'
                 % (fmt_date(sox_dates[-1]), sox[-1], pct_text(pct_change(sox, 5)),
                    pct_text(pct_change(sox, 20))))
    specs = [
        ('c_cpi.png', '美国核心CPI同比（%，月，BLS非季调）'),
        ('c_us10y.png', '美债10Y收益率（%）'),
        ('c_dxy.png', '广义贸易加权美元指数（FRED，周度）'),
        ('c_wti.png', 'WTI原油（美元/桶）'),
        ('c_cusn.png', '铜锡相对强弱（SHFE主力，2024-01-02=1）'),
        ('c_agsn.png', '银锡相对强弱（SHFE主力，2024-01-02=1）'),
    ]
    parts = [BEGIN,
             '<div class="card" id="nonferrousCommon" style="border-left:3px solid var(--blue);margin:14px 0;">',
             '<h3 style="color:var(--blue);margin-bottom:6px;">有色共性前瞻 · 每日独立重建</h3>',
             '<p style="font-size:12px;color:var(--dim);">本站每日管线独立生成，不再依赖上游周报：宏观=FRED/新浪，商品比值=新浪SHFE主力收盘价共同交易日对齐并归一化，SOX=新浪美股，核心CPI=BLS非季调。各图最新日期分别标注。</p>',
             '<h4 style="color:var(--gold);margin:14px 0 5px;">宏观与跨资产</h4>',
             '<p style="font-size:12.5px;line-height:1.8;"><b>每日数据：</b>%s</p>' % esc(macro_facts),
             '<p style="font-size:12.5px;line-height:1.8;"><b>共性策略含义：</b>利率、美元和油价用于观察有色共同的估值与风险预算；铜锡、银锡相对强弱只比较主力合约价格表现，不代表供需平衡或跨品种套利建议。</p>',
             '<div class="grid2">']
    for index, (key, title) in enumerate(specs, 1):
        date, value = last(charts[key])
        footer = ('官方最新披露期 ' if key == 'c_cpi.png' else '最新 ') + date + ' ｜ ' + str(value)
        parts.append('<div class="mini"><h4>%s</h4><div id="nfCommon%d" data-nf-chart="%s" style="height:220px;"></div><div style="font-size:11px;color:var(--dim);">%s</div></div>'
                     % (esc(title), index, esc(key), esc(footer)))
    date, value = last(charts['m_sox.png'])
    parts.extend(['</div>',
                  '<h4 style="color:var(--gold);margin:14px 0 5px;">美股与半导体 AI</h4>',
                  '<p style="font-size:12.5px;line-height:1.8;"><b>每日数据：</b>%s</p>' % esc(sox_facts),
                  '<p style="font-size:12.5px;line-height:1.8;"><b>共性策略含义：</b>SOX用于跟踪半导体风险偏好，对锡焊料预期的传导更直接；它不能替代实际订单、收入和经营现金流验证。</p>',
                  '<div class="grid2">',
                  '<div class="mini"><h4>费城半导体指数（SOX）</h4><div id="nfCommon7" data-nf-chart="m_sox.png" style="height:220px;"></div><div style="font-size:11px;color:var(--dim);">最新 %s ｜ %s</div></div>' % (esc(date), value),
                  '</div></div>'])
    script = '''<script>window.NF_COMMON_CHARTS=PAYLOAD;(function(){const charts={};function draw(){document.querySelectorAll("[data-nf-chart]").forEach(function(el){if(!el.offsetParent)return;const c=window.NF_COMMON_CHARTS[el.dataset.nfChart];if(!c)return;const chart=charts[el.id]||(charts[el.id]=echarts.init(el));chart.setOption({animation:false,grid:{left:55,right:16,top:20,bottom:42},tooltip:{trigger:"axis"},xAxis:{type:"category",data:c.labels||[],axisLabel:{fontSize:10}},yAxis:{type:"value",scale:true},series:(c.datasets||[]).map(function(d){return{name:d.label,type:"line",data:d.data||[],showSymbol:false,connectNulls:true,lineStyle:{width:1.5}}})},true);chart.resize();});}window.addEventListener("resize",draw);document.querySelectorAll(".dtabs button").forEach(function(btn){btn.addEventListener("click",function(){setTimeout(draw,50);});});draw();})();</script>'''
    payload = json.dumps(charts, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    parts.append(script.replace('PAYLOAD', payload))
    parts.append(END)
    return '\n'.join(parts)


def main():
    series = load_series()
    for key in ('DGS10', 'DTWEXBGS', 'DCOILWTICO', 'Y_SOX'):
        if len(series.get(key) or []) < 2:
            raise RuntimeError('宏观序列缺失: ' + key)
    releases = json.loads((DATA / 'release_panels.json').read_text(encoding='utf-8'))
    cpi = releases['blocks']['cpi']
    cpi_history = cpi.get('core_yoy_history') or []
    if len(cpi_history) < 12:
        raise RuntimeError('BLS核心CPI非季调同比历史缺失')
    cu, sn, ag = (futures_close(symbol) for symbol in ('CU0', 'SN0', 'AG0'))
    charts = {
        'c_cpi.png': line_chart('核心CPI同比', cpi_history),
        'c_us10y.png': line_chart('美债10Y', series['DGS10']),
        'c_dxy.png': line_chart('美元指数', series['DTWEXBGS']),
        'c_wti.png': line_chart('WTI原油', series['DCOILWTICO']),
        'c_cusn.png': relative_chart('铜锡相对强弱', cu, sn),
        'c_agsn.png': relative_chart('银锡相对强弱', ag, sn),
        'm_sox.png': line_chart('SOX', series['Y_SOX']),
    }
    block = render(charts, cpi['period'])
    page = PAGE.read_text(encoding='utf-8')
    pattern = re.escape(BEGIN) + r'.*?' + re.escape(END)
    if not re.search(pattern, page, re.S):
        raise RuntimeError('日报缺少有色共性区锚点')
    page = re.sub(pattern, lambda _match: block, page, count=1, flags=re.S)
    temporary = PAGE.with_suffix('.html.tmp')
    temporary.write_text(page, encoding='utf-8')
    temporary.replace(PAGE)
    print('有色共性区独立重建:', ', '.join('%s=%s' % (key, last(chart)[0]) for key, chart in charts.items()))


if __name__ == '__main__':
    main()
