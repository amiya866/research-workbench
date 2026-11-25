# -*- coding: utf-8 -*-
"""生成铝周会面板：日报/周报数据自动更新，手动配置优先，腾讯会议纪要按发言人提炼。"""
import datetime
import json
import os
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from build_aluminum_weekly import ANNUAL_BALANCE_ROWS

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'aluminum-weekly' / 'meeting'
TEMPLATE = BASE / 'scripts' / 'templates' / 'aluminum-meeting'
CACHE = Path(r'D:/Kimi/金属总网/网站构建/db/数据缓存_v1.db')
WEB_DB = Path(r'D:/Kimi/web_mirror/web_mirror.db')
LME_JSON = BASE / 'data' / 'lme_cash3m.json'
OVERRIDES = BASE / 'data' / 'aluminum_meeting_overrides.json'
SUMMARY = BASE / 'data' / 'aluminum_meeting_panel.json'
MINUTES_DIR = Path(os.environ.get('AL_MINUTES_DIR', r'D:/Kimi/腾讯会议纪要/铝'))
PEOPLE = ['天', '杨', '陈', '昊', '文', '标']


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def cache_series(conn, ind_id):
    return [(d, float(v)) for d, v in conn.execute(
        'select date,value from series_points where ind_id=? order by date', (ind_id,)) if v is not None]


def web_series(ind_id):
    if not WEB_DB.exists():
        return []
    conn = sqlite3.connect(f'file:{WEB_DB.as_posix()}?mode=ro', uri=True)
    rows = [(d, float(v)) for d, v in conn.execute(
        'select date,value from series_points where indicator_id=? order by date', (ind_id,)) if v is not None]
    conn.close()
    return rows


def lme03_series():
    data = read_json(LME_JSON, {}).get('AL', {})
    return sorted((d, float(v[0]) - float(v[1])) for d, v in (data.get('hist') or {}).items()
                  if isinstance(v, list) and len(v) >= 2)


def window_change(rows, days=7):
    if not rows:
        return None, None
    date, value = rows[-1]
    cutoff = (datetime.date.fromisoformat(date) - datetime.timedelta(days=days)).isoformat()
    base = next(((d, v) for d, v in reversed(rows) if d <= cutoff), rows[0])
    delta = value - base[1]
    pct = delta / abs(base[1]) if base[1] else None
    return {'date': base[0], 'delta': delta, 'pct': pct}, rows[-1]


def num(value, digits=1, signed=False):
    if value is None:
        return '—'
    text = f'{value:+,.{digits}f}' if signed else f'{value:,.{digits}f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def pct(value):
    return '—' if value is None else f'{value:+.1%}'


def stock_text(label, rows, scale=1, unit='万吨', days=7):
    change, latest = window_change(rows, days)
    if not latest:
        return f'{label}暂无有效数据。', None
    value = latest[1] / scale
    delta = change['delta'] / scale if change else None
    text = f'{label}{num(value, 2)}{unit}（{latest[0]}），近{days}天{num(delta, 2, True)}{unit}'
    if change and change['date'] != latest[0]:
        text += f'（对比{change["date"]}）'
    return text + '。', {'label': label, 'value': f'{num(value, 2)}{unit}；近{days}天{num(delta, 2, True)}{unit}',
                         'date': latest[0], 'source': '数据缓存_v1.db / 铝周报'}


def read_text(path):
    if path.suffix.lower() == '.docx':
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        return '\n'.join(''.join(node.text or '' for node in p.findall('.//w:t', ns))
                         for p in root.findall('.//w:p', ns))
    raw = path.read_bytes()
    for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='replace')


def speaker_name(text):
    text = re.sub(r'(?:老师|发言人)$', '', text.strip())
    if text in PEOPLE:
        return text
    if len(text) <= 6 and text[-1:] in PEOPLE:
        return text[-1]
    return None


def parse_speakers(text):
    blocks = {person: [] for person in PEOPLE}
    current, unassigned = None, 0
    for raw in text.splitlines():
        line = re.sub(r'^\s*(?:\d+\s+)?(?:\d{1,2}:\d{2}:\d{2}[,.]\d+\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d+)\s*$', '', raw).strip()
        if not line or line.upper() in ('WEBVTT',):
            continue
        line = re.sub(r'^\[[\d:.\-—\s]+\]\s*', '', line)
        match = re.match(r'^(?:发言人\s*[:：]?\s*)?([\u4e00-\u9fff·]{1,6})(?:老师)?\s*[:：]\s*(.*)$', line)
        if match:
            current = speaker_name(match.group(1))
            content = match.group(2).strip()
            if current and content:
                blocks[current].append(content)
            elif not current and content:
                unassigned += 1
            continue
        match = re.match(r'^(?:发言人\s*[:：]?\s*)?([\u4e00-\u9fff·]{1,6})(?:老师)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*$', line)
        if match:
            current = speaker_name(match.group(1))
            continue
        if current:
            blocks[current].append(line)
        elif line:
            unassigned += 1
    return blocks, unassigned


def summarize(lines):
    sentences = []
    for line in lines:
        for sentence in re.split(r'(?<=[。！？；])', line):
            sentence = re.sub(r'\s+', ' ', sentence).strip()
            if len(sentence) >= 8 and re.search(r'铝|氧化铝|LME|SHFE|库存|升贴水|月差|仓单|持仓|borrow|lending|反套|正套|偏[多空头]|看空|看多', sentence, re.I):
                sentences.append(sentence)
    scored = []
    for index, sentence in enumerate(sentences):
        score = len(re.findall(r'认为|预计|建议|关注|风险|偏[多空头]|看多|看空|库存|升贴水|月差|borrow|lending|反套|正套|止损|复产|去库|累库', sentence, re.I))
        scored.append((score, index, sentence))
    chosen = sorted(sorted(scored, reverse=True)[:3], key=lambda item: item[1])
    output = []
    for _score, _index, sentence in chosen:
        if len(sentence) > 150:
            sentence = sentence[:147].rstrip('，、；') + '…'
        output.append(sentence)
    return '\n'.join(output)


def load_minutes():
    MINUTES_DIR.mkdir(parents=True, exist_ok=True)
    files = [p for p in MINUTES_DIR.iterdir() if p.is_file() and p.suffix.lower() in ('.txt', '.md', '.vtt', '.srt', '.docx') and not p.name.startswith('~$')]
    opinions = {person: '' for person in PEOPLE}
    if not files:
        return opinions, {'status': '待接入', 'file': None, 'unassigned': 0}
    path = max(files, key=lambda p: p.stat().st_mtime)
    try:
        blocks, unassigned = parse_speakers(read_text(path))
        for person in PEOPLE:
            opinions[person] = summarize(blocks[person])
        stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec='seconds')
        count = sum(bool(opinions[p]) for p in PEOPLE)
        return opinions, {'status': f'{path.name} · 已提炼{count}/6人', 'file': path.name,
                          'updated_at': stamp, 'unassigned': unassigned}
    except Exception as exc:
        return opinions, {'status': f'{path.name} · 解析失败：{exc}', 'file': path.name, 'unassigned': 0}


def build_auto():
    conn = sqlite3.connect(f'file:{CACHE.as_posix()}?mode=ro', uri=True)
    rows = {key: cache_series(conn, key) for key in (
        'a10166772', 'ID00188313', 'a10134438', 'ID00188281', 'FU00024308',
        'ID00188139', 'a10016216', 'ID01001759')}
    conn.close()
    cftc_net = web_series('cftc:ALUMINUM:nc_net')
    cftc_oi = web_series('cftc:ALUMINUM:oi')
    lme03 = lme03_series()
    social, social_source = stock_text('国内铝锭社库', rows['a10166772'])
    billet, billet_source = stock_text('铝棒库存', rows['ID00188313'])
    lme_stock, lme_source = stock_text('LME铝库存', rows['a10134438'], scale=10000)
    shfe_stock, shfe_source = stock_text('SHFE铝库存', rows['ID00188281'], scale=10000)
    social_change = window_change(rows['a10166772'], 20)[0]
    lme03_change, lme03_latest = window_change(lme03, 7)
    basis_change, basis_latest = window_change(rows['FU00024308'], 7)
    alumina_latest = rows['ID00188139'][-1] if rows['ID00188139'] else (None, None)
    profit_latest = rows['a10016216'][-1] if rows['a10016216'] else (None, None)
    molten_latest = rows['ID01001759'][-1] if rows['ID01001759'] else (None, None)
    annual = {row[0]: row for row in ANNUAL_BALANCE_ROWS}
    tight = bool(lme03_latest and basis_latest and lme03_latest[1] > 0 and basis_latest[1] > 0)
    destocking = bool(social_change and social_change['delta'] < 0)
    near = '近端低库存与强结构仍有支撑' if tight and destocking else '近端库存与结构信号分化，需继续验证'
    balance = (
        f'年度基准：2026E全球原铝短缺{num(abs(float(annual["2026E"][3])), 1)}万吨，'
        f'2027E转为过剩{num(abs(float(annual["2027E"][3])), 1)}万吨（CRU 2026-06），中期供应恢复方向不变。\n'
        f'短期验证：{near}；国内社库20天{num(social_change["delta"], 2, True) if social_change else "—"}万吨，'
        f'LME 0-3 {num(lme03_latest[1] if lme03_latest else None, 1, True)}美元/吨，'
        f'SHFE铝基差{num(basis_latest[1] if basis_latest else None, 0, True)}元/吨。'
    )
    spot = '\n'.join([
        '1、' + social[:-1] + '；' + billet,
        '2、' + lme_stock[:-1] + '；' + shfe_stock,
        f'3、结构：LME 0-3 {num(lme03_latest[1] if lme03_latest else None, 1, True)}美元/吨（{lme03_latest[0] if lme03_latest else "—"}），'
        f'近7天{num(lme03_change["delta"], 1, True) if lme03_change else "—"}美元；'
        f'SHFE铝基差{num(basis_latest[1] if basis_latest else None, 0, True)}元/吨（{basis_latest[0] if basis_latest else "—"}）。',
        f'4、氧化铝{num(alumina_latest[1], 0)}元/吨（{alumina_latest[0] or "—"}），电解铝利润{num(profit_latest[1], 0)}元/吨（{profit_latest[0] or "—"}），'
        f'铝水比例{num(molten_latest[1], 1)}%（{molten_latest[0] or "—"}）。'
    ])
    net_change, net_latest = window_change(cftc_net, 7)
    oi_change, oi_latest = window_change(cftc_oi, 7)
    positions = '\n'.join([
        f'1、CFTC铝非商业净持仓{num(net_latest[1], 0, True)}手（{net_latest[0]}），周度{num(net_change["delta"], 0, True) if net_change else "—"}手；'
        f'总持仓{num(oi_latest[1], 0)}手，周度{num(oi_change["delta"], 0, True) if oi_change else "—"}手。' if net_latest and oi_latest else '1、CFTC铝持仓暂无有效数据。',
        f'2、伦铝0-3结构{num(lme03_latest[1] if lme03_latest else None, 1, True)}美元/吨（{"Back" if lme03_latest and lme03_latest[1] > 0 else "Contango" if lme03_latest and lme03_latest[1] < 0 else "持平"}），'
        f'近7天{num(lme03_change["delta"], 1, True) if lme03_change else "—"}美元。',
        '3、持仓口径：CFTC COMEX铝非商业头寸，不等同原表LME高盛净多；与原表不可直接拼接。'
    ])
    if tight and destocking:
        strategy = ('中期保留反弹偏空思路，但近月低库存、强Back与国内升水下不追空。优先观察远月反弹后的空配，以及近强远弱／内外反套；'
                    '若库存连续回升、Back与升水同步走弱，再加空；若持续去库或Back继续走强，则停止加空。')
    elif tight:
        strategy = ('近端结构仍强，不逆势追空；中期供应恢复使远月不宜追高。等待库存与现货升贴水同向转弱后，再提高远月空配；'
                    '若Back继续走强，优先控制近月空头风险。')
    else:
        strategy = ('库存与结构未形成近端强支撑，维持区间与反弹偏空观察；远月重点跟踪供应恢复，'
                    '只有库存持续回升且现货结构走弱时才提高空配，若重新去库且Back走强则降低空头仓位。')
    dates = [latest[0] for latest in (net_latest, oi_latest, lme03_latest, basis_latest, alumina_latest, profit_latest, molten_latest) if latest and latest[0]]
    dates += [rows[key][-1][0] for key in ('a10166772', 'ID00188313', 'a10134438', 'ID00188281') if rows[key]]
    asof = max(dates) if dates else datetime.date.today().isoformat()
    dt = datetime.date.fromisoformat(asof)
    week = f'{dt.strftime("%b")}-W{(dt.day - 1) // 7 + 1}'
    sources = [s for s in (social_source, billet_source, lme_source, shfe_source) if s]
    sources += [
        {'label': 'LME 0-3', 'value': f'{num(lme03_latest[1], 1, True)}美元/吨', 'date': lme03_latest[0], 'source': 'westmetall cash-3M / 每日点评'} if lme03_latest else {'label': 'LME 0-3', 'value': '—', 'date': '', 'source': 'westmetall'},
        {'label': 'SHFE铝基差', 'value': f'{num(basis_latest[1], 0, True)}元/吨', 'date': basis_latest[0], 'source': '数据缓存_v1.db / 每日点评'} if basis_latest else {'label': 'SHFE铝基差', 'value': '—', 'date': '', 'source': '数据缓存_v1.db'},
        {'label': 'CFTC非商业净持仓', 'value': f'{num(net_latest[1], 0, True)}手', 'date': net_latest[0], 'source': 'web_mirror.db / CFTC COT周报'} if net_latest else {'label': 'CFTC非商业净持仓', 'value': '—', 'date': '', 'source': 'web_mirror.db'},
        {'label': '年度平衡', 'value': '2026E -88.0万吨；2027E +53.5万吨', 'date': '2026-06', 'source': 'CRU Aluminium Market Outlook / 铝周报'},
        {'label': '氧化铝价格', 'value': f'{num(alumina_latest[1], 0)}元/吨', 'date': alumina_latest[0] or '', 'source': '数据缓存_v1.db / 铝周报'},
    ]
    auto = {'week': week, 'strategyTitle': week + '策略', 'balance': balance, 'spot': spot,
            'positions': positions, 'watch': '', 'contradiction': '', 'strategy': strategy}
    for person in PEOPLE:
        auto['name.' + person] = person
        auto['opinion.' + person] = '待本期腾讯会议纪要自动提炼。'
    origins = {key: 'auto' for key in auto}
    for person in PEOPLE:
        origins['opinion.' + person] = 'pending'
    return auto, origins, sources, asof


def main():
    auto, origins, sources, asof = build_auto()
    minutes, minutes_meta = load_minutes()
    for person, text in minutes.items():
        if text:
            auto['opinion.' + person] = text
            origins['opinion.' + person] = 'minutes'
    manual = read_json(OVERRIDES, {'values': {}, 'auto_reset': []})
    manual.setdefault('values', {})
    manual.setdefault('auto_reset', [])
    built = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    meta = {'asof': asof, 'built_at': built, 'minutes_status': minutes_meta['status'],
            'minutes_file': minutes_meta.get('file'), 'minutes_unassigned_lines': minutes_meta.get('unassigned', 0),
            'minutes_help': f'腾讯会议纪要放入 {MINUTES_DIR}（TXT / MD / VTT / SRT / DOCX）。最新文件按“天／杨／陈／昊／文／标”及姓名末字识别发言人，保留原句提炼，不识别“发言人1”等匿名标签；原始纪要不进入网站目录。'}
    payload = {'auto': auto, 'origins': origins, 'manual': manual, 'people': PEOPLE,
               'sources': sources, 'meta': meta}
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'panel.css', 'panel.js'):
        shutil.copyfile(TEMPLATE / name, OUT / name)
    text = 'window.AL_MEETING_PANEL=' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/') + ';\n'
    tmp = OUT / 'panel_data.js.tmp'
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, OUT / 'panel_data.js')
    SUMMARY.write_text(json.dumps({'asof': asof, 'built_at': built, 'minutes': minutes_meta,
                                   'local_url': 'aluminum-weekly/meeting/', 'sync_status': 'ok'},
                                  ensure_ascii=False, indent=2), encoding='utf-8')
    assert len(PEOPLE) == 6 and all('opinion.' + p in auto for p in PEOPLE)
    assert all(key in auto for key in ('balance', 'spot', 'positions', 'watch', 'contradiction', 'strategy'))
    print(json.dumps({'output': str(OUT), 'asof': asof, 'minutes': minutes_meta['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
