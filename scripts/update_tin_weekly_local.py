# -*- coding: utf-8 -*-
"""用最新本地锡周报 PPT 的综述表与策略段更新工作台本周总结。"""
import datetime
import hashlib
import html
import json
import re
import sys
from pathlib import Path

from pptx import Presentation

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import fetch_tin_weekly as mirror

PPT_DIR = Path(r'D:/拷贝文件/E/永安/周报数据更新/图表格式(1)/锡周报20260709_试跑/周报更新图')
OUT = BASE / 'tin-weekly' / 'index.html'
META = BASE / 'data' / 'tin_weekly.json'


def shape(slide, name):
    return next(sh for sh in slide.shapes if sh.name == name)


def plain(value):
    return re.sub(r'\s+', ' ', value or '').strip()


def lines(value):
    return [plain(item) for item in (value or '').splitlines() if plain(item)]


def main():
    candidates = [p for p in PPT_DIR.glob('锡周报[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].pptx')]
    if not candidates:
        raise RuntimeError('未找到本地锡周报 PPT')
    ppt = max(candidates, key=lambda p: p.stat().st_mtime)
    match = re.search(r'(\d{8})$', ppt.stem)
    report_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
    asof = report_date - datetime.timedelta(days=(report_date.weekday() - 4) % 7)

    prs = Presentation(str(ppt))
    table = shape(prs.slides[3], '表格 3').table
    cell = lambda r, c: plain(table.cell(r, c).text)
    strategy = lines(shape(prs.slides[5], '矩形 7').text_frame.text)
    if len(strategy) < 6:
        raise RuntimeError('锡周报综述页段落结构不完整')

    headline = '本周定调：周度仍偏空（中性偏谨慎）。%s。%s' % (cell(0, 1), strategy[-1])
    metrics = [
        {'name': '本周价格', 'value': strategy[0]},
        {'name': '库存与结构', 'value': strategy[2].replace('基本面评述：', '')},
        {'name': '需求与成交', 'value': strategy[3]},
        {'name': '本周策略', 'value': strategy[-1]},
    ]

    def summary_row(label, datum, conclusion, direction):
        cls = 'up' if '多' in direction else ('dn' if '空' in direction or '谨慎' in direction else 'nt')
        return ('<tr><td class="c">%s</td><td>%s</td><td>%s</td>'
                '<td><span class="dir %s">%s</span></td></tr>') % tuple(
                    html.escape(str(v)) for v in (label, datum, conclusion, cls, direction))

    supply = '<br>'.join(html.escape(v) for v in lines(table.cell(1, 2).text))
    demand = '<br>'.join(html.escape(v) for v in lines(table.cell(2, 2).text))
    inventory = '<br>'.join(html.escape(v) for v in lines(table.cell(3, 2).text))
    rows = [
        summary_row('价格', cell(0, 1), '价格破位，低库存托底但结构走弱', '偏空'),
        '<tr><td class="c">供应</td><td>%s</td><td>%s</td><td><span class="dir dn">偏空</span></td></tr>' % (supply, html.escape(cell(1, 1))),
        '<tr><td class="c">需求</td><td>%s</td><td>%s</td><td><span class="dir nt">中性</span></td></tr>' % (demand, html.escape(cell(2, 1))),
        '<tr><td class="c">库存</td><td>%s</td><td>%s</td><td><span class="dir up">利多</span></td></tr>' % (inventory, html.escape(cell(3, 1))),
        summary_row('策略', strategy[-1], strategy[-2], '偏空·谨慎'),
        summary_row('关注点', cell(5, 1), '下周验证清单', '跟踪'),
    ]
    summary = '<table class="sum"><tr><th>环节</th><th>相关数据与边际</th><th>周度结论</th><th>跟踪</th></tr>%s</table>' % ''.join(rows)

    page = OUT.read_text(encoding='utf-8')
    replacements = [
        (r'<div class="tone"><b>.*?</b></div>', lambda: '<div class="tone"><b>%s</b></div>' % html.escape(headline)),
        (r'(<div id="sumsec"><h2>总结<span class="en">SUMMARY</span></h2>).*?(</div>)', lambda: None),
        (r'(<span class="research-stamp">数据截至 <b>).*?(</b>)', lambda: None),
        (r'数据更新至 \d{4}-\d{2}-\d{2}', lambda: '数据更新至 %s' % asof.isoformat()),
    ]
    for index, (pattern, replacement) in enumerate(replacements):
        def sub(_match, index=index):
            if index == 1:
                return _match.group(1) + summary + _match.group(2)
            if index == 2:
                return _match.group(1) + asof.isoformat() + _match.group(2)
            return replacement()
        page, count = re.subn(pattern, sub, page, count=1, flags=re.S)
        if count != 1:
            raise RuntimeError('周报页面锚点替换失败：%s' % pattern)
    mirror.write_atomic(OUT, page)

    meta = mirror.load_json(META, {}) or {}
    meta.update({
        'title': '锡研究周报 · %d-W%02d' % (asof.isocalendar().year, asof.isocalendar().week),
        'asof': asof.isoformat(),
        'headline': headline,
        'metrics': metrics,
        'synced_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'sync_status': 'ok',
        'last_error': '',
        'local_summary_source': str(ppt),
        'local_summary_sha256': hashlib.sha256(ppt.read_bytes()).hexdigest(),
    })
    mirror.write_atomic(META, json.dumps(meta, ensure_ascii=False, indent=2))
    mirror.update_daily_card(meta)
    print(json.dumps({'ppt': str(ppt), 'asof': asof.isoformat(), 'headline': headline}, ensure_ascii=False))


if __name__ == '__main__':
    main()
