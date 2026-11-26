# -*- coding: utf-8 -*-
"""锡周会面板的专用数据与会议纪要工具。"""
import datetime
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

BASE = Path(__file__).resolve().parents[1]
LME_JSON = BASE / 'data' / 'lme_cash3m.json'


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def cache_series(conn, ind_id):
    return [(d, float(v)) for d, v in conn.execute(
        'select date,value from series_points where ind_id=? order by date', (ind_id,)) if v is not None]


def lme03_series():
    data = read_json(LME_JSON, {}).get('SN', {})
    rows = {d: float(v[0]) - float(v[1]) for d, v in (data.get('hist') or {}).items()
            if isinstance(v, list) and len(v) >= 2}
    daily_path = BASE / 'reports' / 'variety_latest.html'
    daily = daily_path.read_text(encoding='utf-8') if daily_path.exists() else ''
    marker = '<div class="comm"><h2>锡</h2>'
    if marker in daily:
        section = daily.split(marker, 1)[1].split('<div class="comm"><h2>', 1)[0]
        match = re.search(r'LME 0-3\s+([+\-]?[\d,.]+)\s*美元/吨（(\d{4}-\d{2}-\d{2})）', section)
        if match:
            rows[match.group(2)] = float(match.group(1).replace(',', ''))
    return sorted(rows.items())


def window_change(rows, days=7):
    if not rows:
        return None, None
    date, value = rows[-1]
    cutoff = (datetime.date.fromisoformat(date) - datetime.timedelta(days=days)).isoformat()
    base = next(((d, v) for d, v in reversed(rows) if d <= cutoff), rows[0])
    delta = value - base[1]
    pct_value = delta / abs(base[1]) if base[1] else None
    return {'date': base[0], 'delta': delta, 'pct': pct_value}, rows[-1]


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
                         'date': latest[0], 'source': '数据缓存_v1.db / 锡周报与日报'}


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


def speaker_name(text, people):
    text = re.sub(r'(?:老师|发言人)$', '', text.strip())
    if text in people:
        return text
    if len(text) <= 6 and text[-1:] in people:
        return text[-1]
    return None


def parse_speakers(text, people):
    blocks = {person: [] for person in people}
    current, unassigned = None, 0
    for raw in text.splitlines():
        line = re.sub(r'^\s*(?:\d+\s+)?(?:\d{1,2}:\d{2}:\d{2}[,.]\d+\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d+)\s*$', '', raw).strip()
        if not line or line.upper() in ('WEBVTT',):
            continue
        line = re.sub(r'^\[[\d:.\-—\s]+\]\s*', '', line)
        if re.match(r'^(?:发言人\s*\d+|speaker\s*\d+)\s*(?:[:：]|\d{1,2}:\d{2})', line, re.I):
            current = None
            unassigned += 1
            continue
        match = re.match(r'^(?:发言人\s*[:：]?\s*)?([\u4e00-\u9fff·]{1,6})(?:老师)?\s*[:：]\s*(.*)$', line)
        if match:
            current = speaker_name(match.group(1), people)
            content = match.group(2).strip()
            if current and content:
                blocks[current].append(content)
            elif not current and content:
                unassigned += 1
            continue
        match = re.match(r'^(?:发言人\s*[:：]?\s*)?([\u4e00-\u9fff·]{1,6})(?:老师)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*$', line)
        if match:
            current = speaker_name(match.group(1), people)
            continue
        if current:
            blocks[current].append(line)
        elif line:
            unassigned += 1
    return blocks, unassigned


def summarize(lines, commodity_pattern):
    sentences, candidates = [], []
    for line in lines:
        for sentence in re.split(r'(?<=[。！？；])', line):
            sentence = re.sub(r'\s+', ' ', sentence).strip()
            if len(sentence) < 8:
                continue
            candidates.append(sentence)
            if re.search(commodity_pattern, sentence, re.I):
                sentences.append(sentence)
    if not sentences:
        sentences = candidates
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


def load_minutes(directory, commodity_pattern, people):
    directory.mkdir(parents=True, exist_ok=True)
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in ('.txt', '.md', '.vtt', '.srt', '.docx') and not p.name.startswith('~$')]
    opinions = {person: '' for person in people}
    if not files:
        return opinions, {'status': '待接入', 'file': None, 'unassigned': 0}
    path = max(files, key=lambda p: p.stat().st_mtime)
    try:
        blocks, unassigned = parse_speakers(read_text(path), people)
        for person in people:
            opinions[person] = summarize(blocks[person], commodity_pattern)
        stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec='seconds')
        count = sum(bool(opinions[p]) for p in people)
        return opinions, {'status': f'{path.name} · 已提炼{count}/{len(people)}人', 'file': path.name,
                          'updated_at': stamp, 'unassigned': unassigned}
    except Exception as exc:
        return opinions, {'status': f'{path.name} · 解析失败：{exc}', 'file': path.name, 'unassigned': 0}
