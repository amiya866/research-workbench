# -*- coding: utf-8 -*-
"""Polymarket 政策预期抓取（在 GitHub Actions 运行——沙箱/国内网络到不了 polymarket）。
产物：data/polymarket.json（含CLOB历史曲线；CLOB失败时回退为每日快照累积）"""
import json, datetime, sys, os
import requests

UA = {"User-Agent": "Mozilla/5.0"}
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
TOPICS = ["Iran nuclear deal", "Strait of Hormuz", "Iran", "Hormuz traffic",
          "Fed rate hike", "Fed decision September", "US recession", "Fed rate decision",
          "government shutdown", "Trump approval rating", "tariff", "China trade",
          "Fed chair Powell", "midterm elections", "Senate 2026", "House 2026", "oil price"]
KEYWORDS = ["recession", "fed", "fomc", "rate cut", "rate decision", "senate", "congress",
            "approval", "tariff", "shutdown", "debt ceiling", "powell", "midterm", "house",
            "hormuz", "rate hike", "hike", "strait", "iran", "nuclear"]
CAP = 28
# 必抓市场（按slug定点, 放在名单最前）：参众两院控制权（2026中期选举）
TARGET_SLUGS = ["which-party-will-win-the-senate-in-2026", "which-party-will-win-the-house-in-2026"]

def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r.json()

def pick_from_events(events, picks, seen, cap):
    for ev in events:
        title = (ev.get("title") or "")
        for m in (ev.get("markets") or [])[:1]:
            ctoken = None
            try:
                ct = json.loads(m.get("clobTokenIds") or "[]")
                if ct:
                    ctoken = ct[0]
            except Exception:
                pass
            q = m.get("question") or title
            if q in seen:
                continue
            try:
                outs = json.loads(m.get("outcomes") or "[]")
                prcs = json.loads(m.get("outcomePrices") or "[]")
            except Exception:
                continue
            if not outs or not prcs or len(outs) != len(prcs):
                continue
            seen.add(q)
            picks.append({"question": q,
                          "outcomes": [{"name": o, "price": round(float(p), 4)} for o, p in zip(outs, prcs)],
                          "vol24": round(float(m.get("volume24hr") or ev.get("volume24hr") or 0)),
                          "end": (m.get("endDate") or ev.get("endDate") or "")[:10],
                          "slug": ev.get("slug") or m.get("slug") or "",
                          "ctoken": ctoken, "history": []})
        if len(picks) >= cap:
            break
    return picks

def fetch_history(token, days=400):
    """CLOB prices-history：返回 [[YYYY-MM-DD, price], ...]，失败返回 None"""
    if not token:
        return None
    for interval in ("max", "all"):
        try:
            r = requests.get(f"{CLOB}/prices-history", headers=UA, timeout=30,
                             params={"market": token, "interval": interval, "fidelity": 1440})
            if r.status_code != 200:
                continue
            hist = (r.json() or {}).get("history") or []
            pts = {}
            for h in hist:
                d = datetime.datetime.utcfromtimestamp(h["t"]).strftime("%Y-%m-%d")
                pts[d] = round(float(h["p"]), 4)
            out = [[d, pts[d]] for d in sorted(pts)]
            return out[-days:] if out else None
        except Exception:
            continue
    return None

def main():
    picks, seen = [], set()
    # 0) 必抓定点市场（slug直取, 最优先）
    for slug in TARGET_SLUGS:
        try:
            evs = get(f"{GAMMA}/events", params={"slug": slug})
            if not evs:
                # 兜底：部分市场只有 market 级 slug（如众议院控制权）
                mks = get(f"{GAMMA}/markets", params={"slug": slug})
                evs = [{"slug": slug, "title": mks[0].get("question") or slug,
                        "markets": mks}] if mks else []
            pick_from_events(evs or [], picks, seen, CAP)
        except Exception as e:
            print("slug fail:", slug, str(e)[:80])
    # 1) 定向主题搜索
    for topic in TOPICS:
        try:
            res = get(f"{GAMMA}/public-search", params={"q": topic, "limit_per_type": 4})
            pick_from_events(res.get("events") or [], picks, seen, CAP)
        except Exception as e:
            print("search fail:", topic, str(e)[:80])
    # 2) 高成交量榜补充（带关键词过滤）
    try:
        top = get(f"{GAMMA}/events", params={"limit": 200, "active": "true", "closed": "false",
                                             "order": "volume24hr", "ascending": "false"})
        us = [ev for ev in top if any(k in ((ev.get("title") or "") + " " + (ev.get("description") or "")).lower()
                                      for k in KEYWORDS)]
        pick_from_events(us, picks, seen, CAP)
    except Exception as e:
        print("top fail:", str(e)[:80])
    # 历史曲线：CLOB优先；失败则沿用上期文件累积今日快照
    old = {}
    if os.path.exists("data/polymarket.json"):
        try:
            for m0 in json.load(open("data/polymarket.json", encoding="utf-8")).get("markets", []):
                old[m0["question"]] = m0.get("history") or []
        except Exception:
            pass
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    n_hist, n_snap = 0, 0
    for p in picks:
        h = fetch_history(p.pop("ctoken", None))
        if h:
            p["history"] = h; n_hist += 1
        else:
            prev = [pt for pt in old.get(p["question"], []) if pt[0] != today]
            cur = p["outcomes"][0]["price"] if p["outcomes"] else None
            if cur is not None:
                prev.append([today, cur])
            p["history"] = prev[-400:]
            if prev: n_snap += 1
    out = {"source": "Polymarket Gamma/CLOB API（GitHub Actions每日更新）",
           "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
           "markets": picks}
    if not picks and old:  # 本地补丁：全源失败抓空时保留旧文件不清空
        print("polymarket.json: 本轮抓取为空，保留旧数据 %d 个市场" % len(old))
        return
    with open("data/polymarket.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"polymarket.json: {len(picks)} 个市场（CLOB历史{n_hist}个，快照累积{n_snap}个）")
    for p in picks:
        print(" -", p["question"][:70], "|", ", ".join(f"{o['name']} {o['price']*100:.0f}%" for o in p["outcomes"]))

if __name__ == "__main__":
    main()
