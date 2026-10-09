#!/usr/bin/env python3
# 东财历史宏观库直采 → 合并进 data/chart_series.js (键 EM_CN_*) + data/macro_catalog.js
# 背景: iFinD插件仅9个证券级API无宏观EDB(网关原话); 东财数据中心宏观库免key,
#       CPI/PPI/PMI/货币供应/GDP/工增/新增贷款/海关进出口 均~19-20年月度历史, L2·东财汇编(底层官方发布)
# 用法: python3 scripts/fetch_cn_macro.py   (GitHub Actions每日管线可跑)
import json, re, os, sys, datetime

import requests

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CS_PATH = os.path.join(APP, 'data', 'chart_series.js')
CAT_PATH = os.path.join(APP, 'data', 'macro_catalog.js')

EM_API = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName={rn}'
          '&columns=ALL&pageSize=500&sortColumns=REPORT_DATE&sortTypes=-1&source=WEB&client=WEB')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36'}

# (reportName, [(字段, 入库键, 名称, 单位), ...])
SPECS = [
    ('RPT_ECONOMY_CPI', [
        ('NATIONAL_SAME', 'EM_CN_CPI_YOY', '中国CPI同比', '%'),
        ('NATIONAL_BASE', 'EM_CN_CPI_IDX', '中国CPI指数(上年=100)', '点'),
    ]),
    ('RPT_ECONOMY_PPI', [
        ('BASE_SAME', 'EM_CN_PPI_YOY', '中国PPI同比', '%'),
    ]),
    ('RPT_ECONOMY_PMI', [
        ('MAKE_INDEX', 'EM_CN_PMI_MFG', '官方制造业PMI', '点'),
        ('NMAKE_INDEX', 'EM_CN_PMI_NMFG', '官方非制造业PMI', '点'),
    ]),
    ('RPT_ECONOMY_CURRENCY_SUPPLY', [
        ('BASIC_CURRENCY_SAME', 'EM_CN_M2_YOY', '中国M2同比', '%'),
        ('CURRENCY_SAME', 'EM_CN_M1_YOY', '中国M1同比', '%'),
        ('FREE_CASH_SAME', 'EM_CN_M0_YOY', '中国M0同比', '%'),
        ('BASIC_CURRENCY', 'EM_CN_M2_STK', '中国M2存量', '亿元'),
    ]),
    ('RPT_ECONOMY_GDP', [
        ('SUM_SAME', 'EM_CN_GDP_YOY', '中国GDP累计同比', '%'),
        ('DOMESTICL_PRODUCT_BASE', 'EM_CN_GDP_STK', '中国GDP(累计)', '亿元'),
    ]),
    ('RPT_ECONOMY_INDUS_GROW', [
        ('BASE_SAME', 'EM_CN_IAV_YOY', '规上工业增加值同比', '%'),
    ]),
    ('RPT_ECONOMY_RMB_LOAN', [
        ('RMB_LOAN', 'EM_CN_LOAN_NEW', '新增人民币贷款(月)', '亿元'),
        ('RMB_LOAN_ACCUMULATE', 'EM_CN_LOAN_YTD', '新增人民币贷款(累计)', '亿元'),
    ]),
    ('RPT_ECONOMY_CUSTOMS', [
        ('EXIT_BASE_SAME', 'EM_CN_EXP_YOY', '出口同比(人民币)', '%'),
        ('IMPORT_BASE_SAME', 'EM_CN_IMP_YOY', '进口同比(人民币)', '%'),
    ]),
]

# 计算项: 贸易差额 = (出口-进口)/10000 (原始单位万元→亿元)
CALC = [('EM_CN_TRADE_BAL', '贸易差额(人民币,月)', '亿元', 'RPT_ECONOMY_CUSTOMS', 'EXIT_BASE', 'IMPORT_BASE')]


def fetch_report(rn):
    r = requests.get(EM_API.format(rn=rn), headers=UA, timeout=30)
    d = r.json()
    return (d.get('result') or {}).get('data') or []


def load_cs():
    raw = open(CS_PATH, encoding='utf-8').read()
    m = re.search(r'window\.CHART_SERIES\s*=\s*(\{.*\})\s*;?\s*$', raw, re.S)
    return json.loads(m.group(1))


def save_cs(cs):
    tmp = CS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('window.CHART_SERIES = ' + json.dumps(cs, ensure_ascii=False, separators=(',', ':')) + ';')
    os.replace(tmp, CS_PATH)


def load_cat():
    raw = open(CAT_PATH, encoding='utf-8').read()
    m = re.search(r'window\.MACRO_CATALOG\s*=\s*(\[.*\])\s*;?\s*$', raw, re.S)
    return json.loads(m.group(1))


def save_cat(cat):
    tmp = CAT_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('window.MACRO_CATALOG = ' + json.dumps(cat, ensure_ascii=False, separators=(',', ':')) + ';')
    os.replace(tmp, CAT_PATH)


def rows_to_series(data, field):
    """东财行(新→旧) → [[date,val],...](旧→新); 跳过空值"""
    out = {}
    for r in data:
        v = r.get(field)
        if v is None or v == '':
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        d = (r.get('REPORT_DATE') or '')[:10]
        if d:
            out[d] = v
    return [[d, out[d]] for d in sorted(out)]


def main():
    cs = load_cs()
    cat = load_cat()
    cat_ids = {c['id'] for c in cat}
    cache = {}
    added = []
    for rn, fields in SPECS:
        try:
            data = fetch_report(rn)
            cache[rn] = data
        except Exception as e:
            print('EM_FAIL', rn, e)
            continue
        for field, key, name, unit in fields:
            ser = rows_to_series(data, field)
            if not ser:
                print('空序列', rn, field)
                continue
            cs[key] = ser
            if key not in cat_ids:
                cat.append({'id': key, 'name': name, 'unit': unit})
                cat_ids.add(key)
            added.append((key, name, len(ser), ser[-1]))
    for key, name, unit, rn, f1, f2 in CALC:
        data = cache.get(rn) or fetch_report(rn)
        a = {d: v for d, v in rows_to_series(data, f1)}
        b = {d: v for d, v in rows_to_series(data, f2)}
        out = {d: round((a[d] - b[d]) / 10000, 1) for d in a if d in b}
        ser = [[d, out[d]] for d in sorted(out)]
        if ser:
            cs[key] = ser
            if key not in cat_ids:
                cat.append({'id': key, 'name': name, 'unit': unit})
                cat_ids.add(key)
            added.append((key, name, len(ser), ser[-1]))
    save_cs(cs)
    save_cat(cat)
    print('入库%d条:' % len(added))
    for key, name, n, last in added:
        print('  %-18s %-22s %4d点 最新 %s = %s' % (key, name, n, last[0], last[1]))


if __name__ == '__main__':
    main()
