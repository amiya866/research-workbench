#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日财经图集生成器 —— 全部用自有管线数据(chart_series.js)绘制, 版权自有
产物: charts/*.png + charts/catalog.json
分类: rates(利率美债) / fx(美元外汇) / cmdty(商品贵金属) / liq(流动性) / cn(中国资产)
"""
import json, os, re, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
for _f in ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
           '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'):
    try: font_manager.fontManager.addfont(_f)
    except Exception: pass
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'WenQuanYi Zen Hei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BASE = os.path.dirname(os.path.abspath(__file__))
APP  = os.path.dirname(BASE)
OUT  = os.path.join(APP, 'charts')
os.makedirs(OUT, exist_ok=True)

raw = open(os.path.join(APP, 'data', 'chart_series.js'), encoding='utf-8').read()
CS = json.loads(raw[raw.find('{'):raw.rfind('}') + 1])

BG, FG, DIM, LINE = '#10131a', '#d5dae4', '#8a94a6', '#232a38'
GOLD, UP, DN, BLU, PUR = '#d4a944', '#e5534b', '#4caf7d', '#5b9bd5', '#b08ad9'
plt.rcParams.update({
    'figure.facecolor': BG, 'axes.facecolor': BG, 'savefig.facecolor': BG,
    'axes.edgecolor': LINE, 'axes.labelcolor': DIM, 'text.color': FG,
    'xtick.color': DIM, 'ytick.color': DIM, 'grid.color': LINE,
    'font.size': 10, 'axes.titlesize': 13, 'axes.titleweight': 'bold',
})

def ser(key, days=380):
    d = CS.get(key) or []
    d = d[-days:] if len(d) > days else d
    xs = [datetime.datetime.strptime(a, '%Y-%m-%d') for a, _ in d]
    ys = [b for _, b in d]
    return xs, ys

def style(ax, title, sub):
    ax.set_title(title, loc='left', color=FG, pad=14)
    ax.text(0, 1.02, sub, transform=ax.transAxes, color=DIM, fontsize=8.5)
    ax.grid(alpha=.35, linewidth=.6)
    ax.spines[['top', 'right']].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))

def footer(fig, src):
    fig.text(0.01, 0.012, '来源: ' + src + ' · 研究框架自建图集 · 每日管线自动重绘', color=DIM, fontsize=8)
    fig.text(0.99, 0.012, datetime.datetime.utcnow() + datetime.timedelta(hours=8) and
             (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d'), color=DIM, fontsize=8, ha='right')

def save(fig, name):
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.savefig(os.path.join(OUT, name + '.png'), dpi=110)
    plt.close(fig)
    print('  √', name, flush=True)

CATS = [
    ('rates', '利率·美债'), ('fx', '美元·外汇'), ('cmdty', '商品·贵金属'),
    ('liq', '流动性'), ('cn', '中国资产'),
]
catalog = []

def reg(fn, cat, title, sub):
    catalog.append({'file': fn + '.png', 'cat': cat, 'title': title, 'sub': sub})

# 1 美债三期限
xs10, y10 = ser('DGS10'); xs2, y2 = ser('DGS2'); xs30, y30 = ser('DGS30')
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xs10, y10, color=GOLD, lw=1.6, label='10Y')
ax.plot(xs2, y2, color=BLU, lw=1.4, label='2Y')
ax.plot(xs30, y30, color=PUR, lw=1.4, label='30Y')
ax.legend(frameon=False, loc='upper left', fontsize=9)
style(ax, '美债收益率 · 关键期限', '10Y / 2Y / 30Y 近一年走势 · L1 FRED')
footer(fig, 'FRED(财政部H.15)'); save(fig, 'ust_yields'); reg('ust_yields', 'rates', '美债收益率·关键期限', '10Y/2Y/30Y')

# 2 利差
xsa, ya = ser('T10Y2Y'); xsb, yb = ser('T10Y3M')
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xsa, [v * 100 for v in ya], color=GOLD, lw=1.6, label='10Y-2Y')
ax.plot(xsb, [v * 100 for v in yb], color=BLU, lw=1.4, label='10Y-3M')
ax.axhline(0, color=DIM, lw=.8, ls='--')
ax.legend(frameon=False, loc='upper left', fontsize=9)
style(ax, '美债期限利差(bp)', '曲线形态: 走陡=熊陡(加息定价) / 走平=衰退定价 · L1 FRED')
footer(fig, 'FRED'); save(fig, 'ust_spread'); reg('ust_spread', 'rates', '美债期限利差', '10Y-2Y 与 10Y-3M(bp)')

# 3 实际利率 vs 黄金
xsr, yr = ser('DFII10'); xsg, yg = ser('Y_GOLD', 380)
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xsr, yr, color=GOLD, lw=1.6, label='10Y实际利率(左,%)')
ax2 = ax.twinx(); ax2.plot(xsg, yg, color=UP, lw=1.3, alpha=.9, label='COMEX黄金(右)')
ax2.spines[['top']].set_visible(False); ax2.tick_params(colors=DIM)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc='upper left', fontsize=9)
style(ax, '实际利率 vs 黄金', '框架核心矛盾: 实际利率压估值 vs 实物重估 · L1 FRED + L2行情')
footer(fig, 'FRED + Yahoo'); save(fig, 'realrate_gold'); reg('realrate_gold', 'cmdty', '实际利率vs黄金', '框架核心矛盾双轴')

# 4 美元与日元
xsd, yd = ser('Y_DXY'); xsj, yj = ser('Y_USDJPY')
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xsd, yd, color=GOLD, lw=1.6, label='美元指数DXY(左)')
ax2 = ax.twinx(); ax2.plot(xsj, yj, color=BLU, lw=1.3, label='USDJPY(右)')
ax2.spines[['top']].set_visible(False); ax2.tick_params(colors=DIM)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc='upper left', fontsize=9)
style(ax, '美元指数 vs 日元', '紧缩型走强: 息差驱动 · L2 行情')
footer(fig, 'Yahoo Finance'); save(fig, 'dxy_jpy'); reg('dxy_jpy', 'fx', '美元指数vs日元', '紧缩型走强双轴')

# 5 油价
xsw, yw = ser('DCOILWTICO'); xsb2, yb2 = ser('DCOILBRENTEU')
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xsw, yw, color=GOLD, lw=1.6, label='WTI现货')
ax.plot(xsb2, yb2, color=UP, lw=1.4, label='Brent现货')
ax.legend(frameon=False, loc='upper left', fontsize=9)
style(ax, '原油现货价格(美元/桶)', '霍尔木兹海峡2/28起关闭 · EIA日度现货(发布滞后约1周) · L1 EIA')
footer(fig, 'EIA via FRED'); save(fig, 'oil'); reg('oil', 'cmdty', '原油现货价格', 'WTI/Brent·霍尔木兹溢价')

# 6 流动性: SOFR-IORB
xss, ys_ = ser('SPR_SOFR_IORB', 500)
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xss, ys_, color=PUR, lw=1.5)
ax.axhline(0, color=DIM, lw=.8, ls='--'); ax.axhline(10, color=UP, lw=.8, ls=':')
ax.text(xss[2], 10.5, '警报线 10bp', color=UP, fontsize=8.5)
style(ax, 'SOFR-IORB 利差(bp)', '货币市场压力温度计: >0=压力积聚 · ⚙️自建(FRED计算)')
footer(fig, 'FRED ⚙️计算'); save(fig, 'sofr_iorb'); reg('sofr_iorb', 'liq', 'SOFR-IORB利差', '货币市场压力温度计')

# 7 ON RRP与准备金
xsr2, yr2 = ser('RRPONTSYD', 500); xsw2, yw2 = ser('WRESBAL', 500)
fig, ax = plt.subplots(figsize=(9, 4.6))
if xsr2: ax.plot(xsr2, [v for v in yr2], color=BLU, lw=1.5, label='ON RRP(十亿$,左)')
if xsw2:
    ax2 = ax.twinx(); ax2.plot(xsw2, [v / 1000 for v in yw2], color=GOLD, lw=1.3, label='准备金(万亿$,右)')
    ax2.spines[['top']].set_visible(False); ax2.tick_params(colors=DIM)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc='upper right', fontsize=9)
style(ax, 'ON RRP 与 银行准备金', '缓冲垫: RRP近枯竭后准备金直接承压 · L1 FRED/NYFed')
footer(fig, 'FRED · NYFed H.4.1'); save(fig, 'rrp_reserves'); reg('rrp_reserves', 'liq', 'ON RRP与准备金', '缓冲垫消耗双轴')

# 8 中美利差
xsc, yc = ser('SPR_USCN10Y', 500)
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xsc, [v * 100 for v in yc], color=UP, lw=1.5)
ax.axhline(0, color=DIM, lw=.8, ls='--')
style(ax, '中美10Y利差(美-中, bp)', '倒挂深度=人民币外压计 · ⚙️自建(FRED-中债)')
footer(fig, 'FRED + 中债 ⚙️计算'); save(fig, 'us_cn_spread'); reg('us_cn_spread', 'cn', '中美10Y利差', '倒挂深度(bp)')

# 9 FedWatch加息概率(柱状)
try:
    fw = json.load(open(os.path.join(APP, 'data', 'fedwatch.json'), encoding='utf-8'))
    ms = fw['meetings'][:6]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = range(len(ms))
    ax.bar([i - .2 for i in x], [m['hike'] for m in ms], width=.4, color=UP, label='加息')
    ax.bar([i + .2 for i in x], [m['no_change'] for m in ms], width=.4, color=BLU, label='维持')
    ax.set_xticks(list(x)); ax.set_xticklabels([m['meeting'] for m in ms], fontsize=8.5)
    ax.legend(frameon=False, loc='upper right', fontsize=9)
    style(ax, 'CME FedWatch · 各会议概率(%)', '截至 ' + fw.get('asof', '') + ' · L2·交易所口径')
    footer(fig, 'CME FedWatch(官方抓取)'); save(fig, 'fedwatch'); reg('fedwatch', 'rates', 'FedWatch各会议概率', '加息/维持(%)')
except Exception as e:
    print('  x fedwatch', repr(e)[:80], flush=True)

# 10 金银比
xsgs, ygs = ser('GOLD_SILVER_RATIO', 500)
if xsgs:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(xsgs, ygs, color=GOLD, lw=1.5)
    style(ax, '金银比', '避险/美元信用温度计: 上行=防御 · ⚙️自建(金/银)')
    footer(fig, 'Yahoo ⚙️计算'); save(fig, 'gold_silver'); reg('gold_silver', 'cmdty', '金银比', '避险温度计')

json.dump({'asof': (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M BJT'),
           'cats': CATS, 'charts': catalog},
          open(os.path.join(OUT, 'catalog.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('完成:', len(catalog), '张图', flush=True)
