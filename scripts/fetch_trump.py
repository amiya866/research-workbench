# -*- coding: utf-8 -*-
"""特朗普专区数据抓取：ocmacro川普仪表盘（压力指数/支持率/TACO事件）+ CNN Truth Social存档。
在每日管线中运行，产物：data/trump_zone.json, data/truth_posts.json"""
import json, re, sys, datetime
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
OUT_TZ = "data/trump_zone.json"
OUT_TR = "data/truth_posts.json"

def strip_tags(s):
    s = re.sub(r"<!-- -->", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()

def fetch_ocmacro():
    r = requests.get("https://ocmacro.com/dashboard/trump", headers=UA, timeout=40)
    r.raise_for_status()
    html = r.text
    un = html.replace('\\"', '"').replace("\\n", "\n")

    # 1) 压力指数历史（含分项贡献）
    m = re.search(r'"history":(\[\{"date".*?\}\])', un)
    hist = json.loads(m.group(1))
    pressure = {
        "asof": hist[-1]["date"], "value": hist[-1]["value"],
        "latest_contrib": hist[-1]["contributions"],
        "history": [[h["date"], h["value"], h["contributions"].get("approval"), h["contributions"].get("dgs10"),
                     h["contributions"].get("move"), h["contributions"].get("sp500"), h["contributions"].get("vix"),
                     h["contributions"].get("bkevenpy02")] for h in hist],
    }

    # 2) 支持率序列（逐对象收集，含置信带）
    appr = []
    for mo in re.finditer(r'\{"date":"(\d{4}-\d{2}-\d{2})","dateLabel":"[^"]*","fullDateLabel":"[^"]*",'
                          r'"approve":([\d.]+),"disapprove":([\d.]+),"approveLo":([\d.]+),"approveHi":([\d.]+),'
                          r'"disapproveLo":([\d.]+),"disapproveHi":([\d.]+),"net":(-?[\d.]+)', un):
        g = mo.groups()
        appr.append({"date": g[0], "approve": round(float(g[1]), 2), "disapprove": round(float(g[2]), 2),
                     "net": round(float(g[7]), 2), "netLo": None, "netHi": None})
    seen = set(); appr2 = []
    for a in appr:
        if a["date"] not in seen:
            seen.add(a["date"]); appr2.append(a)
    appr2.sort(key=lambda x: x["date"])
    approval = {"asof": appr2[-1]["date"], "net": appr2[-1]["net"],
                "approve": appr2[-1]["approve"], "disapprove": appr2[-1]["disapprove"],
                "series": [[a["date"], a["net"]] for a in appr2]}

    # 3) 图表标注（SVG title）：压力图TACO标记 + 支持率图事件标记
    taco_marks, appr_marks = [], []
    for t in re.findall(r"<title>([^<]+)</title>", html):
        t = strip_tags(t)
        mm = re.match(r"^(\d{4}-\d{2}-\d{2}(?:\s*→\s*\d{4}-\d{2}-\d{2})?)\s*·\s*(强|最强|中|中强|地缘|财政)\s*·\s*(.+)$", t)
        if mm:
            taco_marks.append({"date": mm.group(1), "strength": mm.group(2), "text": mm.group(3)})
            continue
        mm2 = re.match(r"^(\d{4}-\d{2}-\d{2})\s*·\s*(.+)$", t)
        if mm2:
            appr_marks.append({"date": mm2.group(1), "text": mm2.group(2)})
    approval["annotations"] = appr_marks
    pressure["taco_marks"] = taco_marks

    # 4) TACO事件复盘（30条卡片）
    events = []
    for li in re.findall(r'<li class="[^"]*tacoEventItem[^"]*">(.*?)</li>', html, re.S):
        tm = re.search(r'<time dateTime="([^"]+)">([^<]+)</time>', li)
        st = re.search(r'tacoStrength[^"]*__[^"]*">([^<]+)</span>', li)
        h4 = re.search(r"<h4>([^<]+)</h4>", li)
        flow = re.findall(r"<p><span>(威胁|回撤)</span>(.*?)</p>", li, re.S)
        reason = re.search(r'tacoReason[^"]*">(.*?)</p>', li, re.S)
        detail = re.search(r'tacoEventDetail[^"]*">.*?<span>含义</span>(.*?)</p>', li, re.S)
        ev = {"end": tm.group(1) if tm else "", "range": strip_tags(tm.group(2)) if tm else "",
              "strength": strip_tags(st.group(1)) if st else "", "title": strip_tags(h4.group(1)) if h4 else "",
              "threat": "", "retreat": "",
              "reason": strip_tags(reason.group(1)) if reason else "",
              "implication": strip_tags(detail.group(1)) if detail else ""}
        for k, v in flow:
            ev["threat" if k == "威胁" else "retreat"] = strip_tags(v)
        if ev["title"]:
            events.append(ev)
    upd = re.search(r"更新至\s*([\d年月日\s]+)", html)

    return {"source": "ocmacro.com 川普dashboard（原始数据：Yahoo Finance/FRED/U.S. Treasury/Cleveland Fed/Silver Bulletin）",
            "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
            "pressure": pressure, "approval": approval,
            "taco_events": events, "taco_updated": strip_tags(upd.group(1)) if upd else ""}

def fetch_truths(limit=120):
    r = requests.get("https://ix.cnn.io/data/truth-social/truth_archive.json", headers=UA, timeout=60)
    r.raise_for_status()
    arr = r.json()
    posts = []
    for p in arr[:limit]:
        txt = strip_tags(p.get("content", ""))
        posts.append({"t": p.get("created_at", ""), "text": txt,
                      "url": p.get("url") or p.get("uri") or "",
                      "rt": bool(p.get("reblog"))})
    return {"source": "CNN Truth Social存档（ix.cnn.io，约每5分钟更新）",
            "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
            "total_in_archive": len(arr), "posts": posts}

if __name__ == "__main__":
    tz = fetch_ocmacro()
    with open(OUT_TZ, "w", encoding="utf-8") as f:
        json.dump(tz, f, ensure_ascii=False, separators=(",", ":"))
    print(f"trump_zone.json: 压力指数{len(tz['pressure']['history'])}点(最新{tz['pressure']['asof']} {tz['pressure']['value']}), "
          f"支持率{len(tz['approval']['series'])}点(最新{tz['approval']['asof']} {tz['approval']['net']}), "
          f"TACO事件{len(tz['taco_events'])}条, 标注{len(tz['pressure']['taco_marks'])}/{len(tz['approval']['annotations'])}")
    tr = fetch_truths()
    with open(OUT_TR, "w", encoding="utf-8") as f:
        json.dump(tr, f, ensure_ascii=False, separators=(",", ":"))
    print(f"truth_posts.json: {len(tr['posts'])}条, 存档共{tr['total_in_archive']}条, 最新{tr['posts'][0]['t'] if tr['posts'] else 'N/A'}")
