#!/usr/bin/env python3
# CFTC COT持仓(期货版) → data/chart_series.js (CFTC_*) + data/cftc.json (含贵金属杠杆指标)
# 数据源: cftc.gov 官方年包 deacot{YYYY}.zip (免费免key, 每周五更新, 持仓日为每周二)
# 首次运行拉 2019-今年 全历史; 之后只拉当年增量(历史键已存chart_series.js)
# 贵金属杠杆指标(⚙️自建商品杠杆方法论):
#   期货腿杠杆分位 = 非商业净持仓(手)在2019以来全样本的分位数(0-100)
#   ETF腿(GLD/SLV份额)经Yahoo快照积累, 未足26周前标"积累中"
import json, re, os, io, csv, zipfile, datetime, urllib.request, time, sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(APP, 'data')
CS_PATH = os.path.join(DATA, 'chart_series.js')
OUT_JSON = os.path.join(DATA, 'cftc.json')
FIRST_YEAR = 2019

# 品种: (键, 市场代码, 名称, 单位, 板块, 合约乘数oz, 用于杠杆指标)
MKTS = [
    ('CFTC_GC_NET', '088691', '黄金非商业净持仓',   '手', 'asset', 100,  'gold'),
    ('CFTC_SI_NET', '084691', '白银非商业净持仓',   '手', 'asset', 5000, 'silver'),
    ('CFTC_PL_NET', '076651', '铂金非商业净持仓',   '手', 'asset', 50,   'platinum'),
    ('CFTC_PA_NET', '075651', '钯金非商业净持仓',   '手', 'asset', 100,  'palladium'),
    ('CFTC_TY_NET', '043602', '10Y美债期货净投机',  '手', 'rate',  None, None),
    ('CFTC_US_NET', '020601', '30Y美债期货净投机',  '手', 'rate',  None, None),
    ('CFTC_TU_NET', '042601', '2Y美债期货净投机',   '手', 'rate',  None, None),
    ('CFTC_DX_NET', '098662', '美元指数非商业净持仓','手', 'asset', None, None),
    ('CFTC_JY_NET', '097741', '日元非商业净持仓',   '手', 'asset', None, None),
    ('CFTC_ES_NET', '13874A', '标普E-mini非商业净持仓','手','asset', None, None),
    ('CFTC_BTC_NET','133741', '比特币期货非商业净持仓','手','asset', None, None),
    ('CFTC_HG_NET', '085692', '铜非商业净持仓',     '手', 'asset', None, None),
    ('CFTC_CL_NET', '067651', 'WTI原油非商业净持仓',  '手', 'asset', None, None),
]
LEV_KEYS = {'gold': 'CFTC_GC_NET', 'silver': 'CFTC_SI_NET',
            'platinum': 'CFTC_PL_NET', 'palladium': 'CFTC_PA_NET'}
CN = {'gold': '黄金', 'silver': '白银', 'platinum': '铂金', 'palladium': '钯金'}

def log(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)

def http_get(url, timeout=60, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research workbench)'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            log('  重试%d %s %s' % (i + 1, url.split('/')[-1], repr(e)[:80]))
            time.sleep(2 + 2 * i)
    return None

def load_cs():
    if not os.path.exists(CS_PATH):
        return {}
    raw = open(CS_PATH, encoding='utf-8').read()
    m = re.search(r'window\.CHART_SERIES\s*=\s*(\{.*\})\s*;?\s*$', raw, re.S)
    return json.loads(m.group(1)) if m else {}

def save_cs(cs):
    tmp = CS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('window.CHART_SERIES = ' + json.dumps(cs, ensure_ascii=False, separators=(',', ':')) + ';')
    os.replace(tmp, CS_PATH)

def parse_year(year, codes):
    """下载某年COT年包, 返回 {code: {date: (nc_long, nc_short, oi)}}"""
    url = f'https://www.cftc.gov/files/dea/history/deacot{year}.zip'
    blob = http_get(url, timeout=90)
    if not blob:
        log('  x 年包失败', year)
        return {}
    out = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            text = io.TextIOWrapper(f, encoding='latin-1')
            for r in csv.DictReader(text):
                cd = r.get('CFTC Contract Market Code', '').strip()
                if cd not in codes:
                    continue
                try:
                    d = r['As of Date in Form YYYY-MM-DD'].strip()
                    nl = float(r['Noncommercial Positions-Long (All)'].replace(',', '') or 0)
                    ns = float(r['Noncommercial Positions-Short (All)'].replace(',', '') or 0)
                    oi = float(r['Open Interest (All)'].replace(',', '') or 0)
                except Exception:
                    continue
                out.setdefault(cd, {})[d] = (nl, ns, oi)
    log('  年包%d: %s' % (year, {c: len(v) for c, v in out.items()}))
    return out

def percentile(series, v):
    """v在series(值列表)中的分位0-100"""
    xs = sorted(x for x in series if x is not None)
    if not xs:
        return None
    import bisect
    return round(100.0 * bisect.bisect_left(xs, v) / len(xs), 1)

def fetch_etf_shares(cs):
    """Yahoo份额快照积累: GLD/SLV sharesOutstanding → ETF腿序列 (26周后启用)
    v7/quote需cookie+crumb鉴权(免费), 限流则跳过保留旧值"""
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', 'Mozilla/5.0 (research workbench)')]
    try:
        op.open('https://fc.yahoo.com', timeout=15)
    except Exception:
        pass  # fc.yahoo.com 返404属正常, cookie已种
    try:
        crumb = op.open('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=15).read().decode().strip()
    except Exception as e:
        log('  crumb获取失败, ETF腿跳过:', repr(e)[:80])
        return {}
    out = {}
    try:
        j = json.loads(op.open(
            f'https://query1.finance.yahoo.com/v7/finance/quote?symbols=GLD,SLV&crumb={urllib.parse.quote(crumb)}',
            timeout=15).read())
        res = {r['symbol']: r for r in j.get('quoteResponse', {}).get('result', [])}
    except Exception as e:
        log('  ETF份额请求失败(Yahoo限流则跳过, 保留旧值):', repr(e)[:80])
        return {}
    for sym, key in [('GLD', 'GLD_SHARES'), ('SLV', 'SLV_SHARES')]:
        sh = res.get(sym, {}).get('sharesOutstanding')
        if not sh:
            log('  %s份额缺失, 跳过' % sym)
            continue
        today = datetime.date.today().isoformat()
        old = {p[0]: p[1] for p in cs.get(key, [])}
        old[today] = round(sh)
        cs[key] = sorted(old.items())
        out[sym] = sh
        log('  %s份额: %.0f (累计%d点)' % (sym, sh, len(cs[key])))
    return out

def main():
    cs = load_cs()
    codes = {m[1] for m in MKTS}
    cur_year = datetime.date.today().year
    have_hist = any(k in cs and len(cs[k]) > 30 for k, *_ in MKTS)
    years = range(FIRST_YEAR, cur_year + 1) if not have_hist else [cur_year]
    if not have_hist:
        log('首次运行: 拉取%d-%d全历史' % (FIRST_YEAR, cur_year))
    store = {}  # code -> {date: (l,s,oi)}
    for y in years:
        res = parse_year(y, codes)
        for cd, dd in res.items():
            store.setdefault(cd, {}).update(dd)
        time.sleep(1)
    # ETF份额快照积累(每日一点)
    etf = fetch_etf_shares(cs)
    # 合并进 chart_series
    n_ok = 0
    for key, cd, name, unit, sec, mult, lev in MKTS:
        dd = store.get(cd, {})
        old = {p[0]: p[1] for p in cs.get(key, [])}
        for d, (nl, ns, oi) in dd.items():
            old[d] = round(nl - ns)
        if dd:
            cs[key] = sorted(old.items())
            n_ok += 1
    # HT仓位镜像: HT_asset_仓位_* 本质=CFTC免费周报的拷贝, 直接镜像免手工Excel
    HT_MIRROR = {
        'CFTC_TY_NET': 'HT_asset_仓位_10Y美债-非商业_非商业多头净持仓',
        'CFTC_US_NET': 'HT_asset_仓位_超长债-非商业_非商业多头净持仓',
        'CFTC_GC_NET': 'HT_asset_仓位_COMEX黄金-非商业_非商业多头净持仓',
        'CFTC_DX_NET': 'HT_asset_仓位_美元指数-非商业_非商业多头净持仓',
        'CFTC_HG_NET': 'HT_asset_仓位_LME铜-非商业_非商业多头净持仓',
        'CFTC_CL_NET': 'HT_asset_仓位_WTI原油-非商业_非商业多头净持仓',
        'CFTC_BZ_NET': 'HT_asset_仓位_IPE原油-非商业_非商业多头净持仓',
    }
    for src_key, ht_key in HT_MIRROR.items():
        if src_key in cs and cs[src_key]:
            cs[ht_key] = [list(p) for p in cs[src_key]]
            log('HT镜像:', ht_key, '<-', src_key)
    if n_ok or etf:
        save_cs(cs)
        log('合并%d条CFTC序列' % n_ok)
    # 杠杆指标(贵金属四品种)
    lev = {}
    for eng, key in LEV_KEYS.items():
        ser = cs.get(key, [])
        if len(ser) < 30:
            lev[eng] = {'name': CN[eng], 'gap': True}
            continue
        vals = [v for _, v in ser]
        cur = vals[-1]
        lev[eng] = {
            'name': CN[eng],
            'net_contracts': cur,
            'asof': ser[-1][0],
            'pct': percentile(vals, cur),           # 杠杆水平分位
            'chg_13w': cur - vals[-14] if len(vals) > 14 else None,  # 13周净持仓变化(手)
            'pct_chg': percentile([vals[i] - vals[i - 13] for i in range(13, len(vals))],
                                  cur - vals[-14]) if len(vals) > 14 else None,  # 杠杆变化分位
            'series_tail': ser[-160:],               # 近3年周频, 画小图
        }
    # ETF腿状态
    etf_leg = {}
    for sym, key in [('GLD', 'GLD_SHARES'), ('SLV', 'SLV_SHARES')]:
        s2 = cs.get(key, [])
        etf_leg[sym] = {'n': len(s2), 'last': s2[-1] if s2 else None,
                        'ready': len(s2) >= 26}
    meta = {
        'updated': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M') + ' 北京',
        'src': 'L1·CFTC官网COT周报(免费) · 持仓日=每周二, 周五发布',
        'method': '⚙️自建商品杠杆方法论: 杠杆水平分位=非商业净持仓(手)在%d以来全样本分位; 杠杆变化分位=13周净持仓变化的分位。ETF腿(GLD/SLV份额)经Yahoo快照积累中, 暂以期货腿为准。' % FIRST_YEAR,
        'leverage': lev,
        'etf_leg': etf_leg,
        'markets': [{'key': k, 'name': n, 'unit': u, 'sec': s,
                     'last': (cs.get(k) or [[None, None]])[-1], 'n': len(cs.get(k, []))}
                    for k, _, n, u, s, *_ in MKTS],
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
    log('cftc.json 写出; 杠杆分位:',
        {k: (v.get('pct') if not v.get('gap') else 'gap') for k, v in lev.items()})

if __name__ == '__main__':
    main()
