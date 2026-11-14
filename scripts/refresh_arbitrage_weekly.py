import datetime
import os
import subprocess
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')

BASE = Path(__file__).resolve().parents[1]
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def main():
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    results = []
    for name in ('scripts/build_arbitrage_weekly.py', 'scripts/build_update_health.py', '_deploy_git.py'):
        print('=== %s %s ===' % (datetime.datetime.now().strftime('%F %T'), name), flush=True)
        try:
            process = subprocess.run([sys.executable, str(BASE / name)], cwd=BASE, env=env,
                                     capture_output=True, text=True, encoding='utf-8', errors='replace',
                                     timeout=1200, creationflags=NW)
            print('\n'.join((process.stdout or '').splitlines()[-8:]), flush=True)
            if process.returncode:
                print((process.stderr or '')[-1600:], file=sys.stderr, flush=True)
            results.append((name, process.returncode))
            if process.returncode:
                break
        except Exception as exc:
            print('EXC %r' % exc, file=sys.stderr, flush=True)
            results.append((name, 1))
            break
    print('SUMMARY ' + repr(results), flush=True)
    return 1 if any(code for _name, code in results) else 0


if __name__ == '__main__':
    sys.exit(main())
