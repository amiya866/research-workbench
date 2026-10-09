# -*- coding: utf-8 -*-
"""知识星球面板 → 整合站「外资研报观点」数据桥。
读 zsxq-panel 的分类数据（方向雷达 + PDF 要点），抽出宏观/美债/金银部分，
PDF 拷本地供下载。产物：data/zsxq_radar.json + data/zsxq_pdfs/*.pdf
源：D:\\Kimi\\金属总网\\网站构建\\小作文平台\\知识星球\\panel\\data\\zsxq_panel.json
"""
import json, os, shutil, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = r'D:\Kimi\金属总网\网站构建\小作文平台\知识星球'
PANEL_JSON = os.path.join(PANEL, 'panel', 'data', 'zsxq_panel.json')
PANEL_PDFS = os.path.join(PANEL, 'panel', 'data', 'pdfs')
ARCHIVE_PDFS = r'D:\Kimi\金属总网\_本地便利层\知识星球爬取\pdfs'
DIGEST_CACHE = os.path.join(PANEL, '_pdf_digest_cache.json')
OUT = os.path.join(BASE, 'data', 'zsxq_radar.json')
OUT_PDFS = os.path.join(BASE, 'data', 'zsxq_pdfs')

GOLD_KW = ['黄金', '白银', '金价', '银价', '贵金属', 'gold', 'silver', 'XAU', 'XAG']
PDF_MAX = 15
PDF_MAX_BYTES = 8 * 1024 * 1024


def hit(text, kws):
    t = (text or '').lower()
    return any(k.lower() in t for k in kws)


def main():
    d = json.load(open(PANEL_JSON, encoding='utf-8'))
    cache = json.load(open(DIGEST_CACHE, encoding='utf-8')) if os.path.exists(DIGEST_CACHE) else {}
    # fid → 本地 PDF 真身：优先面板嵌入目录，回退爬取存档（{fid}_{name}.pdf）
    fid2pdf = {}
    for fid in cache:
        p = os.path.join(PANEL_PDFS, fid + '.pdf')
        if os.path.exists(p):
            fid2pdf[fid] = p
            continue
        for f in os.listdir(ARCHIVE_PDFS) if os.path.isdir(ARCHIVE_PDFS) else []:
            if f.startswith(fid + '_'):
                fid2pdf[fid] = os.path.join(ARCHIVE_PDFS, f)
                break
    name2fid = {v.get('name'): fid for fid, v in cache.items() if v.get('name')}

    direction = d.get('direction', {})

    def bucket(key, label):
        b = direction.get(key) or {}
        return {'key': key, 'label': label,
                'bull': b.get('bull', 0), 'bear': b.get('bear', 0), 'neutral': b.get('neutral', 0),
                'items': b.get('items', [])[:12]}

    buckets = [bucket('macro', '宏观'), bucket('eq_美债', '美债')]

    # 金银：全桶方向条目关键词扫描聚合成虚拟桶 + 分类标题命中帖
    g_bull = g_bear = g_neu = 0
    gold_posts, seen = [], set()
    for key, b in direction.items():
        for it in (b.get('items') or []):
            if hit(it.get('title', ''), GOLD_KW):
                dv = it.get('dir')
                if dv == '看多': g_bull += 1
                elif dv == '看空': g_bear += 1
                else: g_neu += 1
                if it.get('url') not in seen:
                    seen.add(it.get('url'))
                    gold_posts.append({'date': it.get('date'), 'title': it.get('title'),
                                       'dir': dv, 'url': it.get('url'),
                                       'readers': it.get('readers'), 'src': '方向雷达·' + key})
    for cat, items in d['categories'].items():
        for it in items:
            if hit(it.get('title', ''), GOLD_KW) and it.get('url') not in seen:
                seen.add(it.get('url'))
                gold_posts.append({'date': it.get('date'), 'title': it.get('title'),
                                   'dir': None, 'url': it.get('url'),
                                   'readers': it.get('readers'), 'src': cat})
    gold_posts.sort(key=lambda x: (x.get('date') or ''), reverse=True)
    gold_posts = gold_posts[:15]
    buckets.append({'key': 'gold', 'label': '金银', 'bull': g_bull, 'bear': g_bear,
                    'neutral': g_neu, 'items': []})

    # PDF 精选：研报纪要 高质量 + 有PDF要点（该类别天然是外资研报/大行日报）
    os.makedirs(OUT_PDFS, exist_ok=True)
    pdfs = []
    for cat in ('研报纪要', '宏观外汇'):
        for it in d['categories'].get(cat, []):
            pdg = it.get('pdf_digest') or {}
            pts = pdg.get('pts') or []
            if it.get('quality') != '高' or not pts:
                continue
            text = it.get('title', '') + ' ' + ' '.join(pts)
            tags = ([t for t, kws in (('金银', GOLD_KW),) if hit(text, kws)]
                    + (['宏观'] if cat == '宏观外汇' else []))
            href = None
            fid = name2fid.get(pdg.get('name'))
            if fid and fid in fid2pdf:
                srcf = fid2pdf[fid]
                if os.path.getsize(srcf) <= PDF_MAX_BYTES:
                    dst = os.path.join(OUT_PDFS, fid + '.pdf')
                    if not os.path.exists(dst):
                        shutil.copy2(srcf, dst)
                    href = 'zsxq_pdfs/%s.pdf' % fid
            pdfs.append({'date': it.get('date'), 'title': it.get('title'), 'category': cat,
                         'url': it.get('url'), 'readers': it.get('readers'), 'tags': tags,
                         'pdf_name': pdg.get('name'), 'pts': pts[:6], 'pdf_href': href})
    pdfs.sort(key=lambda x: (x.get('date') or ''), reverse=True)
    pdfs = pdfs[:PDF_MAX]

    # 市场观点：宏观外汇/观点讨论/权益策略 高质量条目（宏观与股市强相关）
    opinions = []
    for cat in ('宏观外汇', '观点讨论', '权益策略'):
        for it in d['categories'].get(cat, []):
            if it.get('quality') != '高':
                continue
            pts = [p for p in (it.get('points') or []) if p and not p.startswith('#')][:4]
            if not pts and it.get('summary'):
                pts = [it['summary'][:110]]
            opinions.append({'date': it.get('date'), 'title': it.get('title'),
                             'url': it.get('url'), 'readers': it.get('readers'),
                             'category': cat, 'pts': pts})
    opinions.sort(key=lambda x: (x.get('date') or ''), reverse=True)
    opinions = opinions[:30]

    out = {'asof': d.get('updated_at'), 'dir_window_days': d.get('dir_window_days', 30),
           'dir_global_share': d.get('dir_global_share'), 'buckets': buckets,
           'gold_posts': gold_posts, 'pdfs': pdfs, 'opinions': opinions,
           'panel_url': 'https://amiya866.github.io/metals-framework/zsxq-panel/',
           'built_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print('buckets:', [(b['label'], b['bull'], b['bear'], b['neutral']) for b in buckets])
    print('gold_posts:', len(gold_posts), 'pdfs:', len(pdfs),
          'with file:', sum(1 for p in pdfs if p['pdf_href']), 'opinions:', len(opinions))

    # 数据内嵌进 daily_latest.html（防浏览器缓存导致 fetch 拿不到新 json）
    html_path = os.path.join(BASE, 'reports', 'daily_latest.html')
    s = open(html_path, encoding='utf-8').read()
    begin = s.find('/*ZSXQ_RADAR_INLINE_BEGIN*/')
    end = s.find('/*ZSXQ_RADAR_INLINE_END*/')
    block = ('/*ZSXQ_RADAR_INLINE_BEGIN*/\nwindow.ZSXQ_RADAR='
             + json.dumps(out, ensure_ascii=False).replace('</', '<\\/')
             + ';\n/*ZSXQ_RADAR_INLINE_END*/')
    if begin >= 0 and end > begin:
        s = s[:begin] + block + s[end + len('/*ZSXQ_RADAR_INLINE_END*/'):]
    else:
        anchor = '/* ============ 外资研报观点（dp17） ============ */'
        assert anchor in s
        s = s.replace(anchor, block + '\n' + anchor, 1)
    open(html_path, 'w', encoding='utf-8').write(s)
    print('inlined into daily_latest.html')


if __name__ == '__main__':
    main()
