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
    'xs_views': {},          # {品种中文名: 基本面/价量点评}，手改层，承转同 freezes
    'xs_views_since': '',
    # 内外盘套利研究结论（2026-10-12 六品种统一回测刷新，手改层；
    # 报告=套利研究\内外盘\报告\内外盘六品种统一回测与驱动拆解_20261012.md）
    'arb_notes': {
        '镍': '已回测：正套有统计支撑——窗口开后20日比价 -0.42%/胜率67%，四分位单调，双向 Sharpe 1.02/只正套 0.83；驱动=比价>均衡（-0.73%/80%）+宽窗口（76%）。当前 +1,670 超宽窗口阈值 1,215 且比分位 78%，六品种中唯一窗口+驱动同满足',
        '锌': '窗口 6.7 年仅开 14 次但开后强收敛（20日 -1.30%/胜率92%），只正套 Sharpe 0.84——由"不做"上调为窗口开时小仓试正套；当前 -4,242 深关',
        '铅': '已回测：方向对（窗口开20日 -1.30%/71%）但窗口仅开 7 次，样本不足不构成操作依据，保持观察',
        '锡': '正套唯一有统计支撑（现货口径 Sharpe 1.21，9/21 报告），期货口径复现一致；最强驱动=比价>均衡 1.142（-1.15%/77%），弱形态（窗口开但比价<均衡）反向 +0.34%。当前关窗+比分位 10%，远离触发；触发=比价升破均衡且窗口重开',
        '铜': '回测不支持（只正套 Sharpe -0.46）；唯一有效形态=窗口开且比价>均衡 1.133（-0.51%/78%），当前两项均不满足',
        '铝': '正套侧不支持（双向 Sharpe 0.00）；比价>均衡时收敛 -1.25%/69% 但被成本吃掉；反套沿 9/21 报告（深亏档 +0.87%/20日）。当前 +513/98% 分位：观察不操作',
    },
    # 内外盘套利结构性背景（手改层，2026-10-12 自回测报告第四节；货流结构决定统计形态；
    # 面板中作为灰字附在每日自动刷新的中短期数据行 fund_auto 之后）
    'arb_fund': {
        '镍': '中国纯镍资源贫乏、精炼镍进口常态化（俄镍/印尼镍豆长单不断），窗口开关与真实货流联动紧密，"超均衡→点价进口→砸回均衡"链条完整，故统计显著；印尼 NPI/中间品放量节奏决定内盘相对强弱大方向',
        '锌': '国内冶炼产能过剩、锌锭进口窗口常年关闭；一旦打开=海外紧到极点或国内真缺货，收敛又急又狠（92%）——14 次样本小是品种结构决定的，每次都对应真实供需错配',
        '铅': '基本自给自足且再生铅占比过半，精铅进口货流近乎不存在，套利机制缺乏实物基础，统计方向再对也不能当真',
        '锡': '缅甸/印尼供给冲击频繁，精锡进口是真实边际调节变量（海关月报可验证货流），正套有实物支撑；当前利润由 LME 深 contango 现金折扣构成、比价低于均衡——无货流就无收敛压力',
        '铜': '年进口数百万吨的常态化大货流，套利资金最充分，比价长期贴均衡线窄幅波动——六品种中定价最有效率，窗口边际信息含量最低',
        '铝': '电解铝进口受政策与关税结构约束，窗口开后收敛慢，价差常靠汇率与单边趋势弥合而非货流；统计支撑在反套侧（深亏档空LME多SHFE）',
    },
    'arb_fund_since': '2026-10-12',
    'arb_review': '可操作性排序 镍＞锡＞锌＞铝(反套)＞铜＞铅，根源在进口货流结构：货流常态化且边际可调的品种（镍/锡）统计显著；窗口罕见但一开即极端错配的品种（锌）少而强；自给自足无货流的（铅）不可操作；定价最有效的（铜）留给盘面的空间最小',
    # 截面策略总综述（手改层；留空=按当日持仓因子自动合成）
    'xs_book_review': '',
    'xs_book_review_since': '',
}

# 内外盘套利：六品种进口盈亏日度序列（zhiji id, 口径注）
ARB_SERIES = [
    ('CU', '铜', 'ID01030232', 'Mysteel 铜进口盈亏'),
    ('AL', '铝', 'a12759731', 'SMM 电解铝进口盈亏'),
    ('ZN', '锌', 'ID01030236', 'Mysteel 锌锭进口盈亏(含税)'),
    ('PB', '铅', 'ID01030003', 'Mysteel 铅锭进口盈亏'),
    ('NI', '镍', 'a10125274', 'SMM 纯镍期货进口盈亏'),
    ('SN', '锡', 'ID01590826', 'Mysteel 锡锭现货进口盈亏'),
]
ARB_CACHE = os.path.join(DATA, 'arb_import_pnl.json')
ARB_BOOTSTRAP_START = '2023-01-01'
ZHIJI_SERIES = 'https://zhiji-ai.xyz/commodity/api/series'
# 移仓+滑点假设（手改层）：费用=双边滑点+手续费+FX对冲，按 SHFE 价百分比
ARB_COST_PCT = 0.0012
ARB_LME_FIELDS = {'CU': 'LME_Cu_cash', 'AL': 'LME_Al_cash', 'ZN': 'LME_Zn_cash',
                  'PB': 'LME_Pb_cash', 'NI': 'LME_Ni_cash', 'SN': 'LME_Sn_cash'}
LME_CACHE = os.path.join(DATA, 'lme_cash3m.json')
_WM_MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
              "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}

# 截面策略因子归类与口语化解读（z>0 / z<0 两种措辞）
XS_FUND_FACTORS = ('注销占比', '升贴水', 'TC变化率', '进口盈亏', '库存变化')
XS_PV_FACTORS = ('动量', '外盘强弱', '股商背离')
XS_MACRO_FACTORS = ('美元指数变化率', 'SOX')
XS_PHRASE = {
    '注销占比': ('注销仓单占比偏高，实货提货强', '注销仓单占比偏低，提货意愿弱'),
    '升贴水': ('现货升水走强/贴水收窄', '现货升水走弱/贴水走阔'),
    'TC变化率': ('TC 回升，矿端边际宽松', 'TC 下行，矿端趋紧'),
    '进口盈亏': ('进口窗口改善', '进口窗口恶化'),
    '库存变化': ('显性库存去化', '显性库存累积'),
    '动量': ('近月动量偏强', '近月动量偏弱'),
    '外盘强弱': ('外盘强于内盘', '外盘弱于内盘'),
    '股商背离': ('股票强于商品，权益端先行看多', '股票弱于商品，权益端先行看空'),
    '美元指数变化率': ('美元指数走强', '美元指数回落'),
    'SOX': ('费城半导体走强，需求预期改善', '费城半导体走弱，需求预期转弱'),
}
XS_SYM2CN = {'CU': '铜', 'AL': '铝', 'ZN': '锌', 'PB': '铅', 'NI': '镍', 'SN': '锡'}

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

def variety_stats(sym, asof=None):
    ks = guan_kline(sym)
    if ks and asof:
        ks = [k for k in ks if k[0] <= asof]  # 回填历史日期时不混入更晚的行情
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
    closes = [k[1] for k in ks]
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    return {'date': ks[-1][0], 'close': close, 'chg': chg, 'chg20': chg20,
            'pos': pos, 'vol_ratio': vr, 'ma10': ma10, 'ma20': ma20}

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

# ---------- 内外盘套利（进口盈亏） ----------
def westmetall_cash3m(field, year):
    """westmetall LME 日报：返回 {iso_date: (cash, 3M)}（表行序年内倒序，取 max）"""
    import re as _re
    url = 'https://www.westmetall.com/en/markdaten.php?action=table&field=%s&year=%d' % (field, year)
    try:
        t = subprocess.run(['curl', '-sL', '--max-time', '30', '-H', 'User-Agent: Mozilla/5.0', url],
                           capture_output=True, timeout=40).stdout.decode('utf-8', errors='replace')
    except Exception:
        return {}
    out = {}
    for row in _re.findall(r'<tr[^>]*>(.*?)</tr>', t, _re.S):
        cells = [_re.sub(r'<[^>]+>|\s+', ' ', c).strip()
                 for c in _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.S)]
        if len(cells) < 3:
            continue
        m = _re.match(r'(\d{2})\. (\w+) (\d{4})', cells[0])
        if not m or m.group(2) not in _WM_MONTHS:
            continue
        day = '%s-%02d-%02d' % (m.group(3), _WM_MONTHS[m.group(2)], int(m.group(1)))
        try:
            out[day] = (float(cells[1].replace(',', '')), float(cells[2].replace(',', '')))
        except ValueError:
            continue
    return out

def lme_cash3m_latest():
    """六品种 LME cash/3M 最新值，带缓存（westmetall 只更到上一 LME 工作日）；
    条目带 hist（近 60 个 LME 交易日 {date:[cash,m3]}），供边际变化计算"""
    cache = load_json(LME_CACHE) or {}
    try:
        fresh = bool(cache) and all(
            v.get('hist') and
            (datetime.date.today() - datetime.date.fromisoformat(v.get('date', '2000-01-01'))).days <= 3
            for v in cache.values())
    except Exception:
        fresh = False
    if not fresh:
        for sym, field in ARB_LME_FIELDS.items():
            pts = westmetall_cash3m(field, datetime.date.today().year)
            if pts:
                d = max(pts)
                hist = {dd: [pts[dd][0], pts[dd][1]] for dd in sorted(pts)[-60:]}
                cache[sym] = {'date': d, 'cash': pts[d][0], 'm3': pts[d][1], 'hist': hist}
        try:
            with open(LME_CACHE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception:
            pass
    return cache

def usdcny():
    """新浪 USDCNY 即期买卖中价"""
    try:
        out = subprocess.run(['curl', '-s', '-H', 'Referer: https://finance.sina.com.cn',
                              '--max-time', '10', 'https://hq.sinajs.cn/list=fx_susdcny'],
                             capture_output=True, timeout=15).stdout.decode('gbk', errors='replace')
        f = out.split('="', 1)[1].split(',')
        return (float(f[1]) + float(f[2])) / 2
    except Exception:
        return None

def sina_contract_close(code, asof=None):
    """新浪逐合约日K（InnerFuturesNewService）：返回 (date, close, prev_close)；asof 截断；失败 None"""
    import re as _re
    url = ('https://stock2.finance.sina.com.cn/futures/api/jsonp.php/x/'
           'InnerFuturesNewService.getDailyKLine?symbol=%s' % code)
    try:
        t = subprocess.run(['curl', '-s', '--max-time', '15', url],
                           capture_output=True, timeout=25).stdout.decode('utf-8', 'replace')
        mt = _re.search(r'\((\[.*\])\)', t, _re.S)
        if not mt:
            return None
        rows = json.loads(mt.group(1))
        rows = [r for r in rows if not asof or r['d'] <= asof]
        if len(rows) < 2:
            return None
        return rows[-1]['d'], float(rows[-1]['c']), float(rows[-2]['c'])
    except Exception:
        return None

def shfe_month_spread(sym, asof=None):
    """M+1 与 M+2 收盘差（近月-次月，元/吨）；asof 截断供回填；失败返回 None。
    返回 (spread, codes, spread_date, prev_spread)。guan 对合约代码可能静默回退主力
    （两腿逐点相同），检测到即弃用转新浪逐合约日K（新浪更新滞后约一天，日期随返回值带出）。"""
    ref = datetime.date.fromisoformat(asof) if asof else datetime.date.today()
    codes = []
    for k in (1, 2):
        m = ref.month + k
        y = ref.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        codes.append('%s%02d%02d' % (sym, y % 100, m))
    legs = []
    for c in codes:
        ks = guan_kline(c, limit=10)
        if asof:
            ks = [k for k in (ks or []) if k[0] <= asof]
        if not ks:
            break
        legs.append(ks)
    if len(legs) == 2 and not (legs[0][-1][1:] == legs[1][-1][1:]):
        prev = legs[0][-2][1] - legs[1][-2][1] if min(len(legs[0]), len(legs[1])) >= 2 else None
        return legs[0][-1][1] - legs[1][-1][1], codes, legs[0][-1][0], prev
    # guan 回退主力或缺失 → 新浪逐合约
    sina = [sina_contract_close(c, asof) for c in codes]
    if sina[0] and sina[1]:
        d0, d1 = sina[0][0], sina[1][0]
        return (sina[0][1] - sina[1][1], codes,
                d0 if d0 == d1 else '%s/%s' % (d0, d1),
                sina[0][2] - sina[1][2])
    return None

def zhiji_series(ind_id, start, end):
    """zhiji commodity /series（curl 绕 WAF）；返回 {date: float} 或 None"""
    key = zkey()
    if not key:
        return None
    url = '%s?id=%s&start=%s&end=%s' % (ZHIJI_SERIES, ind_id, start, end)
    try:
        out = subprocess.run(['curl', '-s', '--ssl-no-revoke', '-H', 'X-Data-Key: %s' % key, url],
                             capture_output=True, text=True, timeout=40).stdout
        d = json.loads(out)
        pts = d.get('points')
        if not isinstance(pts, list):
            return None
        res = {}
        for p in pts:
            try:
                res[str(p['date'])[:10]] = float(p['value'])
            except Exception:
                pass
        return res
    except Exception:
        return None

def arb_collect(ctx):
    """进口盈亏缓存增量更新（首跑从 2023-01 自举），产出 ctx['arb'] 评估行"""
    import time as _time
    cache = load_json(ARB_CACHE) or {}
    today = ctx['today']
    rows = []
    for sym, name, ind_id, src in ARB_SERIES:
        ent = cache.get(ind_id) or {'name': name, 'src': src, 'points': {}}
        pts = ent.get('points') or {}
        last = max(pts) if pts else None
        start = ARB_BOOTSTRAP_START if not last else (
            (datetime.date.fromisoformat(last) + datetime.timedelta(days=1)).isoformat())
        if start <= today:
            new = zhiji_series(ind_id, start, today)
            if new:
                pts.update(new)
                ent['points'] = pts
                cache[ind_id] = ent
                _time.sleep(2.2)  # zhiji 限流 30 次/分
        dates = [d for d in sorted(pts) if d <= today]  # 回填历史日期不混入更晚数据
        if not dates:
            continue
        d_last = dates[-1]
        val = pts[d_last]
        win_pts = [pts[d] for d in dates[-250:]]  # 近一年分位
        pct = sum(1 for x in win_pts if x <= val) / len(win_pts)
        pct_prev = None
        if len(dates) > 2:
            wp = [pts[d] for d in dates[-251:-1]]
            pct_prev = sum(1 for x in wp if x <= pts[dates[-2]]) / len(wp)
        rows.append({'sym': sym, 'name': name, 'val': val,
                     'prev': pts[dates[-2]] if len(dates) > 1 else None,
                     'chg5': val - pts[dates[-6]] if len(dates) > 5 else None,
                     'chg20': val - pts[dates[-21]] if len(dates) > 20 else None,
                     'pct': pct, 'pct_prev': pct_prev, 'date': d_last, 'src': src, 'n': len(win_pts)})
    # 移仓换月损益 + 滑点费用：正套(买LME空SHFE) 净移仓/月 = (SHFE次月−近月) − (LME3M−cash)/3×汇率
    lme = lme_cash3m_latest()
    fx = usdcny()
    for r in rows:
        sp = shfe_month_spread(r['sym'], asof=today)
        lm = lme.get(r['sym']) or {}
        shfe_gain = (-sp[0]) if sp else None            # 空头移仓收益=次月−近月
        r['month_codes'] = sp[1] if sp else None
        r['shfe_spread'] = sp[0] if sp else None        # 近月−次月，正=back
        r['shfe_date'] = sp[2] if sp else ''
        r['shfe_spread_prev'] = sp[3] if sp else None
        lme_cost = ((lm['m3'] - lm['cash']) / 3 * fx) if (lm.get('cash') and fx) else None
        r['lme_date'] = lm.get('date', '')
        r['lme_cash'] = lm.get('cash')
        r['lme_m3'] = lm.get('m3')
        # LME 结构边际：hist 中当前日期前一个 LME 交易日
        hist = lm.get('hist') or {}
        if r['lme_cash'] and r['lme_m3'] and r['lme_date'] in hist:
            hds = [d for d in sorted(hist) if d < r['lme_date']]
            if hds:
                pc, pm = hist[hds[-1]]
                r['lme_spread_prev'] = pc - pm
        r['net_roll'] = ((shfe_gain or 0) - (lme_cost or 0)) \
            if (shfe_gain is not None and lme_cost is not None) else None
        close = (ctx['varieties'].get(r['sym']) or {}).get('close')
        r['fee'] = close * ARB_COST_PCT if close else None
        r['adj'] = (r['val'] + (r['net_roll'] or 0) - (r['fee'] or 0)) \
            if r['net_roll'] is not None and r['fee'] is not None else None
    try:
        with open(ARB_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        log('!! arb 缓存写失败: %s' % e)
    ctx['arb'] = rows

# ---------- 数据汇总 ----------
def xs_factor_note(f):
    """因子行 → 口语化归因句；无法解读的因子返回 None"""
    ph = XS_PHRASE.get(f.get('factor'))
    if not ph:
        return None
    txt = ph[0] if (f.get('z') or 0) >= 0 else ph[1]
    return '%s z=%+.1f：%s（贡献 %+.2f）' % (f.get('factor'), f.get('z') or 0, txt, f.get('contrib') or 0)

# 套利基本面自动行引用的 xs 现货端因子（进口盈亏本身已单列，不重复）
ARB_FUND_XS = ('注销占比', '升贴水', '库存变化', 'TC变化率')

def arb_fund_auto(r, ctx, win=None, cat=None):
    """边际变化（相对上一数据日/上一报告期）+ 中短期现状：进口盈亏动量 + 内外期限结构 + xs 现货端因子"""
    seg = []
    # ---- 边际 ----
    mg = []
    if r.get('prev') is not None:
        s = '盈亏日 %s' % format(r['val'] - r['prev'], '+,.0f')
        if r.get('pct_prev') is not None:
            s += '（分位 %.0f%%→%.0f%%）' % (r['pct_prev'] * 100, r['pct'] * 100)
        mg.append(s)
    if r.get('lme_cash') and r.get('lme_m3') and r.get('lme_spread_prev') is not None:
        cur = r['lme_cash'] - r['lme_m3']
        chg = cur - r['lme_spread_prev']
        d_word = ('back 走阔' if chg > 0 else 'back 收窄') if cur > 0 else \
                 ('contango 收窄' if chg > 0 else 'contango 加深')
        mg.append('LME 结构 %s %.1f 美元（%s）' % ('+' if chg >= 0 else '-', abs(chg), d_word))
    if r.get('shfe_spread') is not None and r.get('shfe_spread_prev') is not None:
        mg.append('SHFE 月差 %s 元' % format(r['shfe_spread'] - r['shfe_spread_prev'], '+,.0f'))
    prev = (ctx.get('arb_prev') or {}).get(r['name']) or {}
    prev_cat = prev.get('cat') or prev.get('win_cat')
    if prev_cat and cat and prev_cat != cat:
        mg.append('判定变化 %s → %s（%s 起）' % (prev_cat, cat, prev.get('date') or '?'))
    if mg:
        seg.append('边际：' + '；'.join(mg))
    # ---- 现状 ----
    seg.append('进口盈亏 %s（%s，5 日 %s / 20 日 %s，近一年分位 %.0f%%）' % (
        format(r['val'], '+,.0f'), r['date'][5:],
        format(r['chg5'], '+,.0f') if r.get('chg5') is not None else '—',
        format(r['chg20'], '+,.0f') if r.get('chg20') is not None else '—',
        r['pct'] * 100))
    st = []
    if r.get('lme_cash') and r.get('lme_m3'):
        d = r['lme_cash'] - r['lme_m3']
        st.append('LME %s %.1f 美元（%s）' % ('back' if d > 0 else 'contango', abs(d),
                                             r.get('lme_date') or '缺'))
    if r.get('shfe_spread') is not None:
        st.append('SHFE %s %s 元（%s 至 %s）' % ('back' if r['shfe_spread'] > 0 else 'contango',
                  format(abs(r['shfe_spread']), ',.0f'),
                  '/'.join(r['month_codes']) if r.get('month_codes') else '缺',
                  r.get('shfe_date') or '缺'))
    if st:
        seg.append('内外结构：' + ' · '.join(st))
    fs = []
    for f in ((ctx.get('xs') or {}).get('breakdown') or {}).get(r['sym']) or []:
        if f.get('factor') in ARB_FUND_XS and XS_PHRASE.get(f.get('factor')):
            ph = XS_PHRASE[f['factor']]
            fs.append('%s z=%+.1f：%s' % (f['factor'], f.get('z') or 0,
                                          ph[0] if (f.get('z') or 0) >= 0 else ph[1]))
    if fs:
        seg.append('现货端因子（xs %s）：%s' % ((ctx.get('xs') or {}).get('sig_date') or '?',
                                             '；'.join(fs)))
    return '；'.join(seg)

def build_arb(ctx):
    """09 内外盘套利评估：窗口判定 + 行装配（独立成函数供回填脚本复用）"""
    nar = ctx['narrative']
    arb_rows = []
    arb_notes = nar.get('arb_notes') or {}
    arb_fund = nar.get('arb_fund') or {}
    for r in ctx.get('arb') or []:
        val, pct, adj = r['val'], r['pct'], r.get('adj')
        if adj is not None and adj > 0 and pct >= 0.6:
            win, cls, cat = '正套窗口开（扣移仓+费用后仍可锁 %s）' % format(adj, '+,.0f'), 'up', '窗口开'
        elif val > 0 and adj is not None and adj <= 0:
            win, cls, cat = '纸面窗口被移仓/费用吃掉（调整后 %s）' % format(adj, '+,.0f'), '', '纸面被吃掉'
        elif adj is not None and adj > 0:
            win, cls, cat = '扣费后微利（%s），观察' % format(adj, '+,.0f'), '', '微利'
        elif pct >= 0.8:
            win, cls, cat = '盈亏逼近转正（高分位），窗口临近', 'up', '临近'
        elif pct <= 0.2:
            win, cls, cat = '进口深亏（反套关注：空LME多SHFE）', 'dn', '深亏'
        else:
            win, cls, cat = '无窗口', '', '无窗口'
        stale = False
        try:
            stale = (datetime.date.fromisoformat(ctx['today'])
                     - datetime.date.fromisoformat(r['date'])).days > 4
        except Exception:
            pass
        arb_rows.append(dict(r, win=win, win_cat=cat, cls=cls, stale=stale,
                             note=(arb_notes.get(r['name']) or '').strip(),
                             fund_auto=arb_fund_auto(r, ctx, win, cat),
                             fund=(arb_fund.get(r['name']) or '').strip()))
    return {'arb': arb_rows,
            'arb_review': (nar.get('arb_review') or '').strip(),
            'arb_fund_since': nar.get('arb_fund_since', '')}

# ---------- 事前冻结自动核对（规则代理；🔴失效触发 🟡逼近 ✅维持 ⚪无自动数据源） ----------
def xs_fz(ctx, sym, fname):
    for f in ((ctx['xs'].get('breakdown') or {}).get(sym) or []):
        if f.get('factor') == fname:
            return f.get('z')
    return None

def _ck_ma(v, ma_key, label):
    if not v or not v.get(ma_key):
        return None
    above = v['close'] >= v[ma_key]
    return ('ok' if above else 'trigger',
            '价格%s%s（%s vs %s）' % ('站上' if above else '跌破', label,
                                      fmt_px(v['close']), fmt_px(v[ma_key])))

def fzck_ni(ctx):
    out = []
    z = xs_fz(ctx, 'NI', '注销占比')
    if z is None:
        out.append(('na', '注销占比因子缺数据'))
    elif z < 1.0:
        out.append(('trigger', '注销占比回落至均值区 z=%+.1f → 失效条件触发' % z))
    elif z < 2.0:
        out.append(('warn', '注销占比自极值回落中 z=%+.1f（失效线 z<+1）' % z))
    else:
        out.append(('ok', '注销占比维持高位 z=%+.1f' % z))
    m = _ck_ma(ctx['varieties'].get('NI'), 'ma10', 'MA10')
    if m:
        out.append(m)
    if ctx['xs'] and '镍' not in (ctx['xs'].get('longs') or []):
        out.append(('warn', '截面策略已调出多头'))
    return out

def fzck_cu(ctx):
    out = []
    m = _ck_ma(ctx['varieties'].get('CU'), 'ma20', 'MA20（支撑破位代理）')
    if m:
        out.append(m)
    z_tc = xs_fz(ctx, 'CU', 'TC变化率')
    if z_tc is not None:
        if z_tc > 1.0:
            out.append(('warn', 'TC 明显回升 z=%+.1f，矿端转松（失败条件逼近）' % z_tc))
        else:
            out.append(('ok', 'TC 未连升 z=%+.1f' % z_tc))
    z_p = xs_fz(ctx, 'CU', '升贴水')
    if z_p is not None:
        out.append(('ok' if z_p >= 0 else 'warn',
                    '现货升水%s z=%+.1f' % ('维持偏强' if z_p >= 0 else '转弱', z_p)))
    return out

def fzck_zn(ctx):
    out = []
    z = xs_fz(ctx, 'ZN', '注销占比')
    if z is None:
        out.append(('na', '注销占比因子缺数据'))
    elif z > 2.0:
        out.append(('trigger', '注销占比再飙升 z=%+.1f → 挤仓二波风险触发，按纪律应平空' % z))
    elif z > 1.0:
        out.append(('warn', '注销占比抬升 z=%+.1f（触发线 z>+2）' % z))
    else:
        out.append(('ok', '注销占比平稳 z=%+.1f，无挤仓迹象' % z))
    if ctx['xs'] and '锌' not in (ctx['xs'].get('shorts') or []):
        out.append(('warn', '截面策略已调出空头'))
    return out

def fzck_sn(ctx):
    out = []
    arb = {r['sym']: r for r in (ctx.get('arb') or [])}.get('SN')
    if arb:
        if arb['val'] > 0:
            out.append(('warn', '进口窗口重开（%s）→ 比价结构变化，区间逻辑待重估' % format(arb['val'], '+,.0f')))
        else:
            out.append(('ok', '进口关窗维持（%s）' % format(arb['val'], '+,.0f')))
    v = ctx['varieties'].get('SN')
    if v:
        if v['pos'] >= 0.9:
            out.append(('warn', '价格抵近 120 日区间上沿（位置 %.0f%%），区间策略勿追多' % (v['pos'] * 100)))
        elif v['pos'] <= 0.1:
            out.append(('ok', '价格处 120 日区间下沿（位置 %.0f%%），接近回调买入触发区' % (v['pos'] * 100)))
        else:
            out.append(('ok', '价格居区间中段（120 日位置 %.0f%%）' % (v['pos'] * 100)))
    out.append(('na', '缅甸供给回归/社库加速无自动源，人工核对海关月报+社库'))
    return out

def fzck_lc(ctx):
    return [('na', '碳酸锂不在截面六品种内，去库/仓单无自动数据源，人工核对 SMM 周度')]

FREEZE_CHECKS = [('镍偏多', fzck_ni), ('铜偏多', fzck_cu), ('锌逢高', fzck_zn),
                 ('锡区间', fzck_sn), ('碳酸锂', fzck_lc), ('锂', fzck_lc)]
_FZ_RANK = {'trigger': 3, 'warn': 2, 'na': 1, 'ok': 0}
_FZ_ICON = {'trigger': '🔴', 'warn': '🟡', 'ok': '✅', 'na': '⚪'}

def freeze_check(ctx, text):
    for kw, fn in FREEZE_CHECKS:
        if kw in text:
            try:
                out = fn(ctx)
            except Exception as e:
                return '⚪ 核对异常：%s' % e
            if not out:
                return ''
            worst = max(out, key=lambda x: _FZ_RANK[x[0]])[0]
            return '%s %s' % (_FZ_ICON[worst], '；'.join(d for _s, d in out))
    return '⚪ 无匹配核对规则'

def collect(today):
    ctx = {'today': today}
    # 品种行情
    vs = {}
    for sym, name, grp in VARIETIES:
        st = variety_stats(sym, asof=today)
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
    ctx['heat'] = load_json(os.path.join(DATA, 'heat_pool.json')) or {}
    arb_collect(ctx)
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

    # 08 每日截面策略（持仓 + 因子归因[基本面/价量] + 人工点评层）
    sec = None
    if xs and xs.get('scores'):
        cn2sym = {v: k for k, v in XS_SYM2CN.items()}
        sc_map = {n: s for n, s in xs.get('scores', [])}
        longs, shorts = xs.get('longs') or [], xs.get('shorts') or []
        views = nar.get('xs_views') or {}
        views_since = nar.get('xs_views_since', '')
        views_stale = False
        try:
            views_stale = (datetime.date.fromisoformat(ctx['today'])
                           - datetime.date.fromisoformat(views_since)).days > 7
        except Exception:
            views_stale = bool(views)
        held = [(n, '多') for n in longs] + [(n, '空') for n in shorts]
        # 信号日调仓涉及的品种也附点评（如平空锡）
        sig_ev = [e for e in (xs.get('events') or []) if e[0] == xs.get('sig_date')]
        today_names = [e[2] for e in (C['xs_today'] or sig_ev)]
        positions = []
        for name, side in held:
            sym = cn2sym.get(name, '')
            rows = (xs.get('breakdown') or {}).get(sym) or []
            fund = [x for x in (xs_factor_note(f) for f in rows if f.get('factor') in XS_FUND_FACTORS) if x]
            pv = [x for x in (xs_factor_note(f) for f in rows
                              if f.get('factor') in XS_PV_FACTORS + XS_MACRO_FACTORS) if x]
            frows = [f for f in rows if f.get('factor') in XS_FUND_FACTORS]
            fnet = sum((f.get('contrib') or 0) for f in frows)
            fup = sum(1 for f in frows if (f.get('z') or 0) > 0)
            fdn = sum(1 for f in frows if (f.get('z') or 0) < 0)
            fshort = [XS_PHRASE[f['factor']][0 if (f.get('z') or 0) >= 0 else 1]
                      for f in frows if f.get('factor') in XS_PHRASE]
            pvshort = [XS_PHRASE[f['factor']][0 if (f.get('z') or 0) >= 0 else 1]
                       for f in rows
                       if f.get('factor') in XS_PV_FACTORS + XS_MACRO_FACTORS
                       and f.get('factor') in XS_PHRASE]
            v = vs.get(sym)
            tape = ''
            if v:
                tape = '20 日 %s · 120 日位置 %.0f%%' % (fmt_pct(v['chg20']), v['pos'] * 100)
                if v.get('vol_ratio'):
                    tape += ' · 量比 %.1f' % v['vol_ratio']
            positions.append({'side': side, 'name': name, 'score': sc_map.get(name),
                              'fund': fund, 'pv': pv, 'tape': tape,
                              'fund_sum': ('基本面净贡献 %+.2f（%d 项偏多/%d 项偏空）' % (fnet, fup, fdn)) if frows else '',
                              'fund_short': fshort,
                              'drv_short': fshort or pvshort,
                              'view': (views.get(name) or '').strip()})
        book_review = (nar.get('xs_book_review') or '').strip()
        if not book_review and positions:
            def _side_txt(side):
                return '；'.join('%s（%s）' % (p['name'], '、'.join(p['drv_short'][:2]))
                                 for p in positions if p['side'] == side and p.get('drv_short'))
            _lo, _so = _side_txt('多'), _side_txt('空')
            _parts = ([('多头侧：' + _lo)] if _lo else []) + ([('空头侧：' + _so)] if _so else [])
            book_review = ('。'.join(_parts) + '（自动合成自因子归因，手改层 xs_book_review 可覆盖）') if _parts else ''
        exits = [{'name': n, 'view': (views.get(n) or '').strip()}
                 for n in today_names if n not in longs + shorts and (views.get(n) or '').strip()]
        score_rows = [(n, s, '多' if n in longs else ('空' if n in shorts else '—'))
                      for n, s in xs.get('scores', [])]
        sec = {'sig_date': xs.get('sig_date', ''), 'equity': xs.get('equity'),
               'cum': xs.get('cum'), 'ann': xs.get('ann'), 'sharpe': xs.get('sharpe'),
               'mdd': xs.get('mdd'), 'positions': positions, 'exits': exits,
               'score_rows': score_rows, 'stale_factors': xs.get('stale') or [],
               'today_events': C['xs_today'], 'recent_events': (xs.get('events') or [])[:3],
               'views_since': views_since, 'views_stale': views_stale,
               'book_review': book_review}
    C['xs_sec'] = sec

    C.update(build_arb(ctx))

    # 10 热度量化观测池（_heat_pool.py 产物：星球×公众号）
    hp = ctx.get('heat') or {}
    heat_rows = []
    for cc, name in [('cu', '铜'), ('al', '铝'), ('zn', '锌'), ('pb', '铅'), ('ni', '镍'), ('sn', '锡')]:
        m = (hp.get('metals') or {}).get(cc)
        if m:
            heat_rows.append(m)
    heat_rows.sort(key=lambda x: -x['heat'])
    C['heat'] = {'date': hp.get('date', ''), 'rows': heat_rows,
                 'global_share': hp.get('global_share'),
                 'stale': hp.get('date', '') < ctx['today']}

    # 11 事前冻结（state 承转, 超 21 天标注重估）
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
        row.append(freeze_check(ctx, f[0]))
        fr.append(row)
    C['freezes'] = fr

    # 11 来源
    C['sources'] = [
        '期货行情：知几 guan 日线（%s）' % (max((v['date'] for v in vs.values()), default='—')),
        '宏观快照：%s（%s）' % (ctx['lq_asof'], (load_json(os.path.join(DATA, 'live_quotes.json')) or {}).get('src', '')),
        'FedWatch：%s' % fw.get('asof', '—'),
        '数据发布面板：%s' % (ctx['releases'].get('updated', '—')[:10]),
        '星球雷达：%s' % (ctx['zsxq'].get('asof', '—')),
        '截面策略：%s' % (xs.get('sig_date', '—')),
        '内外盘套利：进口盈亏六系列（最新 %s，zhiji/Mysteel/SMM）' % (
            max((r['date'] for r in C.get('arb') or []), default='—')),
        '热度观测池：星球分类面板×8 家公众号（%s）' % ((C.get('heat') or {}).get('date') or '—'),
    ]
    C['narrative_note'] = '主要矛盾/事前冻结承自 %s（state 文件可手改，次日生效）' % nar.get('contradiction_since', '—')
    return C

# ---------- 渲染 ----------
def arb_md_lines(C):
    """09 内外盘套利 md 段（独立成函数供回填脚本复用）"""
    L = []
    if not C.get('arb'):
        return L
    L += ['## 09 内外盘套利评估（基本面 × 量化）', '']
    for r in C['arb']:
        L.append('- **%s**（%s）：%s' % (r['name'], r['win'], r.get('fund_auto') or ''))
        if r.get('fund'):
            L.append('  - 结构性背景：' + r['fund'])
    L += ['', '_结构性背景承自 %s 六品种统一回测报告第四节（手改层）。_' % (
              C.get('arb_fund_since') or '2026-10-12'), '',
          '<details><summary>量化明细：进口盈亏 − 移仓 − 滑点（表格 + 回测结论 + 口径）</summary>', '',
          '| 品种 | 进口盈亏 | 净移仓/月 | 调整后空间 | 近一年分位 | 窗口判定 |', '|---|---|---|---|---|---|']
    for r in C['arb']:
        roll = format(r['net_roll'], '+,.0f') if r.get('net_roll') is not None else '缺'
        adj = format(r['adj'], '+,.0f') if r.get('adj') is not None else '—'
        L.append('| %s | %s | %s | %s | %.0f%% | %s |' % (
            r['name'], format(r['val'], '+,.0f'), roll, adj, r['pct'] * 100, r['win']))
    L.append('')
    if C.get('arb_review'):
        L += ['综述：' + C['arb_review'], '']
    for r in C['arb']:
        if r['note']:
            L.append('- **%s**（%s，至 %s%s）：%s' % (
                r['name'], r['src'], r['date'], '，滞后' if r['stale'] else '', r['note']))
    L += ['', '_口径：正套=买LME空SHFE，单位元/吨。净移仓/月=(SHFE次月−近月)−(LME3M−cash)/3×汇率，正=正套有利（SHFE contango 空头赚月差 / LME back 多头赚贴水）；调整后空间=进口盈亏+净移仓−滑点费用（双边滑点+手续费+FX 对冲按 SHFE 价 %.2f%% 估，持有 1 个月）。分位为近 250 个交易点。评估默认正套视角：进口盈亏指标本身即买外盘/卖内盘损益，且中国为净进口国、实物货流只支持正套方向；反套不单独计算，仅在进口深亏（分位≤20%%）时提示关注。窗口判定 ⚙️ 规则生成，操作结论以套利研究回测为准。_' % (ARB_COST_PCT * 100), '',
          '</details>', '']
    return L

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
    sec = C.get('xs_sec')
    if sec:
        L += ['## 08 每日截面策略（有色截面多空 · 信号日 %s）' % sec['sig_date'], '']
        eq = format(round(sec['equity']), ',d') if sec.get('equity') else '—'
        L += ['净值 %s（累计 %s）· 年化 %s · Sharpe %.2f · 最大回撤 %s · [实时面板 ↗](https://amiya866.github.io/metals-framework/xs-panel/)' % (
            eq, fmt_pct(sec['cum'] or 0), fmt_pct(sec['ann'] or 0), sec['sharpe'] or 0,
            fmt_pct(sec['mdd'] or 0)), '']
        L += ['| 品种 | 评分 | 方向 |', '|---|---|---|']
        L += ['| %s | %+.2f | %s |' % r for r in sec['score_rows']] + ['']
        for p in sec['positions']:
            L.append('**%s·%s（评分 %s）**' % (p['side'], p['name'],
                                               '%+.2f' % p['score'] if p['score'] is not None else '—'))
            if p['fund']:
                L.append('- 基本面：' + (('【' + p['fund_sum'] + '】') if p.get('fund_sum') else '')
                         + '；'.join(p['fund']))
            pv = '；'.join(p['pv'])
            if p['tape']:
                pv = (pv + '｜' if pv else '') + p['tape']
            if pv:
                L.append('- 价量：' + pv)
            if p['view']:
                L.append('- 点评：' + p['view'])
            L.append('')
        if sec.get('book_review'):
            L += ['综述：' + sec['book_review'], '']
        for e in sec['exits']:
            L.append('- 调出·%s：%s' % (e['name'], e['view']))
        if sec['exits']:
            L.append('')
        evs = sec['today_events'] or sec['recent_events']
        L += [('今日调仓：' if sec['today_events'] else '今日无调仓；最近调仓：')
              + '；'.join('%s %s%s' % (e[0][5:], e[1], e[2]) for e in evs), '']
        if sec['stale_factors']:
            L += ['⚠ 因子数据滞后：' + '、'.join(sec['stale_factors']), '']
        if sec['views_stale']:
            L += ['_点评承自 %s，超 7 天未更新，待重估_' % sec['views_since'], '']
    L += arb_md_lines(C)
    hp_sec = C.get('heat') or {}
    if hp_sec.get('rows'):
        L += ['## 10 热度量化观测池（星球 × 公众号 · 数据日 %s%s）' % (
                  hp_sec.get('date') or '—', '，非今日' if hp_sec.get('stale') else ''), '',
              '| 品种 | 热度分 | 候选(星球+公众号) | Top10均热 | 方向(相对基线) | 趋势 |',
              '|---|---|---|---|---|---|']
        for m in hp_sec['rows']:
            nvote = (m.get('bull') or 0) + (m.get('bear') or 0) + (m.get('neutral') or 0)
            dirn = ('多%d/空%d/中%d（%+.0fpp）' % (m.get('bull') or 0, m.get('bear') or 0,
                                                 m.get('neutral') or 0, m.get('rel') or 0)) if nvote else '无表态'
            L.append('| %s | %s | %d（%d+%d） | %s | %s | %s |' % (
                m['name'], format(m.get('heat') or 0, ',d'), m.get('n_cand') or 0,
                (m.get('n_cand') or 0) - (m.get('n_wx') or 0), m.get('n_wx') or 0,
                format(m.get('top10_mean') or 0, ',d'), dirn, m.get('trend') or '→'))
        L.append('')
        for m in hp_sec['rows']:
            vps = (m.get('viewpoints') or [])[:3]
            if vps:
                L.append('- **%s**（热度 %s）：%s' % (m['name'], format(m.get('heat') or 0, ',d'),
                                                       '；'.join(vps)))
        L += ['', '_口径：热度=阅读+3×评论+2×点赞；候选=星球近180天（面板+全量存档+实时流）+8家公众号各取近100条选30，均须标题/正文/要点真提该品种（已剔"无锡"等地名误命中）；方向=句级归属——只数提到该品种的句子的多空词，90天窗口，rel=看多占比−全场基线（同口径重计 %.0f%%），贝叶斯收缩 k=10；趋势=热度 vs 7日均（首周→为基线未满）。_' % ((hp_sec.get('global_share') or 0) * 100), '']
    L += ['## 11 事前冻结', '| 判断 | 期限 | 成功条件 | 失败/失效条件 | 重估节点 | 自动核对 ⚙️ |', '|---|---|---|---|---|---|']
    L += ['| %s | %s | %s | %s | %s | %s |' % tuple(r) for r in C['freezes']] + ['']
    L += ['_自动核对=规则代理每日重算：🔴 失效触发或成功条件被破坏（按纪律应复核/行动）/ 🟡 逼近或部分触发 / ✅ 条件维持 / ⚪ 无自动数据源需人工核对；代理口径：支撑破位≈跌破 MA20、均值区≈|z|<1，触发以人工复核为准。_', '']
    L += ['## 12 数据来源'] + ['- %s' % s for s in C['sources']] + ['']
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

def arb_html_lines(C):
    """09 内外盘套利 html 段（独立成函数供回填脚本复用）"""
    h = []
    if not C.get('arb'):
        return h
    h.append('<section><div class="sec-no">09 / ARBITRAGE</div><div class="sec-t">内外盘套利评估 · 基本面（中短期数据）× 量化</div>')
    h.append('<ul>')
    for r in C['arb']:
        h.append('<li><b>%s</b> <span class="%s">%s</span>：%s%s</li>' % (
            esc(r['name']), r['cls'], esc(r['win']), esc(r.get('fund_auto') or ''),
            ('<br><span style="color:var(--gray);font-size:12px">结构性背景：%s</span>' % esc(r['fund']))
            if r.get('fund') else ''))
    h.append('</ul>')
    h.append('<p class="note">结构性背景（灰字）承自 %s 六品种统一回测报告第四节，手改层；上方数据行 ⚙️ 每日自动刷新。</p>' % esc(C.get('arb_fund_since') or '2026-10-12'))
    h.append('<details style="margin-top:6px"><summary style="cursor:pointer;font-size:13px;color:var(--gray)">量化明细 · 进口盈亏 − 移仓 − 滑点（表格 + 回测结论 + 口径）▸</summary>')
    h.append('<table><tr><th>品种</th><th>进口盈亏</th><th>净移仓/月</th><th>调整后空间</th><th>近一年分位</th><th>窗口判定</th></tr>')
    for r in C['arb']:
        roll = format(r['net_roll'], '+,.0f') if r.get('net_roll') is not None else '缺'
        adj = format(r['adj'], '+,.0f') if r.get('adj') is not None else '—'
        vcls = 'up' if (r.get('adj') or r['val']) > 0 else 'dn'
        h.append('<tr><td>%s</td><td>%s</td><td>%s</td><td class="%s">%s</td><td>%.0f%%</td><td class="%s">%s</td></tr>' % (
            esc(r['name']), format(r['val'], '+,.0f'), roll, vcls, adj, r['pct'] * 100,
            r['cls'], esc(r['win'])))
    h.append('</table>')
    if C.get('arb_review'):
        h.append('<p style="font-size:13.5px;margin:8px 0"><b>综述</b>：%s</p>' % esc(C['arb_review']))
    h.append('<ul>')
    for r in C['arb']:
        if r['note']:
            h.append('<li><b>%s</b>（%s，至 %s%s；月差 %s 至 %s，LME 结构至 %s）：%s</li>' % (
                esc(r['name']), esc(r['src']), r['date'],
                '，滞后' if r['stale'] else '',
                '/'.join(r['month_codes']) if r.get('month_codes') else '缺',
                r.get('shfe_date') or '缺',
                r.get('lme_date') or '缺', esc(r['note'])))
    h.append('</ul><p class="note">口径：正套=买LME空SHFE，单位元/吨。净移仓/月=(SHFE次月−近月)−(LME3M−cash)/3×汇率，正=正套有利（SHFE contango 空头赚月差 / LME back 多头赚贴水）；调整后空间=进口盈亏+净移仓−滑点费用（双边滑点+手续费+FX 对冲按 SHFE 价 %.2f%% 估，持有 1 个月）；分位为近 250 个交易点。评估默认正套视角：进口盈亏指标本身即买外盘/卖内盘损益，且中国为净进口国、实物货流只支持正套方向；反套不单独计算，仅在进口深亏（分位≤20%%）时提示关注。窗口判定 ⚙️ 规则生成，操作结论以套利研究回测为准。</p></details></section>' % (ARB_COST_PCT * 100))
    return h

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

    sec = C.get('xs_sec')
    if sec:
        h.append('<section><div class="sec-no">08 / XS STRATEGY</div><div class="sec-t">每日截面策略 · 有色截面多空</div>')
        eq = format(round(sec['equity']), ',d') if sec.get('equity') else '—'
        h.append('<p class="note">信号日 %s · 净值 %s（累计 %s）· 年化 %s · Sharpe %.2f · 最大回撤 %s · <a href="https://amiya866.github.io/metals-framework/xs-panel/">实时面板 ↗</a></p>' % (
            esc(sec['sig_date']), eq, fmt_pct(sec['cum'] or 0), fmt_pct(sec['ann'] or 0),
            sec['sharpe'] or 0, fmt_pct(sec['mdd'] or 0)))
        h.append('<table><tr><th>品种</th><th>评分</th><th>方向</th></tr>')
        for n, s, d in sec['score_rows']:
            cls = 'up' if s > 0 else 'dn'
            dcls = 'up' if d == '多' else ('dn' if d == '空' else '')
            h.append('<tr><td>%s</td><td class="%s">%+.2f</td><td class="%s">%s</td></tr>' % (esc(n), cls, s, dcls, d))
        h.append('</table>')
        cards = []
        for p in sec['positions']:
            side_cls = 'up' if p['side'] == '多' else 'dn'
            sc = '%+.2f' % p['score'] if p['score'] is not None else '—'
            body = []
            if p['fund']:
                body.append('<div class="sub"><b>基本面</b>%s：%s</div>' % (
                    ('【' + esc(p['fund_sum']) + '】') if p.get('fund_sum') else '',
                    esc('；'.join(p['fund']))))
            pv = '；'.join(p['pv'])
            if p['tape']:
                pv = (pv + '｜' if pv else '') + p['tape']
            if pv:
                body.append('<div class="sub"><b>价量</b>：%s</div>' % esc(pv))
            if p['view']:
                body.append('<div style="font-size:13px;margin-top:4px"><b>点评</b>：%s</div>' % esc(p['view']))
            cards.append('<div class="card"><div class="nm"><span class="%s">%s</span>·%s '
                         '<span style="color:var(--gray);font-size:11px">评分 %s</span></div>%s</div>' % (
                             side_cls, p['side'], esc(p['name']), sc, ''.join(body)))
        h.append('<div class="cards" style="grid-template-columns:repeat(auto-fill,minmax(300px,1fr))">%s</div>' % ''.join(cards))
        if sec.get('book_review'):
            h.append('<p style="font-size:13.5px;margin-top:8px"><b>综述</b>：%s</p>' % esc(sec['book_review']))
        for e in sec['exits']:
            h.append('<p class="note">调出·%s：%s</p>' % (esc(e['name']), esc(e['view'])))
        evs = sec['today_events'] or sec['recent_events']
        h.append('<p class="note">%s%s</p>' % (
            '今日调仓：' if sec['today_events'] else '今日无调仓；最近调仓：',
            esc('；'.join('%s %s%s' % (e[0][5:], e[1], e[2]) for e in evs))))
        if sec['stale_factors']:
            h.append('<p class="note">⚠ 因子数据滞后：%s</p>' % esc('、'.join(sec['stale_factors'])))
        if sec['views_stale']:
            h.append('<p class="note">点评承自 %s，超 7 天未更新，待重估。</p>' % esc(sec['views_since']))
        h.append('</section>')

    h.extend(arb_html_lines(C))

    hp_sec = C.get('heat') or {}
    if hp_sec.get('rows'):
        h.append('<section><div class="sec-no">10 / HEAT POOL</div><div class="sec-t">热度量化观测池 · 星球 × 公众号</div>')
        h.append('<p class="note">数据日 %s%s · 热度=阅读+3×评论+2×点赞 · 候选=星球近180天（面板+全量存档+实时流）+8家公众号各取近100条选30，须真提该品种（已剔地名误命中） · 方向=句级归属（只数提到该品种的句子）90天窗口，相对全场基线 %.0f%%，贝叶斯收缩 k=10</p>' % (
            esc(hp_sec.get('date') or '—'), '（非今日，滞后）' if hp_sec.get('stale') else '',
            (hp_sec.get('global_share') or 0) * 100))
        h.append('<table><tr><th>品种</th><th>热度分</th><th>候选(星球+公众号)</th><th>Top10均热</th><th>方向(相对基线)</th><th>趋势</th></tr>')
        for m in hp_sec['rows']:
            rel = m.get('rel') or 0
            nvote = (m.get('bull') or 0) + (m.get('bear') or 0) + (m.get('neutral') or 0)
            dtxt = ('多%d/空%d/中%d（%+.0fpp）' % (m.get('bull') or 0, m.get('bear') or 0,
                                                 m.get('neutral') or 0, rel)) if nvote else '无表态'
            dcls = ('up' if rel > 5 else ('dn' if rel < -5 else '')) if nvote else ''
            h.append('<tr><td>%s</td><td class="num">%s</td><td>%d（%d+%d）</td><td class="num">%s</td>'
                     '<td class="%s">%s</td><td>%s</td></tr>' % (
                         esc(m['name']), format(m.get('heat') or 0, ',d'), m.get('n_cand') or 0,
                         (m.get('n_cand') or 0) - (m.get('n_wx') or 0), m.get('n_wx') or 0,
                         format(m.get('top10_mean') or 0, ',d'), dcls, dtxt,
                         m.get('trend') or '→'))
        h.append('</table><ul>')
        for m in hp_sec['rows']:
            vps = (m.get('viewpoints') or [])[:3]
            if vps:
                h.append('<li><b>%s</b>（热度 %s）：%s</li>' % (
                    esc(m['name']), format(m.get('heat') or 0, ',d'), esc('；'.join(vps))))
        h.append('</ul></section>')

    h.append('<section><div class="sec-no">11 / PRE-COMMITMENT</div><div class="sec-t">事前冻结</div><table><tr><th>判断</th><th>期限</th><th>成功条件</th><th>失败/失效条件</th><th>重估节点</th><th>自动核对 ⚙️</th></tr>')
    for r in C['freezes']:
        cells = [esc(x) for x in r]
        ck = cells[5] if len(cells) > 5 else ''
        ccls = ' style="color:var(--red);font-weight:700"' if ck.startswith('🔴') else ''
        h.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td%s>%s</td></tr>' % (
            cells[0], cells[1], cells[2], cells[3], cells[4], ccls, ck))
    h.append('</table><p class="note">自动核对=规则代理每日重算：🔴 失效触发或成功条件被破坏（按纪律应复核/行动）/ 🟡 逼近或部分触发 / ✅ 条件维持 / ⚪ 无自动数据源需人工核对；代理口径：支撑破位≈跌破 MA20、均值区≈|z|&lt;1，触发以人工复核为准。</p></section>')

    h.append('<section><div class="sec-no">12 / SOURCES</div><div class="sec-t">数据来源</div><ul>')
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
def write_protected(path, content, hashes, force=False):
    """返回 'written' / 'kept_manual' / 'unchanged'"""
    h = sha(content)
    if os.path.exists(path) and not force:
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
    nar = state.get('narrative') or {}
    for k, v in DEFAULT_NARRATIVE.items():  # state 缺的键回退默认（新增手改层免手动补）
        nar.setdefault(k, v)
    hashes = state.get('hashes') or {}

    ctx = collect(today)
    ctx['narrative'] = nar
    ctx['arb_prev'] = state.get('arb_prev') or {}  # 上一期套利判定快照（边际对比）
    if not ctx['varieties']:
        log('!! 品种行情全空（guan 不可达?），中止不产出')
        return
    C = build_content(ctx)

    md = render_md(ctx, C)
    html = render_panel(ctx, C)
    r1 = write_protected(os.path.join(BASE, 'reports', '%s.md' % today), md, hashes, force)
    r2 = write_protected(os.path.join(BASE, 'panels', '%s.html' % today), html, hashes, force)
    log('report: %s | panel: %s' % (r1, r2))

    if r2 in ('written',) or r1 in ('written',):
        update_archive(ctx, C)

    if C.get('arb'):
        state['arb_prev'] = {r['name']: {'win': r['win'], 'cat': r.get('win_cat'),
                                         'adj': r.get('adj'), 'val': r['val'], 'date': today}
                             for r in C['arb']}
    state['narrative'] = nar
    state['hashes'] = hashes
    state['last_run'] = datetime.datetime.now().strftime('%F %T')
    open(STATE_PATH, 'w', encoding='utf-8').write(json.dumps(state, ensure_ascii=False, indent=1))
    log('state -> %s' % STATE_PATH)

if __name__ == '__main__':
    main()
