#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 一次性修复: 经 igo_open_data(agent-gw官方FRED REST API) 补齐 fredgraph被墙期间丢失的FRED键
# 只补缺/短键, 不覆盖健康键; 衍生逻辑与fetch_macro注册表一致
import json, os, re, subprocess, sys, csv, io, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
TOOL = '/app/.agents/plugins/igo_open_data/scripts/igo_open_data_tool.py'

import importlib.util
spec = importlib.util.spec_from_file_location('fm', os.path.join(BASE, 'scripts', 'fetch_macro.py'))
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)  # 仅取 S/yoy/diff, main有守卫不会跑
S = fm.S

raw = open(os.path.join(BASE, 'data', 'chart_series.js'), encoding='utf-8').read()
CS = json.loads(re.search(r'=\s*(\{[\s\S]*\})\s*;?\s*$', raw).group(1))

def fred_gw(sid, start='2017-01-01', limit=10000):
    fp = '/tmp/gw_%s.csv' % sid
    if os.path.exists(fp): os.remove(fp)
    r = subprocess.run(['python3', TOOL, 'call', '--data-source', 'fred', '--api-name', 'fred_query',
                        '--params-json', json.dumps({'id': sid, 'start': start, 'filepath': fp, 'limit': limit})],
                       capture_output=True, text=True, timeout=300)
    if not os.path.exists(fp):
        print('  x', sid, 'gw失败', (r.stdout or r.stderr)[-120:]); return []
    out = []
    for row in csv.DictReader(open(fp)):
        v = (row.get('value') or '').strip()
        if v in ('', '.'): continue
        try: out.append([row['date'], round(float(v), 6)])
        except Exception: pass
    out.sort()
    return out

cache = {}
def base_series(sid):
    if sid not in cache:
        cache[sid] = fred_gw(sid)
    return cache[sid]

fixed, skipped = [], []
for it in S:
    kid = it['id']; how = it['how']; kind = how[0]
    if kind not in ('fred', 'yoy', 'diff', 'fred_div', 'calc_cn'): continue
    cur = CS.get(kid, [])
    if len(cur) >= 100:  # 健康键不动
        skipped.append(kid); continue
    try:
        if kind == 'fred':
            ser = base_series(how[1])
        elif kind == 'yoy':
            ser = fm.yoy(base_series(how[1]), how[2])
        elif kind == 'diff':
            ser = fm.diff(base_series(how[1]), how[2] if len(how) > 2 else 1)
        elif kind == 'fred_div':
            ser = [[d, round(v / how[2], 3)] for d, v in base_series(how[1])]
        elif kind == 'calc_cn':
            bd = dict(base_series('EXPCH'))
            ser = [[d, round(v - bd[d], 1)] for d, v in base_series('IMPCH') if d in bd]
        if len(ser) >= 3:
            if len(ser) > len(cur):
                CS[kid] = ser[-2600:]
                fixed.append('%s(n=%d,last=%s)' % (kid, len(CS[kid]), ser[-1][0]))
            else:
                skipped.append(kid + '(旧值更长)')
        else:
            print('  x', kid, '修复空')
    except Exception as e:
        print('  x', kid, repr(e)[:100])

with open(os.path.join(BASE, 'data', 'chart_series.js'), 'w', encoding='utf-8') as f:
    f.write('window.CHART_SERIES = ' + json.dumps(CS, separators=(',', ':')) + ';')
print('修复%d键:' % len(fixed))
for x in fixed: print(' ', x)
print('跳过(健康)%d键' % len(skipped))
