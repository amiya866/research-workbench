# -*- coding: utf-8 -*-
"""整合研究站 自动部署（2026-10-09 建）
git add -A → 有变更才 commit → pull --rebase origin/main → push（走 Clash 代理 7897，RW_PROXY 可覆盖）
token 从 ~/.kimi-work/_gh_amiya866.token 读（remote URL 里的 gho_ token 已失效则用它兜底改 URL）
挂 _refresh_all.py 全链尾部；rc 不炸链。
"""
import os, sys, subprocess, datetime, socket, time

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

def main():
    run(['git', 'add', '-A'])
    diff = run(['git', 'diff', '--cached', '--name-only'])
    files = [x for x in (diff.stdout or '').splitlines() if x.strip()]
    if files:
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        run(['git', '-c', 'user.name=amiya866', '-c', 'user.email=amiya866@users.noreply.github.com',
             'commit', '-m', 'auto daily %s（%d 文件）' % (stamp, len(files))])
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
            import re
            new = re.sub(r'x-access-token:[^@]+@', 'x-access-token:%s@' % tok, url)
            run(['git', 'remote', 'set-url', 'origin', new])
    except Exception as e:
        print('token 兜底跳过:', e)
    ensure_proxy()
    pull = run(['git', '-c', 'http.proxy=%s' % PROXY, '-c', 'http.schannelCheckRevoke=false', 'pull', '--rebase', 'origin', 'main'], env=env)
    if pull.returncode:
        tail = '\n'.join(((pull.stdout or '') + (pull.stderr or '')).strip().splitlines()[-8:])
        print('pull --rebase 失败，停止推送以免覆盖远端：\n' + tail)
        sys.exit(2)
    p = run(['git', '-c', 'http.proxy=%s' % PROXY, 'push', 'origin', 'HEAD'], env=env)
    tail = '\n'.join(((p.stdout or '') + (p.stderr or '')).strip().splitlines()[-3:])
    print('push rc=%d | %s' % (p.returncode, tail))
    sys.exit(0 if p.returncode == 0 else 1)

if __name__ == '__main__':
    main()
