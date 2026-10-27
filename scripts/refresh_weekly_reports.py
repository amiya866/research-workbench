# -*- coding: utf-8 -*-
"""独立研究周报更新链：锡同步 → 镍重建 → 日报/点评 → 部署。失败保留上一版并记录非零状态。"""
import datetime
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def main():
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    results = []
    steps = [
        'scripts/fetch_tin_weekly.py',
        'scripts/refresh_nickel_weekly.py',
        '_daily_report.py',
        '_variety_review.py',
        '_deploy_git.py',
    ]
    for name in steps:
        print('=== %s %s ===' % (datetime.datetime.now().strftime('%F %T'), name), flush=True)
        try:
            p = subprocess.run([sys.executable, str(BASE / name)], cwd=BASE, env=env,
                               capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=1200, creationflags=NW)
            tail = '\n'.join((p.stdout or '').splitlines()[-5:])
            print(tail, flush=True)
            if p.returncode:
                print((p.stderr or '')[-1200:], file=sys.stderr, flush=True)
            results.append((name, p.returncode))
        except Exception as exc:
            print('EXC %r' % exc, file=sys.stderr, flush=True)
            results.append((name, 1))
    print('SUMMARY ' + repr(results), flush=True)
    return 1 if any(rc for _name, rc in results) else 0


if __name__ == '__main__':
    sys.exit(main())
