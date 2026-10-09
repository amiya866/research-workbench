#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时行情快照管线 —— 每2小时(工作日)跑一次
数据源: Yahoo Finance chart API (服务端, 免key)
产物: data/live_quotes.json  {asof, quotes:{key:{sym,price,chg,chg_pct,time}}}
页面「更新最新数据」按钮实时拉取此文件刷新总览实时卡
"""
import json, os, sys, time, datetime

try:
    from _yproxy import YAHOO_SESSION as _SESS  # 本机直连 Yahoo 403, 走 Clash 代理
except Exception:
    try:
        from curl_cffi import requests as _creq
        _SESS = _creq.Session(impersonate='chrome')
    except Exception:
        import requests as _req
        _SESS = _req.Session()

BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(os.path.dirname(BASE), 'data', 'live_quotes.json')

# key = 页面实时卡 data-ovid / 通用名;  sym = Yahoo代码
TICKERS = {
    'VIXCLS':    '^VIX',
    'Y_GSPC':    '^GSPC',
    'Y_IXIC':    '^IXIC',
    'Y_GOLD':    'GC=F',
    'Y_SLV':     'SI=F',
    'DCOILWTICO': 'CL=F',
    'DCOILBRENTEU': 'BZ=F',
    'Y_COPPER':  'HG=F',
    'Y_USDJPY':  'JPY=X',
    'Y_EURUSD':  'EURUSD=X',
    'Y_DXY':     'DX-Y.NYB',
    'Y_TNX':     '^TNX',
    'Y_TYX':     '^TYX',
    'Y_BTC':     'BTC-USD',
}

def bjt_now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M BJT')

def fetch_one(sym):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=1d' % sym
    for i in range(3):
        try:
            r = _SESS.get(url, timeout=15)
            if r.status_code != 200:
                raise RuntimeError('HTTP %s' % r.status_code)
            res = r.json()['chart']['result'][0]
            meta = res['meta']
            q = res['indicators']['quote'][0]
            ts = res.get('timestamp') or []
            closes = [c for c in q['close'] if c is not None]
            if not closes:
                raise RuntimeError('empty')
            price = meta.get('regularMarketPrice') or closes[-1]
            prev = meta.get('chartPreviousClose') or (closes[-2] if len(closes) > 1 else None)
            chg = (price - prev) if prev else None
            chg_pct = (chg / prev * 100) if (chg is not None and prev) else None
            tstr = ''
            if meta.get('regularMarketTime'):
                tstr = datetime.datetime.utcfromtimestamp(meta['regularMarketTime']).strftime('%Y-%m-%d %H:%M UTC')
            return {'sym': sym, 'price': round(float(price), 4),
                    'chg': round(chg, 4) if chg is not None else None,
                    'chg_pct': round(chg_pct, 3) if chg_pct is not None else None,
                    'time': tstr, 'currency': meta.get('currency', '')}
        except Exception as e:
            print('  retry', i + 1, sym, repr(e)[:80], flush=True)
            time.sleep(2 * (i + 1))
    return None

def main():
    out = {'asof': bjt_now(), 'src': 'L2·Yahoo Finance 服务端快照(每2小时)', 'quotes': {}}
    ok = fail = 0
    for key, sym in TICKERS.items():
        d = fetch_one(sym)
        if d:
            out['quotes'][key] = d; ok += 1
            print('  √', key, d['price'], flush=True)
        else:
            fail += 1
        time.sleep(0.8)
    # 全败不写盘(保留旧快照)
    if ok == 0:
        print('全部失败, 保留旧快照', flush=True)
        sys.exit(1)
    # 合并旧文件: 本次失败的键沿用旧值
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding='utf-8'))
            for k, v in (old.get('quotes') or {}).items():
                if k not in out['quotes']:
                    out['quotes'][k] = v
        except Exception:
            pass
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('完成: 成功%d 失败%d -> %s' % (ok, fail, OUT), flush=True)

if __name__ == '__main__':
    main()
