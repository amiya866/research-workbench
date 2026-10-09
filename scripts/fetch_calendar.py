#!/usr/bin/env python3
# 宏观日历预期值 → data/calendar_consensus.json
# 三源合并(金十WS为主, FF/东财兜底):
#   A. ForexFactory 免费公开周历 XML —— 本周 USD/CNY 高/中重要性事件, 带 预期/前值/实际
#   B. 东方财富财经日历 (RPT_CPH_FECALENDAR) —— 未来14天全球宏观数据+财经会议/大事,
#      中文名+北京时间, 覆盖中国数据(CPI/PMI/M1/外储/贸易)、欧日英加央行决议等, 但无预期值
# 合并逻辑: FF供预期值(仅本周), EM供全景骨架(14天); 前端按日期挂芯片
# 证据分层: L2·权威财经数据商汇编(底层均为官方机构预告)
# 单源失败不影响另一源; 全失败保留旧文件并标 stale。
import json, os, re, sys, datetime, struct, xml.etree.ElementTree as ET

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(APP, 'data', 'calendar_consensus.json')
ECON_OUT = os.path.join(APP, 'data', 'econ_calendar.json')
URL = 'https://nfs.faireconomy.media/ff_calendar_thisweek.xml'

CN_MAP = {
    # 美国
    'Non-Farm Employment Change': '非农就业变动', 'Unemployment Rate': '失业率',
    'Average Hourly Earnings m/m': '平均时薪环比', 'CPI m/m': 'CPI环比', 'Core CPI m/m': '核心CPI环比',
    'CPI y/y': 'CPI同比', 'Core CPI y/y': '核心CPI同比', 'PPI m/m': 'PPI环比', 'Core PPI m/m': '核心PPI环比',
    'PPI y/y': 'PPI同比', 'ISM Manufacturing PMI': 'ISM制造业PMI', 'ISM Services PMI': 'ISM服务业PMI',
    'ISM Manufacturing Prices': 'ISM制造业物价指数', 'JOLTS Job Openings': 'JOLTS职位空缺',
    'ADP Non-Farm Employment Change': 'ADP就业变动', 'Unemployment Claims': '初请失业金',
    'Retail Sales m/m': '零售销售环比', 'Core Retail Sales m/m': '核心零售环比',
    'Advance GDP q/q': 'GDP环比折年初值', 'GDP q/q': 'GDP环比折年',
    'Personal Spending m/m': '个人支出环比', 'Personal Income m/m': '个人收入环比',
    'Core PCE Price Index m/m': '核心PCE物价环比', 'PCE Price Index m/m': 'PCE物价环比',
    'PCE price index m/m': 'PCE物价环比',
    'CB Consumer Confidence': '咨商会消费者信心', 'Michigan Consumer Sentiment': '密歇根消费者信心',
    'Michigan Inflation Expectations': '密歇根通胀预期',
    'New Home Sales': '新屋销售', 'Existing Home Sales': '成屋销售', 'Pending Home Sales m/m': '成屋签约环比',
    'Building Permits': '营建许可', 'Housing Starts': '新屋开工',
    'Durable Goods Orders m/m': '耐用品订单环比', 'Core Durable Goods Orders m/m': '核心耐用品订单环比',
    'Trade Balance': '贸易差额', 'Factory Orders m/m': '工厂订单环比',
    'Empire State Manufacturing Index': '纽约联储制造业指数', 'Philly Fed Manufacturing Index': '费城联储制造业指数',
    'Richmond Manufacturing Index': '里奇蒙德制造业指数', 'Chicago PMI': '芝加哥PMI',
    'Industrial Production m/m': '工业产出环比', 'Capacity Utilization Rate': '产能利用率',
    'Import Prices m/m': '进口价格环比', 'Export Prices m/m': '出口价格环比',
    'Construction Spending m/m': '营建支出环比', 'Business Inventories m/m': '商业库存环比',
    'Wholesale Inventories m/m': '批发库存环比', 'Consumer Credit m/m': '消费信贷',
    'Final Manufacturing PMI': 'Markit制造业PMI终值', 'Final Services PMI': 'Markit服务业PMI终值',
    'Flash Manufacturing PMI': 'Markit制造业PMI初值', 'Flash Services PMI': 'Markit服务业PMI初值',
    'S&P/CS HPI Composite-20 y/y': '20城房价同比', 'Federal Funds Rate': '联邦基金利率',
    'FOMC Statement': 'FOMC声明', 'FOMC Press Conference': 'FOMC记者会',
    'Fed Chair Powell Speaks': '鲍威尔讲话', 'Crude Oil Inventories': 'EIA原油库存',
    'Natural Gas Storage': '天然气库存', 'Revised Nonfarm Productivity q/q': '非农生产力修正值',
    'Revised Unit Labor Costs q/q': '单位劳工成本修正值', 'Challenger Job Cuts y/y': '挑战者裁员同比',
    'Prelim UoM Consumer Sentiment': '密歇根消费者信心初值', 'Prelim UoM Inflation Expectations': '密歇根通胀预期初值',
    'Revised UoM Consumer Sentiment': '密歇根消费者信心终值', 'Revised UoM Inflation Expectations': '密歇根通胀预期终值',
    'FOMC Meeting Minutes': 'FOMC会议纪要', 'Beige Book': '美联储褐皮书',
    'Treasury Refunding Announcement': '财政部再融资公告(QRA)',
    # 中国
    'Chinese Manufacturing PMI': '中国官方制造业PMI', 'Chinese Non-Manufacturing PMI': '中国官方非制造业PMI',
    'Caixin Manufacturing PMI': '财新制造业PMI', 'Caixin Services PMI': '财新服务业PMI',
    'Chinese CPI y/y': '中国CPI同比', 'Chinese PPI y/y': '中国PPI同比',
    'Chinese Trade Balance': '中国贸易差额', 'Chinese GDP y/y': '中国GDP同比',
    'Chinese Industrial Production y/y': '中国工业增加值同比', 'Chinese Retail Sales y/y': '中国社零同比',
    'Chinese Fixed Asset Investment ytd/y': '中国固投累计同比', 'Chinese Unemployment Rate': '中国城镇调查失业率',
    'NBS Press Conference': '统计局发布会',
}
KEEP_IMP = {'High', 'Medium', 'Holiday'}
KEEP_CCY = {'USD', 'CNY'}

# —— 金十WS(私有协议, 登录态cookie) ——
# PLUS账号走plus节点; 免费节点(wss-flash-2)对数据中心IP不友好, 作降级
J10_WS_LIST = ('wss://wss-jin10-plus-flash.jin10.com/', 'wss://wss-flash-2.jin10.com/')
J10_UID = 3749462
J10_KEEP_COUNTRY = ('美国', '中国', '欧元区', '日本', '英国', '加拿大', '澳大利亚', '瑞士', '德国', '法国', '欧盟', '新西兰')
J10_MAX_PER_DAY = 10

# —— 金十中国宏观积累收割(东财历史库没有的序列, 滚动窗口每日积累) ——
# indicator_name → (入库键, 名称, 单位)
J10_HARVEST = {
    '今年迄今社会融资规模增量': ('J10_CN_TSF_YTD', '社融增量(累计)', '亿元'),
    '社会消费品零售总额同比': ('J10_CN_RETAIL_YOY', '社零同比', '%'),
    '今年迄今城镇固定资产投资同比': ('J10_CN_FAI_YTD_YOY', '固投累计同比', '%'),
    '城镇调查失业率': ('J10_CN_UR', '城镇调查失业率', '%'),
    '外汇储备': ('J10_CN_FXRES', '外汇储备', '亿美元'),
    'RatingDog制造业PMI': ('J10_CN_PMI_CX', '财新(RatingDog)制造业PMI', '点'),
    '财新制造业PMI': ('J10_CN_PMI_CX', '财新(RatingDog)制造业PMI', '点'),
    '全社会用电量同比': ('J10_CN_ELEC_YOY', '全社会用电量同比', '%'),
    'GDP年率': ('J10_CN_GDP_YOY', '中国GDP单季同比', '%'),
    '以美元计算出口年率': ('J10_CN_EXP_USD_YOY', '出口同比(美元)', '%'),
    '以美元计算进口年率': ('J10_CN_IMP_USD_YOY', '进口同比(美元)', '%'),
    '以美元计算贸易帐': ('J10_CN_TRADE_USD', '贸易差额(美元,月)', '亿美元'),
}

_QMAP = {'一': 1, '二': 2, '三': 3, '四': 4, '1': 1, '2': 2, '3': 3, '4': 4}


def _j10_period_date(tp, pub_dt):
    """time_period('7月'/'第二季度') + 发布日 → 数据期月末日期 'YYYY-MM-DD'; 无法解析返回None"""
    if not tp:
        return None
    m = re.match(r'^(\d{1,2})月$', tp.strip())
    if m:
        mo = int(m.group(1))
    else:
        q = re.search(r'第?([一二三四1234])季度', tp)
        if not q:
            return None
        mo = _QMAP[q.group(1)] * 3
    y = pub_dt.year if mo <= pub_dt.month else pub_dt.year - 1
    if mo == 12:
        return '%d-12-31' % y
    return (datetime.date(y, mo + 1, 1) - datetime.timedelta(days=1)).isoformat()


def _f(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def _j10_wstr(s):
    b = s.encode('utf-8')
    return struct.pack('<H', len(b)) + b


def _j10_xor(buf, key):
    kb = key.encode('latin1')
    off = kb[0]
    n = len(kb)
    return bytes(b ^ kb[(i + off) % n] for i, b in enumerate(buf))


class _J10R:
    def __init__(self, buf):
        self.b = buf
        self.p = 0

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.p)[0]
        self.p += 4
        return v

    def i16(self):
        v = struct.unpack_from('<h', self.b, self.p)[0]
        self.p += 2
        return v

    def s(self):
        ln = struct.unpack_from('<H', self.b, self.p)[0]
        self.p += 2
        v = self.b[self.p:self.p + ln].decode('utf-8', 'ignore')
        self.p += ln
        return v


def fetch_j10(bjt_now, days_past=62, days_fwd=13):
    """金十WS日历: type0宏观数据(前值/预期/公布/星级) + type2大事, 北京时间
    需 JIN10_TOKEN (x-token cookie)。单连接批量查询, 限速友好。
    返回 (当日芯片条目, 中国宏观收割dict); WS历史窗口约当前月-2个月, 收割随每日运行滚动积累。"""
    import websocket, socket, base64, zlib
    tok = os.environ.get('JIN10_TOKEN')
    if not tok:
        for p in ('/mnt/agents/output/凭证与API档案/jin10_token.json',):
            if os.path.exists(p):
                tok = json.load(open(p, encoding='utf-8')).get('token')
                break
    if not tok:
        raise RuntimeError('无JIN10_TOKEN')

    _ga = socket.getaddrinfo
    socket.getaddrinfo = lambda h, pp, *a, **k: [x for x in _ga(h, pp, *a, **k) if x[0] == socket.AF_INET]
    ws, last_err = None, None
    for url in J10_WS_LIST:
        try:
            ws = websocket.create_connection(
                url, timeout=25,
                header=['Origin: https://rili.jin10.com',
                        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36',
                        'Cookie: x-token=' + tok])
            print('J10节点:', url)
            break
        except Exception as e:
            last_err = e
            print('J10节点失败', url, e)
    if ws is None:
        raise RuntimeError('金十WS全部节点不可达: %s' % last_err)
    try:
        hs = ws.recv()                      # 16字节密钥握手(明文)
        r0, i, s = struct.unpack_from('<III', hs, 0)
        key = '%d.%d' % (s, i)

        def send(b):
            ws.send_binary(_j10_xor(b, key))

        send(struct.pack('<h', 4002) + struct.pack('<i', J10_UID) + _j10_wstr('')
             + _j10_wstr('chrome') + struct.pack('<i', 0) + _j10_wstr('calendar'))

        # 等登录回执
        import time as _t
        end = _t.time() + 15
        login_ok = False
        while _t.time() < end and not login_ok:
            msg = ws.recv()
            if isinstance(msg, str):
                continue
            r = _J10R(_j10_xor(msg, key))
            if r.i16() == 4002:
                resp = r.s()
                login_ok = '"status":100' in resp
                if not login_ok:
                    raise RuntimeError('金十登录失败: ' + resp[:100])

        # 逐日请求 type0(数据)+type2(大事)
        dates = [(bjt_now + datetime.timedelta(days=k)).strftime('%Y-%m-%d')
                 for k in range(-days_past, days_fwd + 1)]
        reqid, pending = 100000, {}
        for d in dates:
            for rt in (0, 2):
                send(struct.pack('<h', 2006) + struct.pack('<I', rt) + _j10_wstr(d) + struct.pack('<I', reqid))
                pending[reqid] = (rt, d)
                reqid += 1
        results = {}
        end = _t.time() + 45
        while pending and _t.time() < end:
            try:
                msg = ws.recv()
            except Exception:
                break
            if isinstance(msg, str):
                continue
            r = _J10R(_j10_xor(msg, key))
            op = r.i16()
            if op == 1201:
                try:
                    ws.send('')
                except Exception:
                    pass
                continue
            if op != 2006:
                continue
            rt = r.u32(); date = r.s(); rid = r.u32(); js = r.s()
            lst = None
            data = json.loads(js).get('data')
            if data:
                rawz = base64.b64decode(data)
                try:
                    lst = json.loads(zlib.decompress(rawz))
                except zlib.error:
                    lst = json.loads(zlib.decompress(rawz, -15))
            results[pending.pop(rid, (rt, date))] = lst or []
    finally:
        try:
            ws.close()
        except Exception:
            pass

    # 整形
    items = []
    harvest = {}   # 入库键 → {name, unit, points: {期日: {ac,fc,pv,pub}}}
    for (rt, d), lst in results.items():
        for it in lst:
            if rt == 0:
                c = it.get('country') or ''
                star = it.get('star') or 0
                # —— 中国宏观收割(不受国家白名单/星级过滤影响) ——
                nm0 = it.get('indicator_name') or ''
                if c == '中国' and nm0 in J10_HARVEST:
                    pt0 = it.get('pub_time') or ''
                    try:
                        pub_dt = datetime.datetime.strptime(pt0[:16], '%Y-%m-%d %H:%M')
                    except ValueError:
                        pub_dt = None
                    pd = _j10_period_date(it.get('time_period') or '', pub_dt) if pub_dt else None
                    ac = _f(it.get('actual'))
                    if pd and ac is not None:
                        key, hname, hunit = J10_HARVEST[nm0]
                        h = harvest.setdefault(key, {'name': hname, 'unit': hunit, 'points': {}})
                        cur = h['points'].get(pd)
                        if cur is None or (it.get('pub_time') or '') > (cur.get('pub') or ''):
                            h['points'][pd] = {'ac': ac, 'fc': _f(it.get('consensus')),
                                               'pv': _f(it.get('previous')), 'pub': (it.get('pub_time') or '')[:10]}
                if c not in J10_KEEP_COUNTRY:
                    continue
                if star < 3 and not (c in ('美国', '中国') and star >= 2):
                    continue
                pt = it.get('pub_time') or it.get('actual_time') or ''
                try:
                    dt = datetime.datetime.strptime(pt[:16], '%Y-%m-%d %H:%M')
                    dd, tm = '%d/%d' % (dt.month, dt.day), '%02d:%02d' % (dt.hour, dt.minute)
                except ValueError:
                    dd, tm = '%d/%d' % (int(d[5:7]), int(d[8:10])), ''
                nm = it.get('indicator_name') or ''
                if c not in ('美国', '中国'):
                    nm = c + nm
                if it.get('time_period'):
                    nm = nm + '(' + it['time_period'] + ')'
                items.append({'d': dd, 'tm': tm, 'kind': 'data', 'star': star, 'name': nm,
                              'fc': it.get('consensus') or '', 'pv': it.get('previous') or '',
                              'ac': it.get('actual') or ''})
            else:
                star = it.get('star') or 0
                if star < 3:
                    continue
                et = it.get('event_time') or ''
                dd = '%d/%d' % (int(d[5:7]), int(d[8:10]))
                tm = et[11:16] if len(et) >= 16 and et[11:16] != '00:00' else ''
                nm = (it.get('event_content') or '').strip()
                if len(nm) > 34:
                    nm = nm[:33] + '…'
                items.append({'d': dd, 'tm': tm, 'kind': 'event', 'star': star, 'name': nm,
                              'fc': '', 'pv': '', 'ac': ''})
    # 排序+每日限量
    def _sk(e):
        mo, da = e['d'].split('/')
        return (int(mo), int(da), 0 if e['kind'] == 'data' else 1, e['tm'] or '99', -e['star'])
    items.sort(key=_sk)
    per, slim = {}, []
    for e in items:
        n = per.get(e['d'], 0)
        if n >= J10_MAX_PER_DAY:
            continue
        per[e['d']] = n + 1
        slim.append(e)
    return slim, harvest


# —— 东财日历过滤规则 ——
EM_URL = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_CPH_FECALENDAR'
          '&columns=START_DATE,END_DATE,FE_NAME,FE_TYPE,STD_TYPE_CODE,SPONSOR_NAME,CITY'
          '&sortColumns=START_DATE&sortTypes=1&pageSize=500'
          '&filter=(END_DATE>=%27{from}%27)(START_DATE<%27{to}%27)&source=WEB&client=WEB')
EM_KEEP_COUNTRY = ('中国', '美国', '欧元区', '日本', '英国', '加拿大', '澳大利亚', '德国', '法国', '瑞士', '欧盟')
EM_DROP_KW = [
    '引申需求', '燃料乙醇', '库欣', '精炼油', '车用汽油', '库存量:原油', 'EIA汽油', 'EIA精炼油',
    'DOE', '小麦', '棉花', '玉米', '大豆', '香港', '澳门', '台湾', '四周移动平均',
    '就业人数:政府', '全职', '兼职', '就业人口', '加拿大:15岁', '就业率',
    '平均每周制造业', '制造业平均小时工资', '新增非农私营', '新增就业人数:季调', '非农就业人数:季调',
    '累计同比', 'ISM:PMI:物价', 'ISM:PMI:产出', 'ISM:PMI:自有', 'ISM:PMI:就业',
    'ISM:PMI:供应商', 'ISM:PMI:新订单', '服务业PMI:物价', '服务业PMI:库存',
    '服务业PMI:就业', '服务业PMI:新订单', '服务业PMI:供应商', '出口金额:累计', '进出口金额:累计',
    '出口金额(报告期', '进口总额', 'PPI:全部工业品:累计',
    '库存:贸易矿', '库存:球团', '库存:精粉', '库存:块矿', '库存:电解铝',
    '边际贷款利率', '隔夜存款利率', '再融资利率',
    'PPI:环比:季调', 'PPI:最终需求', '核心PPI:非季调', 'PPI:季调:同比(报告期:2026年09月',
]
EM_KEEP_EVENT_TYPE = ('高峰论坛', '其他会议')  # 大事类(会议); 行业会议/其他 丢弃


def fetch_em(bjt_now):
    """东财财经日历: 未来14天, 返回 [{d,tm,name,kind}]"""
    d_from = bjt_now.strftime('%Y-%m-%d')
    d_to = (bjt_now + datetime.timedelta(days=14)).strftime('%Y-%m-%d')
    url = EM_URL.replace('{from}', d_from).replace('{to}', d_to)
    raw = fetch(url)
    rows = (json.loads(raw.decode('utf-8', 'ignore')).get('result') or {}).get('data') or []
    out = []
    for r in rows:
        name = (r.get('FE_NAME') or '').strip()
        ft = r.get('FE_TYPE')
        if not name:
            continue
        kind = None
        if ft == '经济数据':
            if not name.startswith(EM_KEEP_COUNTRY):
                continue
            if any(kw in name for kw in EM_DROP_KW):
                continue
            kind = 'data'
        elif ft in EM_KEEP_EVENT_TYPE:
            kind = 'event'
        elif ft is None and re.search(r'休市|假期|节\b', name):
            kind = 'holiday'
        if not kind:
            continue
        sd = r.get('START_DATE') or ''
        try:
            dt = datetime.datetime.strptime(sd[:16], '%Y-%m-%d %H:%M')
        except ValueError:
            continue
        # 名字精简: 去"(报告期:...)", 国家前缀后的冗余项保留
        nm = re.sub(r'\(报告期[:：][^)]*\)', '', name).strip()
        out.append({'d': '%d/%d' % (dt.month, dt.day),
                    'tm': '%02d:%02d' % (dt.hour, dt.minute) if dt.hour or dt.minute else '',
                    'name': nm, 'kind': kind})
    # 按日限量: 每日最多10条, 全天项(00:00)排后
    out.sort(key=lambda e: (int(e['d'].split('/')[0]), int(e['d'].split('/')[1]),
                            1 if not e['tm'] else 0, e['tm']))
    per_day = {}
    slim = []
    for e in out:
        n = per_day.get(e['d'], 0)
        if n >= 10:
            continue
        per_day[e['d']] = n + 1
        slim.append(e)
    return slim, len(rows)


def fetch(url):
    # FF有限速(429), 退避重试
    import time
    last = None
    for wait in (0, 20, 50):
        if wait:
            time.sleep(wait)
        try:
            from curl_cffi import requests as creq
            r = creq.Session(impersonate='chrome').get(url, timeout=25)
            if r.status_code == 200:
                return r.content
            last = 'HTTP %s' % r.status_code
        except Exception as e:
            last = str(e)
    import requests
    r = requests.get(url, timeout=25, headers={'User-Agent': 'Mozilla/5.0'})
    if r.status_code == 200:
        return r.content
    raise RuntimeError('FF周历抓取失败: %s / HTTP %s' % (last, r.status_code))


def to_bjt(date_s, time_s):
    # date: MM-DD-YYYY ; time: '9:30am' / '12:30pm' / 'All Day' / 'Tentative' (GMT)
    try:
        dt = datetime.datetime.strptime(date_s, '%m-%d-%Y')
    except ValueError:
        return None, ''
    m = re.match(r'^(\d{1,2}):(\d{2})(am|pm)$', (time_s or '').strip().lower())
    if not m:
        return dt, ''  # 全天/待定
    hh = int(m.group(1)) % 12 + (12 if m.group(3) == 'pm' else 0)
    dt = dt.replace(hour=hh, minute=int(m.group(2))) + datetime.timedelta(hours=8)
    return dt, '%d:%02d' % (dt.hour, dt.minute)


def fetch_ff():
    """FF周历: 本周 USD/CNY 高/中重要性, 带预期值"""
    raw = fetch(URL)
    root = ET.fromstring(raw.decode('windows-1252', 'ignore'))
    events = []
    for ev in root.findall('event'):
        g = lambda t: (ev.findtext(t) or '').strip()
        ccy, imp, title = g('country'), g('impact'), g('title')
        if ccy not in KEEP_CCY or imp not in KEEP_IMP:
            continue
        dt, hm = to_bjt(g('date'), g('time'))
        if dt is None:
            continue
        events.append({
            'd': '%d/%d' % (dt.month, dt.day),          # BJT日期, 如 9/4
            'tm': hm,                                    # BJT时刻, ''=全天/待定
            'ccy': ccy, 'imp': imp,
            'tcn': CN_MAP.get(title, ''), 'ten': title,
            'fc': g('forecast'), 'pv': g('previous'), 'ac': g('actual'),
        })
    events.sort(key=lambda e: (int(e['d'].split('/')[0]), int(e['d'].split('/')[1]),
                               e['tm'] or '99', 0 if e['imp'] == 'High' else 1))
    return events


def main():
    bjt_now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) + datetime.timedelta(hours=8)
    old = None
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding='utf-8'))
        except Exception:
            old = None

    ff_events, em_events, j10_items, fails = None, None, None, []
    j10_harvest = None
    try:
        j10_items, j10_harvest = fetch_j10(bjt_now)
        print('J10 %d条 收割%d键' % (len(j10_items), len(j10_harvest or {})))
    except Exception as e:
        print('J10_FAIL:', e); fails.append('j10')
    try:
        ff_events = fetch_ff()
    except Exception as e:
        print('FF_FAIL:', e); fails.append('ff')
    try:
        em_events, em_raw_n = fetch_em(bjt_now)
        print('EM原始%d条 → 过滤后%d条' % (em_raw_n, len(em_events)))
    except Exception as e:
        print('EM_FAIL:', e); fails.append('em')

    if ff_events is None and em_events is None and j10_items is None:
        if old:
            old['stale'] = True
            json.dump(old, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
            print('三源均失败,保留旧数据', old.get('asof'))
            return
        sys.exit(1)

    # 单源失败用旧文件的对应部分兜底
    if ff_events is None and old:
        ff_events = old.get('events', [])
    if em_events is None and old:
        em_events = old.get('em', [])
    if j10_items is None and old:
        j10_items = (old.get('j10') or {}).get('items', [])

    # —— 静态注入：FOMC官方会议日程（L1官方，提前一年公布）——
    # 抓取源只覆盖当周/未来14天，会议经常缺席；注入到 em 列表，保证共识表/关键日期/宏观日历三处永远在历。
    FOMC_BJT = [
        ('2026-09-17', '02:00'), ('2026-10-29', '02:00'), ('2026-12-10', '03:00'),
        ('2027-01-28', '03:00'), ('2027-03-18', '02:00'), ('2027-04-29', '02:00'),
        ('2027-06-17', '02:00'), ('2027-07-29', '02:00'), ('2027-09-16', '02:00'),
        ('2027-10-28', '02:00'), ('2027-12-08', '03:00'),
    ]
    try:
        if em_events is None:
            em_events = []
        if ff_events is None:
            ff_events = []
        _now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        for iso, tm in FOMC_BJT:
            dt = datetime.date.fromisoformat(iso)
            if abs((dt - _now.date()).days) > 180:
                continue
            tag = '%d/%d' % (dt.month, dt.day)
            hh, mm = int(tm[:2]), int(tm[3:])
            tm2 = '%02d:%02d' % (hh, mm + 30)
            if not any(x.get('d') == tag and ('FOMC' in str(x.get('name', '')) or '利率决议' in str(x.get('name', ''))) for x in em_events):
                em_events.append({'d': tag, 'tm': tm, 'name': '美联储FOMC利率决议+声明 · FOMC Statement', 'kind': 'event', 'src': 'L1·美联储官方日程'})
                em_events.append({'d': tag, 'tm': tm2, 'name': '美联储主席记者会 · FOMC Press Conference', 'kind': 'event', 'src': 'L1·美联储官方日程'})
            if not any(x.get('d') == tag and ('FOMC' in str(x.get('tcn', '')) + str(x.get('ten', ''))) for x in ff_events):
                ff_events.append({'d': tag, 'tm': tm, 'ccy': 'USD', 'imp': 'High',
                                  'tcn': '美联储FOMC利率决议+声明', 'ten': 'FOMC Statement', 'fc': '', 'pv': '', 'ac': ''})
                ff_events.append({'d': tag, 'tm': tm2, 'ccy': 'USD', 'imp': 'Medium',
                                  'tcn': '美联储主席记者会', 'ten': 'FOMC Press Conference', 'fc': '', 'pv': '', 'ac': ''})
        em_events.sort(key=lambda x: (tuple(int(p) for p in x.get('d', '0/0').split('/')), x.get('tm', '')))
        ff_events.sort(key=lambda x: (tuple(int(p) for p in str(x.get('d', '0/0')).split('/')), x.get('tm', '')))
    except Exception as e:
        print('FOMC_INJECT_FAIL:', e)

    # —— 金十收割积累: j10_store.json → chart_series.js + macro_catalog.js ——
    if j10_harvest:
        try:
            store_p = os.path.join(APP, 'data', 'j10_store.json')
            store = {}
            if os.path.exists(store_p):
                store = json.load(open(store_p, encoding='utf-8'))
            for key, h in j10_harvest.items():
                s = store.setdefault(key, {'name': h['name'], 'unit': h['unit'], 'points': {}})
                s['points'].update(h['points'])
            json.dump(store, open(store_p, 'w', encoding='utf-8'), ensure_ascii=False)
            # 并入图表墙
            cs_p = os.path.join(APP, 'data', 'chart_series.js')
            cat_p = os.path.join(APP, 'data', 'macro_catalog.js')
            raw = open(cs_p, encoding='utf-8').read()
            m = re.search(r'window\.CHART_SERIES\s*=\s*(\{.*\})\s*;?\s*$', raw, re.S)
            cs = json.loads(m.group(1))
            raw = open(cat_p, encoding='utf-8').read()
            mc = re.search(r'window\.MACRO_CATALOG\s*=\s*(\[.*\])\s*;?\s*$', raw, re.S)
            cat = json.loads(mc.group(1))
            cat_ids = {c['id'] for c in cat}
            for key, s in store.items():
                pts = s.get('points') or {}
                ser = [[d, pts[d]['ac']] for d in sorted(pts) if pts[d].get('ac') is not None]
                if not ser:
                    continue
                cs[key] = ser
                if key not in cat_ids:
                    cat.append({'id': key, 'name': s['name'], 'unit': s['unit']})
                    cat_ids.add(key)
            open(cs_p + '.tmp', 'w', encoding='utf-8').write(
                'window.CHART_SERIES = ' + json.dumps(cs, ensure_ascii=False, separators=(',', ':')) + ';')
            os.replace(cs_p + '.tmp', cs_p)
            open(cat_p + '.tmp', 'w', encoding='utf-8').write(
                'window.MACRO_CATALOG = ' + json.dumps(cat, ensure_ascii=False, separators=(',', ':')) + ';')
            os.replace(cat_p + '.tmp', cat_p)
            print('J10积累库: %d键入图表墙' % sum(1 for k in store if store[k].get('points')))
        except Exception as e:
            print('J10_STORE_FAIL:', e)

    out = {
        'asof': bjt_now.strftime('%Y-%m-%d %H:%M BJT'),
        'src': 'L2·财经日历快照(多源汇编,底层官方预告)',
        'note': '金十覆盖T-2至T+13(含预期/前值/公布/星级); FF覆盖本周; 东财覆盖未来14天; 时间均为北京时间',
        'events': ff_events or [],
        'em': em_events or [],
        'j10': {'asof': bjt_now.strftime('%Y-%m-%d %H:%M BJT'), 'items': j10_items or []},
    }
    if fails:
        out['partial'] = fails
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)

    # 同步生成页面顶部宏观日历使用的 econ_calendar.json。
    # 之前只提交 calendar_consensus.json，导致页面日历停留在旧日期。
    try:
        base = bjt_now.date()
        week_start = base - datetime.timedelta(days=base.weekday())
        week_end = week_start + datetime.timedelta(days=6)
        next_end = week_end + datetime.timedelta(days=7)
        default_grp = '下周' if base.weekday() == 6 else '本周'
        weeks = ['一', '二', '三', '四', '五', '六', '日']
        imp_star = {'High': 4, 'Medium': 3, 'Low': 2, 'Holiday': 0}

        def parse_day(d):
            m, d2 = map(int, d.split('/'))
            dt = datetime.date(base.year, m, d2)
            if (dt - base).days > 180:
                dt = datetime.date(base.year - 1, m, d2)
            if (base - dt).days > 180:
                dt = datetime.date(base.year + 1, m, d2)
            return dt

        def norm(x):
            return None if x in (None, '') else str(x)

        bucket = {}
        def add(dt, tm, name, star, ac=None, fc=None, pv=None):
            # 同源事件经 events/em 双通道进入时去重，保留最高星级
            lst = bucket.setdefault(dt, [])
            for i, x in enumerate(lst):
                if x[0] == (tm or '') and x[1] == name:
                    if (star or 0) > (x[2] or 0):
                        lst[i] = (tm or '', name, star, ac, fc, pv)
                    return
            lst.append((tm or '', name, star, ac, fc, pv))

        for e in out.get('events', []):
            try:
                dt = parse_day(e.get('d', ''))
            except Exception:
                continue
            name = e.get('tcn') or e.get('ten') or ''
            if not name:
                continue
            if e.get('ten') and e.get('tcn') and e.get('ten') != e.get('tcn'):
                name += ' · ' + e['ten']
            add(dt, e.get('tm', ''), name, imp_star.get(e.get('imp'), 1), norm(e.get('ac')), norm(e.get('fc')), norm(e.get('pv')))
        for e in out.get('em', []):
            try:
                dt = parse_day(e.get('d', ''))
            except Exception:
                continue
            if e.get('name'):
                star = 1
                if 'FOMC' in e['name'] or '利率决议' in e['name']:
                    star = 5 if '声明' in e['name'] or 'Statement' in e['name'] else 4
                add(dt, e.get('tm', ''), e['name'], star)

        # —— 静态注入：FOMC官方会议日程（美联储提前一年公布，L1官方）——
        # 抓取源只覆盖当周/未来14天，会议经常缺席；官方日程固定，直接注入确保永远在历。
        # 声明=会议第二日14:00 ET → 北京时间次日02:00(夏令)/03:00(冬令)；记者会+30分钟。
        FOMC_BJT = [
            ('2026-09-17', '02:00'), ('2026-10-29', '02:00'), ('2026-12-10', '03:00'),
            ('2027-01-28', '03:00'), ('2027-03-18', '02:00'), ('2027-04-29', '02:00'),
            ('2027-06-17', '02:00'), ('2027-07-29', '02:00'), ('2027-09-16', '02:00'),
            ('2027-10-28', '02:00'), ('2027-12-08', '03:00'),
        ]
        for iso, tm in FOMC_BJT:
            try:
                dt = datetime.date.fromisoformat(iso)
            except Exception:
                continue
            if abs((dt - base).days) > 180:
                continue
            names = ' '.join(str(x[1]) for x in bucket.get(dt, []))
            if 'FOMC' in names or '联邦基金利率' in names or '利率决议' in names:
                continue
            add(dt, tm, '美联储FOMC利率决议+声明 · FOMC Statement', 5)
            hh, mm = int(tm[:2]), int(tm[3:])
            add(dt, '%02d:%02d' % (hh, mm + 30), '美联储主席记者会 · FOMC Press Conference', 4)

        days = []
        for dt in sorted(bucket):
            grp = '本周' if week_start <= dt <= week_end else ('下周' if week_end < dt <= next_end else '关键节点')
            evs = sorted(bucket[dt], key=lambda x: (x[0] or '99:99', -(x[2] or 0), x[1]))
            days.append({'date': '%d/%d 周%s' % (dt.month, dt.day, weeks[dt.weekday()]), 'grp': grp, 'events': [list(x) for x in evs]})
        if default_grp == '下周':
            order = {'下周': 0, '本周': 1, '关键节点': 2}
        else:
            order = {'本周': 0, '下周': 1, '关键节点': 2}
        days.sort(key=lambda x: (order.get(x['grp'], 9), parse_day(x['date'].split()[0])))
        econ = {
            'updated': bjt_now.strftime('%Y-%m-%d'),
            'default_grp': default_grp,
            'src': 'L2·财经日历快照（由 calendar_consensus.json 同步生成；底层官方预告/财经数据商汇编）',
            'tz': '北京时间',
            'rule': '周日自动默认显示下周，其他日期默认显示本周；本周/下周/关键节点可手动切换；每卡仅显星级最高的1条，其余折叠进「其他+N」；公布值红/绿，预期金，前值灰',
            'days': days,
        }
        json.dump(econ, open(ECON_OUT, 'w', encoding='utf-8'), ensure_ascii=False)
        print('ECON_CAL_SYNC:', ECON_OUT, len(days), 'days')
    except Exception as e:
        print('ECON_CAL_SYNC_FAIL:', e)
    hi = [e for e in out['events'] if e.get('imp') == 'High']
    print('OK J10 %d条 + FF %d条(High %d) + EM %d条 截至%s' % (len(out['j10']['items']), len(out['events']), len(hi), len(out['em']), out['asof']))
    for e in hi:
        print(' ', e['d'], e['tm'], e['ccy'], e['tcn'] or e['ten'], '| 预期', e['fc'], '前值', e['pv'], '实际', e['ac'])


if __name__ == '__main__':
    main()
