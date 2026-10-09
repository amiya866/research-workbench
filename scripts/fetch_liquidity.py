#!/usr/bin/env python3
# 美元流动性追踪 → data/chart_series.js (流动性键) + data/liquidity.json (日度看板)
# 框架来源: GMF美元流动性体系 —— 广义(美元指数/真实利率/HY利差/VIX >2σ信号) + 狭义(在岸拆借/离岸/央行投放/财政/银行/MM基金)
# 数据源(全部免费免key):
#   FRED fredgraph.csv : SOFR/SOFR99/TGCRRATE/IORB/RRPONTSYAWARD/RRPONTSYD/WRESBAL/WTREGEN/WALCL/WREPOFOR/SWPT/DCPF1M/M2SL/ECBASSETSW/JPNASSETS/VIXCLS/BAMLH0A0HYM2/DFII10/DTWEXBGS
#   NY Fed Markets API : SRF常备回购便利用量 (last/520.json ≈ 近1年)
#   ECB Data Portal    : 欧元区M3 (BSI M.U2.Y.V.M30...)
#   东方财富API        : 中国M2/M1 (PBOC口径, L3·第三方转载官方数)
# 缺口(标灰, 不分配权重): XCCY互换基差/贴现窗口借款量/一级交易商持仓/高盛FCI/日本M2现行/英加M2/CP-OIS真实值
import json, re, os, io, csv, datetime, urllib.request, time, math

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(APP, 'data')
CS_PATH = os.path.join(DATA, 'chart_series.js')
OUT_JSON = os.path.join(DATA, 'liquidity.json')
START = '2019-01-01'
TAIL = 350

def log(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)

try:
    import requests as _rq
except Exception:
    _rq = None

def http_get(url, timeout=40, retries=3, quiet=False):
    for i in range(retries):
        try:
            if _rq is not None:
                r = _rq.get(url, headers={'User-Agent': 'python-requests/2.31.0'}, timeout=timeout)
                if r.status_code == 200: return r.content
                raise Exception('HTTP %s' % r.status_code)
            req = urllib.request.Request(url, headers={'User-Agent': 'python-requests/2.31.0'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if not quiet: log('  重试%d %s %s' % (i + 1, url[:70], repr(e)[:70]))
            time.sleep(2 + 2 * i)
    return None

def fred(sid):
    """FRED fredgraph.csv → [(date,val)] 全历史"""
    raw = http_get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s' % (sid, START), timeout=60, retries=4)
    if not raw: return []
    out = []
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8', 'ignore'))):
        v = row.get(sid, '.')
        if v in ('.', '', None): continue
        try: out.append((row['observation_date'], float(v)))
        except Exception: pass
    return out

# ---- FRED 序列注册: (键, FRED ID, 名称, 单位, 来源) ----
FRED_S = [
    ('SOFR',          'SOFR',          'SOFR担保隔夜融资利率', '%',      'L1·FRED/NYFed'),
    ('SOFR99',        'SOFR99',        'SOFR第99分位(尾部)',   '%',      'L1·FRED/NYFed'),
    ('TGCRRATE',      'TGCRRATE',      'TGCR三方回购中位利率', '%',      'L1·FRED/NYFed'),
    ('IORB',          'IORB',          '准备金利率IORB',       '%',      'L1·FRED'),
    ('DFF',           'DFF',           'EFFR联邦基金有效利率', '%',      'L1·FRED'),
    ('RRPONTSYAWARD', 'RRPONTSYAWARD', 'ON RRP中标利率',       '%',      'L1·FRED/NYFed'),
    ('RRPONTSYD',     'RRPONTSYD',     'ON RRP余额',           '十亿美元','L1·FRED/NYFed'),
    ('WRESBAL',       'WRESBAL',       '银行准备金余额',       '百万美元','L1·FRED/H.4.1'),
    ('WTREGEN',       'WTREGEN',       '财政部TGA余额',        '百万美元','L1·FRED/H.4.1'),
    ('WALCL',         'WALCL',         '美联储总资产',         '百万美元','L1·FRED/H.4.1'),
    ('WREPOFOR',      'WREPOFOR',      '外国官方逆回购池(FIMA)','百万美元','L1·FRED/H.4.1'),
    ('SWPT',          'SWPT',          '央行流动性互换余额',   '百万美元','L1·FRED/H.4.1'),
    ('DCPF1M',        'DCPF1M',        '1M AA金融商票利率',    '%',      'L1·FRED'),
    ('VIXCLS',        'VIXCLS',        'VIX波动率',            '点',     'L1·FRED/CBOE'),
    ('BAMLH0A0HYM2',  'BAMLH0A0HYM2',  '高收益债OAS',          '%',      'L1·FRED/ICE'),
    ('DFII10',        'DFII10',        '10Y实际利率TIPS',      '%',      'L1·FRED'),
    ('DTWEXBGS',      'DTWEXBGS',      '广义贸易加权美元指数', '点',     'L1·FRED'),
    ('M2SL',          'M2SL',          '美国M2(季调)',         '十亿美元','L1·FRED'),
    ('ECBASSETSW',    'ECBASSETSW',    '欧央行总资产',         '百万欧元','L1·FRED/ECB'),
    ('JPNASSETS',     'JPNASSETS',     '日央行总资产',         '十亿日元','L1·FRED/BOJ'),
]

def load_cs():
    if not os.path.exists(CS_PATH): return {}
    raw = open(CS_PATH, encoding='utf-8').read()
    m = re.search(r'window\.CHART_SERIES\s*=\s*(\{.*\})\s*;?\s*$', raw, re.S)
    return json.loads(m.group(1)) if m else {}

def save_cs(cs):
    tmp = CS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('window.CHART_SERIES = ' + json.dumps(cs, ensure_ascii=False, separators=(',', ':')) + ';')
    os.replace(tmp, CS_PATH)

def tail(s, n=TAIL): return s[-n:] if len(s) > n else s

def to_map(s): return {d: v for d, v in s}

def align_sub(a, b, scale=1.0):
    """按日期交集 (a-b)*scale → [(d,v)]"""
    bm = to_map(b); out = []
    for d, v in a:
        if d in bm: out.append((d, (v - bm[d]) * scale))
    return out

def yoy(s, per):
    out = []
    for i in range(per, len(s)):
        base = s[i - per][1]
        if base != 0:
            out.append((s[i][0], (s[i][1] / base - 1) * 100))
    return out

def pct_rank(full_series, value):
    """value在full_series(值列表)中的分位 0-100"""
    vals = sorted(v for _, v in full_series)
    if not vals: return None
    import bisect
    return round(bisect.bisect_left(vals, value) / len(vals) * 100, 1)

def chg(s, n):
    return (s[-1][1] - s[-1 - n][1]) if len(s) > n else None

def ffill_to_daily(*series_list):
    """多条序列按并集日期前向填充对齐 → 日期列表 + 各序列填充值"""
    ds = sorted(set().union(*[set(to_map(s).keys()) for s in series_list]))
    out = []
    curs = [None] * len(series_list)
    its = [sorted(s) for s in series_list]
    idx = [0] * len(series_list)
    for d in ds:
        for k, s in enumerate(its):
            while idx[k] < len(s) and s[idx[k]][0] <= d:
                curs[k] = s[idx[k]][1]; idx[k] += 1
        if all(c is not None for c in curs):
            out.append((d, list(curs)))
    return out

def ecb_m3():
    """欧央行M3 → [(d, 万亿欧元)]"""
    u = 'https://data-api.ecb.europa.eu/service/data/BSI/M.U2.Y.V.M30.X.1.U2.2300.Z01.E?format=csvdata'
    raw = http_get(u, timeout=50)
    if not raw: return []
    out = []
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8', 'ignore'))):
        try: out.append((row['TIME_PERIOD'] + '-01', float(row['OBS_VALUE'])))
        except Exception: pass
    out.sort()
    if out and out[-1][1] > 1e9:   # 单位欧元 → 万亿
        out = [(d, v / 1e12) for d, v in out]
    return out

def cn_money():
    """东财中国货币供应 → {key:[(d,v)]} M2/M1(万亿元) + 同比(%)"""
    u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_CURRENCY_SUPPLY'
         '&columns=ALL&pageNumber=1&pageSize=400&sortColumns=REPORT_DATE&sortTypes=-1')
    raw = http_get(u)
    res = {'LIQ_CNM2': [], 'LIQ_CNM1': [], 'LIQ_CNM2_YOY': [], 'LIQ_CNM1_YOY': []}
    if not raw: return res
    try: data = json.loads(raw.decode('utf-8', 'ignore'))['result']['data']
    except Exception: return res
    rows = sorted(data, key=lambda r: r['REPORT_DATE'])
    for r in rows:
        d = r['REPORT_DATE'][:10]
        try:
            if r.get('BASIC_CURRENCY'): res['LIQ_CNM2'].append((d, round(r['BASIC_CURRENCY'] / 1e4, 2)))
            if r.get('CURRENCY'):       res['LIQ_CNM1'].append((d, round(r['CURRENCY'] / 1e4, 2)))
            if r.get('BASIC_CURRENCY_SAME') is not None: res['LIQ_CNM2_YOY'].append((d, r['BASIC_CURRENCY_SAME']))
            if r.get('CURRENCY_SAME') is not None:       res['LIQ_CNM1_YOY'].append((d, r['CURRENCY_SAME']))
        except Exception: pass
    return res

def srf_usage():
    """NY Fed SRF常备回购用量 → [(d, 十亿美元)] (近约1年)"""
    raw = http_get('https://markets.newyorkfed.org/api/rp/repo/all/results/last/520.json')
    if not raw: return []
    try: ops = json.loads(raw.decode('utf-8', 'ignore'))['repo']['operations']
    except Exception: return []
    agg = {}
    for o in ops:
        d = o.get('operationDate'); amt = o.get('totalAmtAccepted') or 0
        if d: agg[d] = agg.get(d, 0) + amt / 1e9
    return sorted(agg.items())

def main():
    os.makedirs(DATA, exist_ok=True)
    cs = load_cs()
    series = {}   # 键 → [(d,v)] 全历史
    fails = []

    log('== 1/5 FRED 流动性序列 ==')
    for key, fid, name, unit, src in FRED_S:
        s = fred(fid)
        if len(s) >= 3:
            series[key] = s
            log('  %s n=%d last=%s' % (key, len(s), s[-1]))
        else:
            fails.append(key); log('  %s 失败' % key)
        time.sleep(0.4)

    log('== 2/5 ECB M3 / 中国M2 / SRF ==')
    ez = ecb_m3()
    if ez: series['LIQ_EZM3'] = ez; log('  LIQ_EZM3 n=%d last=%s' % (len(ez), ez[-1]))
    else: fails.append('LIQ_EZM3')
    cnm = cn_money()
    for k, s in cnm.items():
        if s: series[k] = s; log('  %s n=%d last=%s' % (k, len(s), s[-1]))
        else: fails.append(k)
    srf = srf_usage()
    if srf: series['LIQ_SRF'] = srf; log('  LIQ_SRF n=%d last=%s 年内峰值=%.2fbn' % (len(srf), srf[-1], max(v for _, v in srf)))
    else: fails.append('LIQ_SRF')

    # MOVE美债波动率: Y_MOVE(Yahoo ^MOVE日度, fetch_macro每日刷新) + EDB_GLB_MOVE(L3·第三方终端EDB快照底座) 拼接去重
    mv = {}
    for k in ('EDB_GLB_MOVE', 'Y_MOVE'):
        for d_, v in (cs.get(k) or []):
            if v: mv[d_] = float(v)
    if mv:
        series['MOVE_X'] = sorted(mv.items())
        log('  MOVE_X n=%d last=%s' % (len(series['MOVE_X']), series['MOVE_X'][-1]))
    else:
        fails.append('MOVE_X')

    log('== 3/5 衍生利差/同比 ⚙️ ==')
    d = {}
    def has(k): return k in series and len(series[k]) >= 3
    if has('SOFR') and has('IORB'):          d['SPR_SOFR_IORB']  = align_sub(series['SOFR'], series['IORB'], 100)
    if has('TGCRRATE') and has('IORB'):      d['SPR_TGCR_IORB']  = align_sub(series['TGCRRATE'], series['IORB'], 100)
    if has('SOFR') and has('DFF'):           d['SPR_SOFR_EFFR']  = align_sub(series['SOFR'], series['DFF'], 100)
    if has('SOFR99') and has('SOFR'):        d['SPR_SOFR99']     = align_sub(series['SOFR99'], series['SOFR'], 100)
    if has('SOFR') and has('RRPONTSYAWARD'): d['SPR_SOFR_ONRRP'] = align_sub(series['SOFR'], series['RRPONTSYAWARD'], 100)
    if has('DCPF1M') and has('SOFR'):        d['SPR_CP_SOFR']    = align_sub(series['DCPF1M'], series['SOFR'], 100)
    # 净流动性(万亿$) = WALCL(百万→万亿) - TGA(百万→万亿) - RRP(十亿→万亿)
    if has('WALCL') and has('WTREGEN') and has('RRPONTSYD'):
        rows = ffill_to_daily(series['WALCL'], series['WTREGEN'], series['RRPONTSYD'])
        d['NETLIQ'] = [(dt, round(w / 1e6 - t / 1e6 - r / 1e3, 3)) for dt, (w, t, r) in rows]
    if has('M2SL'):         d['M2SL_YOY']        = yoy(series['M2SL'], 12)
    if has('LIQ_EZM3'):     d['LIQ_EZM3_YOY']    = yoy(series['LIQ_EZM3'], 12)
    if has('ECBASSETSW'):   d['ECBASSETSW_YOY']  = yoy(series['ECBASSETSW'], 52)
    if has('JPNASSETS'):    d['JPNASSETS_YOY']   = yoy(series['JPNASSETS'], 12)
    if has('WALCL'):        d['WALCL_YOY']       = yoy(series['WALCL'], 52)
    # 全球M2同比⚙️ = 美/欧/中 简单平均(未折美元, 口径注记)
    legs = [to_map(d['M2SL_YOY']) if 'M2SL_YOY' in d else None,
            to_map(d['LIQ_EZM3_YOY']) if 'LIQ_EZM3_YOY' in d else None,
            to_map(cnm.get('LIQ_CNM2_YOY', []))]
    legs = [l for l in legs if l]
    if len(legs) >= 2:
        ds = sorted(set.intersection(*[set(l.keys()) for l in legs]))
        d['GM2_YOY'] = [(dt, round(sum(l[dt] for l in legs) / len(legs), 2)) for dt in ds]
    for k, s in d.items():
        if s: log('  %s n=%d last=%s' % (k, len(s), s[-1]))
    series.update({k: v for k, v in d.items() if v})

    log('== 4/5 ⚙️综合压力指数 + 2σ信号 ==')
    stress = None; signals = {'broad': [], 'funding': []}
    comp_defs = [
        ('SPR_SOFR_IORB', 'SOFR-IORB利差', 1), ('SPR_SOFR99', 'SOFR尾部99分位差', 1),
        ('SPR_CP_SOFR', '商票-SOFR利差', 1), ('BAMLH0A0HYM2', '高收益OAS', 1),
        ('VIXCLS', 'VIX(股市波动)', 1), ('MOVE_X', 'MOVE(债市波动)', 1),
    ]
    comp_pct = []
    for k, name, _w in comp_defs:
        if k in series and series[k]:
            p = pct_rank(series[k], series[k][-1][1])
            if p is not None: comp_pct.append((k, name, p))
    # 净流动性63日变化(下降=收紧, 取反) + 美元/真实利率63日变化
    for k, name in [('NETLIQ', '净流动性63日Δ(逆)'), ('DTWEXBGS', '美元指数63日Δ'), ('DFII10', '10Y实际利率63日Δ')]:
        if k in series and len(series[k]) > 64:
            s = series[k]
            deltas = [(s[i][0], s[i][1] - s[i - 63][1]) for i in range(63, len(s))]
            val = deltas[-1][1]
            if k == 'NETLIQ': val = -val
            p = pct_rank(deltas, val)
            if p is not None: comp_pct.append((k, name, p))
    if comp_pct:
        stress_val = round(sum(p for _, _, p in comp_pct) / len(comp_pct), 1)
        stress = {'value': stress_val, 'n_comp': len(comp_pct),
                  'components': [{'id': k, 'name': n, 'pct': p} for k, n, p in comp_pct]}
        log('  综合压力分位=%.1f (%d项)' % (stress_val, len(comp_pct)))
    # 广义2σ信号(对标GMF: 美元指数/真实利率/HY/VIX 63日变化 z≥2 → 冲击极值=买入窗口)
    for k, name in [('DTWEXBGS', '美元指数'), ('DFII10', '10Y实际利率'), ('BAMLH0A0HYM2', '高收益OAS'), ('VIXCLS', 'VIX'), ('MOVE_X', 'MOVE')]:
        s = series.get(k, [])
        if len(s) > 200:
            deltas = [s[i][1] - s[i - 63][1] for i in range(63, len(s))]
            win = deltas[-756:] if len(deltas) > 756 else deltas
            mu = sum(win) / len(win)
            sd = math.sqrt(sum((x - mu) ** 2 for x in win) / len(win)) or 1e-9
            z = (deltas[-1] - mu) / sd
            signals['broad'].append({'id': k, 'name': name, 'z': round(z, 2), 'chg63': round(deltas[-1], 3), 'triggered': z >= 2})
    for k, name in [('SPR_SOFR_IORB', 'SOFR-IORB'), ('SPR_SOFR99', 'SOFR尾部'), ('SPR_CP_SOFR', '商票-SOFR')]:
        s = series.get(k, [])
        if len(s) > 200:
            deltas = [s[i][1] - s[i - 20][1] for i in range(20, len(s))]
            win = deltas[-504:] if len(deltas) > 504 else deltas
            mu = sum(win) / len(win)
            sd = math.sqrt(sum((x - mu) ** 2 for x in win) / len(win)) or 1e-9
            z = (deltas[-1] - mu) / sd
            signals['funding'].append({'id': k, 'name': name, 'z': round(z, 2), 'chg20': round(deltas[-1], 2), 'triggered': z >= 2})

    log('== 5/5 看板卡 + 写盘 ==')
    def card(cid, name, key, unit, scale=1.0, dec=2, chg_n=1, good_low=None):
        s = series.get(key, [])
        if not s: return None
        v = s[-1][1] * scale
        c = chg(s, chg_n)
        return {'id': cid, 'name': name, 'val': round(v, dec), 'unit': unit, 'date': s[-1][0],
                'chg': round(c * scale, dec) if c is not None else None,
                'pct': pct_rank(s, s[-1][1]), 'key': key}
    cards = [c for c in [
        card('sofr_iorb', 'SOFR-IORB利差', 'SPR_SOFR_IORB', 'bp'),
        card('sofr_tail', 'SOFR尾部(99分位-中位)', 'SPR_SOFR99', 'bp'),
        card('sofr_onrrp', 'SOFR-ONRRP利差', 'SPR_SOFR_ONRRP', 'bp'),
        card('cp_sofr', '商票-SOFR利差', 'SPR_CP_SOFR', 'bp'),
        card('onrrp', 'ON RRP余额', 'RRPONTSYD', '十亿$'),
        card('reserves', '银行准备金', 'WRESBAL', '万亿$', scale=1 / 1e6),
        card('tga', '财政部TGA', 'WTREGEN', '十亿$', scale=1 / 1e3),
        card('netliq', '净流动性(总资产-TGA-RRP)', 'NETLIQ', '万亿$'),
        card('srf', 'SRF常备回购用量', 'LIQ_SRF', '十亿$'),
        card('hy', '高收益债OAS', 'BAMLH0A0HYM2', '%'),
        card('move', 'MOVE美债波动率(债市)', 'MOVE_X', '点'),
        card('vix', 'VIX(股市)', 'VIXCLS', '点'),
        card('real10y', '10Y实际利率', 'DFII10', '%'),
        card('dxy', '广义美元指数', 'DTWEXBGS', '点'),
        card('gm2', '全球M2同比⚙️简单平均', 'GM2_YOY', '%'),
    ] if c]
    onrrp_bn = series['RRPONTSYD'][-1][1] if has('RRPONTSYD') else None
    regime = {'stage': 2 if (onrrp_bn is not None and onrrp_bn < 100) else 1,
              'onrrp_bn': onrrp_bn,
              'desc': 'ON RRP近枯竭→银行准备金边际定价, TGCR/SOFR对供给冲击更敏感(缩表阶段2)' if (onrrp_bn is not None and onrrp_bn < 100)
                      else 'ON RRP仍有余量→货币基金边际融出, 利率传导相对平滑(缩表阶段1)'}
    out = {
        'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'asof': max((s[-1][0] for s in series.values() if s), default=None),
        'regime': regime, 'stress': stress, 'signals': signals,
        'buy_signal': any(x['triggered'] for x in signals['broad']),
        'funding_alert': any(x['triggered'] for x in signals['funding']),
        'cards': cards, 'fails': fails,
        'gaps': ['XCCY交叉货币互换基差(需彭博)', '贴现窗口借款量(FRED无直读序列, H.4.1表2待解析)',
                 '一级交易商持仓(FR2004网页抓取待做)', '高盛/彭博金融条件指数(商业数据)',
                 '日本M2现行值(FRED/OECD序列已停更, 待BOJ直抓)', '英国/加拿大M2(免费序列缺失)',
                 'CP-OIS真实值(此处以1M商票-SOFR代理)'],
        'methodology': '综合压力分位=9项分量(6项水平分位+3项63日变化分位, 2019以来全样本; MOVE分位自2020H2, Yahoo ^MOVE日度+L3·第三方终端EDB快照拼接)等权平均; '
                       '广义信号=美元指数/真实利率/HY/VIX/MOVE 63日变化z≥2(对标GMF>2σ买入窗口); '
                       '融资警报=SOFR-IORB/尾部/商票 20日变化z≥2; 阶段判定=ON RRP<1000亿$→阶段2',
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    # 写chart_series (截断350点, 分析用全历史已算完)
    n_up = 0
    for k, s in series.items():
        cs[k] = [[d, round(v, 6)] for d, v in tail(s)]
        n_up += 1
    save_cs(cs)
    log('完成: %d键入chart_series, 看板卡%d张, 失败%d %s' % (n_up, len(cards), len(fails), fails))

if __name__ == '__main__':
    main()
