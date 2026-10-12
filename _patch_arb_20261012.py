# -*- coding: utf-8 -*-
"""一次性回填 v2：重算 2026-10-12 面板 09 套利段（边际变化版）。
- LME 冻结在 10-09（补 hist 供边际计算，不改最新值）
- arb_prev 种子解析自 10-09 旧面板（判定变化对比基准）
- 表格数值由修复后的管线重算（guan 月差回退 bug 已修）"""
import os, re, types

BASE = os.path.dirname(os.path.abspath(__file__))
m = types.ModuleType('dr')
m.__file__ = os.path.join(BASE, '_daily_report.py')
exec(compile(open(os.path.join(BASE, '_daily_report.py'), encoding='utf-8').read(),
             '_daily_report.py', 'exec'), m.__dict__)

DATE = '2026-10-12'
PREV_PANEL = '2026-10-09'
SYMS = ['CU', 'AL', 'ZN', 'PB', 'NI', 'SN']

state = m.load_json(m.STATE_PATH) or {}
nar = state.get('narrative') or {}
for k, v in m.DEFAULT_NARRATIVE.items():
    nar.setdefault(k, v)

# LME 冻结 10-09：补 hist（≤10-09）供边际计算
lme_cache = m.load_json(m.LME_CACHE) or {}
for sym, field in m.ARB_LME_FIELDS.items():
    pts = m.westmetall_cash3m(field, 2026)
    cur = lme_cache.get(sym) or {}
    cut = cur.get('date', DATE)
    hist = {d: [pts[d][0], pts[d][1]] for d in sorted(pts) if d <= cut}
    cur['hist'] = dict(sorted(hist.items())[-60:])
    lme_cache[sym] = cur
m.lme_cash3m_latest = lambda: lme_cache

# arb_prev 种子：10-09 旧面板的判定列（全文映射到类别，避免金额噪声）
WIN2CAT = [('正套窗口开', '窗口开'), ('纸面窗口', '纸面被吃掉'), ('扣费后微利', '微利'),
           ('盈亏逼近', '临近'), ('进口深亏', '深亏')]
arb_prev = {}
try:
    old = open(os.path.join(BASE, 'panels', '%s.html' % PREV_PANEL), encoding='utf-8').read()
    s = old.index('sec-no">09')
    e = old.index('</section>', s)
    for mt in re.finditer(r'<tr><td>([^<]+)</td>(?:<td[^>]*>[^<]*</td>){4}<td class="\w*">([^<]+)</td></tr>',
                          old[s:e]):
        w = mt.group(2)
        cat = next((c for p, c in WIN2CAT if p in w), '无窗口')
        arb_prev[mt.group(1)] = {'win': w, 'cat': cat, 'date': PREV_PANEL}
except Exception as ex:
    print('!! arb_prev 种子解析失败: %s' % ex)
print('arb_prev 种子:', {k: v['cat'] for k, v in arb_prev.items()})

ctx = {'today': DATE, 'xs': m.load_json(m.XS_PAYLOAD) or {}, 'narrative': nar,
       'varieties': {}, 'arb_prev': arb_prev}
for sym in SYMS:
    ctx['varieties'][sym] = m.variety_stats(sym, asof=DATE)

m.arb_collect(ctx)
C = m.build_arb(ctx)

for r in C['arb']:
    print('%-2s val=%+8.0f roll=%s adj=%s pct=%.0f%% | %s' % (
        r['name'], r['val'],
        format(r['net_roll'], '+,.0f') if r.get('net_roll') is not None else '缺',
        format(r['adj'], '+,.0f') if r.get('adj') is not None else '—',
        r['pct'] * 100, r['win']))
    print('   ', r['fund_auto'][:200])

hp = os.path.join(BASE, 'panels', '%s.html' % DATE)
html = open(hp, encoding='utf-8').read()
s = html.index('<section><div class="sec-no">09 / ARBITRAGE')
e = html.index('</section>', s) + len('</section>')
new_sec = ''.join(m.arb_html_lines(C))
open(hp, 'w', encoding='utf-8').write(html[:s] + new_sec + html[e:])
print('panel spliced: %d -> %d bytes' % (e - s, len(new_sec)))

mp = os.path.join(BASE, 'reports', '%s.md' % DATE)
md = open(mp, encoding='utf-8').read()
s = md.index('## 09 ')
e = md.index('## 10 ')
new_md = '\n'.join(m.arb_md_lines(C))
open(mp, 'w', encoding='utf-8').write(md[:s] + new_md + md[e:])
print('md spliced')

# 写 state 快照：明日日更的边际对比基准 = 本期
state['arb_prev'] = {r['name']: {'win': r['win'], 'cat': r.get('win_cat'),
                                 'adj': r.get('adj'), 'val': r['val'], 'date': DATE}
                     for r in C['arb']}
open(m.STATE_PATH, 'w', encoding='utf-8').write(__import__('json').dumps(state, ensure_ascii=False, indent=1))
print('state arb_prev <- %s' % DATE)
