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
    # 内外盘套利研究结论（套利研究\内外盘 回测定论，手改层）
    'arb_notes': {
        '锡': '正套（买LME空SHFE）唯一有统计支撑：窗口开后 20 日均值 -0.46%、近三年胜率 68%、纯策略 Sharpe 1.21；盘面锁价套利 +3,485 元/吨可做、纸面等比价 1.174；弱形态时期望≈0',
        '铝': '反套中等强度：进口深亏档 2024 起 +0.87%/20 日、胜率 61%；正套侧统计不支持',
        '铜': '回测不支持，观察不操作',
        '锌': '盈亏到 1% 分位统计也两侧塌，观察不操作',
        '铅': '未回测，仅作窗口观察',
        '镍': '未回测，仅作窗口观察（内外盘受印尼供给与汇率扰动大）',
    },
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
    """六品种 LME cash/3M 最新值，带缓存（westmetall 只更到上一 LME 工作日）"""
    cache = load_json(LME_CACHE) or {}
    try:
        fresh = bool(cache) and all(
            (datetime.date.today() - datetime.date.fromisoformat(v.get('date', '2000-01-01'))).days <= 3
            for v in cache.values())
    except Exception:
        fresh = False
    if not fresh:
        for sym, field in ARB_LME_FIELDS.items():
            pts = westmetall_cash3m(field, datetime.date.today().year)
            if pts:
                d = max(pts)
                cache[sym] = {'date': d, 'cash': pts[d][0], 'm3': pts[d][1]}
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

def shfe_month_spread(sym, asof=None):
    """guan 逐合约：M+1 与 M+2 收盘差（近月-次月，元/吨）；asof 截断供回填；失败返回 None"""
    ref = datetime.date.fromisoformat(asof) if asof else datetime.date.today()
    codes = []
    for k in (1, 2):
        m = ref.month + k
        y = ref.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        codes.append('%s%02d%02d' % (sym, y % 100, m))
    closes = []
    for c in codes:
        ks = guan_kline(c, limit=10)
        if asof:
            ks = [k for k in (ks or []) if k[0] <= asof]
        if not ks:
            return None
        closes.append(ks[-1][1])
    return closes[0] - closes[1], codes

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
        rows.append({'sym': sym, 'name': name, 'val': val,
                     'prev': pts[dates[-2]] if len(dates) > 1 else None,
                     'pct': pct, 'date': d_last, 'src': src, 'n': len(win_pts)})
    # 移仓换月损益 + 滑点费用：正套(买LME空SHFE) 净移仓/月 = (SHFE次月−近月) − (LME3M−cash)/3×汇率
    lme = lme_cash3m_latest()
    fx = usdcny()
    for r in rows:
        sp = shfe_month_spread(r['sym'], asof=today)
        lm = lme.get(r['sym']) or {}
        shfe_gain = (-sp[0]) if sp else None            # 空头移仓收益=次月−近月
        r['month_codes'] = sp[1] if sp else None
        lme_cost = ((lm['m3'] - lm['cash']) / 3 * fx) if (lm.get('cash') and fx) else None
        r['lme_date'] = lm.get('date', '')
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
            v = vs.get(sym)
            tape = ''
            if v:
                tape = '20 日 %s · 120 日位置 %.0f%%' % (fmt_pct(v['chg20']), v['pos'] * 100)
                if v.get('vol_ratio'):
                    tape += ' · 量比 %.1f' % v['vol_ratio']
            positions.append({'side': side, 'name': name, 'score': sc_map.get(name),
                              'fund': fund, 'pv': pv, 'tape': tape,
                              'view': (views.get(name) or '').strip()})
        exits = [{'name': n, 'view': (views.get(n) or '').strip()}
                 for n in today_names if n not in longs + shorts and (views.get(n) or '').strip()]
        score_rows = [(n, s, '多' if n in longs else ('空' if n in shorts else '—'))
                      for n, s in xs.get('scores', [])]
        sec = {'sig_date': xs.get('sig_date', ''), 'equity': xs.get('equity'),
               'cum': xs.get('cum'), 'ann': xs.get('ann'), 'sharpe': xs.get('sharpe'),
               'mdd': xs.get('mdd'), 'positions': positions, 'exits': exits,
               'score_rows': score_rows, 'stale_factors': xs.get('stale') or [],
               'today_events': C['xs_today'], 'recent_events': (xs.get('events') or [])[:3],
               'views_since': views_since, 'views_stale': views_stale}
    C['xs_sec'] = sec

    # 09 内外盘套利评估（进口盈亏窗口 × 套利研究回测结论）
    arb_rows = []
    arb_notes = nar.get('arb_notes') or {}
    for r in ctx.get('arb') or []:
        val, pct, adj = r['val'], r['pct'], r.get('adj')
        if adj is not None and adj > 0 and pct >= 0.6:
            win, cls = '正套窗口开（扣移仓+费用后仍可锁 %s）' % format(adj, '+,.0f'), 'up'
        elif val > 0 and adj is not None and adj <= 0:
            win, cls = '纸面窗口被移仓/费用吃掉（调整后 %s）' % format(adj, '+,.0f'), ''
        elif adj is not None and adj > 0:
            win, cls = '扣费后微利（%s），观察' % format(adj, '+,.0f'), ''
        elif pct >= 0.8:
            win, cls = '盈亏逼近转正（高分位），窗口临近', 'up'
        elif pct <= 0.2:
            win, cls = '进口深亏（反套关注：空LME多SHFE）', 'dn'
        else:
            win, cls = '无窗口', ''
        stale = False
        try:
            stale = (datetime.date.fromisoformat(ctx['today'])
                     - datetime.date.fromisoformat(r['date'])).days > 4
        except Exception:
            pass
        arb_rows.append(dict(r, win=win, cls=cls, stale=stale,
                             note=(arb_notes.get(r['name']) or '').strip()))
    C['arb'] = arb_rows

    # 10 事前冻结（state 承转, 超 21 天标注重估）
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
                L.append('- 基本面：' + '；'.join(p['fund']))
            pv = '；'.join(p['pv'])
            if p['tape']:
                pv = (pv + '｜' if pv else '') + p['tape']
            if pv:
                L.append('- 价量：' + pv)
            if p['view']:
                L.append('- 点评：' + p['view'])
            L.append('')
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
    if C.get('arb'):
        L += ['## 09 内外盘套利评估（进口盈亏 − 移仓 − 滑点 ⚙️ + 回测结论）', '',
              '| 品种 | 进口盈亏 | 净移仓/月 | 调整后空间 | 近一年分位 | 窗口判定 |', '|---|---|---|---|---|---|']
        for r in C['arb']:
            roll = format(r['net_roll'], '+,.0f') if r.get('net_roll') is not None else '缺'
            adj = format(r['adj'], '+,.0f') if r.get('adj') is not None else '—'
            L.append('| %s | %s | %s | %s | %.0f%% | %s |' % (
                r['name'], format(r['val'], '+,.0f'), roll, adj, r['pct'] * 100, r['win']))
        L.append('')
        for r in C['arb']:
            if r['note']:
                L.append('- **%s**（%s，至 %s%s）：%s' % (
                    r['name'], r['src'], r['date'], '，滞后' if r['stale'] else '', r['note']))
        L += ['', '_口径：正套=买LME空SHFE，单位元/吨。净移仓/月=(SHFE次月−近月)−(LME3M−cash)/3×汇率，正=正套有利（SHFE contango 空头赚月差 / LME back 多头赚贴水）；调整后空间=进口盈亏+净移仓−滑点费用（双边滑点+手续费+FX 对冲按 SHFE 价 %.2f%% 估，持有 1 个月）。分位为近 250 个交易点。_' % (ARB_COST_PCT * 100), '']
    L += ['## 10 事前冻结', '| 判断 | 期限 | 成功条件 | 失败/失效条件 | 重估节点 |', '|---|---|---|---|---|']
    L += ['| %s | %s | %s | %s | %s |' % tuple(r) for r in C['freezes']] + ['']
    L += ['## 11 数据来源'] + ['- %s' % s for s in C['sources']] + ['']
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
                body.append('<div class="sub"><b>基本面</b>：%s</div>' % esc('；'.join(p['fund'])))
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

    if C.get('arb'):
        h.append('<section><div class="sec-no">09 / ARBITRAGE</div><div class="sec-t">内外盘套利评估 · 进口盈亏 − 移仓 − 滑点</div>')
        h.append('<table><tr><th>品种</th><th>进口盈亏</th><th>净移仓/月</th><th>调整后空间</th><th>近一年分位</th><th>窗口判定</th></tr>')
        for r in C['arb']:
            roll = format(r['net_roll'], '+,.0f') if r.get('net_roll') is not None else '缺'
            adj = format(r['adj'], '+,.0f') if r.get('adj') is not None else '—'
            vcls = 'up' if (r.get('adj') or r['val']) > 0 else 'dn'
            h.append('<tr><td>%s</td><td>%s</td><td>%s</td><td class="%s">%s</td><td>%.0f%%</td><td class="%s">%s</td></tr>' % (
                esc(r['name']), format(r['val'], '+,.0f'), roll, vcls, adj, r['pct'] * 100,
                r['cls'], esc(r['win'])))
        h.append('</table><ul>')
        for r in C['arb']:
            if r['note']:
                h.append('<li><b>%s</b>（%s，至 %s%s；月差 %s，LME 结构至 %s）：%s</li>' % (
                    esc(r['name']), esc(r['src']), r['date'],
                    '，滞后' if r['stale'] else '',
                    '/'.join(r['month_codes']) if r.get('month_codes') else '缺',
                    r.get('lme_date') or '缺', esc(r['note'])))
        h.append('</ul><p class="note">口径：正套=买LME空SHFE，单位元/吨。净移仓/月=(SHFE次月−近月)−(LME3M−cash)/3×汇率，正=正套有利（SHFE contango 空头赚月差 / LME back 多头赚贴水）；调整后空间=进口盈亏+净移仓−滑点费用（双边滑点+手续费+FX 对冲按 SHFE 价 %.2f%% 估，持有 1 个月）；分位为近 250 个交易点。窗口判定 ⚙️ 规则生成，操作结论以套利研究回测为准。</p></section>' % (ARB_COST_PCT * 100))

    h.append('<section><div class="sec-no">10 / PRE-COMMITMENT</div><div class="sec-t">事前冻结</div><table><tr><th>判断</th><th>期限</th><th>成功条件</th><th>失败/失效条件</th><th>重估节点</th></tr>')
    h += ['<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % tuple(esc(x) for x in r) for r in C['freezes']]
    h.append('</table></section>')

    h.append('<section><div class="sec-no">11 / SOURCES</div><div class="sec-t">数据来源</div><ul>')
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

    state['narrative'] = nar
    state['hashes'] = hashes
    state['last_run'] = datetime.datetime.now().strftime('%F %T')
    open(STATE_PATH, 'w', encoding='utf-8').write(json.dumps(state, ensure_ascii=False, indent=1))
    log('state -> %s' % STATE_PATH)

if __name__ == '__main__':
    main()
