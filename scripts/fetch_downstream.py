# -*- coding: utf-8 -*-
"""
下游需求低频数据更新器（月度）
- 白电排产: 产业在线 ChinaIOL；原站无文字结果时通过 Mysteel 搜索接口发现最新转载并解析
  * 两路均失败则保留旧数据并在日志中提示人工更新
- 地产/汽车/基建/出口链: 华泰国内宏观库快照(ht_series_domestic.js 入库时同步, 本脚本不重复抓)
失败策略: 任何异常都不覆盖现有 downstream.json, 不中断管线
"""
import json, os, re, sys, urllib.request

DATA = os.path.join(os.path.dirname(__file__), '..', 'data')
OUT = os.path.join(DATA, 'downstream.json')

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      'X-Requested-With': 'XMLHttpRequest'}

def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', 'ignore')

def log(*a): print('[downstream]', *a)

def find_latest_article():
    """找最新三大白电排产；原站无文字结果时用Mysteel搜索接口发现转载。"""
    cands = []
    for url in ('https://weixin.chinaiol.com/News?classID=80',
                'https://weixin.chinaiol.com/News/Index?classID=80',
                'http://www.chinaiol.com/News/Channel/18.html'):
        try:
            h = get(url)
        except Exception as e:
            log('列表页失败', url, e); continue
        for m in re.finditer(r'三大白电(\d{4})年(\d{1,2})月排产数据发布.*?[?&]id=(\d+)', h, re.S):
            cands.append((int(m.group(1)), int(m.group(2)), m.group(3)))
        for m in re.finditer(r'[?&]id=(\d+)[^<]*?三大白电(\d{4})年(\d{1,2})月排产', h, re.S):
            cands.append((int(m.group(2)), int(m.group(3)), m.group(1)))
        if cands: break
    if not cands:
        payload = json.dumps({'query': '三大白电', 'startTime': '', 'endTime': '',
                              'sortType': 'time', 'platform': 'pc', 'pageNo': 1, 'pageSize': 20},
                             ensure_ascii=False).encode('utf-8')
        try:
            result = json.loads(get('https://search.mysteel.com/searchapi/search/getAllData', payload,
                                    {**UA, 'Content-Type': 'application/json;charset=utf8', 'token': '-1'}))
            for item in result.get('articleList') or []:
                article = item.get('articleBean') or {}
                match = re.search(r'三大白电(\d{4})年(\d{1,2})月排产数据发布', article.get('title') or '')
                if match and article.get('url'):
                    cands.append((int(match.group(1)), int(match.group(2)), article['url']))
        except Exception as e:
            log('Mysteel排产搜索失败', e)
    if not cands: return None
    cands.sort(reverse=True)
    y, m, aid = cands[0]
    log('找到最新排产文章: %d年%d月 %s' % (y, m, aid))
    return y, m, aid

def parse_article(aid):
    """抓文章正文; 返回 dict 或 None(图片版无法解析)"""
    url = aid if str(aid).startswith('http') else 'https://weixin.chinaiol.com/News/Details?classID=80&id=%s' % aid
    h = get(url)
    t = re.sub(r'<script[\s\S]*?</script>', ' ', h)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    def num(pat, s=t, signed=False):
        m = re.search(pat, s)
        if not m:
            return None
        value = float(m.group(1))
        context = s[max(0, m.start() - 30):m.end()]
        if signed and value > 0 and re.search(r'下降|下滑|微降|减少|下跌|降低', context):
            value = -value
        return value
    total = num(r'合计总量[为共]?(\d+\.?\d*)万台')
    tot_yoy = num(r'合计总量[为共]?\d+\.?\d*万台[^。]*?([\-\+]?\d+\.?\d*)%', signed=True)
    ac = num(r'家用?空调排产(\d+\.?\d*)万台')
    ac_yoy = num(r'家用?空调排产\d+\.?\d*万台[^。]*?([\-\+]?\d+\.?\d*)%', signed=True)
    fr = num(r'冰箱排产(\d+\.?\d*)万台')
    fr_yoy = num(r'冰箱排产\d+\.?\d*万台[^。]*?([\-\+]?\d+\.?\d*)%', signed=True)
    wm = num(r'洗衣机排产(\d+\.?\d*)万台')
    wm_yoy = num(r'洗衣机排产\d+\.?\d*万台[^。]*?([\-\+]?\d+\.?\d*)%', signed=True)
    if None in (total, tot_yoy, ac, ac_yoy, fr, fr_yoy, wm, wm_yoy):
        return None
    return {'total_v': total, 'total_yoy': tot_yoy, 'ac_v': ac, 'ac_yoy': ac_yoy,
            'fr_v': fr, 'fr_yoy': fr_yoy, 'wm_v': wm, 'wm_yoy': wm_yoy}

def main():
    old = {}
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding='utf-8'))
    try:
        found = find_latest_article()
        if not found:
            log('未找到新文章, 保留旧数据'); return
        y, m, aid = found
        period = '%04d-%02d' % (y, m)
        parsed = parse_article(aid)
        if not parsed:
            log('!! %s 排产文章为图片版, 数字无法自动解析 —— 需人工把报告发给Kimi更新' % period)
            return
        hv = old.get('hvac', {})
        hist = hv.get('hist', [])
        hist = [r for r in hist if r[0] != period]
        hist.append([period, parsed['total_v'], parsed['total_yoy'],
                     parsed['ac_v'], parsed['ac_yoy'],
                     parsed['fr_v'], parsed['fr_yoy'],
                     parsed['wm_v'], parsed['wm_yoy']])
        hist.sort()
        hv.update({'updated': '%04d-%02d' % (y, m), 'period': period,
                   'total': {'v': parsed['total_v'], 'yoy': parsed['total_yoy']}})
        for k, pre in (('ac', 'ac'), ('fr', 'fr'), ('wm', 'wm')):
            hv.setdefault(k, {})
            hv[k].update({'v': parsed[pre+'_v'], 'yoy': parsed[pre+'_yoy']})
            # 内外销明细为新版报告才有, 抓不到则保留旧值并标注
        hv['note_split'] = '内外销明细若新报告未含文字版则沿用上一期, 以最新人工更新为准'
        hv['hist'] = hist[-12:]
        old['hvac'] = hv
        old['asof'] = __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        json.dump(old, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        log('已更新排产期 %s: 合计%s万台 同比%s%%' % (period, parsed['total_v'], parsed['total_yoy']))
    except Exception as e:
        log('更新失败(保留旧数据):', e)

if __name__ == '__main__':
    main()
