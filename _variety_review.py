# -*- coding: utf-8 -*-
"""分品种每日点评生成器（2026-10-09 建）
四段式【价格】【行业新闻】【供需与库存】【观点】× 8 品种（铜铝锌铅镍锡锂硅）
数据源：知几 guan 日线(SHFE 主力) + westmetall(LME cash/3M) + 金属网数据缓存库(库存/升贴水/TC/开工率/利润)
       + caibao-hub 信息速递 news.json + 供应扰动 disruptions.json + 星球小作文 zsxq_metals.json
产出: reports/variety_latest.html(固定URL=最新) + panels/review_YYYY-MM-DD.html(归档)
手改保护: 归档版被手改(hash 不符)则不覆盖；观点 override 写 _variety_review_state.json
用法: python _variety_review.py [--date YYYY-MM-DD]
"""
import os, re, sys, json, sqlite3, subprocess, hashlib, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, '_variety_review_state.json')
KEYS_PATH = os.path.join(BASE, '_local_keys.json')
CACHE_DB = r'D:\Kimi\金属总网\网站构建\db\数据缓存_v1.db'
NEWS_JSON = r'D:\Kimi\caibao-hub\data\news.json'
DISR_JSON = r'D:\Kimi\caibao-hub\data\disruptions.json'
ZSXQ_JSON = r'D:\Kimi\金属总网\网站构建\小作文平台\data\zsxq_metals.json'
GUAN = 'https://zhiji-ai.xyz/guan/api'

MONTHS = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,'July':7,
          'August':8,'September':9,'October':10,'November':11,'December':12}

# 品种配置: (comm代码, 中文, 期货代码列表, LME westmetall field 或 None, news/小作文键)
COMMS = [
    ('CU', '铜', ['CU'], 'LME_Cu_cash', 'cu'),
    ('AL', '铝', ['AL'], 'LME_Al_cash', 'al'),
    ('ZN', '锌', ['ZN'], 'LME_Zn_cash', 'zn'),
    ('PB', '铅', ['PB'], 'LME_Pb_cash', 'pb'),
    ('NI', '镍', ['NI'], 'LME_Ni_cash', 'ni'),
    ('SN', '锡', ['SN'], 'LME_Sn_cash', 'sn'),
    ('LC', '锂', ['LC'], None, 'li'),
    ('SI', '硅', ['SI', 'PS'], None, 'si'),
]

# 供需库存块: (标签, 正则) 按序匹配 series_meta.name, 每组取最新鲜一条
IND_GROUPS = [
    ('LME库存', r'^LME \S{1,3}库存$', None),
    ('SHFE库存', r'^SHFE \S*库存', None),
    ('社会库存', r'社会库存', None),
    ('升贴水', r'升贴水|溢价', None),
    ('TC/加工费', r'TC|加工费', None),
    ('开工率', r'开工率|产能利用率', None),
    ('冶炼利润', r'冶炼利润|生产利润', None),
    ('持仓量', r'总持仓量', None),
    ('进口盈亏', r'进口盈亏|进口利润|沪伦比', None),
]
# 品种特化组（硅系命名不通用，定制；另有多晶硅/工业硅价格与成本）
COMM_GROUPS = {
    'SI': [
        ('仓单', r'仓单', None),
        ('厂家库存', r'生产厂家库存|下游原料.*库存', None),
        ('多晶硅库存', r'多晶硅库存', None),
        ('产量', r'多晶硅产量|样本产量', None),
        ('工业硅产量', r'工业硅产量', None),
        ('成本', r'工业硅421#成本|多晶硅.*生产成本', None),
        ('现货价', r'工业硅553#|多晶硅N型致密料市场价', None),
    ],
}
# 通用组品种级排除正则（如 SI 的"开工率"会误配铝合金）
COMM_EXCLUDE = {'SI': r'铝合金'}

def load_json(p, default=None):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def curl(url, hdr=None):
    c = ['curl', '-sL', '--ssl-no-revoke', '--max-time', '30', '-H', 'User-Agent: Mozilla/5.0']
    if hdr:
        c += ['-H', hdr]
    c.append(url)
    return subprocess.run(c, capture_output=True, timeout=45).stdout.decode('utf-8', 'replace')

def zkey():
    return os.environ.get('ZHIJI_KEY') or (load_json(KEYS_PATH) or {}).get('zhiji_key', '')

def guan_kline(sym, limit=130):
    try:
        d = json.loads(curl('%s/kline?symbol=%s&freq=D&cont=1&limit=%d' % (GUAN, sym, limit),
                            'X-Guan-Key: %s' % zkey()))
        rows = d.get('bars') or d.get('data') or d.get('list') or d
        if isinstance(rows, dict):
            for v in rows.values():
                if isinstance(v, list):
                    rows = v
                    break
        out = []
        for r in rows or []:
            if isinstance(r, dict):
                out.append((str(r.get('date') or r.get('day') or r.get('time'))[:10],
                            float(r.get('close')), float(r.get('volume') or 0),
                            float(r.get('high') or 0), float(r.get('low') or 0)))
            else:
                out.append((str(r[0])[:10], float(r[4]), float(r[5] if len(r) > 5 else 0),
                            float(r[2] if len(r) > 2 else 0), float(r[3] if len(r) > 3 else 0)))
        return [k for k in out if k[1] > 0] or None
    except Exception:
        return None

def westmetall(field):
    """{iso: (cash, 3M)} 近两年"""
    out = {}
    y0 = datetime.date.today().year
    for year in (y0 - 1, y0):
        t = curl('https://www.westmetall.com/en/markdaten.php?action=table&field=%s&year=%d' % (field, year))
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S):
            cells = [re.sub(r'<[^>]+>|\s+', ' ', c).strip()
                     for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            if len(cells) < 3:
                continue
            m = re.match(r'(\d{2})\. (\w+) (\d{4})', cells[0])
            if not m or m.group(2) not in MONTHS:
                continue
            day = '%s-%02d-%02d' % (m.group(3), MONTHS[m.group(2)], int(m.group(1)))
            try:
                out[day] = (float(cells[1].replace(',', '')), float(cells[2].replace(',', '')))
            except ValueError:
                continue
    return out

def pct(a, b):
    return (a / b - 1) if b else None

def fmt_pct(x, d=2):
    return ('%+.*f%%' % (d, x * 100)) if x is not None else '—'

def fmt_px(v):
    return format(round(v), ',d') if v >= 100 else format(v, ',.2f').rstrip('0').rstrip('.')

# ---------- 各块组装 ----------
def block_price(comm):
    """【价格】返回 (html文本行列表, stats dict)"""
    lines, stats = [], {}
    for sym in comm[2]:
        ks = guan_kline(sym)
        if not ks or len(ks) < 25:
            continue
        close, prev = ks[-1][1], ks[-2][1]
        chg = pct(close, prev)
        chg20 = pct(close, ks[-21][1])
        win = [k[1] for k in ks[-120:]]
        lo, hi = min(win), max(win)
        pos = (close - lo) / (hi - lo) if hi > lo else 0.5
        lo20 = min(k[4] for k in ks[-20:] if k[4] > 0)
        hi20 = max(k[3] for k in ks[-20:] if k[3] > 0)
        vols = [k[2] for k in ks[-21:-1] if k[2] > 0]
        vr = ks[-1][2] / (sum(vols) / len(vols)) if vols and ks[-1][2] > 0 else None
        stats[sym] = dict(close=close, chg=chg, chg20=chg20, pos=pos, lo20=lo20, hi20=hi20,
                          vol_ratio=vr, date=ks[-1][0])
        lines.append('%s主力 %s（%s，20 日 %s，120 日位置 %.0f%%）' % (
            sym, fmt_px(close), fmt_pct(chg), fmt_pct(chg20), pos * 100))
    if comm[3]:
        wm = westmetall(comm[3])
        if wm:
            days = sorted(wm)
            d1, d0 = days[-1], days[-2]
            cash, m3 = wm[d1]
            stale = (datetime.date.today() - datetime.date.fromisoformat(d1)).days > 14
            if stale:
                lines.append('LME 价格源（westmetall）停在 %s，已陈旧不引用' % d1)
            else:
                chg = pct(cash, wm[d0][0])
                stats['lme'] = dict(date=d1, cash=cash, m3=m3, chg=chg, basis=cash - m3)
                lines.append('LME cash %s / 3M %s（cash 日 %s，0-3 %s 美元，%s）' % (
                    format(cash, ',.0f'), format(m3, ',.0f'), fmt_pct(chg),
                    format(cash - m3, '+,.0f'), d1))
    return lines, stats

def block_news(comm, news, disr, zsxq, today):
    """【行业新闻】有序编号列表，不带出处标签，保留日期"""
    cn, key = comm[1], comm[4]
    items = []  # (date, text)
    cutoff14 = (datetime.date.fromisoformat(today) - datetime.timedelta(days=14)).isoformat()
    for n in news:
        if n.get('commodity') == cn and n.get('date', '') >= cutoff14:
            items.append((n.get('date', ''), n.get('title', '')))
    for d in disr:
        if d.get('commodity') == cn and d.get('ongoing'):
            txt = '%s（%s）%s：%s；恢复：%s' % (
                d.get('company', ''), d.get('country', ''), d.get('type', ''),
                d.get('impact', ''), d.get('recovery', ''))
            items.append((d.get('date', '')[:10], txt[:90] + ('…' if len(txt) > 90 else '')))
    cutoff7 = (datetime.date.fromisoformat(today) - datetime.timedelta(days=7)).isoformat()
    seen = set()
    for it in (zsxq.get('by_comm', {}).get(key) or []):
        if it.get('date', '') >= cutoff7:
            t = (it.get('title') or '').strip()
            if t[:48] in seen:
                continue
            seen.add(t[:48])
            if comm[0] == 'SI' and not re.search(r'硅|光伏|组件|通威|协鑫|大全|东岳|合盛|新安', t):
                continue  # si 桶噪音多，白名单过滤
            items.append((it.get('date', ''), t[:60]))
    items = [x for x in items if x[1]]
    items.sort(key=lambda x: x[0], reverse=True)  # 日期倒序（日期仅用于排序，不展示）
    return ['%d. %s' % (i + 1, t) for i, (d, t) in enumerate(items[:8])]

def block_fundamental(comm_code):
    """【供需与库存】从缓存库按指标组取最新"""
    if not os.path.exists(CACHE_DB):
        return []
    groups = COMM_GROUPS.get(comm_code, IND_GROUPS)
    excl = COMM_EXCLUDE.get(comm_code)
    con = sqlite3.connect(CACHE_DB)
    metas = con.execute(
        "select ind_id,name,unit,last_date from series_meta where comm=? order by last_date desc",
        (comm_code,)).fetchall()
    lines = []
    used = set()
    for label, pat, _ in groups:
        cand = None
        for ind_id, name, unit, last in metas:
            if ind_id in used:
                continue
            if excl and re.search(excl, name):
                continue
            if re.search(pat, name):
                cand = (ind_id, name, unit, last)
                break
        if not cand:
            continue
        ind_id, name, unit, last = cand
        used.add(ind_id)
        pts = con.execute(
            'select date,value from series_points where ind_id=? order by date desc limit 40',
            (ind_id,)).fetchall()
        if not pts:
            continue
        cur_d, cur_v = pts[0]
        base_v = None
        cutoff = (datetime.date.fromisoformat(cur_d) - datetime.timedelta(days=20)).isoformat()
        for d, v in pts:
            if d <= cutoff:
                base_v = v
                break
        chg = ('20 日 %s' % fmt_pct(pct(cur_v, base_v), 1)) if base_v else ''
        unit_note = ''
        disp_v, disp_u = cur_v, unit or ''
        if disp_u == '万吨' and abs(cur_v) > 50000:
            disp_v, disp_u = cur_v / 10000, '万吨'
            unit_note = '（源单位疑为吨，按吨读⚙️）'
        lines.append('%s %s %s（%s%s）%s' % (name, format(disp_v, ',.2f').rstrip('0').rstrip('.'),
                                            disp_u, cur_d, ('，' + chg) if chg else '', unit_note))
    con.close()
    return lines[:7]

def block_view(comm, stats, fund_lines, override):
    """【观点】规则拼装 + state 覆盖"""
    if override:
        return [override]
    sym = comm[2][0]
    st = stats.get(sym)
    if not st:
        return ['数据不足，暂无规则观点。']
    pos_w = '高位' if st['pos'] > 0.7 else ('低位' if st['pos'] < 0.3 else '中枢')
    trend_w = '上行' if st['chg20'] > 0.02 else ('下行' if st['chg20'] < -0.02 else '震荡')
    inv_w = ''
    for ln in fund_lines:
        if ln.startswith('LME') or '社会库存' in ln:
            m = re.search(r'20 日 ([+-][\d.]+)%', ln)
            if m:
                inv_w = '库存去化' if float(m.group(1)) < 0 else '库存累积'
                break
    combo = {'上行库存去化': '价涨量缩共振，顺势', '上行库存累积': '涨势与库存背离，谨慎追高',
             '下行库存去化': '回调中库存仍紧，关注承接', '下行库存累积': '弱势共振，回避左侧',
             '震荡库存去化': '区间偏强，等方向', '震荡库存累积': '区间偏弱，等方向'}
    view = '主力 20 日 %s，处 120 日 %.0f%% 分位（%s）；%s。组合定性：%s（⚙️规则）。' % (
        fmt_pct(st['chg20']), st['pos'] * 100, pos_w, inv_w or '库存方向无数据',
        combo.get(trend_w + inv_w, '趋势与库存信号不全，观望'))
    watch = '短盯：①关键位 %s / %s；②库存与升贴水最新读数；③供应扰动恢复进展；④宏观（FedWatch/美元）。' % (
        fmt_px(st['lo20']), fmt_px(st['hi20']))
    return [view, watch]

# ---------- 渲染 ----------
CSS = """
:root{--bg:#f2efeb;--ink:#16140f;--line:#d9d2c4;--green:#2e7d4f;--amber:#a3760e;--red:#b23a2e;--gray:#9a948a;--mono:'JetBrains Mono',ui-monospace,monospace;--serif:'Noto Serif SC',"Songti SC",serif}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--serif);line-height:1.75}
.wrap{max-width:880px;margin:0 auto;padding:26px 22px}
.hd{border-bottom:2px solid var(--ink);padding-bottom:14px}
.hd h1{font-size:23px}.hd .meta{font-family:var(--mono);font-size:11.5px;color:var(--gray);margin-top:6px}
.comm{margin-top:34px;border:1px solid var(--line);background:#faf8f4;padding:16px 18px}
.comm h2{font-size:18px;margin-bottom:8px}
.blk{margin-top:12px}.blk-t{font-family:var(--mono);font-size:11px;letter-spacing:.12em;color:var(--gray);border-left:3px solid var(--amber);padding-left:7px;margin-bottom:5px}
.blk p{font-size:13.8px;margin-bottom:3px}
.up{color:var(--red)}.dn{color:var(--green)}
.note{font-size:12px;color:var(--gray);margin-top:8px}
a{color:var(--ink)}
"""

def colorize(s):
    s = re.sub(r'(\+[\d.,]+%)', r'<span class="up">\1</span>', s)
    s = re.sub(r'(-[\d.,]+%)', r'<span class="dn">\1</span>', s)
    return s

def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def render(today, sections, stamps):
    h = ['<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>分品种点评 %s · 整合研究站</title><style>%s</style></head><body><div class="wrap">' % (today, CSS)]
    h.append('<div class="hd"><h1>分品种每日点评 · %s</h1><div class="meta">自动生成（四段式：价格/行业新闻/供需与库存/观点）· <a href="../index.html">返回总站</a></div></div>' % today)
    for name, blocks in sections:
        h.append('<div class="comm"><h2>%s</h2>' % name)
        for bt, lines in blocks:
            h.append('<div class="blk"><div class="blk-t">【%s】</div>' % bt)
            h += ['<p>%s</p>' % colorize(esc(ln)) for ln in lines]
            h.append('</div>')
        h.append('</div>')
    h.append('<p class="note">数据日：%s。数字均来自上述来源自动组装；观点为规则生成（⚙️），深度研判以人工版为准；归档页手改后不被覆盖，观点定制改 _variety_review_state.json。</p>' % ' / '.join(stamps))
    h.append('</div></body></html>')
    return '\n'.join(h)

def write_protected(path, content, hashes):
    h = sha(content)
    if os.path.exists(path):
        cur = sha(open(path, encoding='utf-8').read())
        if cur == h:
            return 'unchanged'
        if hashes.get(os.path.basename(path)) != cur:
            print('保留手改版: %s' % os.path.basename(path), flush=True)
            return 'kept_manual'
    open(path, 'w', encoding='utf-8').write(content)
    hashes[os.path.basename(path)] = h
    return 'written'

def main():
    today = datetime.date.today().isoformat()
    for a in sys.argv[1:]:
        if a.startswith('--date='):
            today = a.split('=', 1)[1]

    state = load_json(STATE_PATH) or {}
    hashes = state.get('hashes') or {}
    overrides = state.get('view_override') or {}

    news = load_json(NEWS_JSON) or []
    disr = (load_json(DISR_JSON) or {}).get('items', [])
    zsxq = load_json(ZSXQ_JSON) or {}

    sections, stamps = [], set()
    for comm in COMMS:
        price_lines, stats = block_price(comm)
        news_lines = block_news(comm, news, disr, zsxq, today)
        fund_lines = block_fundamental(comm[0])
        view_lines = block_view(comm, stats, fund_lines, overrides.get(comm[0]))
        if not price_lines:
            continue
        sections.append((comm[1], [('价格', price_lines), ('行业新闻', news_lines or ['近 14 天无该品种速递/扰动/小作文条目。']),
                                   ('供需与库存', fund_lines or ['缓存库无该品种指标。']),
                                   ('观点', view_lines)]))
        for s in stats.values():
            if isinstance(s, dict) and s.get('date'):
                stamps.add(s['date'])

    html = render(today, sections, sorted(stamps))
    r1 = write_protected(os.path.join(BASE, 'panels', 'review_%s.html' % today), html, hashes)
    # 固定 URL 版始终 = 当日实际版（含手改版内容）
    real = open(os.path.join(BASE, 'panels', 'review_%s.html' % today), encoding='utf-8').read()
    open(os.path.join(BASE, 'reports', 'variety_latest.html'), 'w', encoding='utf-8').write(real)
    print('archive: %s | variety_latest.html 已同步' % r1, flush=True)

    state['hashes'] = hashes
    state.setdefault('view_override', overrides)
    state['last_run'] = datetime.datetime.now().strftime('%F %T')
    open(STATE_PATH, 'w', encoding='utf-8').write(json.dumps(state, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
