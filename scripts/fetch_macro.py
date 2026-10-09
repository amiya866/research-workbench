#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观免费数据管道 v1 —— 特朗普专区12板块 + 日报/周报图表墙
数据源(全部免费/免key):
  FRED fredgraph.csv  (美联储经济数据, 免key)
  Yahoo Finance chart API (行情)
  Treasury FiscalData API (联邦债务, 免key)
  TSA 旅客安检量 (网页抓取, 尽力而为)
产物:
  data/chart_series.js   全量序列(增量合并, 绝不删除MM上传的键)
  data/macro_series.json 板块元数据(不含数据本体)
  data/macro_catalog.js  周报目录合并用
"""
import csv, io, json, os, re, sys, time, datetime, urllib.request, urllib.parse
try:
    from curl_cffi import requests as _creq
    _SESS = _creq.Session(impersonate='chrome')
except Exception:
    _SESS = None
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.abspath(__file__))
APP  = os.path.dirname(BASE)
DATA = os.path.join(APP, 'data')

def log(*a): print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)

def http_get(url, timeout=15, retries=2, backoff=1.0, maxbytes=8 * 1024 * 1024):
    for i in range(retries):
        try:
            if _SESS is not None:  # 浏览器TLS指纹(绕FRED/CME的Akamai HTTP/2重置)
                r = _SESS.get(url, timeout=timeout)
                if r.status_code == 200:
                    return r.content[:maxbytes].decode('utf-8', 'replace')
                raise RuntimeError('HTTP %s' % r.status_code)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research-workbench)'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(maxbytes).decode('utf-8', 'replace')
        except Exception as e:
            log('  retry', i + 1, repr(e)[:110], url[:70])
            time.sleep(backoff * (i + 1))
    return None

# ---------- 抓取器 ----------
def fred(sid, limit=1700):
    t = http_get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=2017-01-01' % sid,
                 timeout=20, retries=3, backoff=3.0)
    if not t or 'observation_date' not in t[:200]:
        return []
    out = []
    for row in csv.reader(io.StringIO(t)):
        if len(row) < 2 or row[0] == 'observation_date':
            continue
        d, v = row[0].strip(), row[1].strip()
        if v in ('.', '', 'NaN'):
            continue
        try:
            out.append([d, round(float(v), 4)])
        except ValueError:
            pass
    return out[-limit:]

def fred_batch(sids, limit=1700):
    """fredgraph 支持逗号分隔多条序列, 12条/批; cosd限起点减负载; 批失败回退单条"""
    out = {}
    nb = (len(sids) + 11) // 12
    for i in range(0, len(sids), 12):
        chunk = sids[i:i + 12]
        log('  FRED批 %d/%d: %s…' % (i // 12 + 1, nb, chunk[0]))
        t = http_get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=' + ','.join(chunk) + '&cosd=2017-01-01',
                     timeout=25, retries=2, backoff=3.0)
        rows = []
        if t and 'observation_date' in t[:200]:
            rows = list(csv.reader(io.StringIO(t)))
        if len(rows) > 1:
            col = {name: idx for idx, name in enumerate(rows[0])}
            for sid in chunk:
                if sid not in col:
                    out[sid] = []
                    continue
                ci = col[sid]
                ser = []
                for row in rows[1:]:
                    if len(row) <= ci:
                        continue
                    v = row[ci].strip()
                    if v in ('.', '', 'NaN'):
                        continue
                    try:
                        ser.append([row[0].strip(), round(float(v), 4)])
                    except ValueError:
                        pass
                out[sid] = ser[-limit:]
        else:
            for sid in chunk:
                out[sid] = []
        time.sleep(1.0)
    # 批失败回退单条: 批量端点易被Akamai按批限流而单条可用(9/2实测), 全败也逐条尝试
    got = sum(1 for s in sids if out.get(s))
    missing = [s for s in sids if not out.get(s)]
    if missing and (got > 0 and len(missing) <= 12 or got == 0):
        log('  单条回退', len(missing), '条(批成功%d)' % got)
        ok = 0
        for _i, sid in enumerate(missing):
            out[sid] = fred(sid)
            if out[sid]: ok += 1
            time.sleep(1.2)
            if got == 0 and ok == 0 and _i >= 4:
                log('  单条连续全败, 判定FRED整体不可达, 放弃剩余', len(missing) - _i - 1, '条')
                break
    elif missing:
        log('  FRED疑似限流(成功%d/%d), 放弃回退, 保留旧数据明日自愈' % (got, len(sids)))
    return out

def yahoo(sym, rng='5y'):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=1d' % (urllib.parse.quote(sym, safe=''), rng)
    t = None
    try:  # 本机直连 Yahoo 403, 优先走 Clash 代理(scripts/_yproxy.py)
        from _yproxy import YAHOO_SESSION
        r = YAHOO_SESSION.get(url, timeout=20)
        if r.status_code == 200:
            t = r.content[:8 * 1024 * 1024].decode('utf-8', 'replace')
    except Exception:
        t = None
    if not t:
        t = http_get(url)
    if not t:
        return []
    try:
        res = (json.loads(t).get('chart', {}).get('result') or [None])[0]
    except Exception:
        return []
    if not res:
        return []
    ts = res.get('timestamp') or []
    cl = ((res.get('indicators', {}).get('quote') or [{}])[0].get('close')) or []
    out = []
    for a, b in zip(ts, cl):
        if b is None:
            continue
        out.append([datetime.datetime.utcfromtimestamp(a).strftime('%Y-%m-%d'), round(float(b), 4)])
    return out

def us_debt():
    url = ('https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/'
           'accounting/od/debt_to_penny?sort=-record_date&page[size]=3000'
           '&fields=record_date,tot_pub_debt_out_amt')
    t = http_get(url)
    if not t:
        return []
    try:
        rows = json.loads(t).get('data', [])
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            v = float(str(r.get('tot_pub_debt_out_amt', '')).replace(',', '')) / 1e12
            out.append([r['record_date'], round(v, 4)])
        except Exception:
            pass
    out.sort()
    return out

def tsa_pax():
    """TSA 每日安检旅客量(本年), 失败返回[]"""
    t = http_get('https://www.tsa.gov/travel/passenger-volumes', timeout=40, retries=2)
    if not t:
        return []
    out = []
    cur = str(datetime.datetime.now().year)
    for m in re.finditer(r'<tr>\s*<td[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})\s*</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>', t):
        ds, num = m.group(1), m.group(2)
        if not ds.endswith(cur):
            continue
        try:
            dt = datetime.datetime.strptime(ds, '%m/%d/%Y').strftime('%Y-%m-%d')
            out.append([dt, round(int(num.replace(',', '')) / 1e6, 4)])
        except Exception:
            pass
    out.sort()
    return out

# ---------- 衍生计算 ----------
def yoy(series, n):
    out = []
    for i in range(n, len(series)):
        prev = series[i - n][1]
        if prev:
            out.append([series[i][0], round((series[i][1] / prev - 1) * 100, 3)])
    return out

def diff(series, n=1):
    return [[series[i][0], round(series[i][1] - series[i - n][1], 3)] for i in range(n, len(series))]

# ---------- 序列注册表 ----------
# (id, 名称, 单位, 板块, 来源标注, 抓取方式)
S = []
def add(sid, name, unit, sec, src, how):
    S.append(dict(id=sid, name=name, unit=unit, sec=sec, src=src, how=how))

# 利率 rate
add('DGS10', '美债10Y收益率', '%', 'rate', 'L1·FRED(+Yahoo收盘补齐)', ('fred', 'DGS10'))
add('DGS2', '美债2Y收益率', '%', 'rate', 'L1·FRED', ('fred', 'DGS2'))
add('DGS30', '美债30Y收益率', '%', 'rate', 'L1·FRED', ('fred', 'DGS30'))
add('T10Y2Y', '10Y-2Y利差', '%', 'rate', 'L1·FRED', ('fred', 'T10Y2Y'))
add('DFII10', '10Y实际利率TIPS', '%', 'rate', 'L1·FRED(+恒等式补齐)', ('fred', 'DFII10'))
add('DFF', '联邦基金有效利率', '%', 'rate', 'L1·FRED', ('fred', 'DFF'))
add('DFEDTARU', '联邦基金目标利率上限', '%', 'rate', 'L1·FRED', ('fred', 'DFEDTARU'))
add('DFEDTARL', '联邦基金目标利率下限', '%', 'rate', 'L1·FRED', ('fred', 'DFEDTARL'))
add('SOFR', 'SOFR', '%', 'rate', 'L1·FRED', ('fred', 'SOFR'))
add('BAMLH0A0HYM2', '高收益债利差OAS', '%', 'rate', 'L1·FRED/ICE', ('fred', 'BAMLH0A0HYM2'))
add('MORTGAGE30US', '30年房贷利率', '%', 'rate', 'L1·FRED', ('fred', 'MORTGAGE30US'))
# 物价 price
add('CPIAUCSL_YOY', 'CPI同比', '%', 'price', 'L1·FRED/BLS⚙️同比', ('yoy', 'CPIAUCSL', 12))
add('CPILFESL_YOY', '核心CPI同比', '%', 'price', 'L1·FRED/BLS⚙️同比', ('yoy', 'CPILFESL', 12))
add('PCEPI_YOY', 'PCE同比', '%', 'price', 'L1·FRED/BEA⚙️同比', ('yoy', 'PCEPI', 12))
add('PCEPILFE_YOY', '核心PCE同比', '%', 'price', 'L1·FRED/BEA⚙️同比', ('yoy', 'PCEPILFE', 12))
add('PPIACO_YOY', 'PPI同比', '%', 'price', 'L1·FRED/BLS⚙️同比', ('yoy', 'PPIACO', 12))
add('T10YIE', '10Y盈亏平衡通胀', '%', 'price', 'L1·FRED', ('fred', 'T10YIE'))
add('T5YIE', '5Y盈亏平衡通胀', '%', 'price', 'L1·FRED', ('fred', 'T5YIE'))
add('MICH', '密歇根1年通胀预期', '%', 'price', 'L1·FRED/UMich', ('fred', 'MICH'))
# 就业 jobs
add('UNRATE', '失业率U3', '%', 'jobs', 'L1·FRED/BLS', ('fred', 'UNRATE'))
add('U6RATE', '失业率U6', '%', 'jobs', 'L1·FRED/BLS', ('fred', 'U6RATE'))
add('PAYEMS_CHG', '非农新增(月)', '千人', 'jobs', 'L1·FRED/BLS⚙️差分', ('diff', 'PAYEMS', 1))
add('ICSA', '初请失业金(周)', '千人', 'jobs', 'L1·FRED/DOL', ('fred_div', 'ICSA', 1000))
add('JTSJOL', 'JOLTS职位空缺', '千人', 'jobs', 'L1·FRED/BLS', ('fred', 'JTSJOL'))
add('CES0500000003_YOY', '平均时薪同比', '%', 'jobs', 'L1·FRED/BLS⚙️同比', ('yoy', 'CES0500000003', 12))
add('MANEMP', '制造业就业', '千人', 'jobs', 'L1·FRED/BLS', ('fred', 'MANEMP'))
# 能源 energy
add('DCOILWTICO', 'WTI原油', '美元/桶',  'energy', 'L2·Yahoo', ('yahoo', 'CL=F'))
add('DCOILBRENTEU', '布伦特原油', '美元/桶',  'energy', 'L2·Yahoo', ('yahoo', 'BZ=F'))
add('DHHNGSP', 'HenryHub天然气', '美元/MMBtu', 'energy', 'L1·FRED/EIA', ('fred', 'DHHNGSP'))
add('GASREGW', '全美汽油零售价', '美元/加仑', 'energy', 'L1·FRED/EIA', ('fred', 'GASREGW'))
add('WCRFPUS2', '美国原油产量(周)', '百万桶/日', 'energy', 'L1·FRED/EIA', ('fred', 'WCRFPUS2'))
# 财政 fiscal
add('US_DEBT', '联邦债务总额', '万亿美元', 'fiscal', 'L1·财政部FiscalData', ('debt',))
add('MTSDS133FMS', '联邦月度赤字(-)/盈余', '百万美元', 'fiscal', 'L1·FRED/财政部', ('fred', 'MTSDS133FMS'))
add('A091RC1Q027SBEA', '联邦净利息支出(年化)', '十亿美元', 'fiscal', 'L1·FRED/BEA', ('fred', 'A091RC1Q027SBEA'))
add('WTREGEN', 'TGA财政部现金(周)', '十亿美元', 'fiscal', 'L1·FRED', ('fred', 'WTREGEN'))
add('GFDEGDQ188S', '联邦债务/GDP', '%', 'fiscal', 'L1·FRED', ('fred', 'GFDEGDQ188S'))
# 贸易 trade
add('BOPGSTB', '商品与服务贸易差额', '百万美元', 'trade', 'L1·FRED/BEA', ('fred', 'BOPGSTB'))
add('EXPGS', '商品与服务出口', '百万美元', 'trade', 'L1·FRED/BEA', ('fred', 'EXPGS'))
add('IMPGS', '商品与服务进口', '百万美元', 'trade', 'L1·FRED/BEA', ('fred', 'IMPGS'))
# 美中竞赛 cn
add('DEXCHUS', '美元兑人民币', '元/美元', 'cn', 'L1·FRED', ('fred', 'DEXCHUS'))
add('Y_000300SS', '沪深300ETF', '元', 'cn', 'L2·Yahoo', ('yahoo', '510300.SS'))
add('Y_HSI', '恒生指数', '点', 'cn', 'L2·Yahoo', ('yahoo', '^HSI'))
# IRLTLT01CNM156N(OECD中国10Y)已被FRED下架404, 由EM_CGB10Y(东财/中债, 日度)替代
add('IMPCH', '美国自中国进口', '百万美元', 'cn', 'L1·FRED/Census', ('fred', 'IMPCH'))
add('EXPCH', '美国对中国出口', '百万美元', 'cn', 'L1·FRED/Census', ('fred', 'EXPCH'))
add('CNTRADE', '美国对华贸易差额', '百万美元', 'cn', 'L1·FRED/Census⚙️计算', ('calc_cn',))
add('B235RC1Q027SBEA', '联邦关税收入(年化)', '十亿美元', 'cn', 'L1·FRED/BEA', ('fred', 'B235RC1Q027SBEA'))
# 资产 asset
add('Y_GSPC', '标普500', '点', 'asset', 'L2·Yahoo', ('yahoo', '^GSPC'))
add('Y_IXIC', '纳斯达克综指', '点', 'asset', 'L2·Yahoo', ('yahoo', '^IXIC'))
add('VIXCLS', 'VIX波动率', '点', 'asset', 'L1·FRED/CBOE', ('fred', 'VIXCLS'))
add('Y_MOVE', 'MOVE美债波动率', '点', 'liq', 'L2·Yahoo(ICE BofA)', ('yahoo', '^MOVE'))
add('Y_DXY', '美元指数DXY', '点', 'asset', 'L2·Yahoo', ('yahoo', 'DX-Y.NYB'))
add('Y_GOLD', 'COMEX黄金', '美元/盎司', 'asset', 'L2·Yahoo', ('yahoo', 'GC=F'))
add('Y_GVZ', '黄金波动率GVZ', '点', 'asset', 'L2·Yahoo(CBOE)', ('yahoo', '^GVZ'))
add('Y_OVX', '原油波动率OVX', '点', 'energy', 'L2·Yahoo(CBOE)', ('yahoo', '^OVX'))
add('Y_COPPER', 'COMEX铜', '美元/磅', 'energy', 'L2·Yahoo', ('yahoo', 'HG=F'))
add('Y_BTC', '比特币', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'BTC-USD'))
add('CSUSHPISA_YOY', 'CS房价指数同比', '%', 'asset', 'L1·FRED/S&P⚙️同比', ('yoy', 'CSUSHPISA', 12))
add('HOUST', '新屋开工', '千户', 'asset', 'L1·FRED/Census', ('fred', 'HOUST'))
add('WALCL', '美联储总资产(周)', '十亿美元', 'asset', 'L1·FRED', ('fred', 'WALCL'))
# 制造业 mfg
add('INDPRO_YOY', '工业产出同比', '%', 'mfg', 'L1·FRED⚙️同比', ('yoy', 'INDPRO', 12))
add('IPMAN_YOY', '制造业产出同比', '%', 'mfg', 'L1·FRED⚙️同比', ('yoy', 'IPMAN', 12))
add('TCU', '产能利用率', '%', 'mfg', 'L1·FRED', ('fred', 'TCU'))
add('DGORDER_YOY', '耐用品订单同比', '%', 'mfg', 'L1·FRED/Census⚙️同比', ('yoy', 'DGORDER', 12))
add('NEWORDER', '核心资本品订单', '百万美元', 'mfg', 'L1·FRED/Census', ('fred', 'NEWORDER'))
# 国际移动 move
add('TSA_PAX', 'TSA日均安检旅客', '百万人', 'move', 'L1·TSA', ('tsa',))
# 民调 poll 补充(支持率主图在 trump_zone.json)
add('UMCSENT', '密歇根消费者信心', '点', 'poll', 'L1·FRED/UMich', ('fred', 'UMCSENT'))
# iFinD直采(由 scripts/fetch_ifind.py 每日沙箱管线刷新, Actions不抓; ext=仅登记元数据)
add('IF_000300SH', '沪深300指数', '点', 'cn', 'L1·iFinD⚙️直采', ('ext',))
add('IF_000001SH', '上证综合指数', '点', 'cn', 'L1·iFinD⚙️直采', ('ext',))
add('IF_399006SZ', '创业板指', '点', 'cn', 'L1·iFinD⚙️直采', ('ext',))
add('IF_000905SH', '中证500指数', '点', 'cn', 'L1·iFinD⚙️直采', ('ext',))
add('IF_AU9999', '沪金AU9999现货', '元/克', 'asset', 'L1·iFinD⚙️直采', ('ext',))
add('IF_AG9999', '沪银AG9999现货', '元/千克', 'asset', 'L1·iFinD⚙️直采', ('ext',))
# CFTC持仓(由 scripts/fetch_cftc.py 每日管线刷新; ext=仅登记)
add('CFTC_GC_NET', '黄金非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_SI_NET', '白银非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_PL_NET', '铂金非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_PA_NET', '钯金非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_DX_NET', '美元指数非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_JY_NET', '日元非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_ES_NET', '标普E-mini非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_BTC_NET', '比特币期货非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_HG_NET', '铜非商业净持仓', '手', 'asset', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_TY_NET', '10Y美债期货净投机', '手', 'rate', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_US_NET', '30Y美债期货净投机', '手', 'rate', 'L1·CFTC⚙️周报', ('ext',))
add('CFTC_TU_NET', '2Y美债期货净投机', '手', 'rate', 'L1·CFTC⚙️周报', ('ext',))
add('GLD_SHARES', 'GLD基金份额(积累)', '份', 'asset', 'L2·Yahoo⚙️快照积累', ('ext',))
add('SLV_SHARES', 'SLV基金份额(积累)', '份', 'asset', 'L2·Yahoo⚙️快照积累', ('ext',))
# ---- B类扩充: 金融条件/外国国债/信用与行业ETF/汇率 ----
add('NFCI', '芝加哥联储金融条件指数', '点', 'rate', 'L1·FRED/ChicagoFed', ('fred', 'NFCI'))
add('STFSI4', '圣路易斯联储金融压力指数', '点', 'rate', 'L1·FRED/StLouisFed(原STFSI4已更名STLFSI4)', ('fred', 'STLFSI4'))
add('IRLTLT01JPM156N', '日本10Y国债收益率', '%', 'rate', 'L1·FRED/OECD', ('fred', 'IRLTLT01JPM156N'))
add('IRLTLT01DEM156N', '德国10Y国债收益率', '%', 'rate', 'L1·FRED/OECD', ('fred', 'IRLTLT01DEM156N'))
add('IRLTLT01GBM156N', '英国10Y国债收益率', '%', 'rate', 'L1·FRED/OECD', ('fred', 'IRLTLT01GBM156N'))
add('ECBDFR', '欧央行存款利率', '%', 'rate', 'L1·FRED/ECB', ('fred', 'ECBDFR'))
add('Y_LQD', '投资级信用债ETF(LQD)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'LQD'))
add('Y_HYG', '高收益信用债ETF(HYG)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'HYG'))
add('Y_EMB', '新兴市场债ETF(EMB)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'EMB'))
add('Y_TLT', '20Y+美债ETF(TLT)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'TLT'))
add('Y_GLD', '黄金ETF(GLD)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'GLD'))
add('Y_SLV', 'COMEX白银', '美元/盎司', 'asset', 'L2·Yahoo', ('yahoo', 'SI=F'))
add('Y_USDJPY', '美元兑日元', '日元', 'asset', 'L2·Yahoo', ('yahoo', 'JPY=X'))
add('Y_EURUSD', '欧元兑美元', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'EURUSD=X'))
add('Y_XLK', '科技行业ETF(XLK)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'XLK'))
add('Y_XLF', '金融行业ETF(XLF)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'XLF'))
add('Y_XLE', '能源行业ETF(XLE)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'XLE'))
add('Y_XLV', '医疗行业ETF(XLV)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'XLV'))
add('Y_XLI', '工业行业ETF(XLI)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'XLI'))
add('Y_IBIT', '比特币ETF(IBIT)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'IBIT'))
add('Y_PLT', '铂金ETF(PPLT)', '美元', 'asset', 'L2·Yahoo', ('yahoo', 'PPLT'))
# ---- 流动性板块(GMF框架): 由 scripts/fetch_liquidity.py 每日管线刷新, ext=仅登记 ----
for sid, name, unit, src in [
    ('SOFR99', 'SOFR第99分位(尾部)', '%', 'L1·FRED/NYFed'),
    ('TGCRRATE', 'TGCR三方回购中位利率', '%', 'L1·FRED/NYFed'),
    ('IORB', '准备金利率IORB', '%', 'L1·FRED'),
    ('RRPONTSYAWARD', 'ON RRP中标利率', '%', 'L1·FRED/NYFed'),
    ('RRPONTSYD', 'ON RRP余额', '十亿美元', 'L1·FRED/NYFed'),
    ('WRESBAL', '银行准备金余额', '百万美元', 'L1·FRED/H.4.1'),
    ('WREPOFOR', '外国官方逆回购池(FIMA)', '百万美元', 'L1·FRED/H.4.1'),
    ('SWPT', '央行流动性互换余额', '百万美元', 'L1·FRED/H.4.1'),
    ('DCPF1M', '1M AA金融商票利率', '%', 'L1·FRED'),
    ('DTWEXBGS', '广义贸易加权美元指数', '点', 'L1·FRED'),
    ('M2SL', '美国M2(季调)', '十亿美元', 'L1·FRED'),
    ('ECBASSETSW', '欧央行总资产', '百万欧元', 'L1·FRED/ECB'),
    ('JPNASSETS', '日央行总资产', '十亿日元', 'L1·FRED/BOJ'),
    ('LIQ_EZM3', '欧元区M3', '万亿欧元', 'L1·ECB'),
    ('LIQ_CNM2', '中国M2', '万亿元', 'L3·东财(PBOC口径)'),
    ('LIQ_CNM1', '中国M1', '万亿元', 'L3·东财(PBOC口径)'),
    ('LIQ_SRF', 'SRF常备回购便利用量', '十亿美元', 'L1·NYFed'),
    ('SPR_SOFR_IORB', 'SOFR-IORB利差', 'bp', '⚙️自建'),
    ('SPR_TGCR_IORB', 'TGCR-IORB利差', 'bp', '⚙️自建'),
    ('SPR_SOFR_EFFR', 'SOFR-EFFR利差', 'bp', '⚙️自建'),
    ('SPR_SOFR99', 'SOFR尾部压力(99分位-中位)', 'bp', '⚙️自建'),
    ('SPR_SOFR_ONRRP', 'SOFR-ONRRP利差', 'bp', '⚙️自建'),
    ('SPR_CP_SOFR', '商票-SOFR利差(CP-OIS代理)', 'bp', '⚙️自建'),
    ('NETLIQ', '净流动性(总资产-TGA-RRP)', '万亿美元', '⚙️自建'),
    ('WALCL_YOY', '美联储总资产同比', '%', '⚙️同比'),
    ('ECBASSETSW_YOY', '欧央行总资产同比', '%', '⚙️同比'),
    ('JPNASSETS_YOY', '日央行总资产同比', '%', '⚙️同比'),
    ('M2SL_YOY', '美国M2同比', '%', '⚙️同比'),
    ('LIQ_EZM3_YOY', '欧元区M3同比', '%', '⚙️同比'),
    ('LIQ_CNM2_YOY', '中国M2同比', '%', 'L3·东财(PBOC口径)'),
    ('LIQ_CNM1_YOY', '中国M1同比', '%', 'L3·东财(PBOC口径)'),
    ('GM2_YOY', '全球M2同比(美欧中简单平均)', '%', '⚙️自建'),
]:
    add(sid, name, unit, 'liq', src, ('ext',))
# ---- B类第二批(fetch_extra.py每日管线刷新, ext=仅登记) ----
for sid, name, unit, sec, src in [
    ('WDTGAL', '财政部TGA现金余额', '百万美元', 'fiscal', 'L1·FRED/Treasury'),
    ('US_AUC_10Y_BTC', '10Y美债拍卖投标倍数', '倍', 'fiscal', 'L1·FiscalData'),
    ('US_AUC_30Y_BTC', '30Y美债拍卖投标倍数', '倍', 'fiscal', 'L1·FiscalData'),
    ('US_AUC_2Y_BTC', '2Y美债拍卖投标倍数', '倍', 'fiscal', 'L1·FiscalData'),
    ('JP_UST_HOLD', '日本持有美债', '十亿美元', 'fiscal', 'L1·美财政部TIC'),
    ('CN_UST_HOLD', '中国持有美债', '十亿美元', 'fiscal', 'L1·美财政部TIC'),
    ('UK_UST_HOLD', '英国持有美债', '十亿美元', 'fiscal', 'L1·美财政部TIC'),
    ('FO_UST_HOLD', '外国官方持有美债', '十亿美元', 'fiscal', 'L1·美财政部TIC'),
    ('M1SL', '美国M1(季调)', '十亿美元', 'liq', 'L1·FRED'),
    ('OBFR', '隔夜银行融资利率OBFR', '%', 'liq', 'L1·FRED/NYFed'),
    ('MMMFFAQ027S', '货币基金总资产', '十亿美元', 'liq', 'L1·FRED/OFR'),
    ('CA_M2', '加拿大M2(季调)', '百万加元', 'liq', 'L1·加拿大央行'),
    ('JPM2_YOY', '日本M2同比', '%', 'liq', 'L1·日本央行'),
    ('UKM4_YOY', '英国M4同比', '%', 'liq', 'L1·英国央行IADB'),
    ('WLCFLPCL', '贴现窗口一级信贷(周)', '百万美元', 'liq', 'L1·FRED/H.4.1'),
    ('WLCFLL', '联储贷款总额(H.4.1)', '百万美元', 'liq', 'L1·FRED/H.4.1'),
    ('WLCFLSCL', '贴现窗口二级信贷(周)', '百万美元', 'liq', 'L1·FRED/H.4.1'),
    ('PD_UST_POS', '一级交易商美债净持仓', '百万美元', 'liq', 'L1·NYFed FR2004'),
    ('PD_MBS_POS', '一级交易商MBS净持仓', '百万美元', 'liq', 'L1·NYFed FR2004'),
    ('PD_CORP_POS', '一级交易商公司债净持仓', '百万美元', 'liq', 'L1·NYFed FR2004'),
    ('PD_AGY_POS', '一级交易商机构债净持仓', '百万美元', 'liq', 'L1·NYFed FR2004'),
    ('SPR_SOFR99_ONRRP', 'SOFR99分位-ONRRP利差', 'bp', 'liq', '⚙️自建'),
    ('SPR_TGCR_ONRRP', 'TGCR-ONRRP利差', 'bp', 'liq', '⚙️自建'),
    ('STICKCPIM157SFRBATL', '粘性CPI(环比折年)', '%', 'price', 'L1·FRED/亚特兰大联储'),
    ('MEDCPIM158SFRBCLE', '中位CPI(环比折年)', '%', 'price', 'L1·FRED/克利夫兰联储'),
    ('PCETRIM12M159SFRBDAL', '截尾PCE(环比折年)', '%', 'price', 'L1·FRED/达拉斯联储'),
    ('EXPINF5YR', '密歇根5年通胀预期', '%', 'price', 'L1·FRED/密歇根大学'),
    ('T5YIFR', '5y5y远期通胀预期', '%', 'price', 'L1·FRED'),
    ('IR14270', '进口价格指数', '指数', 'price', 'L1·FRED/BLS'),
    ('ZORI_US', 'Zillow全美租金指数', '美元/月', 'price', 'L2·Zillow'),
    ('ECIALLCIV', '雇佣成本指数ECI', '指数', 'jobs', 'L1·FRED/BLS'),
    ('CCSA', '持续领取失业金人数', '人', 'jobs', 'L1·FRED/DOL'),
    ('BAMLH0A0HYM2EY', '高收益债收益率', '%', 'rate', 'L1·FRED/ICE BofA'),
    ('BAMLC0A1CAAA', 'AAA公司债利差', '%', 'rate', 'L1·FRED/ICE BofA'),
    ('BAMLC0A4CBBB', 'BBB公司债利差', '%', 'rate', 'L1·FRED/ICE BofA'),
    ('T10Y3M', '10Y-3M国债利差', '%', 'rate', 'L1·FRED'),
    ('ACMTP10', '10Y期限溢价(ACM)', '%', 'rate', 'L1·NYFed ACM'),
    ('SPR_USCN10Y', '中美10Y利差(美-中)', 'pt', 'rate', '⚙️自建'),
    ('USSTHPI', '美国房价指数(购房价)', '指数', 'asset', 'L1·FRED/Census·HUD'),
    ('GOLD_SILVER_RATIO', '金银比', '倍', 'asset', '⚙️自建'),
    ('EM_PMI', '中国制造业PMI', '点', 'cn', 'L3·东财(统计局口径)'),
    ('EM_PMI_NM', '中国非制造业PMI', '点', 'cn', 'L3·东财(统计局口径)'),
    ('EM_CPI_YOY', '中国CPI同比', '%', 'cn', 'L3·东财(统计局口径)'),
    ('EM_PPI_YOY', '中国PPI同比', '%', 'cn', 'L3·东财(统计局口径)'),
    ('EM_GDP_YOY', '中国GDP同比', '%', 'cn', 'L3·东财(统计局口径)'),
    ('EM_RETAIL_YOY', '中国社会零售同比', '%', 'cn', 'L3·东财(统计局口径)'),
    ('EM_LOAN_NEW', '新增人民币贷款', '亿元', 'cn', 'L3·东财(PBOC口径)'),
    ('EM_LOAN_ACC_YOY', '贷款余额同比', '%', 'cn', 'L3·东财(PBOC口径)'),
    ('CN_LPR1Y', 'LPR 1年期', '%', 'cn', 'L1·chinamoney'),
    ('CN_LPR5Y', 'LPR 5年期以上', '%', 'cn', 'L1·chinamoney'),
    ('CN_SHIBOR3M', 'SHIBOR 3M', '%', 'cn', 'L1·chinamoney'),
    ('CN_SHIBORON', 'SHIBOR隔夜', '%', 'cn', 'L1·chinamoney'),
    ('EM_CGB2Y', '中国国债收益率2Y', '%', 'cn', 'L3·东财(中债口径)'),
    ('EM_CGB5Y', '中国国债收益率5Y', '%', 'cn', 'L3·东财(中债口径)'),
    ('EM_CGB10Y', '中国国债收益率10Y', '%', 'cn', 'L3·东财(中债口径)'),
    ('EM_CGB30Y', '中国国债收益率30Y', '%', 'cn', 'L3·东财(中债口径)'),
]:
    add(sid, name, unit, sec, src, ('ext',))
# 仅刷新不进板块(周报已在用的序列)
for extra in ['EFFR', 'WEI', 'GDPNOW', 'PAYEMS',
              'CPIAUCSL', 'CPILFESL', 'PCEPILFE', 'PERMIT', 'EXHOSLUSM495S',
              'CSUSHPISA', 'HOSSUPUSM673N', 'INDPRO', 'BUSINV', 'ISRATIO',
              'RSAFS', 'PCEC96', 'PSAVERT', 'DSPIC96', 'CES0500000003']:
    add(extra, extra, '', None, 'L1·FRED', ('fred', extra))

SECTIONS = [
    ('poll',   '民调'),
    ('pm',     '市场政策预期'),
    ('cn',     '美中竞赛'),
    ('fiscal', '财政'),
    ('trade',  '贸易'),
    ('price',  '物价'),
    ('rate',   '利率'),
    ('liq',    '流动性'),
    ('jobs',   '就业'),
    ('energy', '能源'),
    ('asset',  '资产'),
    ('mfg',    '制造业'),
    ('move',   '国际移动'),
]

def main():
    os.makedirs(DATA, exist_ok=True)
    cs_path = os.path.join(DATA, 'chart_series.js')
    hist = {}
    if os.path.exists(cs_path):
        s = open(cs_path, encoding='utf-8').read()
        try:
            hist = json.loads(s[s.index('{'):s.rindex('}') + 1])
        except Exception:
            hist = {}
    # 1) 收集所有基础抓取任务(含衍生序列的底座)
    fred_ids, other_jobs = [], {}
    for it in S:
        how = it['how']; kind = how[0]
        if kind in ('fred', 'yoy', 'diff', 'fred_div'):
            if how[1] not in fred_ids: fred_ids.append(how[1])
        elif kind == 'yahoo':
            other_jobs[it['id']] = (lambda sym: lambda: yahoo(sym))(how[1])
        elif kind == 'debt':
            other_jobs['US_DEBT'] = us_debt
        elif kind == 'tsa':
            other_jobs['TSA_PAX'] = tsa_pax
    raw = {}
    # 2a) FRED: 12条/批合并请求(绕开限流)
    log('FRED批量抓取', len(fred_ids), '条…')
    t0 = time.time()
    raw.update(fred_batch(fred_ids))
    log('FRED完成, 用时%.0fs' % (time.time() - t0))
    # 2b) Yahoo/财政部/TSA 并发
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fn): key for key, fn in other_jobs.items()}
        for fu in as_completed(futs):
            key = futs[fu]
            try:
                raw[key] = fu.result() or []
            except Exception as e:
                raw[key] = []
                log('  x', key, repr(e)[:120])
    # 2) 计算+入库
    ok, fail = [], []
    for it in S:
        how = it['how']; kind = how[0]
        try:
            if kind == 'ext':
                # 外部管线(如iFinD)刷新的键: 只登记, 保留既有数据
                if len(hist.get(it['id'], [])) >= 3:
                    ok.append(it['id'])
                else:
                    fail.append(it['id'])
                continue
            if kind in ('fred', 'debt', 'tsa'):
                ser = raw.get(how[1] if kind == 'fred' else it['id'], [])
            elif kind == 'yahoo':
                ser = raw.get(it['id'], [])
            elif kind == 'yoy':
                ser = yoy(raw.get(how[1], []), how[2])
            elif kind == 'diff':
                ser = diff(raw.get(how[1], []), how[2])
            elif kind == 'fred_div':
                ser = [[d, round(v / how[2], 3)] for d, v in raw.get(how[1], [])]
            elif kind == 'calc_cn':
                bd = dict(raw.get('EXPCH', []))
                ser = [[d, round(v - bd[d], 1)] for d, v in raw.get('IMPCH', []) if d in bd]
            else:
                ser = []
            if ser and len(ser) >= 3:
                hist[it['id']] = ser
                ok.append(it['id'])
            else:
                fail.append(it['id'])
        except Exception as e:
            fail.append(it['id'])
            log('  x', it['id'], repr(e)[:120])
    # --- FRED发布日滞后补齐(决议日/晚间运行时,FRED名义与实际收益率尚未发布当天值) ---
    # 用Yahoo ^TNX收盘补DGS10缺口; DFII10按恒等式 DFII10 = DGS10 - T10YIE 补齐
    # (FRED上该恒等式精确到0.01成立; 次日FRED发布后整列替换, 自动回正)
    try:
        tnx = yahoo('^TNX', '3mo') or []
        d10 = hist.get('DGS10', [])
        if tnx and d10:
            have = {p[0] for p in d10}
            add_pts = [[d, round(v, 2)] for d, v in tnx if v and d > d10[-1][0] and d not in have]
            if add_pts:
                hist['DGS10'] = d10 + add_pts
                log('DGS10用Yahoo收盘补齐', len(add_pts), '天, 最新→', add_pts[-1])
                ie = dict(hist.get('T10YIE', []))
                re_ser = hist.get('DFII10', [])
                have_re = {p[0] for p in re_ser}
                re_add = [[d, round(v - ie[d], 2)] for d, v in add_pts if d in ie and d not in have_re]
                if re_add:
                    re_ser = sorted(re_ser + re_add, key=lambda p: p[0])
                    hist['DFII10'] = re_ser
                    log('DFII10按恒等式补齐', len(re_add), '天, 最新→', re_add[-1])
    except Exception as e:
        log('  x 滞后补齐失败(不影响主流程)', repr(e)[:120])
    # --- FOMC决议日利率走廊补丁: 决议公布当日FRED的DFEDTARU/DFEDTARL仍滞后一天,
    #     而新区间已由联储官方公布(=fedwatch.json的current_bucket), 直接补齐 ---
    try:
        fw = json.load(open(os.path.join(DATA, 'fedwatch.json'), encoding='utf-8'))
        cb = (fw.get('current_bucket') or '').split('-')
        asof_d = (fw.get('asof') or '')[:10]
        if len(cb) == 2 and asof_d:
            lo_v, hi_v = int(cb[0]) / 100.0, int(cb[1]) / 100.0
            for sid, vv in (('DFEDTARL', lo_v), ('DFEDTARU', hi_v)):
                ser_l = hist.get(sid, [])
                if ser_l and ser_l[-1][0] < asof_d and abs(ser_l[-1][1] - vv) > 0.001:
                    ser_l = ser_l + [[asof_d, vv]]
                    hist[sid] = ser_l
                    log(sid, '决议日补齐→', asof_d, vv)
    except Exception as e:
        log('  x 走廊补齐失败(不影响主流程)', repr(e)[:120])
    # 写 chart_series.js (只更新本次抓到的键, MM上传的键原样保留)
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write('window.CHART_SERIES = ' + json.dumps(hist, separators=(',', ':')) + ';')
    # 板块元数据(保留脚本清单之外的既有扩展分区,避免每日重建冲掉手工/外部扩展)
    meta = {'updated': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M') + ' 北京',
            'sections': []}
    script_keys = {k for k, _ in SECTIONS}
    extra_secs = []
    prev_ms = os.path.join(DATA, 'macro_series.json')
    if os.path.exists(prev_ms):
        try:
            prev = json.load(open(prev_ms, encoding='utf-8'))
            extra_secs = [s for s in prev.get('sections', []) if s.get('key') not in script_keys]
        except Exception:
            extra_secs = []
    for key, name in SECTIONS:
        items = [{'id': it['id'], 'name': it['name'], 'unit': it['unit'], 'src': it['src'],
                  'n': len(hist.get(it['id'], [])), 'last': (hist.get(it['id']) or [[None, None]])[-1]}
                 for it in S if it['sec'] == key]
        meta['sections'].append({'key': key, 'name': name, 'items': items})
    meta['sections'].extend(extra_secs)
    with open(os.path.join(DATA, 'macro_series.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(DATA, 'macro_catalog.js'), 'w', encoding='utf-8') as f:
        cat = [{'id': it['id'], 'name': it['name'], 'unit': it['unit']} for it in S if it['sec']]
        known = {it['id'] for it in S if it['sec']}
        prev_cat_path = os.path.join(DATA, 'macro_catalog.js')
        if os.path.exists(prev_cat_path):
            try:
                t = open(prev_cat_path, encoding='utf-8').read()
                prev_cat = json.loads(t[t.index('['):t.rindex(']') + 1])
                cat += [c for c in prev_cat if c.get('id') not in known]
            except Exception:
                pass
        f.write('window.MACRO_CATALOG = ' + json.dumps(cat, ensure_ascii=False, separators=(',', ':')) + ';')
    log('完成: 成功%d 失败%d | chart_series键数%d' % (len(ok), len(fail), len(hist)))
    log('失败:', ','.join(fail) if fail else '无')

if __name__ == '__main__':
    main()
