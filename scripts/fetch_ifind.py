#!/usr/bin/env python3
# iFinD行情直采 → 合并进 data/chart_series.js (键 IF_*)
# 依赖沙箱内 agent-gw 通道（GitHub Actions 无此通道，仅本地/日报管线运行）
# 用法: python3 scripts/fetch_ifind.py
import json, re, os, subprocess, sys, tempfile, csv, datetime

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CS_PATH = os.path.join(APP, 'data', 'chart_series.js')
IFIND_DIR = '/app/.agents/plugins/ifind'

# (ticker, key, 名称, 单位)
TICKERS = [
    ('000300.SH',  'IF_000300SH', '沪深300指数',   '点'),
    ('000001.SH',  'IF_000001SH', '上证综合指数',   '点'),
    ('AU9999.SHG', 'IF_AU9999',   '沪金AU9999现货', '元/克'),
    ('399006.SZ',  'IF_399006SZ', '创业板指',       '点'),
    ('000905.SH',  'IF_000905SH', '中证500指数',    '点'),
    ('AG9999.SHG', 'IF_AG9999',   '沪银AG9999现货', '元/千克'),
    # 2026-09-01扩充(均已验证ifind_get_price可取)
    ('000016.SH',  'IF_000016SH', '上证50指数',     '点'),
    ('000852.SH',  'IF_000852SH', '中证1000指数',   '点'),
    ('399001.SZ',  'IF_399001SZ', '深证成指',       '点'),
    ('000688.SH',  'IF_000688SH', '科创50指数',     '点'),
]

def load_cs():
    raw = open(CS_PATH, encoding='utf-8').read()
    m = re.search(r'window\.CHART_SERIES\s*=\s*(\{.*\})\s*;?\s*$', raw, re.S)
    return json.loads(m.group(1))

def save_cs(cs):
    tmp = CS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('window.CHART_SERIES = ' + json.dumps(cs, ensure_ascii=False, separators=(',', ':')) + ';')
    os.replace(tmp, CS_PATH)

def fetch_batch(tickers, start, end, out_csv):
    params = json.dumps({
        'ticker': ','.join(tickers),
        'start_date': start, 'end_date': end,
        'file_path': out_csv,
    })
    r = subprocess.run(
        ['python3', 'scripts/ifind_tool.py', 'call',
         '--api-name', 'ifind_get_price', '--params-json', params],
        cwd=IFIND_DIR, capture_output=True, text=True, timeout=180)
    txt = r.stdout + r.stderr
    if 'is_success' not in txt:
        print('iFinD调用失败:', txt[-400:])
        return False
    return os.path.exists(out_csv)

def main():
    end = datetime.date.today().isoformat()
    start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    cs = load_cs()
    # 每批最多3个ticker
    meta = {tk: (key, name, unit) for tk, key, name, unit in TICKERS}
    ok = 0
    for i in range(0, len(TICKERS), 3):
        batch = TICKERS[i:i+3]
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tf:
            out = tf.name
        if not fetch_batch([t[0] for t in batch], start, end, out):
            continue
        with open(out, encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        for tk, key, name, unit in batch:
            def _nd(t):
                t = (t or '').strip()[:10]
                if re.fullmatch(r'\d{8}', t):
                    t = '%s-%s-%s' % (t[:4], t[4:6], t[6:8])
                return t
            add = [[_nd(r['time']), round(float(r['close']), 3)]
                   for r in rows if r.get('thscode') == tk and r.get('close')]
            if not add:
                continue
            old = {p[0]: p[1] for p in cs.get(key, [])}
            for d, v in add:
                old[d] = v
            cs[key] = sorted(old.items())
            ok += 1
            print(f'{key} {name}: +{len(add)}点, 最新 {cs[key][-1]}')
        os.unlink(out)
    if ok:
        save_cs(cs)
        print(f'合并 {ok} 条 iFinD 序列入 chart_series.js')
    else:
        print('无新数据，保留旧值')

if __name__ == '__main__':
    main()
