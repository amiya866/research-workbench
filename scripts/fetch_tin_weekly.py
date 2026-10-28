# -*- coding: utf-8 -*-
"""同步锡研究周报全文与静态资源，并更新日报/分品种页摘要。用法：python scripts/fetch_tin_weekly.py [--force]"""
import concurrent.futures
import datetime
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'tin-weekly'
META = BASE / 'data' / 'tin_weekly.json'
STATE = BASE / 'data' / 'tin_weekly_sync.json'
DAILY = BASE / 'reports' / 'daily_latest.html'
SOURCE = 'https://gsy1005.github.io/tin-research/weekly_full.html'
SOURCE_ROOT = 'https://gsy1005.github.io/tin-research/'
BEGIN = '<!-- TIN_WEEKLY_CARD_BEGIN -->'
END = '<!-- TIN_WEEKLY_CARD_END -->'
KEY_CAPS = ('SMM社会库存', '钢联社会库存', 'SHFE仓单(日)', '沪锡结构：连一 - 连二', '现货升贴水', '沪锡主力结算价')
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def fetch(url, timeout=90):
    raw_url = url.replace(SOURCE_ROOT, 'https://raw.githubusercontent.com/gsy1005/tin-research/main/')
    proxy = os.environ.get('RW_PROXY', 'http://127.0.0.1:7897')
    attempts = [(raw_url, proxy), (url, proxy), (raw_url, ''), (url, '')]
    errors = []
    for candidate, proxy_url in dict.fromkeys(attempts):
        cmd = ['curl', '-fsSL', '--ssl-no-revoke', '--retry', '1', '--connect-timeout', '10',
               '--max-time', str(min(timeout, 60)), '-H', 'User-Agent: Mozilla/5.0']
        if proxy_url:
            cmd += ['--proxy', proxy_url]
        cmd.append(candidate)
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=min(timeout, 60) + 15, creationflags=NW)
            if p.returncode == 0:
                return p.stdout
            errors.append('rc=%d %s' % (p.returncode, p.stderr.decode('utf-8', 'replace')[-120:]))
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise RuntimeError('；'.join(errors[-3:]))


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    if isinstance(data, str):
        data = data.encode('utf-8')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def clean(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', fragment))).strip()


def assets_in(page):
    refs = set()
    for ref in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', page, re.I):
        ref = unquote(urlsplit(ref).path)
        if not ref or ref.startswith(('/', 'data:')):
            continue
        path = PurePosixPath(ref)
        if '..' in path.parts or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.ico', '.md'):
            continue
        refs.add(path.as_posix())
    return sorted(refs)


def extract_meta(page, source_hash, asset_count):
    def one(pattern, fallback=''):
        m = re.search(pattern, page, re.S | re.I)
        return clean(m.group(1)) if m else fallback
    metrics = []
    seen = set()
    for block in re.findall(r'<div class="cbox".*?</div></div>', page, re.S):
        cap = re.search(r'<div class="cap">(.*?)</div>', block, re.S)
        stat = re.search(r'<div class="stats">(.*?)</div>', block, re.S)
        if cap and stat:
            name, value = clean(cap.group(1)), clean(stat.group(1))
            if name in KEY_CAPS and name not in seen:
                metrics.append({'name': name, 'value': value})
                seen.add(name)
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    return {
        'title': one(r'<title>(.*?)</title>', '锡研究周报'),
        'asof': one(r'数据截至\s*<b>(\d{4}-\d{2}-\d{2})</b>'),
        'headline': one(r'<div class="tone">(.*?)</div>'),
        'metrics': metrics,
        'source_url': SOURCE + '#sumsec',
        'local_url': 'tin-weekly/#sumsec',
        'source_sha256': source_hash,
        'asset_count': asset_count,
        'synced_at': now,
        'sync_status': 'ok',
        'last_error': '',
    }


def card_html(meta):
    error = meta.get('last_error')
    status = '同步异常，展示上次成功版本：%s' % error if error else '全文与图表已本地镜像，随研究站管线自动同步'
    metrics = ''.join('<li><b>%s</b>　%s</li>' % (html.escape(m['name']), html.escape(m['value']))
                      for m in meta.get('metrics', [])[:4])
    return '''%s
<div class="card" id="tinWeeklyCard" style="border-left:3px solid var(--gold);margin:14px 0;">
  <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;">
    <h3 style="margin:0;color:var(--gold);">%s</h3>
    <a href="../tin-weekly/#sumsec" style="font-weight:700;">打开完整周报 ↗</a>
  </div>
  <p style="margin-top:8px;">%s</p>
  <ul style="margin:8px 0 0 18px;font-size:12px;color:var(--dim);">%s</ul>
  <p style="font-size:11px;color:var(--dim);margin-top:8px;">数据截至 %s · %s · <a href="%s" target="_blank" rel="noopener">上游原站</a></p>
</div>
%s''' % (BEGIN, html.escape(meta.get('title', '锡研究周报').replace('锡研究周报', '研究周报 · 锡')), html.escape(meta.get('headline', '')),
         metrics, html.escape(meta.get('asof') or '—'), html.escape(status),
         html.escape(meta.get('source_url', SOURCE)), END)


def update_daily_card(meta):
    if not DAILY.exists():
        return
    page = DAILY.read_text(encoding='utf-8')
    card = card_html(meta)
    pattern = re.escape(BEGIN) + r'.*?' + re.escape(END)
    if re.search(pattern, page, re.S):
        page = re.sub(pattern, lambda _m: card, page, count=1, flags=re.S)
    else:
        anchor = '<section class="dp on" id="dp1">'
        if anchor not in page:
            raise RuntimeError('daily_latest.html 缺少总览页锚点')
        page = page.replace(anchor, anchor + '\n' + card, 1)
    write_atomic(DAILY, page)


def localize(page):
    page = page.replace('<a aria-label="返回锡研究首页" class="back-home" href="./">← 锡研究首页</a>',
                        '<a aria-label="返回整合研究站" class="back-home" href="../index.html">← 整合研究站</a>')
    page = page.replace('<title>锡研究周报 ·', '<title>研究周报 · 锡 ·', 1)
    page = page.replace('TIN WEEKLY RESEARCH', 'COMMODITY WEEKLY RESEARCH', 1)
    page = page.replace('<h1>锡研究周报</h1>', '<h1>研究周报 <span class="commodity-current">锡</span></h1>', 1)
    page = page.replace('<link href="research.css" rel="stylesheet"/></head>',
                        '<link href="research.css" rel="stylesheet"/><link href="../weekly-light.css" rel="stylesheet"/></head>', 1)
    switch = '<nav class="commodity-switch" aria-label="品种切换"><a class="active" href="#sumsec">锡</a><a href="../nickel-weekly/#sumsec">镍</a><a href="../zinc-weekly/#sumsec">锌</a><a href="../aluminum-weekly/#sumsec">铝</a></nav>'
    page = page.replace('<div class="research-actions">',
                        '<div class="research-actions">' + switch + '<a class="back-home" href="%s" target="_blank" rel="noopener" style="margin-right:12px">上游原站 ↗</a>' % SOURCE, 1)
    return page


def sync_assets(refs, only_missing=False):
    missing = [r for r in refs if not (OUT / r).is_file()]
    jobs = missing if only_missing else refs
    failures = []

    def one(ref):
        target = OUT / ref
        try:
            data = fetch(SOURCE_ROOT + quote(ref), 60)
            if len(data) < 20:
                raise RuntimeError('资源过短')
            write_atomic(target, data)
            return ref, ''
        except Exception as exc:
            return ref, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i, (ref, error) in enumerate(pool.map(one, jobs), 1):
            if error:
                failures.append((ref, error))
            if i % 40 == 0 or i == len(jobs):
                print('assets %d/%d' % (i, len(jobs)), flush=True)
    fatal = [r for r, _e in failures if not (OUT / r).is_file()]
    if fatal:
        raise RuntimeError('必要资源下载失败：%s' % '、'.join(fatal[:8]))
    return failures


def main():
    force = '--force' in sys.argv
    previous = load_json(META, {}) or {}
    state = load_json(STATE, {}) or {}
    try:
        raw = fetch(SOURCE)
        page = raw.decode('utf-8-sig')
        if '<div id="sumsec">' not in page or 'class="tone"' not in page:
            raise RuntimeError('上游页面结构校验失败')
        source_hash = hashlib.sha256(raw).hexdigest()
        refs = assets_in(page)
        changed = force or source_hash != previous.get('source_sha256') or not (OUT / 'index.html').is_file()
        if not changed:
            had_missing = any(not (OUT / r).is_file() for r in refs)
            failures = sync_assets(refs, only_missing=True)
            if not failures:
                if had_missing or previous.get('asset_count') != len(refs):
                    previous['asset_count'] = len(refs)
                    write_atomic(META, json.dumps(previous, ensure_ascii=False, indent=2))
                update_daily_card(previous)
                state['last_check'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
                write_atomic(STATE, json.dumps(state, ensure_ascii=False, indent=2))
                print('锡周报未变化：%s，资源 %d 个完整' % (previous.get('asof'), len(refs)))
                return
        else:
            failures = sync_assets(refs)
        meta = extract_meta(page, source_hash, len(refs))
        if not meta['asof'] or not meta['headline']:
            raise RuntimeError('周报日期或定调提取失败')
        if failures:
            meta['asset_warnings'] = failures
        write_atomic(OUT / 'upstream.html', page)
        write_atomic(META, json.dumps(meta, ensure_ascii=False, indent=2))
        update_daily_card(meta)
        state.update({'last_check': meta['synced_at'], 'last_success': meta['synced_at'],
                      'source_sha256': source_hash, 'asset_count': len(refs), 'last_error': ''})
        write_atomic(STATE, json.dumps(state, ensure_ascii=False, indent=2))
        build = subprocess.run([sys.executable, str(BASE / 'scripts' / 'build_tin_weekly.py')],
                               cwd=BASE, capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=180, creationflags=NW)
        print(build.stdout, flush=True)
        if build.returncode:
            raise RuntimeError('锡周报结构化构建失败：%s' % build.stderr[-500:])
        print('锡周报已同步：%s，%d 个资源，%d 个非致命警告' % (meta['asof'], len(refs), len(failures)))
    except Exception as exc:
        error = str(exc)
        if not previous or not (OUT / 'index.html').is_file():
            raise
        if error != previous.get('last_error'):
            previous['last_error'] = error
            previous['sync_status'] = 'stale'
            write_atomic(META, json.dumps(previous, ensure_ascii=False, indent=2))
            update_daily_card(previous)
        state['last_check'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
        state['last_error'] = error
        write_atomic(STATE, json.dumps(state, ensure_ascii=False, indent=2))
        print('锡周报同步失败，保留上次成功版本：%s' % error, file=sys.stderr)
        time.sleep(0.1)
        sys.exit(1)


if __name__ == '__main__':
    main()
