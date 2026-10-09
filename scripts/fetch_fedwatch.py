#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_fedwatch.py — 抓取 CME FedWatch（cmegroup.cn 官方中文版）各会议
EASE / NO CHANGE / HIKE 概率、完整利率区间概率矩阵（TARGET RATE 表）、
中间价，落盘 data/fedwatch.json。

页面结构（quikstrike iframe 内，有 referrer 校验，须 playwright 渲染）：
  · 摘要表：表头恰为 EASE / NO CHANGE / HIKE，下一行即三个概率（权威口径）
  · 信息表：含 MID PRICE（30天联邦基金期货 ZQ 价格）
  · 矩阵表：首列 TARGET RATE (BPS)，逐行列出各利率区间概率
逐会议页签点击提取。ease/no_change/hike 以官方摘要表为准，
不做列序猜测（旧版按位置猜三列，曾把列对错，已废弃）。
"""
import json, re, sys, datetime, shutil
from pathlib import Path

URL = "https://www.cmegroup.cn/fed-watch/"
OUT = Path(__file__).resolve().parent.parent / "data" / "fedwatch.json"
CSJS = Path(__file__).resolve().parent.parent / "data" / "chart_series.js"
PCT_RE = re.compile(r"^\d+(?:\.\d+)?\s*%$")
BUCKET_RE = re.compile(r"^(\d{3})-(\d{3})")


def find_chromium():
    for p in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/usr/lib/chromium/chromium", "/opt/chromium/chromium"):
        if Path(p).exists():
            return p
    return shutil.which("chromium") or shutil.which("chromium-browser")


def bucket_from_matrix(meetings):
    """从首场会议桶矩阵推当前目标区间：hold概率所落在的桶=当前区间（决议日即时准确）"""
    try:
        m0 = meetings[0]
        bks = m0.get("buckets") or []
        if not bks:
            return None
        nc = m0.get("no_change")
        if nc is not None:
            for b in bks:
                if abs(b["p"] - nc) < 0.06:
                    return b["r"]
        # 退化规则：加息主导取最低桶，降息主导取最高桶
        return bks[0]["r"] if (m0.get("hike", 0) >= m0.get("ease", 0)) else bks[-1]["r"]
    except Exception:
        return None


def current_bucket():
    """由 chart_series.js 的 DFEDTARU/DFEDTARL 最新值推当前目标区间，如 '350-375'"""
    try:
        txt = CSJS.read_text(encoding="utf-8")
        m = re.search(r'window\.CHART_SERIES\s*=\s*(\{.*\});?\s*$', txt, re.S)
        cs = json.loads(m.group(1))
        lo = [p for p in cs.get("DFEDTARL", []) if p[1] is not None][-1][1]
        hi = [p for p in cs.get("DFEDTARU", []) if p[1] is not None][-1][1]
        return f"{int(round(lo*100))}-{int(round(hi*100))}"
    except Exception:
        return None


def parse_tab(fr):
    """解析当前页签：返回 (ease,no_change,hike), mid, buckets[[rng,p],...]"""
    tbls = fr.evaluate(
        """() => Array.from(document.querySelectorAll('table')).map(t=>
             Array.from(t.querySelectorAll('tr')).map(tr=>
               Array.from(tr.querySelectorAll('th,td')).map(c=>c.innerText.trim())))""")
    enh, mid, buckets = None, None, []
    for rows in tbls:
        flat = [c for r in rows for c in r]
        # ① 官方摘要表：EASE / NO CHANGE / HIKE
        if "EASE" in flat and "HIKE" in flat and enh is None:
            i = flat.index("EASE")
            vals = [float(v.replace("%", "").strip())
                    for v in flat[i + 3:] if PCT_RE.match(v)]
            if len(vals) >= 3 and abs(sum(vals[:3]) - 100) < 2:
                enh = vals[:3]
        # ② 中间价
        if "MID PRICE" in flat and mid is None:
            for v in flat[flat.index("MID PRICE") + 1:]:
                if re.match(r"^\d{2}\.\d{3,4}$", v):
                    mid = float(v); break
        # ③ 利率区间概率矩阵（允许区间后带 * 等标记）
        if flat and flat[0].startswith("TARGET RATE") and not buckets:
            for r in rows:
                if len(r) >= 2 and BUCKET_RE.match(r[0]):
                    rng = BUCKET_RE.match(r[0]).group(0)
                    try:
                        p = float(r[1].replace("%", "").strip())
                    except ValueError:
                        continue
                    buckets.append([rng, p])
    return enh, mid, buckets


def main():
    from playwright.sync_api import sync_playwright
    exe = find_chromium()
    launch_kw = {"headless": True,
                 "args": ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]}
    if exe:
        launch_kw["executable_path"] = exe

    meetings = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kw)
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"),
            viewport={"width": 1400, "height": 2000})
        page.goto(URL, wait_until="load", timeout=60000)
        page.wait_for_timeout(12000)

        fr = next((f for f in page.frames if "quikstrike" in (f.url or "")), None)
        if fr is None:
            print("[fedwatch] quikstrike iframe not found", file=sys.stderr); sys.exit(3)

        tabs = fr.evaluate(
            """() => Array.from(document.querySelectorAll('li a'))
                 .map(a => (a.innerText || '').trim())
                 .filter(t => /^\\d{1,2}\\s*[A-Za-z]{3}\\s*\\d{2}$/.test(t))""")
        tabs = list(dict.fromkeys(tabs))

        for tab in tabs:
            try:
                fr.evaluate(
                    """(t) => { const a = Array.from(document.querySelectorAll('li a'))
                          .find(x => (x.innerText||'').trim() === t); if (a) a.click(); }""", tab)
                page.wait_for_timeout(2500)
                enh, mid, buckets = parse_tab(fr)
                if enh:
                    meetings.append({
                        "meeting": tab,
                        "ease": enh[0], "no_change": enh[1], "hike": enh[2],
                        "mid": mid,
                        "buckets": [{"r": r, "p": p} for r, p in buckets if p > 0.049],
                    })
            except Exception as e:
                print(f"[fedwatch] tab {tab} failed: {e}", file=sys.stderr)
        browser.close()

    if not meetings:
        print("[fedwatch] parse failed, no meetings", file=sys.stderr); sys.exit(4)

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    doc = {
        "asof": now.strftime("%Y-%m-%d %H:%M BJT"),
        "source": "CME FedWatch（cmegroup.cn 官方）",
        "contract": "30天联邦基金期货（ZQ）",
        "current_bucket": bucket_from_matrix(meetings) or current_bucket(),
        "meetings": meetings,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fedwatch] ok: {len(meetings)} meetings -> {OUT}")
    for mt in meetings:
        print(" ", mt["meeting"], "ease/nc/hike =",
              mt["ease"], mt["no_change"], mt["hike"],
              "| mid =", mt["mid"], "| buckets =", len(mt["buckets"]))


if __name__ == "__main__":
    main()
