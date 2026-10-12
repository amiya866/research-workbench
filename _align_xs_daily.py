# -*- coding: utf-8 -*-
"""日报面板 × 截面策略 自动对齐（Windows 任务 RWXsAlignDaily，交易日 15:52）
等 _xs_live_payload.json 信号日翻到今天（15:37 收盘记账后，最多轮询 40 分钟），
然后重跑 _daily_report.py 生成当日面板 + _deploy_git.py 部署。
点评层 xs_views 脚本不动（承转机制自带 7 天保鲜标注），由会话内人工/agent 更新。
日志: _logs\\align_xs_YYYYMMDD.log
"""
import os, sys, json, time, subprocess, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
XS_PAYLOAD = r'D:\Kimi\有色截面配置_2026\_xs_live_payload.json'
LOGDIR = os.path.join(BASE, '_logs')
MAX_WAIT_MIN = 40
POLL_SEC = 300

def log(*a):
    msg = ' '.join(str(x) for x in a)
    line = '%s %s' % (datetime.datetime.now().strftime('%F %T'), msg)
    print(line, flush=True)
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, 'align_xs_%s.log' % datetime.date.today().strftime('%Y%m%d')),
                  'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

def sig_date():
    try:
        with open(XS_PAYLOAD, encoding='utf-8') as f:
            return json.load(f).get('sig_date', '')
    except Exception:
        return ''

def run(script):
    p = subprocess.run([sys.executable, os.path.join(BASE, script)],
                       cwd=BASE, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=600)
    log('%s rc=%d | %s' % (script, p.returncode, (p.stdout or '').strip().splitlines()[-1]
                           if p.stdout and p.stdout.strip() else (p.stderr or '')[-200:]))
    return p.returncode

def ensure_proxy():
    """部署走 Clash 7897；不在就尝试拉起 clash-verge"""
    import socket
    try:
        socket.create_connection(('127.0.0.1', 7897), timeout=3).close()
        return
    except Exception:
        pass
    clash = r'C:\Program Files\Miloucloud\clash-verge.exe'
    if os.path.exists(clash):
        log('7897 不通，拉起 clash-verge')
        subprocess.Popen([clash], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(12)

def main():
    today = datetime.date.today().isoformat()
    if datetime.date.today().weekday() >= 5:
        log('周末，跳过')
        return
    deadline = time.time() + MAX_WAIT_MIN * 60
    while True:
        sd = sig_date()
        if sd >= today:
            log('信号日 %s 已就位' % sd)
            break
        if time.time() > deadline:
            log('!! 等 %d 分钟信号日仍=%s，仍按现有信号生成（面板会标注信号日）' % (MAX_WAIT_MIN, sd))
            break
        log('信号日=%s 未更新，%d 分钟后重查' % (sd or '读取失败', POLL_SEC // 60))
        time.sleep(POLL_SEC)
    r1 = run('_daily_report.py')
    ensure_proxy()
    r2 = run('_deploy_git.py') if r1 == 0 else 99
    log('done daily_rc=%d deploy_rc=%d' % (r1, r2))
    sys.exit(0 if r2 == 0 else 1)

if __name__ == '__main__':
    main()
