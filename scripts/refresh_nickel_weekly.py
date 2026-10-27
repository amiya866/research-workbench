# -*- coding: utf-8 -*-
"""先刷新镍面板数据，再重建研究站镍周报；失败保留上一成功版。"""
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE = Path(r'D:/Kimi/nickel-panel')
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def main():
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    p = subprocess.run([sys.executable, 'scripts/build_nickel_data.py', '--inject'], cwd=SOURCE,
                       env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=900, creationflags=NW)
    print('\n'.join((p.stdout or '').splitlines()[-12:]))
    if p.returncode:
        print(p.stderr[-1200:], file=sys.stderr)
        return p.returncode
    p = subprocess.run([sys.executable, str(BASE / 'scripts' / 'build_nickel_weekly.py')], cwd=BASE,
                       env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=180, creationflags=NW)
    print(p.stdout)
    if p.returncode:
        print(p.stderr[-1200:], file=sys.stderr)
    return p.returncode


if __name__ == '__main__':
    sys.exit(main())
