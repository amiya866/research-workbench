import argparse
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

sys.path.insert(0, r'D:\Kimi\nickel-panel\scripts')
from build_china_balance import ApiLoader, monthly_last

BASE = Path(__file__).resolve().parents[1]
SOURCE = Path(r'D:/拷贝文件/E/永安/周报数据更新/【永安期货研究中心】锡数据库.xlsx')
OUT_DIR = BASE / 'tin-weekly' / 'balance'
OUT = OUT_DIR / 'data' / 'tin_balance.json'
PREVIOUS = OUT_DIR / 'data' / 'tin_balance.previous.json'
PAGE = OUT_DIR / 'index.html'
SHEETS = {'ore': '矿端平衡', 'ingot': '锡锭平衡'}
FIELDS = {
    'ingot': [
        ('production', '精炼锡产量', 'L', '产量'),
        ('imports', '精炼锡进口', 'O', '进出口'),
        ('exports', '精炼锡出口', 'R', '进出口'),
        ('netImports', '精炼锡净进口', 'U', '进出口'),
        ('socialStock', '锡锭社会库存', 'AA', '库存'),
        ('factoryStock', '锡锭厂库', 'AC', '库存'),
    ],
    'ore': [
        ('domesticMine', '国产锡矿（金属量）', 'L', '供应'),
        ('totalImports', '锡矿进口（实物量）', 'O', '进口'),
        ('myanmarImports', '缅甸矿进口（实物量）', 'R', '进口'),
        ('congoImports', '刚果金矿进口（实物量）', 'U', '进口'),
        ('otherImports', '其他国家矿进口（实物量）', 'X', '进口'),
        ('myanmarGrade', '缅甸矿品位', 'Y', '折金属假设'),
        ('otherGrade', '其他国家矿品位', 'OTHER_GRADE', '折金属假设'),
        ('primaryTin', '原生锡产量（金属量）', 'AK', '需求'),
    ],
}
TITLES = {'ore': '中国锡矿平衡', 'ingot': '中国锡锭平衡'}
ACTUAL_CUTOFF = '2026-09'


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def month_value(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime('%Y-%m')
    if finite(value):
        return from_excel(value).strftime('%Y-%m')
    return None


def shift_month(month, delta):
    year, mon = map(int, month[:7].split('-'))
    index = year * 12 + mon - 1 + delta
    return f'{index // 12:04d}-{index % 12 + 1:02d}{month[7:]}'


def read_excel():
    formula_book = load_workbook(SOURCE, read_only=True, data_only=False)
    value_book = load_workbook(SOURCE, read_only=True, data_only=True)
    result = {}
    try:
        for key, sheet_name in SHEETS.items():
            formula_sheet, value_sheet = formula_book[sheet_name], value_book[sheet_name]
            rows = {}
            for row_number, (formula_row, value_row) in enumerate(zip(
                    formula_sheet.iter_rows(), value_sheet.iter_rows()), 1):
                month = month_value(value_row[10].value)
                if not month:
                    continue
                values = {}
                for field, _label, column, _group in FIELDS[key]:
                    if column == 'OTHER_GRADE':
                        continue
                    values[field] = number(value_row[column_index(column)].value)
                formulas = {cell.column_letter: cell.value for cell in formula_row
                            if isinstance(getattr(cell, 'value', None), str) and cell.value.startswith('=')}
                if key == 'ore':
                    other_imports = values.get('otherImports')
                    other_metal = number(value_row[column_index('AD')].value)
                    values['otherGrade'] = other_metal / other_imports if finite(other_metal) and finite(other_imports) and other_imports else None
                rows[month] = {'row': row_number, 'values': values, 'formulas': formulas}
            result[key] = rows
    finally:
        formula_book.close()
        value_book.close()
    return result


def column_index(column):
    result = 0
    for char in column:
        result = result * 26 + ord(char) - 64
    return result - 1


def initial_months(excel, panel):
    output = {}
    for month, row in excel[panel].items():
        output[month] = {
            'date': month, 'values': dict(row['values']), 'excelRow': row['row'],
            'apiFields': [], 'sourceDates': {},
            'primaryFromRefined': bool(panel == 'ore' and '锡锭平衡!L' in row['formulas'].get('AK', '')),
        }
    return output


def overlay(months, field, points, source_key):
    for month, (_, value) in monthly_last(points).items():
        if month not in months or not finite(value):
            continue
        months[month]['values'][field] = value
        if source_key not in months[month]['apiFields']:
            months[month]['apiFields'].append(source_key)
        months[month]['sourceDates'][source_key] = max(points) if points else None


def val(month, field, default=None):
    value = month['values'].get(field)
    return default if not finite(value) else value


def available(month, fields):
    return all(finite(month['values'].get(field)) for field in fields)


def compute(panel, months, ingot_months):
    previous = None
    actual = []
    for month_key in sorted(months):
        month = months[month_key]
        supply = demand = balance = stock_change = None
        if panel == 'ingot':
            if available(month, ['production', 'netImports']):
                supply = val(month, 'production') + val(month, 'netImports')
            if previous and supply is not None and available(month, ['socialStock']) and available(previous, ['socialStock']):
                social_change = val(month, 'socialStock') - val(previous, 'socialStock')
                factory_change = 0
                if available(month, ['factoryStock']) and available(previous, ['factoryStock']):
                    factory_change = val(month, 'factoryStock') - val(previous, 'factoryStock')
                demand = supply - social_change - factory_change
                stock_change = social_change + factory_change
        else:
            if month['primaryFromRefined'] and month_key in ingot_months:
                production = ingot_months[month_key]['values'].get('production')
                if finite(production):
                    month['values']['primaryTin'] = production * 0.794
            if available(month, ['totalImports', 'myanmarImports', 'congoImports']):
                month['values']['otherImports'] = val(month, 'totalImports') - val(month, 'myanmarImports') - val(month, 'congoImports')
            if available(month, ['domesticMine', 'otherImports', 'myanmarImports', 'congoImports', 'myanmarGrade', 'otherGrade']):
                import_metal = val(month, 'myanmarImports') * val(month, 'myanmarGrade') + val(month, 'congoImports') * 0.6 + val(month, 'otherImports') * val(month, 'otherGrade')
                supply = val(month, 'domesticMine') + import_metal
            if available(month, ['primaryTin']):
                demand = val(month, 'primaryTin') / 0.975
        if supply is not None and demand is not None:
            balance = supply - demand
        month['computed'] = {'supply': supply, 'demand': demand, 'balance': balance, 'stockChange': stock_change}
        if balance is not None:
            month['status'] = 'actual' if month_key <= ACTUAL_CUTOFF else 'forecast'
            if month['status'] == 'actual':
                actual.append(month_key)
        else:
            month['status'] = 'partial'
        previous = month
    return actual[-1] if actual else None


def source_definitions():
    return {
        'ingot_production': {'label': 'SMM国内精炼锡产量', 'api': 'a10003083', 'transform': '吨，月度'},
        'ingot_social_stock': {'label': 'Mysteel中国锡锭库存', 'api': 'ID01517441', 'transform': '周度取每月最后值'},
        'ore_total_imports': {'label': '锡矿砂及精矿总进口', 'api': 'Mysteel snImportHomeSum', 'transform': '实物吨，月度'},
        'ore_myanmar_imports': {'label': '缅甸锡矿进口', 'api': 'CM0000451826', 'transform': '实物吨，月度'},
        'ore_congo_imports': {'label': '刚果金锡矿进口', 'api': 'CM0000451831', 'transform': '实物吨，月度'},
        'ore_domestic_mine': {'label': 'NBS国内锡矿砂及精矿产量', 'api': 'a10003078', 'transform': '发布月前移一月对应生产月'},
    }


def build(offline=False):
    previous_payload = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    excel = read_excel()
    months = {panel: initial_months(excel, panel) for panel in SHEETS}
    api = ApiLoader(offline, previous_payload)
    series = {}
    for key, indicator, monthly in [
        ('ingot_production', 'a10003083', False),
        ('ingot_social_stock', 'ID01517441', True),
        ('ore_myanmar_imports', 'CM0000451826', False),
        ('ore_congo_imports', 'CM0000451831', False),
        ('ore_domestic_mine', 'a10003078', False),
    ]:
        points, _ = api.zhiji(key, indicator, monthly=monthly)
        series[key] = points
    key = 'ore_total_imports'
    try:
        grouped = api.client.mirror('snImportHomeSum', start='2020-01-01')
        points = next(values for name, values in grouped.items() if '进口数量合计' in name)
        api.cache[key] = {'points': points, 'indicators': ['Mysteel:snImportHomeSum'], 'scale': 1, 'monthlyLast': False}
        api.status.append({'key': key, 'status': 'ok', 'points': len(points), 'latest': max(points), 'error': ''})
        series[key] = points
    except Exception as exc:
        if key in previous_payload.get('apiCache', {}):
            points = previous_payload['apiCache'][key]['points']
            api.cache[key] = previous_payload['apiCache'][key]
            api.status.append({'key': key, 'status': 'stale', 'points': len(points), 'latest': max(points), 'error': str(exc)[:240]})
            series[key] = points
        else:
            api.status.append({'key': key, 'status': 'error', 'error': str(exc)[:240]})
    overlay(months['ingot'], 'production', series.get('ingot_production', {}), 'ingot_production')
    overlay(months['ingot'], 'socialStock', series.get('ingot_social_stock', {}), 'ingot_social_stock')
    overlay(months['ore'], 'totalImports', series.get('ore_total_imports', {}), 'ore_total_imports')
    overlay(months['ore'], 'myanmarImports', series.get('ore_myanmar_imports', {}), 'ore_myanmar_imports')
    overlay(months['ore'], 'congoImports', series.get('ore_congo_imports', {}), 'ore_congo_imports')
    shifted = {shift_month(month, -1): value for month, value in series.get('ore_domestic_mine', {}).items()}
    overlay(months['ore'], 'domesticMine', shifted, 'ore_domestic_mine')
    actual_ingot = compute('ingot', months['ingot'], months['ingot'])
    actual_ore = compute('ore', months['ore'], months['ingot'])
    panels = {}
    for panel, actual_through in [('ingot', actual_ingot), ('ore', actual_ore)]:
        rows = [months[panel][key] for key in sorted(months[panel]) if key >= '2021-01']
        rows = [row for row in rows if row['status'] != 'partial' or any(finite(value) for value in row['values'].values())]
        fields = [{'key': field, 'label': label, 'group': group,
                   'excel': f'{SHEETS[panel]}!{column}<row>' if column != 'OTHER_GRADE' else f'{SHEETS[panel]}!AD<row>/X<row>'}
                  for field, label, column, group in FIELDS[panel]]
        notes = {
            'ingot': '供应=精炼锡产量+净进口；表消=供应-社库变化-厂库变化；平衡=社库+厂库变化。精锡贸易保留原表，厂库缺报按原表空值=0处理。',
            'ore': '供应=国产矿+进口折金属；进口折金属=缅甸×缅甸品位+刚果金×60%+其他国家×其他国家品位；需求=原生锡/97.5%。NBS国产矿按发布月前移一月。',
        }[panel]
        panels[panel] = {'title': TITLES[panel], 'sheet': SHEETS[panel], 'unit': '金属吨',
                         'actualThrough': actual_through, 'fields': fields, 'months': rows, 'notes': notes}
    payload = {
        'meta': {
            'kind': 'tin', 'builtAt': dt.datetime.now().isoformat(timespec='seconds'),
            'excel': str(SOURCE), 'excelModified': dt.datetime.fromtimestamp(SOURCE.stat().st_mtime).isoformat(timespec='seconds'),
            'unit': '吨（页面可切换万吨）', 'actualCutoff': ACTUAL_CUTOFF, 'apiStatus': api.status,
            'notes': ['源Excel只读；精锡贸易和厂库没有采用同名不同口径API硬替。', '矿端历史原生锡来自独立原生锡列，预测月才按精锡产量×0.794推算。'],
        },
        'sources': source_definitions(), 'panels': panels, 'apiCache': api.cache,
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
    for panel, definition in payload['panels'].items():
        assert definition['months'], panel
        for month in definition['months']:
            c = month['computed']
            if c['supply'] is not None and c['demand'] is not None:
                assert abs(c['supply'] - c['demand'] - c['balance']) < 1e-6, (panel, month['date'])
            if panel == 'ingot' and c['stockChange'] is not None:
                assert abs(c['balance'] - c['stockChange']) < 0.02, month['date']
    ingot_jan = next(row for row in payload['panels']['ingot']['months'] if row['date'] == '2026-01')
    assert abs(ingot_jan['values']['production'] - 15100) < 1, '精锡产量映射错误'
    ore_jan = next(row for row in payload['panels']['ore']['months'] if row['date'] == '2026-01')
    assert abs(ore_jan['values']['domesticMine'] - 4708.29) < 1, 'NBS生产月对齐错误'
    assert abs(ore_jan['values']['myanmarImports'] - 6823.672) < 1, '缅甸矿映射错误'
    assert abs(ore_jan['values']['totalImports'] - 17801) < 2, '锡矿总进口映射错误'
    assert abs(ingot_jan['values']['socialStock'] - 11566) < 20, '社库映射错误'


def write_outputs(payload, inject=True):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        PREVIOUS.write_bytes(OUT.read_bytes())
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, OUT)
    if inject:
        page = PAGE.read_text(encoding='utf-8')
        start = page.index('const TIN_BALANCE=') + len('const TIN_BALANCE=')
        end = page.index(';', start)
        PAGE.write_text(page[:start] + text + page[end:], encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'builtAt': payload['meta']['builtAt'],
                      'panels': {key: {'months': len(panel['months']), 'actualThrough': panel['actualThrough']}
                                 for key, panel in payload['panels'].items()},
                      'api': {status: sum(item['status'] == status for item in payload['meta']['apiStatus'])
                              for status in ['ok', 'stale', 'recovered', 'error']}, 'injected': inject}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='构建中国锡矿/锡锭月度平衡可调面板')
    parser.add_argument('--offline', action='store_true', help='禁用知几直连，使用本地镜像和上次API缓存')
    parser.add_argument('--no-inject', action='store_true')
    args = parser.parse_args()
    write_outputs(build(args.offline), not args.no_inject)


if __name__ == '__main__':
    main()
