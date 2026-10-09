#!/usr/bin/env python3
# B类第二批补充源 → data/chart_series.js + data/auctions.json + data/tic.json
# 覆盖框架v1矩阵缺口: 日度TGA/期限溢价/M1/OBFR/MMF/粘性·中位·截尾通胀/ECI/续请/进口价格/
#   5y5y与5Y预期/HY收益率/AAA·BBB利差/10Y-3M/房价/Zillow租金/中国PMI·CPI·PPI·GDP·社零·信贷/
#   LPR/SHIBOR/美债拍卖投标倍数/日本持美债TIC/加拿大M2/中美利差/金银比
import json, re, os, io, csv, datetime, time, math

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(APP, 'data')
CS_PATH = os.path.join(DATA, 'chart_series.js')
TAIL = 350

def log(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)

import requests
try:
    from curl_cffi import requests as _creq  # 浏览器TLS指纹(绕FRED/CME的Akamai HTTP/2重置)
    RQ = _creq.Session(impersonate='chrome')
except Exception:
    RQ = requests.Session()
    RQ.headers.update({'User-Agent': 'python-requests/2.31.0'})

def http_get(url, timeout=40, retries=3, headers=None):
    for i in range(retries):
        try:
            r = RQ.get(url, timeout=timeout, headers=headers or {})
            if r.status_code == 200: return r.content
            log('  HTTP%d %s' % (r.status_code, url[:60]))
        except Exception as e:
            log('  重试%d %s %s' % (i + 1, url[:60], repr(e)[:60]))
        time.sleep(2 + 2 * i)
    return None

def fred(sid, start='2019-01-01'):
    raw = http_get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s' % (sid, start))
    if not raw: return []
    out = []
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8', 'ignore'))):
        v = row.get(sid, '.')
        if v in ('.', '', None): continue
        try: out.append((row['observation_date'], float(v)))
        except Exception: pass
    return out

FRED_S = [
    ('WDTGAL', 'WDTGAL', '财政部TGA余额(日度)', '百万美元'),
    ('M1SL', 'M1SL', '美国M1(季调)', '十亿美元'),
    ('OBFR', 'OBFR', 'OBFR隔夜银行融资利率', '%'),
    ('MMMFFAQ027S', 'MMMFFAQ027S', '货币基金总资产(MMF)', '百万美元'),
    ('STICKCPIM157SFRBATL', 'STICKCPIM157SFRBATL', '粘性CPI(环比折年)', '%'),
    ('MEDCPIM158SFRBCLE', 'MEDCPIM158SFRBCLE', '中位CPI同比', '%'),
    ('PCETRIM12M159SFRBDAL', 'PCETRIM12M159SFRBDAL', '截尾PCE同比(达拉斯联储)', '%'),
    ('ECIALLCIV', 'ECIALLCIV', 'ECI雇佣成本指数', '点'),
    ('T5YIFR', 'T5YIFR', '5y5y远期通胀预期', '%'),
    ('CCSA', 'CCSA', '续请失业金', '人'),
    ('CUSR0000SASLE', 'CUSR0000SASLE', '超级核心CPI·服务剔除住房租金(季调)', '点'),
    ('CUUR0000SASLE', 'CUUR0000SASLE', '超级核心CPI·服务剔除住房租金(非季调)', '点'),
    ('JTSJOR', 'JTSJOR', 'JOLTS职位空缺率', '%'),
    ('JTSQUR', 'JTSQUR', 'JOLTS离职率(主动)', '%'),
    ('JTSHIR', 'JTSHIR', 'JOLTS雇用率', '%'),
    ('UNEMPLOY', 'UNEMPLOY', '失业人数', '千人'),
    ('IR14270', 'IR14270', '进口价格指数(全部商品)', '点'),
    ('EXPINF5YR', 'EXPINF5YR', '克利夫兰5Y通胀预期', '%'),
    ('BAMLH0A0HYM2EY', 'BAMLH0A0HYM2EY', '高收益债有效收益率', '%'),
    ('BAMLC0A1CAAA', 'BAMLC0A1CAAA', 'AAA公司债利差OAS', '%'),
    ('BAMLC0A4CBBB', 'BAMLC0A4CBBB', 'BBB公司债利差OAS', '%'),
    ('T10Y3M', 'T10Y3M', '10Y-3M利差', '%'),
    ('USSTHPI', 'USSTHPI', '标普Case-Shiller全国房价指数', '点'),
    ('WLCFLPCL', 'WLCFLPCL', '贴现窗口一级信贷(周)', '百万美元'),
    ('WLCFLL', 'WLCFLL', '联储贷款总额(H.4.1)', '百万美元'),
    ('WLCFLSCL', 'WLCFLSCL', '贴现窗口二级信贷(周)', '百万美元'),
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

def em_report(report, keep_map, pages=3):
    """东财报表 → {键:[(d,v)]}; keep_map={源字段: 目标键}"""
    u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=%s&columns=ALL'
         '&pageNumber=1&pageSize=%d&sortColumns=REPORT_DATE&sortTypes=-1' % (report, pages * 100))
    raw = http_get(u, headers={'User-Agent': 'Mozilla/5.0'})
    res = {v: [] for v in keep_map.values()}
    if not raw: return res
    try: data = json.loads(raw.decode('utf-8', 'ignore'))['result']['data']
    except Exception: return res
    for r in sorted(data, key=lambda x: x['REPORT_DATE']):
        d = r['REPORT_DATE'][:10]
        for src, key in keep_map.items():
            if r.get(src) is not None:
                try: res[key].append((d, float(r[src])))
                except Exception: pass
    return res

def chinamoney(path, date_params, fields_map, y0=2019, y1=None):
    """chinamoney按年分片(大跨度返回空)"""
    y1 = y1 or datetime.datetime.now().year
    res = {v: [] for v in fields_map.values()}
    for y in range(y0, y1 + 1):
        params = ('lang=cn&' + date_params) % (f'{y}-01-01', f'{y}-12-31')
        u = 'https://www.chinamoney.com.cn/ags/ms/' + path + '?' + params
        raw = http_get(u, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.chinamoney.com.cn/'})
        if not raw: continue
        try: recs = json.loads(raw.decode('utf-8', 'ignore'))['records']
        except Exception: continue
        for r in recs:
            d = r.get('showDateCN')
            if not d: continue
            for src, key in fields_map.items():
                if r.get(src) not in (None, ''):
                    try: res[key].append((d, float(r[src])))
                    except Exception: pass
        time.sleep(0.5)
    for k in res: res[k] = sorted(res[k])
    return res

def zillow_zori():
    u = 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv'
    raw = http_get(u, timeout=60)
    if not raw: return []
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8', 'ignore'))):
        if row.get('RegionName') == 'United States':
            return [(k, float(v)) for k, v in row.items() if re.match(r'^\d{4}-\d{2}-\d{2}$', k) and v]
    return []

def boc_m2():
    u = 'https://www.bankofcanada.ca/valet/observations/V41552796/json?start_date=2019-01-01'
    raw = http_get(u)
    if not raw: return []
    try:
        obs = json.loads(raw.decode('utf-8', 'ignore'))['observations']
        return [(o['d'], float(o['V41552796']['v'])) for o in obs]
    except Exception: return []

def pd_positions():
    """NY Fed FR2004一级交易商持仓(周度周三, 百万美元) → {键:[(d,v)]}"""
    ks = {'PDPOSGST-TOT': 'PD_UST_POS',   # 美债(除TIPS)净持仓
          'PDPOSMBS-TOT': 'PD_MBS_POS',   # 机构MBS净持仓
          'PDPOSCS-TOT': 'PD_CORP_POS',   # 公司债净持仓
          'PDPOSFGS-TOT': 'PD_AGY_POS'}   # 机构债(除MBS)净持仓
    out = {}
    for kid, key in ks.items():
        raw = http_get('https://markets.newyorkfed.org/api/pd/get/%s.json' % kid,
                       headers={'User-Agent': 'Mozilla/5.0'})
        if not raw: continue
        try:
            rows = json.loads(raw.decode('utf-8', 'ignore'))['pd']['timeseries']
            out[key] = [(r['asofdate'], float(r['value']))
                        for r in rows if r.get('value') not in (None, '')]
        except Exception: pass
        time.sleep(0.4)
    return out

def boj_m2():
    """日本央行M2同比(月度%, MD02主表, 1968/01起) → [(d,v)]"""
    raw = http_get('https://www.stat-search.boj.or.jp/ssi/mtshtml/md02_m_1_en.html',
                   headers={'User-Agent': 'Mozilla/5.0'})
    if not raw: return []
    try:
        import pandas as pd
        t = pd.read_html(io.StringIO(raw.decode('utf-8', 'ignore')))[0]
        out = []
        for _, row in t.iloc[7:].iterrows():
            m = re.match(r'^(\d{4})/(\d{2})$', str(row.iloc[0]))
            if not m: continue
            try: fv = float(row.iloc[1])
            except Exception: continue
            out.append(('%s-%s-01' % (m.group(1), m.group(2)), fv))
        return out
    except Exception: return []

def boe_m4_yoy():
    """英国央行M4存量(月度, £m, IADB LPMAUYN, 1990起) → 同比% [(d,v)]"""
    u = ('https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp'
         '?csv.x=yes&Datefrom=01/Jan/1990&Dateto=31/Dec/2030&SeriesCodes=LPMAUYN&UsingCodes=Y')
    raw = http_get(u, headers={'User-Agent': 'Mozilla/5.0'})
    if not raw: return []
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig', 'ignore'))))
        lv = {}
        for r in rows:
            d, v = (r.get('DATE') or '').strip(), r.get('LPMAUYN')
            if not d or not v: continue
            dt = datetime.datetime.strptime(d, '%d %b %Y').date()
            lv['%04d-%02d' % (dt.year, dt.month)] = (dt.isoformat(), float(v.replace(',', '')))
        out = []
        for ym in sorted(lv):
            y0 = '%04d-%02d' % (int(ym[:4]) - 1, int(ym[5:7]))
            if y0 in lv and lv[y0][1]:
                out.append((lv[ym][0], round((lv[ym][1] / lv[y0][1] - 1) * 100, 3)))
        return out
    except Exception: return []

def acm_tp10():
    """NY Fed ACM 10Y期限溢价(xls)"""
    raw = http_get('https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls', timeout=90)
    if not raw: return []
    try:
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw), sheet_name=0)
        col = [c for c in df.columns if 'ACMTP10' in str(c)]
        dcol = [c for c in df.columns if str(c).upper().startswith('DATE')]
        if not col or not dcol: return []
        out = []
        for _, r in df.iterrows():
            try:
                raw_d = r[dcol[0]]
                if isinstance(raw_d, str):
                    dt = datetime.datetime.strptime(raw_d.strip(), '%d-%b-%Y')
                else:
                    dt = pd.to_datetime(raw_d)
                d = dt.strftime('%Y-%m-%d')
                v = float(r[col[0]])
                if d >= '2019-01-01': out.append((d, v))
            except Exception: pass
        return sorted(out)
    except Exception as e:
        log('  ACM解析失败 %s' % repr(e)[:60]); return []

def auctions():
    """FiscalData拍卖: 10Y/30Y/2Y 投标倍数序列 + 近12场关键拍卖"""
    out = {}
    recent = []
    for term, typ, key in [('10-Year', 'Note', 'US_AUC_10Y_BTC'), ('30-Year', 'Bond', 'US_AUC_30Y_BTC'), ('2-Year', 'Note', 'US_AUC_2Y_BTC')]:
        u = ('https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query'
             '?filter=security_term:eq:%s,security_type:eq:%s&sort=-auction_date&page[size]=60'
             % (term.replace(' ', '%20'), typ))
        raw = http_get(u)
        if not raw: continue
        try: rows = json.loads(raw.decode('utf-8', 'ignore'))['data']
        except Exception: continue
        ser = []
        for r in rows:
            if r.get('bid_to_cover_ratio') in (None, 'null'): continue
            try:
                ser.append((r['auction_date'], float(r['bid_to_cover_ratio'])))
                ta = float(r.get('total_accepted') or 0)
                ib = float(r.get('indirect_bidder_accepted') or 0)
                if len(recent) < 30:
                    recent.append({'term': term, 'date': r['auction_date'], 'btc': float(r['bid_to_cover_ratio']),
                                   'indirect_pct': round(ib / ta * 100, 1) if ta else None,
                                   'high_yield': float(r.get('high_yield') or 0) or None})
            except Exception: pass
        out[key] = sorted(ser)
    recent = sorted(recent, key=lambda x: x['date'], reverse=True)[:12]
    return out, recent

def em_treasury(pages=20):
    """东财 RPTA_WEB_TREASURYYIELD: 中美国债收益率(日度, 1990起) → {键:[(d,v)]}"""
    fmap = {'EMM00588704': 'EM_CGB2Y', 'EMM00166462': 'EM_CGB5Y',
            'EMM00166466': 'EM_CGB10Y', 'EMM00166469': 'EM_CGB30Y'}
    out = {v: [] for v in fmap.values()}
    for p in range(1, pages + 1):
        u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_TREASURYYIELD'
             '&columns=ALL&sortColumns=SOLAR_DATE&sortTypes=-1&pageSize=500&pageNumber=%d' % p)
        raw = http_get(u, headers={'User-Agent': 'Mozilla/5.0'})
        if not raw: break
        try: rows = json.loads(raw)['result']['data']
        except Exception: break
        if not rows: break
        for r in rows:
            d = (r.get('SOLAR_DATE') or '')[:10]
            if not d: continue
            for f, key in fmap.items():
                v = r.get(f)
                if v is not None:
                    try: out[key].append((d, float(v)))
                    except Exception: pass
        time.sleep(0.4)
    return {k: sorted(set(s)) for k, s in out.items()}

def tic_slt():
    """TIC SLT表5(主要海外持有者, 月度13列) → {键:[(月末,v)]} + tic.json快照积累"""
    raw = http_get('https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt')
    if not raw: return {}
    lines = raw.decode('utf-8', 'ignore').split('\n')
    hdr = None
    for i, ln in enumerate(lines):
        if ln.startswith('Country'):
            hdr = ln.split('\t'); rows = lines[i + 1:]; break
    if not hdr: return {}
    import calendar
    def col_date(p):
        try:
            y, m = int(p[:4]), int(p[5:7])
            return '%04d-%02d-%02d' % (y, m, calendar.monthrange(y, m)[1])
        except Exception: return None
    targets = {'Japan': 'JP_UST_HOLD', 'China, Mainland': 'CN_UST_HOLD',
               'United Kingdom': 'UK_UST_HOLD', 'Of Which: Foreign Official': 'FO_UST_HOLD'}
    out = {v: [] for v in targets.values()}
    for ln in rows:
        cells = ln.split('\t')
        name = cells[0].strip()
        for t, key in targets.items():
            if name == t:
                for p, v in zip(hdr[1:], cells[1:]):
                    d = col_date(p.strip())
                    try:
                        if d and v.strip(): out[key].append((d, float(v.replace(',', ''))))
                    except Exception: pass
    # 快照积累(跨月合并)
    tic_path = os.path.join(DATA, 'tic.json')
    hist = {v: {} for v in targets.values()}
    if os.path.exists(tic_path):
        old = json.load(open(tic_path, encoding='utf-8'))
        for k in hist: hist[k].update(old.get(k, {}))
    for k, s in out.items():
        for d, v in s: hist[k][d] = v
    json.dump({'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), **hist},
              open(tic_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return {k: sorted(h.items()) for k, h in hist.items()}

def main():
    os.makedirs(DATA, exist_ok=True)
    cs = load_cs()
    n_ok, fails = 0, []
    def put(key, s, tail_n=TAIL):
        nonlocal n_ok
        if s and len(s) >= 3:
            cs[key] = [[d, round(v, 6)] for d, v in tail(s, tail_n)]
            n_ok += 1; log('  %s n=%d last=%s' % (key, len(s), s[-1]))
        else:
            fails.append(key); log('  %s 失败' % key)

    log('== 1/7 FRED补充 ==')
    for key, fid, name, unit in FRED_S:
        put(key, fred(fid)); time.sleep(0.4)
    log('== 2/7 ACM期限溢价 ==')
    put('ACMTP10', acm_tp10())
    log('== 3/7 东财中国月度 ==')
    em = {}
    em.update(em_report('RPT_ECONOMY_PMI', {'MAKE_INDEX': 'EM_PMI', 'NMAKE_INDEX': 'EM_PMI_NM'}))
    em.update(em_report('RPT_ECONOMY_CPI', {'NATIONAL_SAME': 'EM_CPI_YOY'}))
    em.update(em_report('RPT_ECONOMY_PPI', {'BASE_SAME': 'EM_PPI_YOY'}))
    em.update(em_report('RPT_ECONOMY_GDP', {'SUM_SAME': 'EM_GDP_YOY'}, pages=2))
    em.update(em_report('RPT_ECONOMY_TOTAL_RETAIL', {'RETAIL_TOTAL_SAME': 'EM_RETAIL_YOY'}))
    em.update(em_report('RPT_ECONOMY_RMB_LOAN', {'RMB_LOAN': 'EM_LOAN_NEW', 'LOAN_ACCUMULATE_SAME': 'EM_LOAN_ACC_YOY'}))
    for k, s in em.items():
        if s: put(k, s)
    for k, s in em_treasury().items():
        put(k, s, tail_n=2600)  # 日度收益率曲线留10年, 支撑季节性/回测
    log('== 4/7 chinamoney LPR/SHIBOR ==')
    cnm = {}
    cnm.update(chinamoney('cm-u-bk-currency/LprHis', 'strStartDate=%s&strEndDate=%s',
                          {'1Y': 'CN_LPR1Y', '5Y': 'CN_LPR5Y'}))
    cnm.update(chinamoney('cm-u-bk-shibor/ShiborHis', 'startDate=%s&endDate=%s',
                          {'3M': 'CN_SHIBOR3M', 'ON': 'CN_SHIBORON'}))
    for k, s in cnm.items():
        put(k, s)
    log('== 5/7 拍卖/TIC/Zillow/BoC ==')
    auc, recent = auctions()
    for k, s in auc.items():
        put(k, s)
    json.dump({'updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'recent': recent},
              open(os.path.join(DATA, 'auctions.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log('  auctions.json 近%d场' % len(recent))
    for k, ser in tic_slt().items():
        put(k, ser)
    put('ZORI_US', zillow_zori())
    put('CA_M2', boc_m2())
    log('== 5.5/7 贴现窗口/FR2004/日本M2/英国M4 ==')
    for k, s in pd_positions().items():
        put(k, s)
    put('JPM2_YOY', boj_m2())
    put('UKM4_YOY', boe_m4_yoy())
    log('== 6/7 衍生⚙️ ==')
    def align_div(a, b):
        bm = {d: v for d, v in b}; return [(d, v / bm[d]) for d, v in a if d in bm and bm[d]]
    def align_sub(a, b):
        bm = {d: v for d, v in b}; return [(d, v - bm[d]) for d, v in a if d in bm]
    dgs10, cn10 = cs.get('DGS10', []), cs.get('EM_CGB10Y', [])
    if dgs10 and cn10: put('SPR_USCN10Y', [(d, round(v, 4)) for d, v in align_sub(dgs10, cn10)], tail_n=2600)
    g, s = cs.get('Y_GOLD', []), cs.get('Y_SLV', [])
    if g and s: put('GOLD_SILVER_RATIO', [(d, round(v, 2)) for d, v in align_div(g, s)])
    s99, onr = cs.get('SOFR99', []), cs.get('RRPONTSYAWARD', [])
    if s99 and onr: put('SPR_SOFR99_ONRRP', [(d, round(v * 100, 2)) for d, v in align_sub(s99, onr)])
    tg, onr2 = cs.get('TGCRRATE', []), cs.get('RRPONTSYAWARD', [])
    if tg and onr2: put('SPR_TGCR_ONRRP', [(d, round(v * 100, 2)) for d, v in align_sub(tg, onr2)])
    log('== 7/7 写盘 ==')
    save_cs(cs)
    log('完成: 新增/更新%d键, 失败%d %s' % (n_ok, len(fails), fails))

if __name__ == '__main__':
    main()
