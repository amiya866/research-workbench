# -*- coding: utf-8 -*-
"""近日新出数据收集器（零 token · 规则引擎）
快讯窗口只有最近几十条，数据发布类快讯（如"欧元区PMI初值公布52.3，预期52.8，前值53.1"）
几小时后就被刷走。本脚本在每次快讯快照后扫描全部源，把数据发布类条目解析出来，
持久化到 data/releases_recent.json（去重、保留7天），供日报页"近日新出数据"区块展示。
本机调试可设环境变量 EXTRA_NEWS_PROXY=http://127.0.0.1:7897 走代理。"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / 'data' / 'news_latest.json'
OUT = ROOT / 'data' / 'releases_recent.json'
BJT = timezone(timedelta(hours=8))
now = datetime.now(BJT)

# 数据发布类关键词（命中其一才算候选）
KW = re.compile(
    r'(PMI|CPI|PPI|GDP|非农|零售销售|零售额|工业产出|贸易帐|贸易差额|失业率|初请|'
    r'消费者信心|密歇根|通胀|物价指数|核心PCE|PCE|耐用品订单|成屋销售|新屋开工|建筑许可|'
    r'社融|M2|新增贷款|新增人民币贷款|出口|进口|原油库存|API库存|EIA库存|'
    r'铝锭|电解铝库存|保税区库存|锌锭|镍矿|铁水|高炉开工)')
# 必须带有结果或预期/前值字样，且含数字
HAS_NUM = re.compile(r'\d')
RESULT = re.compile(r'(公布|录得|实际|初值|终值|前值|预期|同比|环比|升至|降至|上升至|下降至)')
# 排除明显的行情/个股类
EXCLUDE = re.compile(r'(期货|现货|股|ETF|涨停|跌停|盘前|盘后|美元/|指数涨|指数跌|涨超|跌超|'
                     r'招标|中标|停牌|复牌|涨停|签署|合同|订单.*亿元)')

RE_ACT = re.compile(r'(?:公布|录得|实际值?|报)\s*[:：为]?\s*(-?[\d,]+(?:\.\d+)?%?)')
RE_ACT2 = re.compile(r'(?:初值|终值)\s*[:：为]?\s*(-?[\d,]+(?:\.\d+)?%?)')
RE_ACT3 = re.compile(r'】\s*[:：]?\s*(-?[\d,]+(?:\.\d+)?%)')
RE_FC = re.compile(r'预期\s*[:：]?\s*(-?[\d,]+(?:\.\d+)?%?)')
RE_PV = re.compile(r'前值\s*[:：]?\s*(-?[\d,]+(?:\.\d+)?%?)')


def clean_name(c):
    m = re.match(r'【([^】]{2,30})】', c)
    if m:
        return m.group(1).strip()
    m = re.split(r'[，。：:；|｜]', c)[0]
    m = re.split(r'(公布|录得|实际值|初值|终值)', m)[0]
    return (m or c)[:28].strip()


def parse_item(it):
    c = (it.get('content') or '').replace('\n', ' ').strip()
    if not (KW.search(c) and HAS_NUM.search(c) and RESULT.search(c)):
        return None
    if EXCLUDE.search(c) and not RE_PV.search(c) and not RE_FC.search(c):
        return None
    act = None
    for rx in (RE_ACT, RE_ACT2, RE_ACT3):
        m = rx.search(c)
        if m:
            act = m.group(1)
            break
    fc = (RE_FC.search(c) or [None])
    fc = fc.group(1) if hasattr(fc, 'group') else None
    pv = (RE_PV.search(c) or [None])
    pv = pv.group(1) if hasattr(pv, 'group') else None
    if not act and not pv:
        return None
    return {
        'name': clean_name(c),
        'act': act, 'fc': fc, 'pv': pv,
        't': (it.get('time') or '')[:16],
        'src': it.get('_src', ''),
        'imp': int(it.get('important') or 0),
    }


def main():
    if not NEWS.exists():
        print('news_latest.json 不存在，跳过')
        return 0
    d = json.loads(NEWS.read_text(encoding='utf-8'))
    old = []
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding='utf-8')).get('items', [])
        except Exception:
            old = []

    seen = {(o['name'], o.get('t', '')[:10], o.get('act')) for o in old}
    fresh = []
    for src in ('jin10', 'cs', 'ah', 'eastmoney', 'sina'):
        for it in d.get(src, []) or []:
            it['_src'] = src
            r = parse_item(it)
            if not r:
                continue
            key = (r['name'], r['t'][:10], r['act'])
            if key in seen:
                continue
            seen.add(key)
            fresh.append(r)

    cutoff = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    items = [o for o in old if (o.get('t', '')[:10] or '9999') >= cutoff]
    items.extend(fresh)
    # 按时间升序去重保留最新
    bykey = {}
    for o in items:
        bykey[(o['name'], o.get('t', '')[:10])] = o
    items = sorted(bykey.values(), key=lambda x: x.get('t', ''))[-120:]

    OUT.write_text(json.dumps({'updated': now.strftime('%Y-%m-%d %H:%M'), 'items': items},
                              ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'added': len(fresh), 'total': len(items),
                      'sample': items[-3:] if items else []}, ensure_ascii=False)[:600])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
