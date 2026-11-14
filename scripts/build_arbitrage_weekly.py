import argparse
import datetime as dt
import json
import math
import os
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
NAMES = {'CU': '铜', 'AL': '铝', 'ZN': '锌', 'PB': '铅', 'NI': '镍', 'SN': '锡', 'LC': '碳酸锂', 'SI': '工业硅'}
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
        'history': history, 'weekly': WEEKLY_LINKS.get(sym),
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
        'scenario': {'premium': 0, 'otherCost': 0}, 'weekly': None,
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
