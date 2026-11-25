# -*- coding: utf-8 -*-
"""整合研究站 本地一键数据刷新（2026-10-08 建）
顺序=原仓 .github/workflows/update_all.yml + daily_data.yml 的合并：
  polymarket → liquidity → cftc → macro → extra → cn_macro → calendar → trump
  → downstream → gen_charts → fedwatch → live → extra_news → collect_releases → tin_weekly → nickel_weekly
本地补丁：
  - PYTHONUTF8=1（防 GBK 控制台崩 ⚙️ 字符）
  - Yahoo 走 scripts/_yproxy.py（Clash 127.0.0.1:7897，RW_PROXY 可覆盖）
  - EXTRA_NEWS_PROXY 走代理（东财/新浪zhibo/westmetall 本机直连被重置）
  - 需密钥脚本（fetch_news 金十/先讯/CS、fetch_release BLS/BEA、fetch_ifind_mcp、
    fetch_shfe_stock）默认跳过；配好密钥后把 SKIP_KEYED 置 0 即自动纳入
每步 SOFT 容错（失败不炸链，脚本自身保留旧值自愈），日志落 _logs/refresh_YYYYMMDD_HHMM.log
2026-10-14 加固：启动先 ensure_proxy（7897 不通自动拉起 clash-verge 并等就绪）；
  代理仍不通时全步骤超时压到 150s 快速失败，保证尾部 日报/点评/部署 不被饿死
  （此前代理宕机时每步 900s 超时 × 17 步 > 任务 2h 上限，链被杀尾部永不执行）。
用法: python _refresh_all.py [--quick]   (--quick 跑 live/news/releases/radar/tin_weekly，不跑报告与部署)
"""
import os, sys, subprocess, datetime, socket, time

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')

# 子进程不弹控制台窗口（2026-10-16 闪窗根治）：本进程所有 subprocess.run/Popen 默认 CREATE_NO_WINDOW
_NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
def _nw(fn):
    def w(*a, **kw):
        kw.setdefault('creationflags', _NW)
        return fn(*a, **kw)
    return w
subprocess.run = _nw(subprocess.run)
subprocess.Popen = _nw(subprocess.Popen)

BASE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(BASE, 'scripts')
LOGDIR = os.path.join(BASE, '_logs')
os.makedirs(LOGDIR, exist_ok=True)

FULL_CHAIN = [
    'fetch_polymarket', 'fetch_liquidity', 'fetch_cftc', 'fetch_macro',
    'fetch_extra', 'fetch_cn_macro', 'fetch_calendar', 'fetch_trump',
    'fetch_downstream', 'gen_charts', 'fetch_fedwatch', 'fetch_live',
    'fetch_news', 'fetch_extra_news', 'collect_releases', 'fetch_release',
    'fetch_zsxq_radar', 'fetch_tin_weekly', 'build_tin_meeting_panel', 'refresh_nickel_weekly', 'build_zinc_weekly', 'build_aluminum_weekly', 'build_aluminum_meeting_panel', 'build_copper_weekly', 'build_lead_weekly',
]
QUICK_CHAIN = ['fetch_live', 'fetch_news', 'fetch_extra_news', 'collect_releases', 'fetch_zsxq_radar', 'fetch_tin_weekly', 'build_tin_meeting_panel', 'refresh_nickel_weekly', 'build_zinc_weekly', 'build_aluminum_weekly', 'build_aluminum_meeting_panel', 'build_copper_weekly', 'build_lead_weekly']
KEYED_CHAIN = ['fetch_ifind_mcp', 'fetch_shfe_stock']
SKIP_KEYED = 1  # 密钥未配，置 0 纳入

CLASH_EXE = r'C:\Program Files\Miloucloud\clash-verge.exe'
PROXY_PORT = 7897

def proxy_alive():
    try:
        socket.create_connection(('127.0.0.1', PROXY_PORT), timeout=3).close()
        return True
    except Exception:
        return False

def ensure_proxy():
    """7897 不通则拉起 clash-verge，轮询最多 150s 等就绪；返回代理是否可用"""
    if proxy_alive():
        return True
    if os.path.exists(CLASH_EXE):
        print('7897 不通，拉起 clash-verge ...', flush=True)
        subprocess.Popen([CLASH_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(5)
            if proxy_alive():
                print('代理已就绪', flush=True)
                return True
    print('!! 代理仍不通，本次全步骤按 150s 超时快速失败', flush=True)
    return False

def main():
    quick = '--quick' in sys.argv
    chain = QUICK_CHAIN if quick else FULL_CHAIN + ([] if SKIP_KEYED else KEYED_CHAIN)
    if datetime.date.today().weekday() not in (4, 5, 6):
        chain = [name for name in chain if name not in ('fetch_tin_weekly', 'refresh_nickel_weekly', 'build_zinc_weekly', 'build_aluminum_weekly', 'build_copper_weekly', 'build_lead_weekly')]
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    logpath = os.path.join(LOGDIR, 'refresh_%s.log' % stamp)
    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    proxy_ok = ensure_proxy()
    env.setdefault('EXTRA_NEWS_PROXY', 'http://127.0.0.1:7897')
    env.setdefault('RW_PROXY', 'http://127.0.0.1:7897')
    env.setdefault('BLS_KEY', 'b1e15847ef0c490abeb0a2e12336c435')  # 2026-10-08 注册（tian4828@agent.qq.com）
    env.setdefault('BEA_KEY', '92529507-784E-48A1-8E12-6D2F7495E670')  # 2026-10-08 注册、10-09 激活生效（tian4828@agent.qq.com）
    results = []
    step_timeout = 900 if proxy_ok else 150
    with open(logpath, 'w', encoding='utf-8') as lf:
        for name in chain:
            head = '=== %s %s ===' % (name, datetime.datetime.now().strftime('%H:%M:%S'))
            print(head, flush=True)
            lf.write(head + '\n')
            try:
                p = subprocess.run(
                    [sys.executable, os.path.join(SCRIPTS, name + '.py')],
                    cwd=BASE, env=env, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=step_timeout)
                tail = '\n'.join((p.stdout or '').strip().splitlines()[-3:])
                err = (p.stderr or '').strip()
                lf.write((p.stdout or '') + ('\n[stderr]\n' + err if err else '') + '\n')
                lf.flush()
                status = 'rc=%d' % p.returncode
                if p.returncode != 0:
                    status += ' ' + '\n'.join(err.splitlines()[-2:])
            except subprocess.TimeoutExpired:
                tail, status = '', 'TIMEOUT(%ds)' % step_timeout
            except Exception as e:
                tail, status = '', 'EXC %r' % e
            print(tail, flush=True)
            print(status, flush=True)
            results.append((name, status.split()[0]))
    # 全链尾部：地缘事件链追加 + 日更研报生成 + 自动部署（2026-10-09 挂；快刷档不跑）
    if not quick:
        lf = open(logpath, 'a', encoding='utf-8')
        for extra in ('_geo_events.py', 'scripts/update_nonferrous_common.py', '_daily_report.py', '_variety_review.py', 'scripts/build_update_health.py', '_deploy_git.py'):
            head = '=== %s %s ===' % (extra, datetime.datetime.now().strftime('%H:%M:%S'))
            print(head, flush=True)
            lf.write(head + '\n')
            try:
                p = subprocess.run([sys.executable, os.path.join(BASE, extra)],
                                   cwd=BASE, env=env, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', timeout=900)
                tail = '\n'.join((p.stdout or '').strip().splitlines()[-3:])
                lf.write((p.stdout or '') + ('\n[stderr]\n' + (p.stderr or '') if p.stderr else '') + '\n')
                status = 'rc=%d' % p.returncode
            except Exception as e:
                tail, status = '', 'EXC %r' % e
            print(tail, flush=True)
            print(status, flush=True)
            results.append((extra, status.split()[0]))
        lf.close()
    ok = sum(1 for _, s in results if s == 'rc=0')
    summary = '完成 %d/%d | %s' % (ok, len(results), logpath)
    print(summary, flush=True)
    with open(os.path.join(LOGDIR, 'last_run.txt'), 'w', encoding='utf-8') as f:
        f.write('%s %s\n' % (datetime.datetime.now().strftime('%F %T'), summary))
        for n, s in results:
            f.write('  %-22s %s\n' % (n, s))

if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        fatal = os.path.join(LOGDIR, 'refresh_fatal_%s.log' % datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        with open(fatal, 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
        print('全链未捕获异常，已写入 %s' % fatal, flush=True)
        raise
