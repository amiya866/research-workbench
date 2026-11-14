import argparse
import datetime as dt
import json
import math
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ARB_SCRIPTS = Path(r'D:/Kimi/套利研究/脚本')
sys.path.insert(0, str(ARB_SCRIPTS))
import _arb_backtest6 as arb

OUT_DIR = BASE / 'arbitrage-weekly'
OUT = OUT_DIR / 'data' / 'arbitrage_weekly.json'
PREVIOUS = OUT_DIR / 'data' / 'arbitrage_weekly.previous.json'
PAGE = OUT_DIR / 'index.html'
SMM_DB = Path(r'D:/Kimi/smm_mirror/smm_mirror.db')
SPOT = {'LC': ('202212050001', 'SMM电池级碳酸锂指数'), 'SI': ('201812270002', '通氧553#硅(华东)')}
DRIVERS = {
    'CU': {'stock': ('mirror', 'cuStockMarketYieldSum', '万吨', 'Mysteel国内市场电解铜库存'),
           'premium': ('s20123047', 'SMM长江1#电解铜升贴水-平均价')},
    'AL': {'stock': ('mirror', 'alStockSpots', '万吨', 'Mysteel中国主要市场电解铝现货库存'),
           'premium': ('s20016488', 'SMM A00铝升贴水-平均价')},
    'ZN': {'stock': ('mirror', 'znStockHomeSum', '万吨', 'Mysteel国内主要市场锌锭库存'),
           'premium': ('ID02038785', 'Mysteel上海0#锌锭升贴水')},
    'PB': {'stock': ('mirror', 'pbStockHomeSum', '万吨', 'Mysteel国内主要市场铅锭库存'),
           'premium': ('ID01029987', 'Mysteel上海驰宏1#铅锭升贴水')},
    'NI': {'stock': ('a10020773', 'SMM纯镍社会库存分地区:六地总计'),
           'premium': ('s20019092', 'SMM 1#金川镍沪镍合约升贴水-平均价')},
    'SN': {'stock': ('a10020744', 'SMM锡锭社会库存:总库存'),
           'premium': ('a10083984', 'SMM沪锡市场现货升贴水-平均价')},
    'LC': {'stock': ('a12752003', 'SMM四地样本碳酸锂社会库存:沪苏赣川'),
           'premium': ('ID01922207', 'Mysteel电池级碳酸锂升贴水')},
    'SI': {'stock': ('a10020032', 'SMM金属硅社会库存:昆明'),
           'premium': ('s22715114', 'SMM 421#硅(广东)升贴水-平均价（非553同口径）')},
}
NAMES = {'CU': '铜', 'AL': '铝', 'ZN': '锌', 'PB': '铅', 'NI': '镍', 'SN': '锡', 'LC': '碳酸锂', 'SI': '工业硅'}
FLOWS = {
    'CU': ('import', 'a10014992', '中国海关电解铜进口量', '万吨', 1),
    'AL': ('import', 'a10016192', '中国海关电解铝进口量', '吨', 1),
    'ZN': ('import', 'a10018062', '中国海关精炼锌进口量', '吨', 1),
    'PB': ('import', 'a12813951', '中国海关精炼铅进口量（原始单位千克，已换算为吨）', '吨', 0.001),
    'NI': ('import', 'ID00188813', '中国海关未锻轧非合金镍进口量', '吨', 1),
    'SN': ('import', 'a10003102', '中国海关未锻轧非合金锡进口量', '吨', 1),
    'LC': ('import', 'a10009654', '中国海关碳酸锂进口量', '吨', 1),
    'SI': ('export', 'a10020029', '中国海关金属硅出口量', '吨', 1),
}
WEEKLY_LINKS = {'CU': 'copper-weekly', 'AL': 'aluminum-weekly', 'ZN': 'zinc-weekly', 'PB': 'lead-weekly', 'NI': 'nickel-weekly', 'SN': 'tin-weekly'}
WARNINGS = []


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def pct_rank(values, current):
    return sum(value <= current for value in values) / len(values) * 100 if values else None


def load_lme(sym):
    result = {}
    path = Path(arb.DATADIR) / f'arb6_{sym}_lme.csv'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines()[1:]:
            parts = line.split(',')
            if len(parts) == 3:
                result[parts[0]] = (float(parts[1]), float(parts[2]))
    return result


def load_driver_csv(path):
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines()[1:]:
        parts = line.split(',')
        if len(parts) >= 2:
            try:
                result[parts[0]] = float(parts[1])
            except ValueError:
                pass
    return result


def save_driver_csv(path, points):
    path.write_text('date,value\n' + ''.join(f'{date},{value}\n' for date, value in sorted(points.items())), encoding='utf-8')


def indicator_series(indicator, offline=False):
    path = Path(arb.DATADIR) / f'arb_driver_{indicator}.csv'
    if offline:
        return load_driver_csv(path)
    try:
        raw = arb.curl(f'{arb.ZSERIES}?id={indicator}&start=2020-01-01&end={dt.date.today().isoformat()}',
                       [f'X-Data-Key: {arb.key()}'])
        points = {}
        for row in json.loads(raw).get('points') or []:
            try:
                points[str(row['date'])[:10]] = float(row['value'])
            except (TypeError, ValueError):
                pass
        if not points:
            raise RuntimeError(f'{indicator} 无有效数据')
        save_driver_csv(path, points)
        return points
    except Exception:
        return load_driver_csv(path)


def lme_stock_series(sym, field, offline=False):
    path = Path(arb.DATADIR) / f'arb6_{sym}_lme_stock.csv'
    cached = load_driver_csv(path)
    if offline or (cached and max(cached) >= (dt.date.today() - dt.timedelta(days=4)).isoformat()):
        return cached
    months = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
              "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}
    try:
        for year in range(2020, dt.date.today().year + 1):
            text = arb.curl(f'https://www.westmetall.com/en/markdaten.php?action=table&field={field}&year={year}',
                            ['User-Agent: Mozilla/5.0'], timeout=40)
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.S):
                cells = [re.sub(r'<[^>]+>|\s+', ' ', cell).strip()
                         for cell in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
                if len(cells) < 4:
                    continue
                match = re.match(r'(\d{2})\. (\w+) (\d{4})', cells[0])
                if not match or match.group(2) not in months:
                    continue
                day = f'{match.group(3)}-{months[match.group(2)]:02d}-{int(match.group(1)):02d}'
                try:
                    cached[day] = float(cells[3].replace(',', ''))
                except ValueError:
                    pass
        save_driver_csv(path, cached)
    except Exception:
        pass
    return cached


def mirror_stock_series(chart_code):
    connection = sqlite3.connect(r'file:D:/Kimi/mysteel_mirror/mysteel_mirror.db?mode=ro', uri=True)
    try:
        rows = connection.execute('select series_name,date,value from series_points where chart_code=? order by date', (chart_code,)).fetchall()
    finally:
        connection.close()
    output = {}
    for _name, date, value in rows:
        if finite(value):
            output[str(date)[:10]] = value
    return output


def nearby_point(points, target, tolerance):
    if not points:
        return None
    date = min(points, key=lambda item: abs((dt.date.fromisoformat(item) - target).days))
    return date if abs((dt.date.fromisoformat(date) - target).days) <= tolerance else None


def seasonal_series(points, years=5):
    if not points:
        return []
    last_year = dt.date.fromisoformat(max(points)).year
    output = []
    for year in range(last_year - years + 1, last_year + 1):
        rows = [{'date': date[5:], 'value': points[date]} for date in sorted(points) if date.startswith(f'{year}-')]
        if rows:
            output.append({'year': year, 'points': rows})
    return output


def driver_metric(points, unit, source):
    empty = {'value': None, 'change': None, 'date': None, 'unit': unit, 'source': source,
             'history': [], 'seasonal': [], 'pctRank': None, 'yoy': None, 'yoyChange': None,
             'oneYearChange': None, 'high': None, 'low': None, 'fromHigh': None, 'level': '未核定'}
    if not points:
        return empty
    ordered = sorted(points)
    last = ordered[-1]
    last_date = dt.date.fromisoformat(last)
    previous = nearby_point(points, last_date - dt.timedelta(days=20), 15)
    year_ago = nearby_point(points, last_date - dt.timedelta(days=365), 45)
    values = list(points.values())
    current = points[last]
    high, low = max(values), min(values)
    rank = pct_rank(values, current)
    previous_year_value = points[year_ago] if year_ago else None
    yoy_change = current - previous_year_value if previous_year_value is not None else None
    yoy = yoy_change / abs(previous_year_value) * 100 if previous_year_value not in (None, 0) else None
    return {
        'value': current, 'change': current - points[previous] if previous else None,
        'date': last, 'previousDate': previous, 'unit': unit, 'source': source,
        'history': [{'date': date, 'value': points[date]} for date in ordered[-120:]],
        'seasonal': seasonal_series(points),
        'pctRank': rank, 'yoy': yoy, 'yoyChange': yoy_change, 'oneYearChange': yoy_change,
        'yearAgoDate': year_ago, 'high': high, 'low': low,
        'fromHigh': (current / high - 1) * 100 if high else None,
        'level': '历史高位区' if rank >= 75 else ('历史低位区' if rank <= 25 else '历史中位区'),
        'sampleStart': ordered[0],
    }


def build_flow(sym, offline, window_open=None):
    direction, indicator, source, unit, scale = FLOWS[sym]
    raw = indicator_series(indicator, offline)
    points = {date: value * scale for date, value in raw.items() if finite(value)}
    metric = driver_metric(points, unit, f'{source}｜知几 {indicator}')
    if not points:
        metric.update({'direction': direction, 'mom': None, 'momChange': None, 'status': '海关货流数据未核定',
                       'indicator': indicator, 'note': '海关月度数据有发布滞后，不能证明当月窗口已经兑现。'})
        return metric
    ordered = sorted(points)
    last = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    mom_change = points[last] - points[previous] if previous else None
    mom = mom_change / abs(points[previous]) * 100 if previous and points[previous] else None
    rising = mom_change is not None and mom_change > 0
    noun = '进口' if direction == 'import' else '出口'
    if window_open is True:
        status = f'窗口后{noun}回升，货流初步验证' if rising else f'窗口开但当月{noun}未放量，待确认'
    elif window_open is False:
        status = f'窗口关闭但{noun}回升，关注边际变化' if rising else f'窗口关闭且{noun}未放量'
    else:
        status = f'{noun}环比回升，跟踪供给边际' if rising else f'{noun}环比回落，跟踪供给边际'
    metric.update({
        'direction': direction, 'mom': mom, 'momChange': mom_change, 'status': status,
        'indicator': indicator, 'history': [{'date': date, 'value': points[date]} for date in ordered[-12:]],
        'note': '海关月度数据有发布滞后，只能验证上一轮窗口后的实际货流，不能证明当月窗口已经兑现。',
    })
    return metric


def build_drivers(sym, field, offline, lme=None):
    config = DRIVERS[sym]
    lme = load_lme(sym) if lme is None and sym not in ('LC', 'SI') else (lme or {})
    lme03 = {date: values[0] - values[1] for date, values in lme.items()}
    return {
        'lmeStock': driver_metric({}, '吨', '无LME对应合约') if sym in ('LC', 'SI') else driver_metric(lme_stock_series(sym, field, offline), '吨', f'westmetall {field}'),
        'lmePremium': driver_metric(lme03, '美元/吨', f'westmetall {field} cash-3M') if sym not in ('LC', 'SI') else driver_metric({}, '美元/吨', '无LME对应合约'),
        'domesticStock': driver_metric(mirror_stock_series(config['stock'][1]) if config['stock'][0] == 'mirror' else indicator_series(config['stock'][0], offline),
                                       config['stock'][2] if config['stock'][0] == 'mirror' else ('万吨' if sym == 'SI' else '吨'), config['stock'][3] if config['stock'][0] == 'mirror' else config['stock'][1]),
        'domesticPremium': driver_metric(indicator_series(config['premium'][0], offline), '元/吨', config['premium'][1]),
    }


def spot_series(item_id):
    connection = sqlite3.connect(f'file:{SMM_DB.as_posix()}?mode=ro', uri=True)
    try:
        rows = connection.execute('select date,avg from hq_price where item_id=? order by date', (item_id,)).fetchall()
    finally:
        connection.close()
    return {date: value for date, value in rows if finite(value)}


def signal(sym, summary):
    imp, ratio, eq = summary['imp_last'], summary['ratio_last'], summary['eq']
    open20, close20 = summary['open20'], summary['close20']
    if imp > 0:
        if ratio >= eq:
            action = '正套候选' if summary['B'][0] >= 0.3 and open20[0] >= 10 else '正套观察'
            thesis = f'买 LME / 空 SHFE，等待比价向均衡值 {eq:.3f} 回归'
            invalid = '进口盈亏跌回零轴以下，或比价跌破均衡且货流未兑现'
        else:
            action = '窗口弱形态'
            thesis = '窗口虽开但比价低于均衡，缺乏进口货流驱动，暂不操作'
            invalid = '比价重新站上均衡且窗口维持，才重新评估正套'
    elif close20[1] > 0 and summary['eq_pct'] <= 25:
        action = '反套候选' if summary['A'][0] > 0 and close20[0] >= 10 else '反套观察'
        thesis = '买 SHFE / 空 LME，等待深亏后的比价修复'
        invalid = '亏损继续扩大且20日统计不再为正，立即停止跟随'
    else:
        action = '窗口关闭'
        thesis = '暂不具备可执行窗口，等待进口盈亏或比价进入触发区'
        invalid = '当前仅观察，不预设方向'
    return action, thesis, invalid


def build_metal(sym, name, indicator, field, fx, offline):
    if offline:
        imp = arb.load_csv(str(Path(arb.DATADIR) / f'arb6_{sym}_imp.csv'))
        shfe = arb.load_csv(str(Path(arb.DATADIR) / f'arb6_{sym}_shfe.csv'))
        lme = load_lme(sym)
    else:
        try:
            imp = arb.get_imp(sym, indicator)
        except Exception as exc:
            imp = arb.load_csv(str(Path(arb.DATADIR) / f'arb6_{sym}_imp.csv'))
            WARNINGS.append(f'{sym} 进口盈亏接口失败，使用缓存：{str(exc)[:120]}')
        try:
            shfe = arb.get_shfe(sym)
        except Exception as exc:
            shfe = arb.load_csv(str(Path(arb.DATADIR) / f'arb6_{sym}_shfe.csv'))
            WARNINGS.append(f'{sym} SHFE接口失败，使用缓存：{str(exc)[:120]}')
        try:
            lme = arb.get_lme(sym, field)
        except Exception as exc:
            lme = load_lme(sym)
            WARNINGS.append(f'{sym} LME接口失败，使用缓存：{str(exc)[:120]}')
    days = sorted(set(imp) & set(shfe) & set(lme) & set(fx))
    if not days:
        raise RuntimeError(f'{sym} 没有共同交易日')
    ratio = [(date, shfe[date] / (lme[date][1] * fx[date])) for date in days if lme[date][1] > 0 and fx[date] > 0]
    rmap = dict(ratio)
    imps = [imp[date] for date in days]
    near0 = sorted(days, key=lambda date: abs(imp[date]))[:max(20, len(days) // 20)]
    eq = sorted(rmap[date] for date in near0)[len(near0) // 2]
    o20 = arb.fwd_stats(ratio, imp, 20, lambda date: imp[date] > 0)
    c20 = arb.fwd_stats(ratio, imp, 20, lambda date: imp[date] < 0)
    pos_vals = sorted(value for value in imps if value > 0)
    wide = pos_vals[int(len(pos_vals) * 0.7)] if pos_vals else 1000
    strategy_a = arb.backtest(ratio, imp, wide, 0)
    strategy_b = arb.backtest(ratio, imp, wide, None)
    last = days[-1]
    summary = {'imp_last': imp[last], 'ratio_last': rmap[last], 'eq': eq,
               'eq_pct': pct_rank([value for _, value in ratio], rmap[last]),
               'open20': o20, 'close20': c20, 'A': strategy_a, 'B': strategy_b, 'wide': wide}
    action, thesis, invalid = signal(sym, summary)
    history = [{'date': date, 'ratio': rmap[date], 'imp': imp[date], 'lme03': lme[date][0] - lme[date][1]} for date in days[-120:]]
    shfe_last, cash_last, m3_last, fx_last = shfe[last], lme[last][0], lme[last][1], fx[last]
    calibration = shfe_last - cash_last * fx_last * 1.13 - imp[last]
    return {
        'symbol': sym, 'name': name, 'kind': 'lme-shfe', 'last': last, 'action': action,
        'thesis': thesis, 'invalid': invalid, 'imp': imp[last], 'ratio': rmap[last], 'eq': eq,
        'ratioPct': summary['eq_pct'], 'impPct': pct_rank(imps, imp[last]),
        'lme03': lme[last][0] - lme[last][1], 'open20': o20, 'close20': c20,
        'sharpeA': strategy_a[0], 'sharpeB': strategy_b[0], 'wide': wide,
        'shfe': shfe_last, 'lmeCash': cash_last, 'lmeM3': m3_last, 'fx': fx_last,
        'scenario': {'premium': 0, 'otherCost': calibration},
        'history': history, 'seasonal': seasonal_series(rmap), 'weekly': WEEKLY_LINKS.get(sym), 'drivers': build_drivers(sym, field, offline, lme),
        'flow': build_flow(sym, offline, imp[last] > 0),
        'source': {'importProfit': indicator, 'lme': field, 'fx': 'CM00891264 / 历史缓存'},
    }


def build_spot(sym, offline):
    futures = arb.load_csv(str(Path(arb.DATADIR) / f'arb6_{sym}_shfe.csv')) if offline else arb.get_shfe(sym)
    item_id, source_name = SPOT[sym]
    spot = spot_series(item_id)
    days = sorted(set(futures) & set(spot))
    if not days:
        raise RuntimeError(f'{sym} 期现没有共同交易日')
    history = [{'date': date, 'spot': spot[date], 'futures': futures[date],
                'basis': spot[date] - futures[date]} for date in days[-120:]]
    bases = [row['basis'] for row in history]
    last = days[-1]
    basis = spot[last] - futures[last]
    percentile = pct_rank(bases, basis)
    if percentile >= 75:
        action, thesis = '买现卖期观察', '现货升水处于高位，关注现货强、期货弱的回归机会'
    elif percentile <= 25:
        action, thesis = '买期卖现观察', '期货升水处于高位，关注期货强、现货弱的回归机会'
    else:
        action, thesis = '基差中性观察', '基差处于中位，暂不追逐方向'
    return {
        'symbol': sym, 'name': NAMES[sym], 'kind': 'spot-futures', 'last': last,
        'action': action, 'thesis': thesis, 'invalid': '仅作期现观察；基差回到中位或流动性不足时不执行',
        'basis': basis, 'basisPct': basis / spot[last] * 100, 'ratioPct': percentile,
        'spot': spot[last], 'futures': futures[last], 'history': history,
        'seasonal': seasonal_series({date: spot[date] - futures[date] for date in days}),
        'scenario': {'premium': 0, 'otherCost': 0}, 'weekly': None, 'drivers': build_drivers(sym, '', offline),
        'flow': build_flow(sym, offline),
        'source': {'spot': f'SMM hq {item_id} {source_name}', 'futures': '知几 guan 主连日K'},
    }


def build(offline=False):
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    try:
        fx = arb.get_fx()
    except Exception:
        fx = arb.load_csv(str(Path(arb.DATADIR) / '_fx_usdcny.csv'))
    panels = []
    for sym, name, indicator, field in arb.METALS:
        print('building', sym, flush=True)
        panels.append(build_metal(sym, name, indicator, field, fx, offline))
    for sym in ['LC', 'SI']:
        print('building', sym, flush=True)
        panels.append(build_spot(sym, offline))
    payload = {
        'meta': {
            'builtAt': dt.datetime.now().isoformat(timespec='seconds'),
            'latest': max(panel['last'] for panel in panels),
            'warnings': WARNINGS,
            'notes': ['正套=买LME/空SHFE；反套=买SHFE/空LME。', '窗口和历史统计需同时满足，候选不等于无条件交易指令。', '碳酸锂与工业硅没有LME对应合约，仅做期现基差观察。'],
        },
        'panels': panels,
    }
    validate(payload)
    return payload


def validate(payload):
    def walk(value):
        if isinstance(value, float):
            assert math.isfinite(value), '存在非有限数值'
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(payload)
    assert len(payload['panels']) == 8
    for panel in payload['panels']:
        assert panel['history'], panel['symbol']
        assert panel['last'] >= '2026-01-01', panel['symbol']
        if panel['kind'] == 'lme-shfe':
            assert panel['ratio'] > 0 and panel['eq'] > 0 and panel['fx'] > 0
            scenario_imp = panel['shfe'] - (panel['lmeCash'] + panel['scenario']['premium']) * panel['fx'] * 1.13 - panel['scenario']['otherCost']
            assert abs(scenario_imp - panel['imp']) < 0.02, f"{panel['symbol']} 情景基准不闭合"
        else:
            assert panel['spot'] > 0 and panel['futures'] > 0


def write_outputs(payload, inject=True):
    template = BASE / 'scripts' / 'templates' / 'arbitrage-weekly'
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template / 'index.html', PAGE)
    (OUT_DIR / 'assets').mkdir(exist_ok=True)
    shutil.copyfile(template / 'assets' / 'app.js', OUT_DIR / 'assets' / 'app.js')
    (OUT_DIR / 'lib').mkdir(exist_ok=True)
    shutil.copyfile(BASE / 'tin-weekly' / 'lib' / 'chart.min.js', OUT_DIR / 'lib' / 'chart.min.js')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        PREVIOUS.write_bytes(OUT.read_bytes())
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, OUT)
    if inject:
        page = PAGE.read_text(encoding='utf-8')
        start = page.index('const ARB_DATA=') + len('const ARB_DATA=')
        end = page.index(';', start)
        PAGE.write_text(page[:start] + text + page[end:], encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'builtAt': payload['meta']['builtAt'], 'latest': payload['meta']['latest'],
                      'actions': {panel['symbol']: panel['action'] for panel in payload['panels']},
                      'injected': inject}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='构建有色套利周报')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--no-inject', action='store_true')
    args = parser.parse_args()
    write_outputs(build(args.offline), not args.no_inject)


if __name__ == '__main__':
    main()
