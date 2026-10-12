# -*- coding: utf-8 -*-
"""热度量化观测池（2026-10-12 建，同日 v2 扩容改版）
数据源：①星球分类面板 zsxq_panel.json（by_comm 全量，readers/full/points 现成）
        ②星球实时流 zsxq_metals.json（补新鲜度，无计数）
        ③星球全量存档 前沿信息收录_deep.jsonl（全史帖，readers/comments/likes 现成；
          按文件 mtime 缓存 data/_archive_metals.json，存档更新才重扫）
        ④weread 公众号观察名单（8 号，每号取最近 100 条→每品种选 30；
          列表验证失效自动 verify 重试，cookie 失效才需重新扫码：weread.mjs login）
规则：候选=星球近180天（面板+存档+实时）+公众号每品种30条，均须真提该品种
      （ALIASES 相关性过滤 + EXCLUDE 地名排除：锡≠无锡/锡婚/锡剧）→ 去重后 ≤150 条
      热度分=阅读+3×评论+2×点赞（面板无评论按0、实时无计数按0）
      方向=句级归属（v2 核心修复）：只数提到该品种的句子的多空词（否定护栏+PRED/FACT 门控），
      帖级净分>0=看多票/<0=看空/=0=中性；窗口90天；rel=品种看多占比−全场基线（同口径重计），
      贝叶斯收缩 k=10，小样本向基线收敛不产生极端假信号
      观点要点=近60天高热度帖中「提到该品种的实质句」（纪要套话已滤），带（MM-DD）日期前缀
产出：site/data/heat_pool.json（含 60 日历史，供日报 10 节渲染热度趋势）
用法：python _heat_pool.py
"""
import os, re, sys, json, subprocess, datetime, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
OUT = os.path.join(DATA, 'heat_pool.json')
ZSXQ_PANEL = r'D:\Kimi\金属总网\网站构建\小作文平台\知识星球\panel\data\zsxq_panel.json'
ZSXQ_RT = r'D:\Kimi\金属总网\网站构建\小作文平台\知识星球\data\zsxq_metals.json'
ZSXQ_ARCHIVE = r'D:\Kimi\金属总网\_本地便利层\知识星球爬取\前沿信息收录_deep.jsonl'
ARCH_CACHE = os.path.join(DATA, '_archive_metals.json')
WEREAD = os.path.expanduser(r'~\.agents\skills\weread-skill\scripts\weread.mjs')
WR_ACCOUNTS = os.path.join(DATA, 'wr_accounts.json')

METALS = [('cu', '铜'), ('al', '铝'), ('zn', '锌'), ('pb', '铅'), ('ni', '镍'), ('sn', '锡')]
TOP_N = 10
CAND_N = 150
HIST_DAYS = 60
POOL_DAYS = 180        # 星球候选窗口
DIR_DAYS = 90          # 方向投票窗口
WX_PER_ACC = 100       # 每公众号取最近 N 条
WX_PER_METAL = 30      # 每品种选 30
DIR_PRIOR_K = 10       # 方向 rel 贝叶斯收缩强度（先验=全场基线）

# 相关性过滤：上游 by_comm 是全文匹配会串桶；候选/方向都必须真提该品种
ALIASES = {'cu': ('铜',), 'al': ('铝',), 'zn': ('锌',), 'pb': ('铅',),
           'ni': ('镍', 'NPI', '镍铁'), 'sn': ('锡',)}
# 误命中词先剔除再匹配（锡→无锡市地名是实测最大噪音源：
# 银行帖"无锡滨湖兴福村行"、两轮车帖"同在无锡"都被归进锡桶判了看多）
EXCLUDE = {'sn': ('无锡', '锡婚', '锡剧'), 'cu': (), 'al': (), 'zn': (), 'pb': (), 'ni': ()}

# 方向词表（与 _zsxq_classify.py 同版；句级归属时只作用于提到该品种的句子）
BULL_KW = ["看多", "看好", "做多", "上涨", "走高", "走强", "反弹", "突破", "牛市", "新高",
           "利好", "超预期", "去库", "缺货", "紧张", "紧缺", "减产", "停产", "检修", "收储",
           "逼仓", "补库", "升水"]
BEAR_KW = ["看空", "做空", "看跌", "下跌", "走低", "走弱", "回落", "回调", "新低",
           "利空", "累库", "过剩", "复产", "增产", "贴水", "承压", "弱势", "抛售", "悲观"]
PRED_KW = ["将", "预计", "有望", "建议", "关注", "目标", "空间", "值得", "警惕", "维持",
           "上调", "下调", "配置", "机会", "拐点", "后市", "展望", "判断", "认为", "倾向",
           "推荐", "继续看好", "继续看空"]
FACT_KW = ["昨日", "今日", "收涨", "收跌", "截至", "同比", "环比", "数据显示", "公布",
           "收盘", "报价", "现报"]
SENT_SPLIT = re.compile(r'[。！？!?\n]+')

def log(*a):
    print(*a, flush=True)

def load_json(p, default=None):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def relevant(cc, title, extra=''):
    txt = (title or '') + ' ' + (extra or '')
    for ex in EXCLUDE.get(cc) or ():
        txt = txt.replace(ex, '')
    return any(a in txt for a in ALIASES[cc])

# 观点要点抽取：纪要套话/元信息句不进 viewpoints（"欢迎参考/总结如下"类噪音实测混入）
BOILER = ('欢迎参考', '总结如下', '会议时间', '参与人', '仅供参考', '风险提示', '免责声明',
          '来源：', '来源:', '提问环节', '纪要', '交流环节', '主持人', '参会', '报名方式',
          '扫描二维码', '添加微信', '进群')

def metal_snips(text, cc, limit=2):
    """从正文抽提到该品种的实质句（滤套话），每条 ≤108 字"""
    t = text or ''
    for ex in EXCLUDE.get(cc) or ():
        t = t.replace(ex, '')
    out = []
    for sent in SENT_SPLIT.split(t):
        sent = sent.strip().strip('，,、：:　 ')
        if not 20 <= len(sent) <= 300:
            continue
        if not any(a in sent for a in ALIASES[cc]):
            continue
        if any(bp in sent for bp in BOILER):
            continue
        out.append(sent[:108])
        if len(out) >= limit:
            break
    return out

def dir_vote(text, cc):
    """句级归属方向：只数提到该品种的句子；返回 'bull'/'bear'/'neutral'/None（无表态）"""
    t = text or ''
    for ex in EXCLUDE.get(cc) or ():
        t = t.replace(ex, '')
    b = s = 0
    touched = False
    for sent in SENT_SPLIT.split(t):
        if not any(a in sent for a in ALIASES[cc]):
            continue
        sb = sum(sent.count(k) for k in BULL_KW)
        ss = sum(sent.count(k) for k in BEAR_KW)
        if not sb and not ss:
            continue
        for neg in ('不看好', '不看多', '难超预期'):
            sb -= sent.count(neg)
        has_pred = any(k in sent for k in PRED_KW)
        if not has_pred and any(k in sent for k in FACT_KW):
            continue
        b += sb
        s += ss
        touched = True
    if not touched:
        return None
    return 'bull' if b - s > 0 else ('bear' if b - s < 0 else 'neutral')

# ---------- weread 公众号 ----------
def weread_mp(book_id, pages=6):
    """拉某公众号近期文章（read_count/like_count）；返回 (rows, err_tag)，tag: ''/'verify'/'err'"""
    if not os.path.exists(WEREAD):
        return [], 'err'
    out = os.path.join(tempfile.gettempdir(), 'wr_mp_%s.jsonl' % book_id)
    try:
        p = subprocess.run(['node', WEREAD, 'mp', '--book-id', book_id, '--pages', str(pages),
                            '--out', out], capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            tail = ((p.stderr or '') + (p.stdout or '')).strip().splitlines()
            blob = '\n'.join(tail)
            log('[weread] %s 降级: %s' % (book_id, tail[-1][:80] if tail else 'rc=%d' % p.returncode))
            return [], ('verify' if 'verification_required' in blob else 'err')
        rows = []
        with open(out, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '"title"' not in line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        return rows, ''
    except Exception as e:
        log('[weread] %s 异常: %s' % (book_id, e))
        return [], 'err'
    finally:
        try:
            os.remove(out)
        except Exception:
            pass

def weread_verify(book_id):
    """列表验证状态失效时自动重过（chrome-profile 在通常无人值守即过，可能短暂弹窗）"""
    try:
        p = subprocess.run(['node', WEREAD, 'verify', '--book-id', book_id],
                           capture_output=True, text=True, timeout=300)
        ok = '"ok":true' in (p.stdout or '')
        log('[weread] 自动 verify %s' % ('成功' if ok else '失败'))
        return ok
    except Exception as e:
        log('[weread] 自动 verify 异常: %s' % e)
        return False

def wx_articles():
    """每号取最近 WX_PER_ACC 条 → 标题相关性匹配 → 每品种热度降序选 WX_PER_METAL"""
    accs = (load_json(WR_ACCOUNTS) or {}).get('accounts') or []
    per_acc = []

    def harvest(acc):
        rows, tag = weread_mp(acc['book_id'])
        arts = {}
        for r in rows:
            try:
                ts = datetime.datetime.fromisoformat((r.get('publish_at') or '').replace('Z', '+00:00'))
            except Exception:
                continue
            title = (r.get('title') or '').strip()
            if not title:
                continue
            url = r.get('canonical_url') or r.get('source_url', '')
            arts[url or title] = {
                'title': title[:60], 'url': url, 'date': ts.date().isoformat(),
                'reads': r.get('read_count') or 0, 'likes': r.get('like_count') or 0,
                'src': '公众号·' + (r.get('account_name') or acc['name'])}
        return sorted(arts.values(), key=lambda x: x['date'], reverse=True)[:WX_PER_ACC], tag

    retry = []
    for acc in accs:
        arts, tag = harvest(acc)
        if tag == 'verify':
            retry.append(acc)
        else:
            per_acc.append(arts)
    if retry:
        log('[weread] %d 个号验证失效，自动重过 verify 后重试' % len(retry))
        if weread_verify(retry[0]['book_id']):
            for acc in retry:
                arts, _tag = harvest(acc)
                per_acc.append(arts)
    out = {sym: [] for sym, _ in METALS}
    n_all = 0
    for arts in per_acc:
        n_all += len(arts)
        for a in arts:
            for sym, _name in METALS:
                if relevant(sym, a['title']):
                    out[sym].append(dict(a, heat=a['reads'] + 2 * a['likes'],
                                         snips=[a['title']] if len(a['title']) >= 15 else [],
                                         points=[], pdf=[]))
    for sym in out:
        out[sym] = sorted(out[sym], key=lambda x: (-x['heat'], x['date']),
                          reverse=False)[:WX_PER_METAL]
        out[sym].sort(key=lambda x: -x['heat'])
    log('weread: %d 篇/号内%d条（%d 个号）→ 各品种选 %d' % (
        n_all, WX_PER_ACC, len(accs), WX_PER_METAL))
    return out

# ---------- 星球全量存档（mtime 缓存） ----------
def archive_scan():
    """扫全量存档 → {cc: {'cands': [...], 'votes': [{'d','v'}]}}；存档 mtime 不变直接用缓存"""
    if not os.path.exists(ZSXQ_ARCHIVE):
        return {}
    mt = os.path.getmtime(ZSXQ_ARCHIVE)
    cache = load_json(ARCH_CACHE) or {}
    if cache.get('mtime') == mt and cache.get('ver') == 2 and cache.get('metals'):
        log('archive: 用缓存（%s）' % datetime.datetime.fromtimestamp(mt).strftime('%F %T'))
        return cache['metals']
    metals = {cc: {'cands': [], 'votes': []} for cc, _ in METALS}
    n = 0
    with open(ZSXQ_ARCHIVE, encoding='utf-8') as f:
        for line in f:
            if '"content"' not in line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            n += 1
            title = t.get('title') or ''
            content = t.get('content') or ''
            counts = t.get('counts') or {}
            date = (t.get('create_time') or '')[:10]
            url = 'https://wx.zsxq.com/topic/%s' % (t.get('topic_id') or '')
            for cc, _name in METALS:
                if not relevant(cc, title, content):
                    continue
                r = counts.get('readers') or 0
                cm = counts.get('comments') or 0
                lk = counts.get('likes') or 0
                metals[cc]['cands'].append({
                    'title': (title or content[:40]).replace('\n', ' ')[:60],
                    'url': url, 'reads': r, 'comments': cm, 'likes': lk,
                    'src': '星球·存档', 'date': date,
                    'heat': r + 3 * cm + 2 * lk,
                    'snips': metal_snips(title + '\n' + content, cc),
                    'points': [], 'pdf': []})
                v = dir_vote(title + '\n' + content, cc)
                if v:
                    metals[cc]['votes'].append({'d': date, 'v': v})
    try:
        with open(ARCH_CACHE, 'w', encoding='utf-8') as f:
            json.dump({'mtime': mt, 'ver': 2, 'metals': metals}, f, ensure_ascii=False)
    except Exception as e:
        log('!! archive 缓存写失败: %s' % e)
    log('archive: 扫描 %d 帖 → %s' % (
        n, '，'.join('%s %d帖/%d票' % (nm, len(metals[cc]['cands']), len(metals[cc]['votes']))
                     for cc, nm in METALS)))
    return metals

# ---------- 品种池构建 ----------
def build_metal(cc, name, panel, rt, wx, arch, today):
    cutoff_pool = (today - datetime.timedelta(days=POOL_DAYS)).isoformat()
    cutoff_dir = (today - datetime.timedelta(days=DIR_DAYS)).isoformat()
    cands = []
    seen = set()

    def push(c):
        u = c.get('url') or c['title']
        if u in seen:
            return
        seen.add(u)
        cands.append(c)

    for it in (panel.get('by_comm', {}).get(cc) or []):
        pts_all = (it.get('points') or []) + ((it.get('pdf_digest') or {}).get('points') or [])
        if not relevant(cc, it.get('title'), ' '.join(pts_all)):
            continue
        readers = it.get('readers') or 0
        push({'title': (it.get('title') or '').replace('\n', ' ')[:60],
              'url': it.get('url', ''), 'reads': readers, 'comments': 0, 'likes': 0,
              'src': '星球', 'date': it.get('date', ''), 'heat': readers,
              'snips': metal_snips((it.get('title') or '') + '\n' + (it.get('full') or ''), cc),
              'points': it.get('points') or [],
              'pdf': ((it.get('pdf_digest') or {}).get('points') or [])})
    for c in (arch.get(cc) or {}).get('cands', []):
        if c['date'] >= cutoff_pool:
            push(c)
    for it in (rt.get('by_comm', {}).get(cc) or []):  # 实时流补新鲜度
        if not relevant(cc, it.get('title'), it.get('summary')):
            continue
        push({'title': (it.get('title') or '').replace('\n', ' ')[:60],
              'url': it.get('url', ''), 'reads': 0, 'comments': 0, 'likes': 0,
              'src': '星球·实时', 'date': it.get('date', ''), 'heat': 0,
              'snips': metal_snips((it.get('title') or '') + '\n' + (it.get('summary') or ''), cc),
              'points': [it.get('summary') or ''], 'pdf': []})
    for c in (wx.get(cc) or []):
        push(c)
    cands.sort(key=lambda x: (-x['heat'], x['date']), )
    cands = cands[:CAND_N]
    top = sorted(cands, key=lambda x: -x['heat'])[:TOP_N]
    # 观点要点：近 60 天候选按热度取帖，抽「提到该品种的实质句」（套话已滤），带日期前缀；
    # 60 天内无实质句才回退全池（防老帖霸占观点位）
    cutoff_vp = (today - datetime.timedelta(days=60)).isoformat()
    pts = []
    seen_vp = set()
    for c in [c for c in cands if c['date'] >= cutoff_vp] or cands:
        for s_ in (c.get('snips') or []):
            if s_[:30] in seen_vp:
                continue
            seen_vp.add(s_[:30])
            pts.append('（%s）%s' % (c['date'][5:], s_))
            if len(pts) >= 4:
                break
        if len(pts) >= 4:
            break
    # 方向：句级归属投票（存档 votes + 面板 full 逐帖现场打分），90 天窗口
    votes = [v['v'] for v in (arch.get(cc) or {}).get('votes', []) if v['d'] >= cutoff_dir]
    for it in (panel.get('by_comm', {}).get(cc) or []):
        if it.get('date', '') < cutoff_dir or not it.get('full'):
            continue
        v = dir_vote((it.get('title') or '') + '\n' + it['full'], cc)
        if v:
            votes.append(v)
    bull = sum(1 for v in votes if v == 'bull')
    bear = sum(1 for v in votes if v == 'bear')
    neu = sum(1 for v in votes if v == 'neutral')
    dates = [c['date'] for c in cands if c['date']]
    return {'sym': cc, 'name': name, 'n_cand': len(cands),
            'n_wx': len(wx.get(cc) or []),
            'n_archive': len((arch.get(cc) or {}).get('cands', [])),
            'heat': sum(c['heat'] for c in cands),
            'comments': sum(c.get('comments') or 0 for c in cands),
            'top10_mean': round(sum(c['reads'] for c in top) / max(1, len(top))),
            'span': '%s~%s' % (min(dates), max(dates)) if dates else '—',
            'top10': [{k: c[k] for k in ('title', 'url', 'reads', 'src', 'date')} for c in top],
            'viewpoints': pts, 'bull': bull, 'bear': bear, 'neutral': neu, 'rel': None}

def main():
    panel = load_json(ZSXQ_PANEL) or {}
    if not panel.get('by_comm'):
        log('!! zsxq_panel.json 不可用，中止')
        sys.exit(1)
    rt = load_json(ZSXQ_RT) or {}
    arch = archive_scan()
    wx = wx_articles()
    today = datetime.date.today()
    old = load_json(OUT) or {}
    hist = old.get('history') or {}
    metals = {}
    for cc, name in METALS:
        metals[cc] = build_metal(cc, name, panel, rt, wx, arch, today)
    # 基线同口径重计：分品种票数已是句级归属干净票，基线用同一池子重算
    g_b = sum(m['bull'] for m in metals.values())
    g_t = sum(m['bull'] + m['bear'] + m['neutral'] for m in metals.values())
    g2 = g_b / g_t if g_t >= 10 else (panel.get('dir_global_share') or 0.89)
    today_s = today.isoformat()
    for cc, name in METALS:
        m = metals[cc]
        h = [x for x in (hist.get(cc) or []) if x['d'] < today_s][-7:]
        avg7 = sum(x['heat'] for x in h) / len(h) if h else 0
        m['heat7_avg'] = round(avg7)
        m['trend'] = '↑' if avg7 and m['heat'] > avg7 * 1.15 else (
            '↓' if avg7 and m['heat'] < avg7 * 0.85 else '→')
        tot = m['bull'] + m['bear'] + m['neutral']
        adj = (m['bull'] + DIR_PRIOR_K * g2) / (tot + DIR_PRIOR_K)
        m['rel'] = round((adj - g2) * 100, 1) if tot else None
        log('%s: 候选 %d（公众号 %d/存档 %d）热度 %d·评论 %d（7日均 %.0f %s）区间 %s 方向 %d多/%d空/%d中 rel %s' % (
            name, m['n_cand'], m['n_wx'], m.get('n_archive') or 0, m['heat'],
            m.get('comments') or 0, avg7, m['trend'], m['span'],
            m['bull'], m['bear'], m['neutral'],
            '%+.1fpp' % m['rel'] if m['rel'] is not None else '—'))
        hist.setdefault(cc, []).append({'d': today_s, 'heat': m['heat'],
                                        'bull': m['bull'], 'bear': m['bear']})
        hist[cc] = hist[cc][-HIST_DAYS:]
    out = {'date': today_s, 'panel_asof': panel.get('updated_at', ''),
           'global_share': round(g2, 3), 'metals': metals, 'history': hist}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log('->', OUT)

if __name__ == '__main__':
    main()
