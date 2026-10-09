# -*- coding: utf-8 -*-
"""整合研究站 日更研报生成器（2026-10-09 建）
产出: panels/YYYY-MM-DD.html + reports/YYYY-MM-DD.md + index.html 归档行(AUTO_ARCHIVE 标记处)
手改保护: _daily_report_state.json 记录每次自动产出文件的 sha256;
  文件存在且 hash 匹配 → 覆盖刷新(仍是自动版); hash 不匹配(被手改) → 跳过该文件, 保留手改版
研判基调(主要矛盾/尾部雷达/事前冻结)在 state json 的 narrative 段, 手改它即影响次日及以后产出
数据源: data/*.json(refresh 链产物) + guan kline(15 品种日线, 需 ZHIJI_KEY 或 _local_keys.json)
       + 有色截面配置_2026/_xs_live_payload.json
用法: python _daily_report.py [--date YYYY-MM-DD] [--force]
"""
import os, sys, json, subprocess, hashlib, datetime, math

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
STATE_PATH = os.path.join(BASE, '_daily_report_state.json')
KEYS_PATH = os.path.join(BASE, '_local_keys.json')
XS_PAYLOAD = r'D:\Kimi\有色截面配置_2026\_xs_live_payload.json'
GUAN = 'https://zhiji-ai.xyz/guan/api'

VARIETIES = [  # (代码, 中文名, 分组)
    ('AU', '沪金', '贵金属'), ('AG', '沪银', '贵金属'),
    ('CU', '沪铜', '基本金属'), ('BC', '国际铜', '基本金属'), ('AL', '沪铝', '基本金属'),
    ('AO', '氧化铝', '基本金属'), ('ZN', '沪锌', '基本金属'), ('PB', '沪铅', '基本金属'),
    ('NI', '沪镍', '基本金属'), ('SS', '不锈钢', '基本金属'), ('SN', '沪锡', '基本金属'),
    ('LC', '碳酸锂', '新能源与加工'), ('AD', '铸造铝合金', '新能源与加工'),
    ('SI', '工业硅', '硅链'), ('PS', '多晶硅', '硅链'),
]
GROUP_ORDER = ['贵金属', '基本金属', '新能源与加工', '硅链']

DEFAULT_NARRATIVE = {
    'central_contradiction': 'A 端紧缩再定价（通胀黏性 + 加息/利率路径押注）vs B 端实物资产重估（央行购金、矿端紧张、库存低位）',
    'contradiction_since': '2026-08-28',
    'tail_risks': [
        'FedWatch 加息押注跳升 → 贵金属/铜同步杀估值',
        '白银工业叙事证伪（光伏/电子排产不及）→ 弹性回吐',
        '锌 LME 挤仓二波（注销占比飙升）→ 空配风险',
    ],
    'freezes': [
        ['金箱体震荡，趋势未破', '2-3 周', '守住房顶箱体下沿', '破箱体下沿 + 实际利率显著上行', 'FedWatch/实际利率周度'],
        ['铜偏多回调买入', '2-3 月', '回调获承接', 'TC 连升两周 + 关键支撑破位', '社库周度'],
        ['锌等发令枪后逢高空', '2-3 周', 'Back 走平 + 库存连升后补跌', '注销占比再飙升', 'LME 日报'],
        ['碳酸锂按反弹对待', '2-3 周', '去库连续但仓单不拐头', '站稳关键位 + 减产证真 → 升级', 'SMM 周度'],
        ['锡区间思路，回调做多', '2-3 周', '区间下沿放量承接', '缅甸供给回归 + 社库加速', '海关月报、社库'],
    ],
    'freezes_since': '2026-08-28',
}

def log(*a):
    print(*a, flush=True)

def load_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def zkey():
    k = os.environ.get('ZHIJI_KEY')
    if k:
        return k
    d = load_json(KEYS_PATH) or {}
    return d.get('zhiji_key', '')

def guan_kline(sym, limit=130):
    key = zkey()
    if not key:
        return None
    url = '%s/kline?symbol=%s&freq=D&cont=1&limit=%d' % (GUAN, sym, limit)
    try:
        out = subprocess.run(['curl', '-s', '--ssl-no-revoke', '-H', 'X-Guan-Key: %s' % key, url],
                             capture_output=True, text=True, timeout=40).stdout
        d = json.loads(out)
        rows = d.get('data') or d.get('list') or d
        if isinstance(rows, dict):
            for v in rows.values():
                if isinstance(v, list):
                    rows = v
                    break
        res = []
        for r in rows or []:
            if isinstance(r, dict):
                res.append((str(r.get('date') or r.get('day') or r.get('time'))[:10],
                            float(r.get('close')), float(r.get('volume') or 0)))
            else:
                res.append((str(r[0])[:10], float(r[4]), float(r[5] if len(r) > 5 else 0)))
        return res or None
    except Exception:
        return None

def variety_stats(sym):
    ks = guan_kline(sym)
    if not ks or len(ks) < 25:
        return None
    ks = [k for k in ks if k[1] > 0]
    close, prev = ks[-1][1], ks[-2][1]
    chg = close / prev - 1
    c20 = ks[-21][1]
    chg20 = close / c20 - 1
    win = [k[1] for k in ks[-120:]]
    lo, hi = min(win), max(win)
    pos = (close - lo) / (hi - lo) if hi > lo else 0.5
    vols = [k[2] for k in ks[-21:-1] if k[2] > 0]
    vr = ks[-1][2] / (sum(vols) / len(vols)) if vols and ks[-1][2] > 0 else None
    return {'date': ks[-1][0], 'close': close, 'chg': chg, 'chg20': chg20,
            'pos': pos, 'vol_ratio': vr}

def fmt_pct(x, digits=2, sign=True):
    s = '%+.*f%%' % (digits, x * 100)
    return s if sign else '%.*f%%' % (digits, x * 100)

def fmt_px(v):
    if v >= 10000:
        return format(round(v), ',d')
    if v < 100:
        return format(v, ',.1f')
    return format(round(v), ',d')

def fw_pct(x):
    """FedWatch 概率字段自适应：<=1.5 视为小数乘 100，否则已是百分数"""
    x = x or 0
    return x * 100 if abs(x) <= 1.5 else x

# ---------- 数据汇总 ----------
def collect(today):
    ctx = {'today': today}
    # 品种行情
    vs = {}
    for sym, name, grp in VARIETIES:
        st = variety_stats(sym)
        if st:
            st['name'], st['grp'], st['sym'] = name, grp, sym
            vs[sym] = st
    ctx['varieties'] = vs
    # 宏观快照
    lq = load_json(os.path.join(DATA, 'live_quotes.json')) or {}
    ctx['lq'] = lq.get('quotes', {})
    ctx['lq_asof'] = lq.get('asof', '')
    fw = load_json(os.path.join(DATA, 'fedwatch.json')) or {}
    ctx['fedwatch'] = fw
    cc = load_json(os.path.join(DATA, 'calendar_consensus.json')) or {}
    ctx['cal_events'] = cc.get('events', [])
    gp = load_json(os.path.join(DATA, 'geopolitics.json')) or {}
    ctx['geo'] = gp
    rp = load_json(os.path.join(DATA, 'release_panels.json')) or {}
    ctx['releases'] = rp
    zr = load_json(os.path.join(DATA, 'zsxq_radar.json')) or {}
    ctx['zsxq'] = zr
    xs = load_json(XS_PAYLOAD) or {}
    ctx['xs'] = xs
    return ctx

# ---------- 内容生成 ----------
def upcoming_events(ctx, days=7, min_imp=('High', 'Medium')):
    today = datetime.date.fromisoformat(ctx['today'])
    out = []
    for e in ctx['cal_events']:
        if e.get('imp') not in min_imp:
            continue
        try:
            m, d = e['d'].split('/')
            cand = datetime.date(today.year, int(m), int(d))
            if cand < today - datetime.timedelta(days=30):
                cand = datetime.date(today.year + 1, int(m), int(d))
        except Exception:
            continue
        delta = (cand - today).days
        if 0 <= delta <= days:
            out.append((cand.isoformat(), e.get('tm', ''), e.get('tcn', ''), e.get('imp', '')))
    return sorted(out)

def build_content(ctx):
    vs = ctx['varieties']
    lq = ctx['lq']
    C = {}

    # 01 今日三变：|涨跌| 前三品种 + 宏观补充
    movers = sorted(vs.values(), key=lambda x: -abs(x['chg']))[:3]
    lines = []
    for m in movers:
        vr = '，量能 %.1f 倍' % m['vol_ratio'] if m['vol_ratio'] else ''
        lines.append('**%s %s**（%s，20 日 %s，120 日位置 %.0f%%%s）' % (
            m['name'], fmt_px(m['close']), fmt_pct(m['chg']), fmt_pct(m['chg20']), m['pos'] * 100, vr))
    C['three_changes'] = lines

    # 02 主要矛盾（state 承转 + 自动证据行）
    nar = ctx['narrative']
    ev = []
    fw = ctx['fedwatch']
    if fw.get('meetings'):
        m0 = fw['meetings'][0]
        ev.append('FedWatch（%s）：%s 会议 ease %.0f%% / hike %.0f%%，当前区间 %s' % (
            fw.get('asof', '')[:10], m0.get('meeting', ''), fw_pct(m0.get('ease')),
            fw_pct(m0.get('hike')), fw.get('current_bucket', '')))
    g = lq.get('Y_GOLD', {})
    if g:
        ev.append('现货金 %.0f（%s）；VIX %s；DXY %s' % (
            g.get('price', 0), fmt_pct((g.get('chg_pct') or 0) / 100),
            lq.get('VIXCLS', {}).get('price', '—'), lq.get('Y_DXY', {}).get('price', '—')))
    C['contradiction'] = nar['central_contradiction']
    C['contradiction_since'] = nar.get('contradiction_since', '')
    C['contradiction_ev'] = ev

    # 03 尾部雷达：state + 自动（近 3 日高星事件 / VIX / 地缘新事件）
    tails = list(nar.get('tail_risks', []))
    vix = lq.get('VIXCLS', {}).get('price')
    if isinstance(vix, (int, float)):
        tails.append('VIX %.1f %s 19 降敞口线' % (vix, '已破' if vix > 19 else '低于'))
    for d, tm, t, imp in upcoming_events(ctx, days=3, min_imp=('High',)):
        tails.append('%s %s %s（%s）' % (d[5:], tm, t, imp))
    C['tails'] = tails[:8]

    # 04 宏观模块
    rows = []
    for k, label in [('Y_TNX', '美债10Y'), ('Y_DXY', 'DXY'), ('VIXCLS', 'VIX'),
                     ('Y_GOLD', '现货金'), ('Y_SLV', '现货银'), ('DCOILWTICO', 'WTI'),
                     ('Y_COPPER', 'COMEX铜'), ('Y_GSPC', 'SPX')]:
        q = lq.get(k)
        if q:
            rows.append((label, q.get('price'), q.get('chg_pct'), q.get('sym', '')))
    C['macro_rows'] = rows
    C['fedwatch'] = fw

    # 05 跨资产裁决（20 日动量定调，规则标注）
    verdicts = []
    for sym in ('AU', 'AG', 'CU', 'SN', 'ZN', 'LC'):
        if sym in vs:
            v = vs[sym]
            tag = '偏多' if v['chg20'] > 0.02 else ('偏空' if v['chg20'] < -0.02 else '中性')
            verdicts.append((v['name'], tag, '20 日 %s · 位置 %.0f%%' % (fmt_pct(v['chg20']), v['pos'] * 100)))
    C['verdicts'] = verdicts

    # 06 品种面板
    C['panels'] = vs

    # 07 事件轴
    C['events'] = upcoming_events(ctx, days=7)
    xs = ctx['xs']
    C['xs_today'] = [e for e in (xs.get('events') or []) if e[0] == ctx['today']]
    C['xs'] = xs

    # 08 事前冻结（state 承转, 超 21 天标注重估）
    fr = []
    since = nar.get('freezes_since', '')
    stale = False
    try:
        stale = (datetime.date.fromisoformat(ctx['today']) - datetime.date.fromisoformat(since)).days > 21
    except Exception:
        pass
    for f in nar.get('freezes', []):
        row = list(f)
        if stale:
            row[0] += '（承自 %s，期限已过→待重估）' % since
        fr.append(row)
    C['freezes'] = fr

    # 09 来源
    C['sources'] = [
        '期货行情：知几 guan 日线（%s）' % (max((v['date'] for v in vs.values()), default='—')),
        '宏观快照：%s（%s）' % (ctx['lq_asof'], (load_json(os.path.join(DATA, 'live_quotes.json')) or {}).get('src', '')),
        'FedWatch：%s' % fw.get('asof', '—'),
        '数据发布面板：%s' % (ctx['releases'].get('updated', '—')[:10]),
        '星球雷达：%s' % (ctx['zsxq'].get('asof', '—')),
        '截面策略：%s' % (xs.get('sig_date', '—')),
    ]
    C['narrative_note'] = '主要矛盾/事前冻结承自 %s（state 文件可手改，次日生效）' % nar.get('contradiction_since', '—')
    return C

# ---------- 渲染 ----------
def render_md(ctx, C):
    t = ctx['today']
    L = ['# 整合研究站 日度点评 %s' % t, '',
         '> 自动生成（数据日 %s）；当日手改直接改本文件不会被覆盖；研判基调改 _daily_report_state.json 次日生效。' % t, '']
    L += ['## 01 今日三变（|涨跌|前三）']
    L += ['%d. %s' % (i + 1, x) for i, x in enumerate(C['three_changes'])] + ['']
    L += ['## 02 唯一主要矛盾', '**%s**' % C['contradiction'], '']
    L += ['- %s' % e for e in C['contradiction_ev']] + ['', '_%s_' % C['narrative_note'], '']
    L += ['## 03 尾部风险雷达'] + ['- %s' % x for x in C['tails']] + ['']
    L += ['## 04 宏观模块', '| 指标 | 最新 | 日变动 |', '|---|---|---|']
    L += ['| %s | %s | %s |' % (n, v, fmt_pct((c or 0) / 100)) for n, v, c, _ in C['macro_rows']] + ['']
    fw = C['fedwatch']
    if fw.get('meetings'):
        L += ['FedWatch 路径：' + '；'.join('%s ease %.0f%%/hike %.0f%%' % (m.get('meeting'), fw_pct(m.get('ease')), fw_pct(m.get('hike'))) for m in fw['meetings'][:3]), '']
    L += ['## 05 跨资产裁决（20 日动量规则，⚙️）', '| 品种 | 裁决 | 依据 |', '|---|---|---|']
    L += ['| %s | %s | %s |' % r for r in C['verdicts']] + ['']
    L += ['## 06 品种面板（%d 品种）' % len(C['panels'])]
    for g in GROUP_ORDER:
        L.append('**%s**' % g)
        for sym, name, grp in VARIETIES:
            v = C['panels'].get(sym)
            if v and grp == g:
                vr = ' · 量比 %.1f' % v['vol_ratio'] if v['vol_ratio'] else ''
                L.append('- **%s %s**（%s，20 日 %s，位置 %.0f%%%s）' % (
                    name, fmt_px(v['close']), fmt_pct(v['chg']), fmt_pct(v['chg20']), v['pos'] * 100, vr))
        L.append('')
    L += ['## 07 事件轴（未来 7 日）', '| 日期 | 时间 | 事件 | 重要性 |', '|---|---|---|---|']
    L += ['| %s | %s | %s | %s |' % e for e in C['events']] + ['']
    if C['xs_today']:
        L += ['截面策略今日调仓：' + '；'.join('%s%s' % (e[1], e[2]) for e in C['xs_today']), '']
    L += ['## 08 事前冻结', '| 判断 | 期限 | 成功条件 | 失败/失效条件 | 重估节点 |', '|---|---|---|---|---|']
    L += ['| %s | %s | %s | %s | %s |' % tuple(r) for r in C['freezes']] + ['']
    L += ['## 09 数据来源'] + ['- %s' % s for s in C['sources']] + ['']
    return '\n'.join(L)

PANEL_CSS = """
:root{--bg:#f2efeb;--ink:#16140f;--line:#d9d2c4;--green:#2e7d4f;--amber:#a3760e;--red:#b23a2e;--gray:#9a948a;--mono:'JetBrains Mono',ui-monospace,monospace;--serif:'Noto Serif SC',"Songti SC",serif}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--serif);line-height:1.7}
.wrap{max-width:960px;margin:0 auto;padding:26px 22px}
.hd{border-bottom:2px solid var(--ink);padding-bottom:14px;margin-bottom:8px}
.hd h1{font-size:24px}.hd .meta{font-family:var(--mono);font-size:11.5px;color:var(--gray);margin-top:6px}
section{margin-top:30px}.sec-no{font-family:var(--mono);font-size:11px;color:var(--gray);letter-spacing:.15em}
.sec-t{font-size:18px;font-weight:700;margin:2px 0 10px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{font-family:var(--mono);font-size:11px;color:var(--gray);font-weight:400}
.up{color:var(--red)}.dn{color:var(--green)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.card{border:1px solid var(--line);padding:10px 12px;background:#faf8f4}
.card .nm{font-weight:700}.card .px{font-family:var(--mono);font-size:16px;margin:2px 0}
.card .sub{font-size:11.5px;color:var(--gray)}
.gname{font-size:13px;color:var(--gray);margin:12px 0 6px;font-family:var(--mono)}
.note{font-size:12px;color:var(--gray);margin-top:10px}
ol,ul{padding-left:22px}li{margin-bottom:6px;font-size:14px}
a{color:var(--ink)}
"""

def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def render_panel(ctx, C):
    t = ctx['today']
    h = ['<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>日度面板 %s · 整合研究站</title><style>%s</style></head><body><div class="wrap">' % (t, PANEL_CSS)]
    h.append('<div class="hd"><h1>日度面板 · %s</h1><div class="meta">自动生成 · 数据日 %s · <a href="../index.html">返回总站</a> · <a href="../reports/%s.md">日报 .md</a></div></div>' % (t, t, t))

    h.append('<section><div class="sec-no">01 / THREE CHANGES</div><div class="sec-t">今日三变</div><ol>')
    h += ['<li>%s</li>' % esc(x).replace('**', '') for x in C['three_changes']]
    h.append('</ol></section>')

    h.append('<section><div class="sec-no">02 / CENTRAL CONTRADICTION</div><div class="sec-t">唯一主要矛盾</div>')
    h.append('<p><b>%s</b></p><ul>' % esc(C['contradiction']))
    h += ['<li>%s</li>' % esc(e) for e in C['contradiction_ev']]
    h.append('</ul><p class="note">%s</p></section>' % esc(C['narrative_note']))

    h.append('<section><div class="sec-no">03 / TAIL RADAR</div><div class="sec-t">尾部风险雷达</div><ul>')
    h += ['<li>%s</li>' % esc(x) for x in C['tails']]
    h.append('</ul></section>')

    h.append('<section><div class="sec-no">04 / MACRO</div><div class="sec-t">宏观模块</div><table><tr><th>指标</th><th>最新</th><th>日变动</th></tr>')
    for n, v, c, _s in C['macro_rows']:
        cls = 'up' if (c or 0) > 0 else 'dn'
        h.append('<tr><td>%s</td><td class="num">%s</td><td class="%s">%s</td></tr>' % (esc(n), v, cls, fmt_pct((c or 0) / 100)))
    h.append('</table>')
    fw = C['fedwatch']
    if fw.get('meetings'):
        h.append('<p class="note">FedWatch：' + esc('；'.join('%s ease %.0f%%/hike %.0f%%' % (m.get('meeting'), fw_pct(m.get('ease')), fw_pct(m.get('hike'))) for m in fw['meetings'][:3])) + '</p>')
    h.append('</section>')

    h.append('<section><div class="sec-no">05 / VERDICTS</div><div class="sec-t">跨资产裁决（20 日动量规则 ⚙️）</div><table><tr><th>品种</th><th>裁决</th><th>依据</th></tr>')
    for n, tag, basis in C['verdicts']:
        h.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (esc(n), esc(tag), esc(basis)))
    h.append('</table></section>')

    h.append('<section><div class="sec-no">06 / COMMODITY PANEL</div><div class="sec-t">品种面板 · %d 品种</div>' % len(C['panels']))
    for g in GROUP_ORDER:
        cards = []
        for sym, name, grp in VARIETIES:
            v = C['panels'].get(sym)
            if not v or grp != g:
                continue
            cls = 'up' if v['chg'] > 0 else 'dn'
            vr = ' · 量比 %.1f' % v['vol_ratio'] if v['vol_ratio'] else ''
            cards.append('<div class="card"><div class="nm">%s <span style="color:var(--gray);font-size:11px">%s</span></div>'
                         '<div class="px">%s <span class="%s" style="font-size:13px">%s</span></div>'
                         '<div class="sub">20 日 %s · 120 日位置 %.0f%%%s</div></div>' % (
                             name, sym, fmt_px(v['close']), cls, fmt_pct(v['chg']),
                             fmt_pct(v['chg20']), v['pos'] * 100, vr))
        if cards:
            h.append('<div class="gname">%s</div><div class="cards">%s</div>' % (g, ''.join(cards)))
    h.append('</section>')

    h.append('<section><div class="sec-no">07 / EVENTS</div><div class="sec-t">事件轴 · 未来 7 日</div><table><tr><th>日期</th><th>时间</th><th>事件</th><th>重要性</th></tr>')
    h += ['<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % tuple(map(esc, e)) for e in C['events']]
    h.append('</table>')
    if C['xs_today']:
        h.append('<p class="note">截面策略今日调仓：%s</p>' % esc('；'.join('%s%s' % (e[1], e[2]) for e in C['xs_today'])))
    h.append('</section>')

    h.append('<section><div class="sec-no">08 / PRE-COMMITMENT</div><div class="sec-t">事前冻结</div><table><tr><th>判断</th><th>期限</th><th>成功条件</th><th>失败/失效条件</th><th>重估节点</th></tr>')
    h += ['<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % tuple(esc(x) for x in r) for r in C['freezes']]
    h.append('</table></section>')

    h.append('<section><div class="sec-no">09 / SOURCES</div><div class="sec-t">数据来源</div><ul>')
    h += ['<li>%s</li>' % esc(s) for s in C['sources']]
    h.append('</ul><p class="note">自动面板：数字真实来源如上；叙事行极简仅作结构承转，深度研判以人工版为准。本页手改后自动流程不再覆盖。</p></section>')

    h.append('</div></body></html>')
    return '\n'.join(h)

# ---------- 归档行 ----------
def update_archive(ctx, C):
    idx = os.path.join(BASE, 'index.html')
    s = open(idx, encoding='utf-8').read()
    marker = '<!-- AUTO_ARCHIVE -->'
    if marker not in s:
        log('!! index.html 无 AUTO_ARCHIVE 标记，跳过归档行')
        return
    t = ctx['today']
    if ('panels/%s.html' % t) in s:
        return  # 已有当日行
    row = ('        <tr>\n          <td class="num"><span class="lamp"></span>%s</td>\n'
           '          <td><a class="lnk" href="panels/%s.html">打开面板 ↗</a> '
           '<span class="tag">15 品种</span><span class="tag">自动日更</span></td>\n'
           '          <td><a class="lnk" href="reports/%s.md">日度点评 .md ↗</a></td>\n'
           '          <td style="font-size:12px;color:#4a463e">%s</td>\n        </tr>\n        %s') % (
               t, t, t, esc(C['contradiction'])[:60], marker)
    s = s.replace(marker, row, 1)
    open(idx, 'w', encoding='utf-8').write(s)
    log('归档行已插入 index.html')

# ---------- 主流程（手改保护） ----------
def write_protected(path, content, hashes):
    """返回 'written' / 'kept_manual' / 'unchanged'"""
    h = sha(content)
    if os.path.exists(path):
        cur = sha(open(path, encoding='utf-8').read())
        if cur == h:
            return 'unchanged'
        if hashes.get(os.path.basename(path)) != cur:
            log('保留手改版: %s（hash 与上次自动产出不符）' % os.path.basename(path))
            return 'kept_manual'
    open(path, 'w', encoding='utf-8').write(content)
    hashes[os.path.basename(path)] = h
    return 'written'

def main():
    today = datetime.date.today().isoformat()
    for a in sys.argv[1:]:
        if a.startswith('--date='):
            today = a.split('=', 1)[1]
    force = '--force' in sys.argv

    state = load_json(STATE_PATH) or {}
    nar = state.get('narrative') or DEFAULT_NARRATIVE
    hashes = state.get('hashes') or {}

    ctx = collect(today)
    ctx['narrative'] = nar
    if not ctx['varieties']:
        log('!! 品种行情全空（guan 不可达?），中止不产出')
        return
    C = build_content(ctx)

    md = render_md(ctx, C)
    html = render_panel(ctx, C)
    if force:
        hashes.pop('%s.md' % today, None)
        hashes.pop('%s.html' % today, None)
    r1 = write_protected(os.path.join(BASE, 'reports', '%s.md' % today), md, hashes)
    r2 = write_protected(os.path.join(BASE, 'panels', '%s.html' % today), html, hashes)
    log('report: %s | panel: %s' % (r1, r2))

    if r2 in ('written',) or r1 in ('written',):
        update_archive(ctx, C)

    state['narrative'] = nar
    state['hashes'] = hashes
    state['last_run'] = datetime.datetime.now().strftime('%F %T')
    open(STATE_PATH, 'w', encoding='utf-8').write(json.dumps(state, ensure_ascii=False, indent=1))
    log('state -> %s' % STATE_PATH)

if __name__ == '__main__':
    main()
