# -*- coding: utf-8 -*-
"""整合研究站 自动部署（2026-10-09 建）
git add -A → 有变更才 commit → pull --rebase origin/main → push（走 Clash 代理 7897，RW_PROXY 可覆盖）
token 从 ~/.kimi-work/_gh_amiya866.token 读（remote URL 里的 gho_ token 已失效则用它兜底改 URL）
挂 _refresh_all.py 全链尾部；rc 不炸链。
"""
import os, sys, subprocess, datetime, socket, time, re

# 子进程不弹控制台窗口（2026-10-16 闪窗根治）
_NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
def _nw(fn):
    def w(*a, **kw):
        kw.setdefault('creationflags', _NW)
        return fn(*a, **kw)
    return w
subprocess.run = _nw(subprocess.run)
subprocess.Popen = _nw(subprocess.Popen)

BASE = os.path.dirname(os.path.abspath(__file__))
PROXY = os.environ.get('RW_PROXY', 'http://127.0.0.1:7897')
TOKEN_PATH = os.path.expanduser(r'~/.kimi-work/_gh_amiya866.token')
CLASH_EXE = r'C:\Program Files\Miloucloud\clash-verge.exe'

def ensure_proxy():
    """push 前确保 7897 在；不在拉起 clash-verge 并轮询最多 150s（2026-10-14 加，
    原 12s 固定等待不够 clash 起端口，曾致部署连续失败）"""
    if not PROXY:
        return True
    def alive():
        try:
            socket.create_connection(('127.0.0.1', 7897), timeout=3).close()
            return True
        except Exception:
            return False
    if alive():
        return True
    if os.path.exists(CLASH_EXE):
        print('7897 不通，拉起 clash-verge ...')
        subprocess.Popen([CLASH_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(5)
            if alive():
                print('代理已就绪')
                return True
    print('!! 代理拉起失败，push 可能不通')
    return False

def run(args, **kw):
    return subprocess.run(args, cwd=BASE, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=300, **kw)

REMOTE_DATA = {
    'data/truth_posts.json', 'data/cftc.json', 'data/macro_series.json',
    'data/liquidity.json', 'data/tic.json', 'data/trump_zone.json',
    'data/auctions.json', 'data/econ_calendar.json', 'data/release_panels.json',
    'data/calendar_consensus.json', 'data/chart_series.js', 'data/fedwatch.json',
    'data/releases_recent.json', 'data/live_quotes.json', 'data/polymarket.json',
    'data/macro_catalog.js', 'data/j10_store.json',
}

def check_report():
    path = os.path.join(BASE, 'reports', 'daily_latest.html')
    text = open(path, encoding='utf-8').read()
    if re.search(r'^(<<<<<<<|=======|>>>>>>>)', text, re.M):
        print('日报仍含 Git 冲突标记，停止部署')
        sys.exit(3)
    if len(re.findall(r'^const N = .*;$', text, re.M)) != 1:
        print('日报快讯兜底块不是唯一一套，停止部署')
        sys.exit(3)

def unmerged_files():
    p = run(['git', 'diff', '--name-only', '--diff-filter=U'])
    return [x for x in (p.stdout or '').splitlines() if x.strip()]

def continue_rebase(paths):
    for path in paths:
        if path in REMOTE_DATA:
            side = '--ours'
        elif (path.startswith('reports/') or path.startswith('arbitrage-weekly/')
              or path.startswith('scripts/templates/arbitrage-weekly/')
              or path in ('data/news_latest.json', 'data/news_fallback.js',
                          'scripts/build_arbitrage_weekly.py', 'scripts/build_update_health.py',
                          'scripts/refresh_arbitrage_weekly.py', 'scripts/register_arbitrage_weekly.ps1')):
            side = '--theirs'
        else:
            print('未登记的冲突文件，停止自动取舍：' + path)
            return None
        p = run(['git', 'checkout', side, '--', path])
        if p.returncode:
            return None
    run(['git', 'add', '--'] + paths)
    env = dict(os.environ, GIT_EDITOR='true')
    return run(['git', 'rebase', '--continue'], env=env)

def main():
    check_report()
    run(['git', 'add', '-A'])
    diff = run(['git', 'diff', '--cached', '--name-only'])
    files = [x for x in (diff.stdout or '').splitlines() if x.strip()]
    if files:
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        commit = run(['git', '-c', 'user.name=amiya866', '-c', 'user.email=amiya866@users.noreply.github.com',
                      'commit', '-m', 'auto daily %s（%d 文件）' % (stamp, len(files))])
        if commit.returncode:
            print((commit.stdout or '') + (commit.stderr or ''))
            sys.exit(2)
    # 无新变更也要检查未推送提交（上轮 push 失败的兜底）
    ahead = run(['git', 'log', 'origin/main..HEAD', '--oneline'])
    if not files and not (ahead.stdout or '').strip():
        print('无变更且无未推送提交，跳过部署')
        return
    if not files:
        print('无新变更，但有未推送提交：\n' + ahead.stdout.strip())
    env = dict(os.environ)
    try:
        tok = open(TOKEN_PATH, encoding='utf-8').read().strip()
        url = run(['git', 'remote', 'get-url', 'origin']).stdout.strip()
        if 'x-access-token:' in url:
            new = re.sub(r'x-access-token:[^@]+@', 'x-access-token:%s@' % tok, url)
            run(['git', 'remote', 'set-url', 'origin', new])
    except Exception as e:
        print('token 兜底跳过:', e)
    ensure_proxy()
    pull = run(['git', '-c', 'http.proxy=%s' % PROXY, '-c', 'http.schannelCheckRevoke=false', '-c', 'http.sslBackend=openssl', 'pull', '--rebase', 'origin', 'main'], env=env)
    for _ in range(30):
        if pull.returncode == 0:
            break
        paths = unmerged_files()
        if not paths:
            tail = '\n'.join(((pull.stdout or '') + (pull.stderr or '')).strip().splitlines()[-8:])
            print('pull --rebase 失败且无可自动处理冲突，停止推送：\n' + tail)
            sys.exit(2)
        print('按来源规则处理 rebase 冲突：' + ', '.join(paths))
        pull = continue_rebase(paths)
        if pull is None:
            sys.exit(2)
    else:
        print('rebase 冲突轮次过多，停止推送')
        sys.exit(2)
    check_report()
    p = run(['git', '-c', 'http.proxy=%s' % PROXY, '-c', 'http.schannelCheckRevoke=false', '-c', 'http.sslBackend=openssl', 'push', 'origin', 'HEAD'], env=env)
    tail = '\n'.join(((p.stdout or '') + (p.stderr or '')).strip().splitlines()[-3:])
    print('push rc=%d | %s' % (p.returncode, tail))
    sys.exit(0 if p.returncode == 0 else 1)

if __name__ == '__main__':
    main()
