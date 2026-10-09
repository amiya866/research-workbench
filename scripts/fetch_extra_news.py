# -*- coding: utf-8 -*-
"""增量快讯源（免费公开接口·免令牌）: 东方财富7x24 + 新浪7x24 + LME锡铜(westmetall)
   合入 data/news_latest.json（保留 jin10/ah/cs 等已有键），并同步 news_fallback.js
   本机调试可设环境变量 EXTRA_NEWS_PROXY=http://127.0.0.1:7897 走代理；GitHub Actions 直连即可"""
import json, os, re, requests, html
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'news_latest.json')
FALLBACK = os.path.join(ROOT, 'data', 'news_fallback.js')
BJT = timezone(timedelta(hours=8))
now = datetime.now(BJT).strftime('%Y-%m-%d %H:%M')
TAG = re.compile(r'<[^>]+>')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
PROXY = os.environ.get('EXTRA_NEWS_PROXY') or None
PROXIES = {'http': PROXY, 'https': PROXY} if PROXY else None

def clean(s):
    return html.unescape(TAG.sub('', s or '')).replace('&nbsp;', ' ').strip()

def get(url, **kw):
    kw.setdefault('headers', UA)
    kw.setdefault('timeout', 25)
    try:
        return requests.get(url, proxies=PROXIES, **kw)
    except requests.exceptions.ConnectionError:
        if PROXIES:
            return requests.get(url, **kw)  # 代理不通则直连兜底
        raise

def fetch_eastmoney():
    """东方财富7x24快讯（全市场，免登录）"""
    r = get('https://np-weblist.eastmoney.com/comm/web/getFastNewsList',
            params={'client': 'web', 'biz': 'web_724', 'fastColumn': '102',
                    'sortEnd': '', 'pageSize': '40',
                    'req_trace': '3c11a7a4-0000-4000-8000-0123456789ab'})
    j = r.json()
    items = []
    for it in (j.get('data') or {}).get('fastNewsList') or []:
        title = clean(it.get('title'))
        summ = clean(it.get('summary'))
        if not title:
            continue
        content = title if not summ or summ == title or summ in title else title + '｜' + summ
        items.append({'src': 'eastmoney', 'time': it.get('showTime', ''),
                      'ts': it.get('showTime', ''), 'content': content,
                      'important': 0, 'vip': 0, 'tags': [], 'id': str(it.get('code', ''))})
    return items

def fetch_sina():
    """新浪财经7x24直播流（zhibo_id=152 全市场）"""
    r = get('https://zhibo.sina.com.cn/api/zhibo/feed',
            params={'page': 1, 'page_size': 40, 'zhibo_id': 152})
    j = r.json()
    items = []
    for it in (j.get('result') or {}).get('data', {}).get('feed', {}).get('list') or []:
        content = clean(it.get('rich_text'))
        if not content:
            continue
        items.append({'src': 'sina', 'time': it.get('create_time', ''),
                      'ts': it.get('create_time', ''), 'content': content,
                      'important': 0, 'vip': 0, 'tags': [],
                      'id': 'sina' + str(it.get('id', ''))})
    return items

MONTHS = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
          'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}

def _num(s):
    s = (s or '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None

def fetch_lme():
    """LME锡/铜 结算价+库存（westmetall 公开表），返回最近10个交易日行"""
    rows = []
    for metal, field in (('sn', 'LME_Sn_cash'), ('cu', 'LME_Cu_cash')):
        r = get('https://www.westmetall.com/en/markdaten.php',
                params={'action': 'table', 'field': field})
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.S):
            tds = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            if len(tds) < 4 or not re.match(r'\d{1,2}\.\s', tds[0]):
                continue
            m = re.match(r'(\d{1,2})\.\s*(\w+)\s+(\d{4})', tds[0])
            if not m or m.group(2) not in MONTHS:
                continue
            d = '%04d-%02d-%02d' % (int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
            row = next((x for x in rows if x['date'] == d), None)
            if row is None:
                row = {'date': d}
                rows.append(row)
            row[metal + '_cash'] = _num(tds[1])
            row[metal + '_m3'] = _num(tds[2])
            row[metal + '_stock'] = _num(tds[3])
    rows.sort(key=lambda x: x['date'], reverse=True)
    return rows[:10]

def main():
    out = {}
    if os.path.exists(OUT):
        try:
            out = json.load(open(OUT, encoding='utf-8'))
        except Exception:
            out = {}
    out.setdefault('sources', [])
    # 源状态按名称去重（重复运行时替换旧记录）
    _names = ('东财7x24', '新浪7x24', 'LME锡铜·westmetall')
    out['sources'] = [s for s in out['sources'] if s.get('name') not in _names]
    out['asof'] = now

    for key, name, fn in (('eastmoney', '东财7x24', fetch_eastmoney),
                          ('sina', '新浪7x24', fetch_sina),
                          ('lme', 'LME锡铜·westmetall', fetch_lme)):
        try:
            out[key] = fn()
            out['sources'].append({'name': name, 'ok': True, 'n': len(out[key])})
        except Exception as e:
            out[key] = out.get(key, [])
            out['sources'].append({'name': name, 'ok': False, 'err': str(e)[:120]})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    open(FALLBACK, 'w', encoding='utf-8').write('window.NEWS_SNAP=' + json.dumps(out, ensure_ascii=False) + ';')
    print(json.dumps({'asof': now, 'sources': out['sources'],
                      'counts': {k: len(out.get(k, [])) for k in ('eastmoney', 'sina', 'lme')}},
                     ensure_ascii=False))

if __name__ == '__main__':
    main()
