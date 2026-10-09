# -*- coding: utf-8 -*-
"""上期所(SHFE)锡/铜期货库存(仓单)日报 —— iFinD EDB 数据源
官方免费接口已失效, 改用 iFinD 宏观库 EDB 指标(数据源: 上海期货交易所, 频率 W/日频更新):
- 期货库存:锡:总计  (displayId S005580468, 单位 吨)
- 期货库存:铜      (displayId S000025739, 单位 吨)

输出: 合入 data/news_latest.json 的 "shfe" 键(保留其他键), 并同步 news_fallback.js
安全: 密钥只从环境变量 IFIND_MCP_KEY 读取; 本机调试可从 ~/.config mcp_config.json 兜底
失败: 保留既有 shfe 数据, 不覆盖"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_ifind_mcp import IFindMCP  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'news_latest.json')
FALLBACK = os.path.join(ROOT, 'data', 'news_fallback.js')
BJT = timezone(timedelta(hours=8))

METALS = {
    'sn': {'query': '期货库存:锡:总计', 'display_id': 'S005580468'},
    'cu': {'query': '期货库存:铜', 'display_id': 'S000025739'},
}
WEEKS_BACK = 10  # 拉取最近约 10 周, 页面算周环比


def log(*args):
    print(datetime.now(BJT).strftime('%H:%M:%S'), *args, flush=True)


def read_token():
    token = os.environ.get('IFIND_MCP_KEY', '').strip()
    if token:
        return token
    # 本机调试兜底(不进仓库)
    cfg = Path.home() / '.config' / 'agents' / 'skills' / 'ifind-finance-data' / 'mcp_config.json'
    try:
        return json.loads(cfg.read_text(encoding='utf-8')).get('auth_token', '').strip()
    except Exception:
        return ''


def extract_series(result, expect_id):
    """从 get_edb_data 返回中提取 [[date, value], ...]"""
    res = (result or {}).get('result') or {}
    text = ''
    for c in res.get('content') or []:
        if c.get('type') == 'text' and c.get('text'):
            text = c['text']
            break
    payload = json.loads(text)
    inner = payload.get('data') or {}
    datas = inner.get('datas') or []
    if not datas:
        raise RuntimeError('EDB 返回 datas 为空')
    entry = datas[0].get('data') or {}
    series = entry.get('data') or []
    attrs = (entry.get('attrs') or {})
    attr = next(iter(attrs.values()), {}) if attrs else {}
    idx_id = attr.get('index_id') or ((datas[0].get('extra') or {}).get('index_id'))
    if idx_id and idx_id != expect_id:
        raise RuntimeError(f'指标ID不符: {idx_id} != {expect_id}')
    out = []
    for row in series:
        try:
            out.append([str(row[0]), float(row[1])])
        except Exception:
            continue
    if len(out) < 2:
        raise RuntimeError(f'可解析数据点不足: {len(out)}')
    out.sort(key=lambda x: x[0])
    return out


def fetch_metal(client, key, cfg):
    today = datetime.now(BJT).date()
    start = (today - timedelta(weeks=WEEKS_BACK)).strftime('%Y%m%d')
    end = today.strftime('%Y%m%d')
    query = f"{cfg['query']}（{start}-{end}）"
    log(f'EDB {key}: {query}')
    result = client.call('edb', 'get_edb_data', {'query': query})
    series = extract_series(result, cfg['display_id'])
    return {
        'name': cfg['query'],
        'display_id': cfg['display_id'],
        'unit': '吨',
        'source': '上海期货交易所·iFinD EDB',
        'series': series,
        'latest': series[-1],
    }


def main():
    token = read_token()
    out = {}
    if os.path.exists(OUT):
        try:
            out = json.load(open(OUT, encoding='utf-8'))
        except Exception:
            out = {}

    if not token:
        log('IFIND_MCP_KEY 未配置, 跳过(保留既有数据)')
        return 0

    client = IFindMCP(token)
    shfe = {'updated': datetime.now(BJT).strftime('%Y-%m-%d %H:%M'), 'metals': {}}
    ok = True
    for key, cfg in METALS.items():
        try:
            shfe['metals'][key] = fetch_metal(client, key, cfg)
            s = shfe['metals'][key]
            log(f"  ✓ {key}: {len(s['series'])}点, 最新 {s['latest'][0]} = {s['latest'][1]}")
        except Exception as e:
            ok = False
            log(f'  x {key}: {str(e)[:200]}')
            old = (out.get('shfe') or {}).get('metals', {}).get(key)
            if old:
                shfe['metals'][key] = old

    if not shfe['metals']:
        log('SHFE 数据全部失败, 保留旧数据')
        return 0

    out['shfe'] = shfe
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    with open(FALLBACK, 'w', encoding='utf-8') as f:
        f.write('window.NEWS_SNAP=' + json.dumps(out, ensure_ascii=False) + ';')
    log('已写入 news_latest.json / news_fallback.js, metals:',
        {k: v['latest'] for k, v in shfe['metals'].items()})
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as e:
        log('FATAL:', str(e)[:300])
        raise SystemExit(0)  # 失败不阻断 workflow
