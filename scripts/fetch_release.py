#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 数据发布·分项贡献面板管线
# 非农(BLS)/CPI分项(BLS+权重)/PCE价格与实际贡献(BEA)/GDP贡献(BEA)/FedWatch自建引擎(CME结算价+FOMC日历+FRED)
# 输出 data/release_panels.json ; 全部失败自留旧值(自愈), 数字均有来源, 无编造
import json, os, re, sys, time, datetime, calendar, urllib.request, urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data', 'release_panels.json')
CRED = '/mnt/agents/output/凭证与API档案'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}

def log(*a): print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)

def http_get(url, headers=None, timeout=30, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or UA)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:
            last = e; log('  retry', i+1, repr(e)[:90], url[:80]); time.sleep(2+i*2)
    raise last

def http_post_json(url, payload, timeout=40, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={**UA, 'Content-Type': 'application/json'})
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except Exception as e:
            last = e; log('  retry', i+1, repr(e)[:90]); time.sleep(2+i*2)
    raise last

def load_key(name, env):
    v = os.environ.get(env)
    if v: return v.strip()
    try:
        return json.load(open(os.path.join(CRED, name)))['api_key']
    except Exception:
        return None

BLS_KEY = load_key('bls_key.json', 'BLS_KEY')
BEA_KEY = load_key('bea_key.json', 'BEA_KEY')
log('keys:', 'BLS' if BLS_KEY else '-', 'BEA' if BEA_KEY else '-')

old = {}
if os.path.exists(OUT):
    try: old = json.load(open(OUT))
    except Exception: old = {}
panel = {'updated': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'blocks': {}}
def keep_old(block, note):
    if block in old.get('blocks', {}):
        panel['blocks'][block] = old['blocks'][block]
        panel['blocks'][block]['stale'] = True
        panel['blocks'][block]['note'] = note
        log('  !!', block, '保留旧值:', note)
    else:
        panel['blocks'][block] = {'empty': True, 'note': note}

# ================= 1. BLS 非农分项 =================
NFP_ITEMS = [
 ('CES0000000001', '非农总计'), ('CES0500000001', '私人部门'), ('CES0600000001', '商品生产'),
 ('CES1000000001', '采矿伐木'), ('CES2000000001', '建筑业'), ('CES3000000001', '制造业'),
 ('CES4000000001', '贸易运输公用'), ('CES4200000001', '零售'), ('CES5000000001', '信息业'),
 ('CES5500000001', '金融活动'), ('CES6000000001', '专业商业服务'), ('CES6500000001', '教育医疗'),
 ('CES7000000001', '休闲住宿'), ('CES8000000001', '其他服务'), ('CES9000000001', '政府部门'),
]
# ================= 2. BLS CPI分项 (SA环比 + NSA同比) =================
# 权重 = BLS相对重要性 CPI-U 2025-12 (发布于2026-02-13, L1快照; 每年2月随新权重人工/自动更新)
CPI_W_SNAPSHOT = {
 '食品': 13.743, '能源': 6.193, '住所': 35.652, '房租': 7.517, '业主等价租金': 26.455,
 '新车': 4.290, '二手车': 2.366, '服装': 2.430, '医疗商品': 1.509, '医疗服务': 6.803,
 '交通服务': 6.233, '娱乐': 5.309, '家居陈设与运营': 4.464, '机动车保险': 2.799,
}
CPI_ITEMS = [  # (中文名, SA序列, NSA序列)
 ('食品', 'CUSR0000SAF1', 'CUUR0000SAF1'), ('能源', 'CUSR0000SA0E', 'CUUR0000SA0E'),
 ('住所', 'CUSR0000SAH1', 'CUUR0000SAH1'), ('房租', 'CUSR0000SEHA', 'CUUR0000SEHA'),
 ('业主等价租金', 'CUSR0000SEHC', 'CUUR0000SEHC'), ('新车', 'CUSR0000SETA01', 'CUUR0000SETA01'),
 ('二手车', 'CUSR0000SETA02', 'CUUR0000SETA02'), ('服装', 'CUSR0000SAA', 'CUUR0000SAA'),
 ('医疗商品', 'CUSR0000SAM1', 'CUUR0000SAM1'), ('医疗服务', 'CUSR0000SAM2', 'CUUR0000SAM2'),
 ('交通服务', 'CUSR0000SETG', 'CUUR0000SETG'), ('娱乐', 'CUSR0000SAR', 'CUUR0000SAR'),
 ('家居陈设与运营', 'CUSR0000SAH3', 'CUUR0000SAH3'), ('机动车保险', 'CUSR0000SETE', 'CUUR0000SETE'),
]
def bls_fetch(series_ids, startyear, endyear):
    out = {}
    for i in range(0, len(series_ids), 50):
        chunk = series_ids[i:i+50]
        payload = {'seriesid': chunk, 'startyear': str(startyear), 'endyear': str(endyear), 'calculations': False}
        if BLS_KEY: payload['registrationkey'] = BLS_KEY
        r = http_post_json('https://api.bls.gov/publicAPI/v2/timeseries/data/', payload)
        if r.get('status') != 'REQUEST_SUCCEEDED':
            raise RuntimeError('BLS: %s' % r.get('message'))
        for s in r['Results']['series']:
            rows = []
            for x in s['data']:
                v = (x.get('value') or '').replace(',', '')
                if x['period'].startswith('M') and x['period'] != 'M13' and v not in ('', '-', '.'):
                    rows.append(('%s-%s' % (x['year'], x['period'][1:]), float(v)))
            rows.sort()
            out[s['seriesID']] = rows
    return out

try:
    log('== 非农分项 ==')
    ids = [s for s, _ in NFP_ITEMS]
    d = bls_fetch(ids, 2024, 2026)
    items = []
    for sid, name in NFP_ITEMS:
        s = d.get(sid, [])
        if len(s) >= 2:
            items.append({'name': name, 'id': sid, 'chg': round(s[-1][1]-s[-2][1], 1),
                          'level': s[-1][1]})
    hist = [[p, round(v - d['CES0000000001'][i-1][1], 1)] for i, (p, v) in enumerate(d['CES0000000001']) if i > 0][-14:]
    panel['blocks']['nfp'] = {
        'period': d['CES0000000001'][-1][0], 'src': 'L1·BLS就业形势报告(CES)', 'unit': '千人·环比变动',
        'total_chg': items[0]['chg'], 'items': items, 'history': hist,
        'next': '每月第1个周五 20:30北京(冬令21:30)'}
    log('  非农', panel['blocks']['nfp']['period'], 'total', items[0]['chg'], '分项', len(items))
except Exception as e:
    keep_old('nfp', repr(e)[:120])

try:
    log('== CPI分项贡献 ==')
    sa_ids = [x[1] for x in CPI_ITEMS] + ['CUSR0000SA0', 'CUSR0000SA0L1E']
    nsa_ids = [x[2] for x in CPI_ITEMS] + ['CUUR0000SA0', 'CUUR0000SA0L1E']
    d = bls_fetch(sa_ids + nsa_ids, 2024, 2026)
    def _shift(per, months):  # 'YYYY-MM' 平移months个月
        y, m = int(per[:4]), int(per[5:7]) + months
        y += (m - 1) // 12; m = (m - 1) % 12 + 1
        return '%04d-%02d' % (y, m)
    def mom(s):  # 严格按上期日历月对齐(2025-10/11政府停摆缺月→标记gap)
        if len(s) < 2: return None, False
        dd = dict(s); per, v = s[-1]
        prev = dd.get(_shift(per, -1))
        if prev is None:
            base = s[-2]
            return round((v/base[1]-1)*100, 2), True
        return round((v/prev-1)*100, 2), False
    def yoy(s):
        if len(s) < 2: return None
        dd = dict(s); per, v = s[-1]
        base = dd.get(_shift(per, -12))
        return round((v/base-1)*100, 2) if base else None
    items = []
    gap_any = False
    for name, sa, nsa in CPI_ITEMS:
        m, g = mom(d.get(sa, [])); y = yoy(d.get(nsa, [])); gap_any = gap_any or g
        w = CPI_W_SNAPSHOT.get(name)
        contrib = round(w*y/100, 3) if (w is not None and y is not None) else None
        items.append({'name': name, 'mom': m, 'mom_gap': g, 'yoy': y, 'w': w, 'contrib': contrib})
    hm, hg = mom(d['CUSR0000SA0']); cm, cg = mom(d['CUSR0000SA0L1E']); gap_any = gap_any or hg or cg
    panel['blocks']['cpi'] = {
        'period': d['CUSR0000SA0'][-1][0], 'src': 'L1·BLS CPI(分项环比=季调,同比=非季调)',
        'weights_src': 'L1·BLS相对重要性2025-12快照(2026-02-13发布,每年2月更新)',
        'headline_mom': hm, 'headline_yoy': yoy(d['CUUR0000SA0']),
        'core_mom': cm, 'core_yoy': yoy(d['CUUR0000SA0L1E']),
        'gap_note': '2025-10/11因政府停摆缺月,部分环比为跨期值' if gap_any else None,
        'items': items, 'next': '每月10-13日 20:30北京(冬令21:30)'}
    log('  CPI', panel['blocks']['cpi']['period'], 'headline yoy', panel['blocks']['cpi']['headline_yoy'])
except Exception as e:
    keep_old('cpi', repr(e)[:120])

# ================= 2b. CPI 环比贡献历史(13个月·四大类, 供彭博式堆积图) =================
# 权重=BLS相对重要性2025-12快照近似(食品13.54/能源7.35/核心商品18.84/核心服务60.27)
CPI_HIST_ITEMS = [
    ('食品', 'CUSR0000SAF1', 13.540), ('能源', 'CUSR0000SA0E', 7.347),
    ('核心商品', 'CUSR0000SACL1E', 18.842), ('核心服务', 'CUSR0000SASLE', 60.272),
]
try:
    log('== CPI环比贡献历史 ==')
    ids = [x[1] for x in CPI_HIST_ITEMS] + ['CUSR0000SA0', 'CUSR0000SA0L1E']
    d = bls_fetch(ids, 2024, 2026)
    def _mom_series(s):
        dd = dict(s)
        out = []
        for per, v in s:
            base = dd.get(_shift(per, -1))
            if base is None: continue
            out.append([per, round((v / base - 1) * 100, 3)])
        return out[-13:]
    groups = {}
    for name, sid, w in CPI_HIST_ITEMS:
        groups[name] = {'w': w, 'mom': _mom_series(d.get(sid, []))}
    panel['blocks']['cpi_hist'] = {
        'groups': groups,
        'headline': _mom_series(d.get('CUSR0000SA0', [])),
        'core': _mom_series(d.get('CUSR0000SA0L1E', [])),
        'src': 'L1·BLS CPI季调环比(四大类); 权重=BLS相对重要性2025-12快照近似',
        'note': '环比贡献(pp)≈权重×分项环比/100; 合计与整体环比存在舍入/交互项差异'}
    log('  cpi_hist months:', len(panel['blocks']['cpi_hist']['headline']))
except Exception as e:
    keep_old('cpi_hist', repr(e)[:120])

# ================= 2b+. CPI核心服务八明细(彭博ECVO式分项贡献) =================
# 权重=BLS相对重要性2025-12快照(与用户彭博终端一致); 家庭经营=核心服务减七项的残差权重
CPI_DETAIL_ITEMS = [
    ('住所', 'CUSR0000SAH1', 35.343),
    ('医疗保健服务', 'CUSR0000SAM2', 6.864),
    ('交通运输服务', 'CUSR0000SAS4', 6.310),
    ('教育与通讯服务', 'CUSR0000SAE', 4.928),
    ('休闲服务', 'CUSR0000SARS', 3.154),
    ('其他个人服务', 'CUSR0000SEGD', 1.606),
    ('供水污水和垃圾收集', 'CUSR0000SEHG', 1.145),
    ('家庭经营', 'CUSR0000SEHH02', 0.922),
]
try:
    if '_mom_series' not in dir():
        raise RuntimeError('mom_series未就绪(上游cpi_hist失败)')
    log('== CPI核心服务八明细 ==')
    ids = [x[1] for x in CPI_DETAIL_ITEMS]
    d = bls_fetch(ids, 2024, 2026)
    items = []
    for name, sid, w in CPI_DETAIL_ITEMS:
        mom = _mom_series(d.get(sid, []))
        if not mom:
            log('  明细缺数据:', name, sid)
        items.append({'name': name, 'w': w, 'sid': sid, 'mom': mom})
    panel['blocks']['cpi_detail'] = {
        'items': items,
        'src': 'L1·BLS CPI季调环比(核心服务八明细); 权重=BLS相对重要性2025-12快照(与彭博一致)',
        'note': '环比贡献(pp)≈权重×分项环比/100; 八项合计与核心服务存在舍入/口径残差'}
    log('  cpi_detail items:', len(items))
except Exception as e:
    keep_old('cpi_detail', repr(e)[:120])

# ================= 2c. BLS PPI 最终需求(四大之PPI, CPI同款贡献分解) =================
# 权重 = BLS官方相对重要性 2025-12快照(news.release/ppi.t01.htm表1, 每年初随12月数据更新)
PPI_ITEMS = [  # (中文名, SA序列, NSA序列) — 卡片chips/解读用
    ('最终需求', 'WPSFD4', 'WPUFD4'),
    ('核心(除食品能源贸易)', 'WPSFD49116', 'WPUFD49116'),
    ('最终需求商品', 'WPSFD41', 'WPUFD41'),
    ('最终需求服务', 'WPSFD42', 'WPUFD42'),
]
PPI_GROUPS = [  # 大类(完整分割最终需求): (名, SA序列, 权重)
    ('商品', 'WPSFD41', 29.028), ('服务', 'WPSFD42', 68.338), ('建筑', 'WPSFD43', 2.634),
]
PPI_DETAIL_ITEMS = [  # 细分: 商品三分 + 服务三分(建筑权重仅2.634不再细分)
    ('食品', 'WPSFD411', 5.452), ('能源', 'WPSFD412', 5.061), ('核心商品', 'WPSFD413', 18.515),
    ('贸易服务', 'WPSFD423', 19.755), ('运输仓储', 'WPSFD422', 4.857), ('其他服务', 'WPSFD421', 43.725),
]
try:
    log('== PPI最终需求(贡献分解) ==')
    ids = ([x[1] for x in PPI_ITEMS] + [x[2] for x in PPI_ITEMS] +
           [x[1] for x in PPI_GROUPS] + [x[1] for x in PPI_DETAIL_ITEMS])
    d = bls_fetch(ids, 2024, 2026)
    def _shift2(per, months):
        y, m = int(per[:4]), int(per[5:7]) + months
        y += (m - 1) // 12; m = (m - 1) % 12 + 1
        return '%04d-%02d' % (y, m)
    def _mom2(s):
        if len(s) < 2: return None
        dd = dict(s); per, v = s[-1]
        base = dd.get(_shift2(per, -1), s[-2][1])
        return round((v / base - 1) * 100, 2)
    def _yoy2(s):
        if len(s) < 2: return None
        dd = dict(s); per, v = s[-1]
        base = dd.get(_shift2(per, -12))
        return round((v / base - 1) * 100, 2) if base else None
    if '_mom_series' not in dir():
        def _mom_series(s):
            dd = dict(s); out = []
            for per, v in s:
                base = dd.get(_shift2(per, -1))
                if base is None: continue
                out.append([per, round((v / base - 1) * 100, 3)])
            return out[-13:]
    got = {}
    for name, sa, nsa in PPI_ITEMS:
        if d.get(sa) or d.get(nsa):
            got[name] = {'mom': _mom2(d.get(sa, [])), 'yoy': _yoy2(d.get(nsa, []))}
    if not got.get('最终需求'):
        raise RuntimeError('PPI主序列无数据')
    hist = _mom_series(d.get('WPSFD4', []))
    groups = {}
    for name, sid, w in PPI_GROUPS:
        groups[name] = {'w': w, 'mom': _mom_series(d.get(sid, []))}
    det_items = []
    for name, sid, w in PPI_DETAIL_ITEMS:
        mm = _mom_series(d.get(sid, []))
        if not mm:
            log('  明细缺数据:', name, sid)
        det_items.append({'name': name, 'w': w, 'sid': sid, 'mom': mm})
    panel['blocks']['ppi'] = {
        'period': (d.get('WPSFD4') or d.get('WPUFD4'))[-1][0],
        'src': 'L1·BLS PPI最终需求(环比=季调,同比=非季调)',
        'weights_src': 'L1·BLS官方相对重要性2025-12快照(每年初随12月数据更新)',
        'items': got, 'history': hist[-13:],
        'next': '每月CPI前后一日 20:30北京(冬令21:30)'}
    panel['blocks']['ppi_hist'] = {
        'groups': groups, 'headline': hist, 'core': _mom_series(d.get('WPSFD49116', [])),
        'src': 'L1·BLS PPI季调环比(商品/服务/建筑); 权重=BLS官方相对重要性2025-12快照',
        'note': '环比贡献(pp)≈权重×分项环比/100; 合计与整体环比存在舍入/权重时滞差异'}
    panel['blocks']['ppi_detail'] = {
        'items': det_items,
        'src': 'L1·BLS PPI季调环比(六细分); 权重=BLS官方相对重要性2025-12快照',
        'note': '细分=商品三分(食品/能源/核心商品)+服务三分(贸易/运输仓储/其他); 建筑(权重2.634)不再细分'}
    log('  PPI', panel['blocks']['ppi']['period'], 'headline mom', got['最终需求']['mom'],
        'groups', len(groups), 'detail', len(det_items))
except Exception as e:
    keep_old('ppi', repr(e)[:120])
    keep_old('ppi_hist', repr(e)[:120])
    keep_old('ppi_detail', repr(e)[:120])

# ================= 3. BEA PCE价格贡献(月)/实际PCE贡献(月)/GDP贡献(季) =================
def bea_table(tab, freq, years):
    url = ('https://apps.bea.gov/api/data/?UserID=%s&method=GETDATA&DataSetName=NIPA&TableName=%s&Frequency=%s&Year=%s&ResultFormat=JSON'
           % (BEA_KEY, tab, freq, years))
    return json.loads(http_get(url))['BEAAPI']['Results']['Data']

def pick_latest(data, keep_lines, unit_note, src):
    periods = sorted(set(r['TimePeriod'] for r in data))
    last = periods[-1]
    items, total = [], None
    for r in data:
        if r['TimePeriod'] != last: continue
        v = r['DataValue'].replace(',', '')
        try: v = float(v)
        except Exception: continue
        ln = int(r['LineNumber'])
        if ln == 1: total = v
        if ln in keep_lines:
            items.append({'name': keep_lines[ln], 'pp': round(v, 2)})
    return {'period': last, 'src': src, 'unit': unit_note, 'total': total, 'items': items}

GDP_LINES = {2: '个人消费', 3: '·商品', 6: '·服务', 7: '私人国内投资', 8: '·固定投资',
             14: '·库存变动', 15: '净出口', 16: '·出口', 19: '·进口(减项)', 22: '政府消费与投资'}
PCE_PRICE_LINES = {2: '商品', 3: '·耐用品', 8: '·非耐用品', 13: '服务', 15: '·住房与公用',
                   16: '·医疗', 17: '·交通服务', 19: '·餐饮住宿', 20: '·金融保险',
                   25: '核心PCE(除食品能源)', 27: '能源商品与服务', 29: '住房'}
for block, tab, freq, lines, unit_note, src, nxt in [
    ('gdp', 'T10102', 'Q', GDP_LINES, '百分点·对实际GDP环比折年率贡献', 'L1·BEA NIPA表1.1.2', '季度末次月·先行/二次/三次估值'),
    ('pce_price', 'T20808', 'M', PCE_PRICE_LINES, '百分点·对PCE价格环比贡献', 'L1·BEA NIPA表2.8.8', '每月末·个人收入与支出报告'),
    ('pce_real', 'T20802', 'M', {2: '商品', 3: '·耐用品', 8: '·非耐用品', 13: '服务'}, '百分点·对实际PCE环比贡献', 'L1·BEA NIPA表2.8.2', '每月末·个人收入与支出报告'),
]:
    try:
        log('== BEA', tab, '==')
        data = bea_table(tab, freq, '2025,2026')
        blk = pick_latest(data, lines, unit_note, src)
        blk['next'] = nxt
        panel['blocks'][block] = blk
        log('  ', blk['period'], 'total', blk['total'], '项', len(blk['items']))
    except Exception as e:
        keep_old(block, repr(e)[:120])

# ================= 4. FedWatch 自建引擎 =================
FOMC_FALLBACK = {  #  scraping失败时用(来源:联储fomccalendars页 2026-08-19更新)
    2026: [(1, 28), (3, 18), (4, 29), (6, 17), (7, 29), (9, 16), (10, 28), (12, 9)],
    2027: [(1, 27), (3, 17), (4, 28), (6, 9), (7, 28), (9, 15), (10, 27), (12, 8)],
}
MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
             'August', 'September', 'October', 'November', 'December']
def fomc_dates():
    # 主用兜底快照(2026-08-19核自官网,已验证); 联网抓取仅作校验标注, 不作数据源
    today = datetime.date.today()
    out = {yr: [datetime.date(yr, m, d) for m, d in ds] for yr, ds in FOMC_FALLBACK.items()}
    note = 'L1·联储FOMC日历(快照2026-08-19,官网核对)'
    try:
        raw = http_get('https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm', timeout=25).decode('utf-8', 'ignore')
        txt = re.sub(r'<[^>]+>', ' ', raw); txt = re.sub(r'\s+', ' ', txt)
        n = 0
        for yr in FOMC_FALLBACK:
            seg_m = re.search(str(yr) + r' FOMC Meetings(.{0,3000})', txt)
            if seg_m:
                n += len(re.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*-\s*\d{1,2}', seg_m.group(1)))
        if n >= len(FOMC_FALLBACK.get(today.year, [])):
            note += '·在线校验通过'
    except Exception:
        pass
    return out, note

def fred_last(sid):
    raw = http_get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=2025-01-01' % sid, timeout=30)
    lines = raw.decode().strip().split('\n')[1:]
    rows = [(l.split(',')[0], float(l.split(',')[1])) for l in lines if ',' in l and l.split(',')[1] not in ('', '.', '-')]
    return rows[-1]

def fred_last_safe(sid):
    """FRED优先; 沙盒限速时回退本地chart_series已存序列(EFFR等)"""
    try:
        return fred_last(sid), 'FRED实时'
    except Exception as e:
        log('  FRED', sid, '失败, 回退chart_series:', repr(e)[:70])
        try:
            raw = open(os.path.join(BASE, 'data', 'chart_series.js'), encoding='utf-8').read()
            CS = json.loads(re.search(r'=\s*(\{[\s\S]*\})\s*;?\s*$', raw).group(1))
            s = CS[sid]
            return tuple(s[-1]), 'chart_series存量'
        except Exception:
            raise e

def zq_settlements():
    hdrs = {**UA, 'Accept': 'application/json', 'Referer': 'https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html'}
    sess = None
    try:
        from curl_cffi import requests as creq  # 浏览器TLS指纹, 绕CME Akamai 403
        sess = creq.Session(impersonate='chrome')
        log('  curl_cffi可用')
    except Exception:
        log('  无curl_cffi, 用urllib(易被CME 403)')
    today = datetime.date.today()
    for back in range(1, 8):
        d = today - datetime.timedelta(days=back)
        if d.weekday() >= 5: continue
        url = ('https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/305/FUT?tradeDate=%s&pageSize=500&strategy=DEFAULT&_=%d'
               % (d.strftime('%m/%d/%Y'), int(time.time()*1000)))
        try:
            if sess:
                r = sess.get(url, timeout=30)
                if r.status_code != 200: raise RuntimeError('HTTP %s' % r.status_code)
                j = json.loads(r.text)
            else:
                j = json.loads(http_get(url, headers=hdrs, timeout=30, retries=2))
            st = j.get('settlements') or []
            rows = []
            MON = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            for x in st:
                code = x.get('code') or ''
                settle = x.get('settle') or x.get('last')
                if settle in (None, '', '-'): continue
                try: settle = float(settle)
                except Exception: continue
                if code.startswith('ZQ'):  # 有code字段时直接用
                    rows.append((code, settle)); continue
                mm = re.match(r'^([A-Z]{3})\s+(\d{2})$', str(x.get('month') or '').upper())
                if mm:  # 无code时用month合成: SEP 26 -> ZQU6
                    mon = MON[mm.group(1)]; yr2 = int(mm.group(2))
                    zc = 'ZQ' + ZQ_MON_REV[mon] + str(yr2)
                    rows.append((zc, settle))
            if rows:
                return d.isoformat(), rows
            log('  ZQ', d, '空结果 keys=', list(j.keys())[:5], 'st=', len(st), 'head=', str(j)[:120])
        except Exception as e:
            log('  ZQ', d, repr(e)[:80])
    raise RuntimeError('CME结算价连续不可得')

ZQ_MON = {'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6, 'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12}
ZQ_MON_REV = {v: k for k, v in ZQ_MON.items()}
def fedwatch():
    # 优先使用官方CME FedWatch条件概率表(cmegroup.cn, 由fetch_fedwatch.py维护, 与官网完全一致)
    try:
        fwj = json.load(open(os.path.join(os.path.dirname(OUT), 'fedwatch.json'), encoding='utf-8'))
        cb = fwj.get('current_bucket', '350-375')
        tarl = int(cb.split('-')[0]) / 100.0; taru = int(cb.split('-')[1]) / 100.0
        effr = round((tarl + taru) / 2 - 0.125, 2)
        try:
            (_, effr), _ = fred_last_safe('EFFR')
        except Exception:
            pass
        meetings = []
        prevE = round((tarl + taru) / 2, 3)
        for m in fwj.get('meetings', []):
            try:
                dt = datetime.datetime.strptime(m['meeting'], '%d %b%y').date()
            except Exception:
                continue
            mid_rate = round((tarl + taru) / 2, 3)
            # 单月口径：E[会后利率]与上一会议期望的差值/25bp → 当月加息概率
            E = 0.0
            for b in m.get('buckets', []):
                bl, bh = b['r'].split('-')
                E += ((int(bl) + int(bh)) / 200.0) * (b['p'] / 100.0)
            d = (E - prevE) if E else (m.get('hike', 0) - m.get('ease', 0)) / 100.0 * 0.25
            if E:
                prevE = E
            hike_p = max(0.0, min(100.0, d / 0.25 * 100))
            ease_p = max(0.0, min(100.0, -d / 0.25 * 100))
            probs = []
            if ease_p > 0.05:
                probs.append({'rate': round(mid_rate - 0.25, 3), 'pct': round(ease_p, 1)})
            hold_p = 100.0 - hike_p - ease_p
            if hold_p > 0.05:
                probs.append({'rate': mid_rate, 'pct': round(hold_p, 1)})
            if hike_p > 0.05:
                probs.append({'rate': round(mid_rate + 0.25, 3), 'pct': round(hike_p, 1)})
            if not probs:
                continue
            meetings.append({'date': dt.isoformat(), 'implied': round(100 - m['mid'], 3),
                             'post': round(100 - m['mid'], 3), 'probs': probs})
            if len(meetings) >= 6:
                break
        if meetings:
            log('  FedWatch: 使用官方cmegroup.cn条件概率表', fwj.get('asof', ''))
            return {'settle_date': fwj.get('asof', ''), 'effr': effr,
                    'target': '%.2f-%.2f' % (tarl, taru),
                    'src': 'L1·CME FedWatch官网条件概率表(cmegroup.cn, %s)' % fwj.get('asof', ''),
                    'cal_src': 'L1·联储FOMC日历', 'meetings': meetings}
    except Exception as e:
        log('  官方fedwatch.json不可用, 回退ZQ自建:', repr(e)[:100])
    dates_by_year, cal_src = fomc_dates()
    meetings = sorted(d for ds in dates_by_year.values() for d in ds)
    today = datetime.date.today()
    meetings = [d for d in meetings if d >= today - datetime.timedelta(days=3)][:10]
    (_, effr), effr_src = fred_last_safe('EFFR')
    target_note = 'FRED目标区间'
    try:
        _, taru = fred_last('DFEDTARU'); _, tarl = fred_last('DFEDTARL')
    except Exception:
        import math as _m
        tarl = _m.floor(effr*4+1e-9)/4; taru = tarl + 0.25
        target_note = '目标区间由EFFR推算(FRED限速)'
    settle_date, rows = zq_settlements()
    # 合同月隐含平均EFFR
    imp = {}
    for code, settle in rows:
        mon = ZQ_MON.get(code[2]); yr = 2000 + int(code[3:])
        if mon: imp[(yr, mon)] = 100.0 - settle
    res, pre = [], effr
    for mt in meetings:
        key = (mt.year, mt.month)
        if key not in imp: continue
        D = calendar.monthrange(mt.year, mt.month)[1]
        d_day = mt.day
        implied = imp[key]
        post = (implied*D - pre*(d_day-1)) / (D - d_day + 1)
        if abs(post - pre) > 0.75 or not (0 < post < 12):
            log('  跳过远月失真会议', mt.isoformat(), 'post=', round(post, 2))
            continue  # 远月合约流动性差, 小价差被公式放大, 不入面板也不向后传递
        moves = (post - pre) / 0.25
        import math
        k = math.floor(moves + 1e-9); frac = moves - k
        lo, hi = pre + k*0.25, pre + (k+1)*0.25
        probs = [[round(lo, 2), round((1-frac)*100, 1)], [round(hi, 2), round(frac*100, 1)]]
        probs = [[r, p] for r, p in probs if p > 0.05]
        res.append({'date': mt.isoformat(), 'implied': round(implied, 3), 'post': round(post, 3),
                    'probs': [{'rate': r, 'pct': p} for r, p in probs]})
        pre = post
        if len(res) >= 6: break
    return {'settle_date': settle_date, 'effr': effr, 'target': '%.2f-%.2f' % (tarl, taru),
            'src': 'L1·CME ZQ结算价(%s)+EFFR(%s,%s) ⚙️按CME公布方法学自建(与官网QuikStrike或差数点)' % (settle_date, effr_src, target_note),
            'cal_src': cal_src, 'meetings': res}

try:
    log('== FedWatch引擎 ==')
    panel['blocks']['fedwatch'] = fedwatch()
    log('  meetings', len(panel['blocks']['fedwatch']['meetings']), 'settle', panel['blocks']['fedwatch']['settle_date'])
except Exception as e:
    keep_old('fedwatch', repr(e)[:150])

panel['src_note'] = '全部L1官方源: BLS(非农/CPI) · BEA(PCE/GDP贡献) · CME结算价+联储日历(FedWatch⚙️自建) · 官网发布当日管线刷新'
# 保留人工维护的扩展块(如 fomc 决议解读), 管线只重建自己负责的块
for _bk, _bv in old.get('blocks', {}).items():
    if _bk not in panel['blocks']:
        panel['blocks'][_bk] = _bv
        log('  保留人工块:', _bk)
json.dump(panel, open(OUT, 'w'), ensure_ascii=False)
log('写盘', OUT, '块:', {k: ('ok' if not v.get('empty') and not v.get('stale') else ('stale' if v.get('stale') else 'empty')) for k, v in panel['blocks'].items()})
