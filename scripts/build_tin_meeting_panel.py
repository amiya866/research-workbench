# -*- coding: utf-8 -*-
"""生成锡周会面板：锡周报/日报数据、沪锡席位与腾讯会议纪要自动更新。"""
import datetime
import json
import os
import sqlite3
from pathlib import Path

import tin_meeting_common as common
from build_tin_weekly import BALANCE_CONFIG

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'tin-weekly' / 'meeting'
TEMPLATE = BASE / 'scripts' / 'templates' / 'tin-meeting'
CACHE = Path(r'D:/Kimi/金属总网/网站构建/db/数据缓存_v1.db')
TIN_DB = Path(r'D:/Kimi/锡席位与期权流动性/data/tin_monitor.db')
OVERRIDES = BASE / 'data' / 'tin_meeting_overrides.json'
SUMMARY = BASE / 'data' / 'tin_meeting_panel.json'
MINUTES_DIR = Path(os.environ.get('SN_MINUTES_DIR', r'D:/Kimi/腾讯会议纪要/锡'))
PEOPLE = ['标', '昊', '天', '航', '陈', '文']
TIN_PATTERN = r'锡|缅甸|佤邦|印尼|LME|SHFE|库存|升贴水|月差|仓单|持仓|borrow|lending|反套|正套|偏[多空头]|看空|看多|焊料|半导体'


def seat_net_series():
    if not TIN_DB.exists():
        return []
    conn = sqlite3.connect(f'file:{TIN_DB.as_posix()}?mode=ro', uri=True)
    rows = [(d, float(net)) for d, net in conn.execute(
        'select date,sum(long_oi)-sum(short_oi) from seat_daily group by date order by date')]
    conn.close()
    return rows


def latest(rows):
    return rows[-1] if rows else (None, None)


def build_auto():
    conn = sqlite3.connect(f'file:{CACHE.as_posix()}?mode=ro', uri=True)
    keys = ('a10020744', 'ID01517441', 'a10006434', 'FU00015998', 'FU00015901', 'FU00015902',
            'FU00017555', 'ID01590826', 'a10156329', 'ID02105841', 'ID01538256', 'a10003083',
            'a10003128', 'a10083975', 'a10099105')
    rows = {key: common.cache_series(conn, key) for key in keys}
    conn.close()
    lme03 = common.lme03_series()
    seats = seat_net_series()
    social, social_source = common.stock_text('SMM锡锭社库', rows['a10020744'], unit='吨')
    social_my, my_source = common.stock_text('Mysteel锡锭社库', rows['ID01517441'], unit='吨')
    lme_stock, lme_source = common.stock_text('LME锡库存', rows['a10006434'], unit='吨')
    shfe_stock, shfe_source = common.stock_text('SHFE锡库存', rows['FU00015998'], unit='吨')
    social20 = common.window_change(rows['a10020744'], 20)[0]
    output_change = common.window_change(rows['a10003083'], 30)[0]
    output_latest = latest(rows['a10003083'])
    tc_latest = latest(rows['ID01538256'])
    profit_latest = latest(rows['ID02105841'])
    solder_latest = latest(rows['a10083975'])
    import_latest = latest(rows['ID01590826'])
    ratio_latest = latest(rows['a10156329'])
    registered_latest = latest(rows['FU00015901'])
    cancelled_latest = latest(rows['FU00015902'])
    lme03_change, lme03_latest = common.window_change(lme03, 7)
    smm03_latest = latest(rows['a10099105'])
    oi_change, oi_latest = common.window_change(rows['FU00017555'], 7)
    seat_change, seat_latest = common.window_change(seats, 7)
    annual = {row[0]: row for row in BALANCE_CONFIG['rows']}
    destocking = bool(social20 and social20['delta'] < 0)
    if destocking and lme03_latest and lme03_latest[1] < 0:
        near = '国内低库存仍在，但LME Back退潮并转为Contango，近端支撑与结构走弱并存'
    elif destocking:
        near = '国内库存持续去化且LME结构仍有支撑，低位不宜追空'
    else:
        near = '库存去化放缓，若LME结构继续走弱，年度宽松逻辑更容易兑现'
    balance = (
        f'年度基准：2026E全球锡锭过剩{annual["2026E"][3].lstrip("+")}万吨，2027E过剩扩大至{annual["2027E"][3].lstrip("+")}万吨'
        '（永安锡周报2026-10-24），供应恢复是中期主线。\n'
        f'短期验证：{near}；SMM社库20天{common.num(social20["delta"], 0, True) if social20 else "—"}吨，'
        f'精炼锡产量{common.num(output_latest[1], 0)}吨（{output_latest[0] or "—"}，近30天{common.pct(output_change["pct"]) if output_change else "—"}），'
        f'LME 0-3 {common.num(lme03_latest[1], 1, True) if lme03_latest else "—"}美元/吨。'
    )
    total_warrant = (registered_latest[1] or 0) + (cancelled_latest[1] or 0)
    cancel_share = cancelled_latest[1] / total_warrant if total_warrant else None
    spot = '\n'.join([
        '1、' + social[:-1] + '；' + social_my,
        '2、' + lme_stock[:-1] + '；' + shfe_stock,
        f'3、LME注册仓单{common.num(registered_latest[1], 0)}吨、注销仓单{common.num(cancelled_latest[1], 0)}吨（{cancelled_latest[0] or "—"}），'
        f'注销占比{format(cancel_share, ".1%") if cancel_share is not None else "—"}；'
        f'锡锭进口利润{common.num(import_latest[1], 0, True)}元/吨（{import_latest[0] or "—"}），沪伦比{common.num(ratio_latest[1], 4)}。',
        f'4、云南40%锡精矿TC {common.num(tc_latest[1], 0)}元/吨（{tc_latest[0] or "—"}），'
        f'锡冶炼利润{common.num(profit_latest[1], 0)}元/吨；焊料企业开工率{common.num(solder_latest[1], 1)}%（{solder_latest[0] or "—"}）。'
    ])
    positions = '\n'.join([
        f'1、沪锡总持仓{common.num(oi_latest[1], 0)}手（{oi_latest[0] or "—"}），近7天{common.num(oi_change["delta"], 0, True) if oi_change else "—"}手；'
        f'上期所前20席位净持仓{common.num(seat_latest[1], 0, True)}手（{seat_latest[0] or "—"}），近7天{common.num(seat_change["delta"], 0, True) if seat_change else "—"}手。',
        f'2、LME 0-3（westmetall）{common.num(lme03_latest[1], 1, True) if lme03_latest else "—"}美元/吨'
        f'（{"Back" if lme03_latest and lme03_latest[1] > 0 else "Contango" if lme03_latest and lme03_latest[1] < 0 else "持平"}，{lme03_latest[0] if lme03_latest else "—"}），'
        f'近7天{common.num(lme03_change["delta"], 1, True) if lme03_change else "—"}美元；SMM口径{common.num(smm03_latest[1], 2, True)}美元/吨（{smm03_latest[0] or "—"}）。',
        '3、前20席位为各合约榜单汇总，存在进出榜可见性偏差，不等于全市场净持仓或席位真实盈亏。'
    ])
    if destocking and lme03_latest and lme03_latest[1] < 0:
        strategy = ('中期维持反弹偏空，但短线快速下跌后不追低，月差正套降低仓位并注意换月。若社库与仓单持续去化、LME Back重新走强且成交改善，'
                    '停止加空；若库存回升、Contango延续且缅甸／印尼供应恢复，则逐步提高空配。锡仓位低于铜铝。')
    elif destocking:
        strategy = ('低库存与强结构下不追空，中期仍等供应恢复后的反弹偏空机会。月差正套可保留但控制换月风险；'
                    '若库存转为持续回升且LME Back走弱，再提高空配；若继续去库则降低空头与反套仓位。')
    else:
        strategy = ('库存与结构若同步转弱，维持反弹偏空和月差正套降仓思路，重点等待缅甸、印尼供应恢复兑现；'
                    '若社库重新持续下降或LME Back快速走强，停止加空。')
    dates = [x[0] for x in (output_latest, tc_latest, profit_latest, solder_latest, import_latest, ratio_latest,
                            registered_latest, cancelled_latest, lme03_latest, smm03_latest, oi_latest, seat_latest) if x and x[0]]
    dates += [rows[key][-1][0] for key in ('a10020744', 'ID01517441', 'a10006434', 'FU00015998') if rows[key]]
    asof = max(dates) if dates else datetime.date.today().isoformat()
    dt = datetime.date.fromisoformat(asof)
    week = f'{dt.strftime("%b")}-W{(dt.day - 1) // 7 + 1}'
    sources = [s for s in (social_source, my_source, lme_source, shfe_source) if s]
    sources += [
        {'label': 'LME 0-3（westmetall）', 'value': f'{common.num(lme03_latest[1], 1, True)}美元/吨', 'date': lme03_latest[0], 'source': 'lme_cash3m.json / 每日点评'} if lme03_latest else {'label': 'LME 0-3', 'value': '—', 'date': '', 'source': 'westmetall'},
        {'label': 'LME 0-3（SMM）', 'value': f'{common.num(smm03_latest[1], 2, True)}美元/吨', 'date': smm03_latest[0] or '', 'source': '数据缓存_v1.db / 锡周报'},
        {'label': '沪锡总持仓', 'value': f'{common.num(oi_latest[1], 0)}手', 'date': oi_latest[0] or '', 'source': '数据缓存_v1.db / 日报'},
        {'label': '前20席位净持仓', 'value': f'{common.num(seat_latest[1], 0, True)}手', 'date': seat_latest[0] or '', 'source': 'tin_monitor.db / 上期所会员榜'},
        {'label': '年度平衡', 'value': '2026E +0.26万吨；2027E +1.02万吨', 'date': '2026-10-24', 'source': '永安锡周报第40页平衡拟合'},
        {'label': '锡锭进口利润', 'value': f'{common.num(import_latest[1], 0, True)}元/吨', 'date': import_latest[0] or '', 'source': '数据缓存_v1.db / 日报'},
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


def copy_template():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'panel.css', 'panel.js'):
        text = (TEMPLATE / name).read_text(encoding='utf-8')
        text = text.replace('铝周会面板', '锡周会面板').replace('ALUMINUM WEEKLY MEETING', 'TIN WEEKLY MEETING')
        text = text.replace('铝研究周报', '锡研究周报').replace('window.AL_MEETING_PANEL', 'window.SN_MEETING_PANEL')
        text = text.replace('aluminum-meeting-panel-overrides-v1', 'tin-meeting-panel-overrides-v1')
        text = text.replace('data/aluminum_meeting_overrides.json', 'data/tin_meeting_overrides.json')
        text = text.replace('aluminum_meeting_overrides.json', 'tin_meeting_overrides.json')
        text = text.replace('>AL</td>', '>SN</td>')
        (OUT / name).write_text(text, encoding='utf-8')


def main():
    auto, origins, sources, asof = build_auto()
    minutes, minutes_meta = common.load_minutes(MINUTES_DIR, TIN_PATTERN, PEOPLE)
    for person, text in minutes.items():
        if text:
            auto['opinion.' + person] = text
            origins['opinion.' + person] = 'minutes'
    manual = common.read_json(OVERRIDES, {'values': {}, 'auto_reset': []})
    manual.setdefault('values', {})
    manual.setdefault('auto_reset', [])
    supplied = [p for p in PEOPLE if manual['values'].get('opinion.' + p)]
    if not minutes_meta.get('file') and supplied:
        minutes_meta['status'] = f'2025-11-W4用户纪要 · 已填{len(supplied)}/{len(PEOPLE)}人'
    built = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    meta = {'asof': asof, 'built_at': built, 'minutes_status': minutes_meta['status'],
            'minutes_file': minutes_meta.get('file'), 'minutes_unassigned_lines': minutes_meta.get('unassigned', 0),
            'balance_note': '年度平衡来自永安锡周报2026-10-24预测，日／周数据用于滚动验证；SMM与Mysteel社库、westmetall与SMM升贴水并列展示，不混成同一序列；前20席位不等于真实盈亏。缺数不补零。',
            'minutes_help': f'腾讯会议纪要放入 {MINUTES_DIR}（TXT / MD / VTT / SRT / DOCX）。最新文件按“标／昊／天／航／陈／文”及姓名末字识别发言人，保留原句提炼，不识别“发言人1”等匿名标签；原始纪要不进入网站目录。本期五段观点来自用户提供的2025-11-W4会议纪要，已设为线上手动默认。'}
    payload = {'auto': auto, 'origins': origins, 'manual': manual, 'people': PEOPLE,
               'sources': sources, 'meta': meta}
    copy_template()
    text = 'window.SN_MEETING_PANEL=' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/') + ';\n'
    tmp = OUT / 'panel_data.js.tmp'
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, OUT / 'panel_data.js')
    SUMMARY.write_text(json.dumps({'asof': asof, 'built_at': built, 'minutes': minutes_meta,
                                   'local_url': 'tin-weekly/meeting/', 'sync_status': 'ok'}, ensure_ascii=False, indent=2), encoding='utf-8')
    assert len(PEOPLE) == 6 and all('opinion.' + p in auto for p in PEOPLE)
    assert all(key in auto for key in ('balance', 'spot', 'positions', 'watch', 'contradiction', 'strategy'))
    print(json.dumps({'output': str(OUT), 'asof': asof, 'minutes': minutes_meta['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
