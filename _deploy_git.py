# -*- coding: utf-8 -*-
"""整合研究站 自动部署（2026-10-09 建）
git add -A → 有变更才 commit → push（走 Clash 代理 7897，RW_PROXY 可覆盖）
token 从 ~/.kimi-work/_gh_amiya866.token 读（remote URL 里的 gho_ token 已失效则用它兜底改 URL）
挂 _refresh_all.py 全链尾部；rc 不炸链。
"""
import os, sys, subprocess, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PROXY = os.environ.get('RW_PROXY', 'http://127.0.0.1:7897')
TOKEN_PATH = os.path.expanduser(r'~/.kimi-work/_gh_amiya866.token')

def run(args, **kw):
    return subprocess.run(args, cwd=BASE, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=300, **kw)

def main():
    run(['git', 'add', '-A'])
    diff = run(['git', 'diff', '--cached', '--name-only'])
    files = [x for x in (diff.stdout or '').splitlines() if x.strip()]
    if not files:
        print('无变更，跳过部署')
        return
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    run(['git', '-c', 'user.name=amiya866', '-c', 'user.email=amiya866@users.noreply.github.com',
         'commit', '-m', 'auto daily %s（%d 文件）' % (stamp, len(files))])
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
    p = run(['git', '-c', 'http.proxy=%s' % PROXY, 'push', 'origin', 'HEAD'], env=env)
    tail = '\n'.join(((p.stdout or '') + (p.stderr or '')).strip().splitlines()[-3:])
    print('push rc=%d | %s' % (p.returncode, tail))
    sys.exit(0 if p.returncode == 0 else 1)

if __name__ == '__main__':
    main()
