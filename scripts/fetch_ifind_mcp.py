#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iFinD MCP 自动更新管线
优先级: 及时免费公开 API 优先; 对更新滞后/时效差的免费源改用 iFinD; Wind/Bloomberg 仅手工 Excel 补充

安全约束:
- 只从环境变量 IFIND_MCP_KEY 读取密钥
- 不把密钥写入任何文件、日志或网页
- iFinD 失败时保留既有序列, 不覆盖旧数据

输出:
- data/chart_series.js
- data/macro_catalog.js
- data/macro_series.json
- data/ifind_mcp_status.json
"""
import datetime as dt
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import requests

APP = Path(__file__).resolve().parents[1]
DATA = APP / "data"
CS_PATH = DATA / "chart_series.js"
CAT_PATH = DATA / "macro_catalog.js"
MS_PATH = DATA / "macro_series.json"
CFG_PATH = DATA / "ifind_mcp_series.json"
STATUS_PATH = DATA / "ifind_mcp_status.json"

MCP_BASE = "https://api-mcp.51ifind.com:8643/ds-mcp-servers"
SERVERS = {
    "stock": f"{MCP_BASE}/hexin-ifind-ds-stock-mcp",
    "fund": f"{MCP_BASE}/hexin-ifind-ds-fund-mcp",
    "edb": f"{MCP_BASE}/hexin-ifind-ds-edb-mcp",
    "news": f"{MCP_BASE}/hexin-ifind-ds-news-mcp",
    "bond": f"{MCP_BASE}/hexin-ifind-ds-bond-mcp",
    "global_stock": f"{MCP_BASE}/hexin-ifind-ds-global-stock-mcp",
    "index": f"{MCP_BASE}/hexin-ifind-ds-index-mcp",
}

BJT = dt.timezone(dt.timedelta(hours=8))
TODAY = dt.datetime.now(BJT).date()
DEFAULT_END = TODAY.strftime("%Y%m%d")


def log(*args):
    print(dt.datetime.now(BJT).strftime("%H:%M:%S"), *args, flush=True)


def now_bjt():
    return dt.datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S 北京")


def load_json_js(path, left, right):
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index(left):text.rindex(right) + 1])


def load_chart_series():
    if not CS_PATH.exists():
        return {}
    return load_json_js(CS_PATH, "{", "}")


def save_chart_series(cs):
    tmp = CS_PATH.with_suffix(CS_PATH.suffix + ".tmp")
    tmp.write_text(
        "window.CHART_SERIES = " + json.dumps(cs, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8",
    )
    os.replace(tmp, CS_PATH)


def load_catalog():
    if not CAT_PATH.exists():
        return []
    return load_json_js(CAT_PATH, "[", "]")


def save_catalog(cat):
    tmp = CAT_PATH.with_suffix(CAT_PATH.suffix + ".tmp")
    tmp.write_text(
        "window.MACRO_CATALOG = " + json.dumps(cat, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8",
    )
    os.replace(tmp, CAT_PATH)


def load_macro_series():
    if not MS_PATH.exists():
        return {"updated": now_bjt(), "sections": []}
    try:
        return json.loads(MS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"updated": now_bjt(), "sections": []}


def save_macro_series(ms):
    tmp = MS_PATH.with_suffix(MS_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(ms, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, MS_PATH)


def load_config():
    if not CFG_PATH.exists():
        raise FileNotFoundError(f"缺少配置文件: {CFG_PATH}")
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    entries = cfg.get("series")
    if not isinstance(entries, list) or not entries:
        raise ValueError("ifind_mcp_series.json 中 series 为空")
    return entries


class IFindMCPError(RuntimeError):
    pass


class IFindMCP:
    """最小 iFinD StreamableHTTP MCP 客户端。"""

    def __init__(self, token):
        self.token = token.strip()
        if not self.token:
            raise IFindMCPError("IFIND_MCP_KEY 为空")
        self.http = requests.Session()
        self.auth = None
        self.sessions = {}
        self.req_ids = {}
        self.tool_sets = {}

    def _next_id(self, server_type):
        self.req_ids[server_type] = self.req_ids.get(server_type, 0) + 1
        return self.req_ids[server_type]

    def _headers(self, server_type=None):
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.auth or self.token,
            "User-Agent": "research-workbench-ifind-mcp/1.0",
        }
        if server_type and server_type in self.sessions:
            h["Mcp-Session-Id"] = self.sessions[server_type]
        return h

    @staticmethod
    def _parse_response(resp):
        text = resp.text or ""
        if not text.strip():
            return None
        try:
            return resp.json()
        except Exception:
            pass
        # 兼容 text/event-stream: 提取 data: 行中的 JSON
        events = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                events.append(json.loads(payload))
            except Exception:
                continue
        if events:
            return events[-1]
        return text

    def _post(self, server_type, payload, timeout=60):
        if server_type not in SERVERS:
            raise IFindMCPError(f"未知 server_type: {server_type}")
        resp = self.http.post(
            SERVERS[server_type],
            json=payload,
            headers=self._headers(server_type),
            timeout=timeout,
        )
        return resp, self._parse_response(resp)

    def _initialize(self, server_type):
        if server_type in self.sessions:
            return
        candidates = [self.token]
        if not self.token.lower().startswith("bearer "):
            candidates.append("Bearer " + self.token)
        last_error = None
        for auth in candidates:
            self.auth = auth
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(server_type),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "research-workbench", "version": "1.0"},
                },
            }
            try:
                resp, data = self._post(server_type, payload, timeout=30)
                if resp.status_code in (401, 403):
                    last_error = f"HTTP {resp.status_code} 鉴权失败"
                    continue
                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}"
                    continue
                if isinstance(data, dict) and data.get("error"):
                    last_error = str(data.get("error"))[:300]
                    continue
                session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if not session_id:
                    last_error = "initialize 未返回 Mcp-Session-Id"
                    continue
                self.sessions[server_type] = session_id
                notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                self._post(server_type, notify, timeout=10)
                return
            except Exception as exc:
                last_error = repr(exc)[:300]
        raise IFindMCPError(last_error or "iFinD MCP initialize 失败")

    def list_tools(self, server_type):
        self._initialize(server_type)
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(server_type),
            "method": "tools/list",
            "params": {},
        }
        resp, data = self._post(server_type, payload, timeout=60)
        if isinstance(data, dict) and data.get("error"):
            raise IFindMCPError(str(data["error"])[:500])
        if resp.status_code >= 400:
            raise IFindMCPError(f"HTTP {resp.status_code}")
        tools = (((data or {}).get("result") or {}).get("tools"))
        if not isinstance(tools, list):
            raise IFindMCPError("tools/list 返回格式异常")
        return tools

    def _tool_set(self, server_type):
        if server_type not in self.tool_sets:
            tools = self.list_tools(server_type)
            self.tool_sets[server_type] = {
                t.get("name") for t in tools if isinstance(t, dict) and t.get("name")
            }
        return self.tool_sets[server_type]

    def call(self, server_type, tool_name, params):
        allowed = self._tool_set(server_type)
        if tool_name not in allowed:
            raise IFindMCPError(f"工具不可用: {server_type}/{tool_name}")
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(server_type),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": params},
        }
        resp, data = self._post(server_type, payload, timeout=120)
        if isinstance(data, dict) and data.get("error"):
            raise IFindMCPError(str(data["error"])[:500])
        if resp.status_code >= 400:
            raise IFindMCPError(f"HTTP {resp.status_code}")
        return data


# ---------- 序列解析 ----------
NUM_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")


def parse_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if math.isfinite(v) else None
    if not isinstance(value, str):
        return None
    s = value.strip().replace(",", "").replace("%", "")
    s = s.replace("－", "-").replace("—", "-")
    if not NUM_RE.match(s):
        return None
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def normalize_date(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 兼容 Excel/Unix 毫秒时间戳以外的纯 YYYYMMDD 数字
        iv = int(value)
        if 19000101 <= iv <= 21001231:
            value = str(iv)
        else:
            return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    s = s.replace("年", "-").replace("月", "-").replace("日", "")
    s = s.replace("/", "-").replace(".", "-")
    m = re.match(r"^(20\d{2}|19\d{2})\s*[Qq]\s*([1-4])$", value.strip())
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        return f"{y:04d}-{q * 3:02d}-01"
    # YYYYMMDD / YYYYMM
    m = re.match(r"^(19\d{2}|20\d{2})(\d{2})(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(19\d{2}|20\d{2})(\d{2})$", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{m.group(2)}-01"
    # YYYY-M-D 或 YYYY-M
    m = re.match(r"^(19\d{2}|20\d{2})-(\d{1,2})(?:-(\d{1,2}))?", s)
    if m and 1 <= int(m.group(2)) <= 12:
        day = int(m.group(3) or 1)
        if 1 <= day <= 31:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{day:02d}"
    return None


def date_in_range(date_s):
    if not date_s:
        return False
    try:
        d = dt.date.fromisoformat(date_s)
    except Exception:
        return False
    return dt.date(1990, 1, 1) <= d <= TODAY + dt.timedelta(days=370)


def _pairs_from_rows(rows):
    out = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        d = normalize_date(row[0])
        v = parse_number(row[1])
        if d and v is not None and date_in_range(d):
            out[d] = v
    return [[d, out[d]] for d in sorted(out)]


def _pairs_from_dicts(rows):
    out = {}
    date_key_re = re.compile(r"date|time|日期|时间|月份|报告期|统计期", re.I)
    value_key_re = re.compile(r"value|数值|最新|数据|收盘|点数|余额|同比|指标", re.I)
    bad_num_key_re = re.compile(r"date|time|year|month|day|id|count|排名|序号|日期|时间", re.I)
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_value = None
        for k, v in row.items():
            if date_key_re.search(str(k)):
                date_value = normalize_date(v)
                if date_value:
                    break
        if not date_value and len(row) == 2:
            # 两字段结构时允许第一个字段是日期
            vals = list(row.values())
            date_value = normalize_date(vals[0])
        if not date_value or not date_in_range(date_value):
            continue
        numeric = []
        for k, v in row.items():
            if bad_num_key_re.search(str(k)):
                continue
            num = parse_number(v)
            if num is not None:
                numeric.append((str(k), num))
        if not numeric:
            continue
        preferred = [x for x in numeric if value_key_re.search(x[0])]
        value = (preferred or numeric)[0][1]
        out[date_value] = value
    return [[d, out[d]] for d in sorted(out)]


TEXT_PAIR_RE = re.compile(
    r"((?:19|20)\d{2}[-/年.]\d{1,2}(?:(?:[-/月.]\d{1,2})日?|月?)|[12][09]\d{6}|[12][09]\d{4})\s*[\|：:，,、\t ]+\s*(-?\d[\d,]*(?:\.\d+)?)\s*(?:%|百分点|亿元|万亿元|点|元|亿美元|万人|千人)?"
)


def _pairs_from_text(text):
    out = {}
    for m in TEXT_PAIR_RE.finditer(text):
        d = normalize_date(m.group(1))
        v = parse_number(m.group(2))
        if d and v is not None and date_in_range(d):
            out[d] = v
    return [[d, out[d]] for d in sorted(out)]


def extract_series(payload):
    """从 MCP JSON-RPC / Markdown / 文本结果中提取最可能的日期-数值序列。"""
    candidates = []

    def add(candidate):
        if isinstance(candidate, list) and len(candidate) >= 3:
            candidates.append(candidate)

    def walk(obj):
        if obj is None:
            return
        if isinstance(obj, str):
            s = obj.strip()
            if not s:
                return
            # 有些 content.text 内嵌 JSON
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    walk(json.loads(s))
                except Exception:
                    pass
            add(_pairs_from_text(s))
            return
        if isinstance(obj, list):
            if obj and all(isinstance(x, (list, tuple)) for x in obj):
                add(_pairs_from_rows(obj))
            if obj and all(isinstance(x, dict) for x in obj):
                add(_pairs_from_dicts(obj))
            for item in obj:
                walk(item)
            return
        if isinstance(obj, dict):
            # 常见结构: {"time": [...], "value": [...]} 或 {"dates": [...], "values": [...]}
            keys = list(obj.keys())
            list_keys = [k for k in keys if isinstance(obj.get(k), list)]
            if len(list_keys) >= 2:
                for dk in list_keys:
                    for vk in list_keys:
                        if dk == vk:
                            continue
                        if re.search(r"date|time|日期|时间|月份", str(dk), re.I) and re.search(
                            r"value|data|数值|数据|close|指标", str(vk), re.I
                        ):
                            add(_pairs_from_rows(list(zip(obj[dk], obj[vk]))))
            add(_pairs_from_dicts([obj]))
            for value in obj.values():
                walk(value)

    walk(payload)
    if not candidates:
        return []
    # 选点数最多且日期跨度最大的候选，避免误取查询参数中的日期
    best = max(candidates, key=lambda x: (len(x), x[-1][0]))
    dedup = {d: v for d, v in best if date_in_range(d)}
    return [[d, dedup[d]] for d in sorted(dedup)]


def apply_scale(series, mode):
    if not series or not mode or mode == "none":
        return series
    latest = abs(series[-1][1]) if series[-1][1] is not None else 0
    factor = 1.0
    if mode == "money_to_yi" and latest and latest < 100000:
        factor = 10000.0  # 万亿元 → 亿元
    elif mode == "money_to_wan" and latest and latest > 10000:
        factor = 0.0001  # 亿元 → 万亿元
    return [[d, round(v * factor, 6)] for d, v in series]


def finish_series(series, cfg):
    scale = cfg.get("scale", "none")
    series = apply_scale(series, scale)
    decimals = int(cfg.get("decimals", 4))
    limit = int(cfg.get("limit", 500))
    out = [[d, round(v, decimals)] for d, v in series if v is not None]
    return out[-limit:]


def upsert_catalog(cat, item_id, name, unit):
    for item in cat:
        if item.get("id") == item_id:
            item["name"] = name
            item["unit"] = unit
            return False
    cat.append({"id": item_id, "name": name, "unit": unit})
    return True


def update_macro_series(ms, updates):
    """updates: {id: {name, unit, section, series}}; 只在对应项已存在时更新, 否则追加主 id。"""
    sections = ms.setdefault("sections", [])
    by_key = {s.get("key"): s for s in sections}
    by_id = {}
    for sec in sections:
        for item in sec.get("items", []):
            by_id[item.get("id")] = (sec, item)
    for item_id, info in updates.items():
        name = info["name"]
        unit = info["unit"]
        series = info["series"]
        src = info.get("src", "L1·iFinD MCP")
        last = series[-1] if series else [None, None]
        if item_id in by_id:
            _, item = by_id[item_id]
            item.update({"name": name, "unit": unit, "src": src, "n": len(series), "last": last})
            continue
        if info.get("skip_append"):
            continue
        sec_key = info.get("section") or "cn"
        sec_name = info.get("section_name") or "美中竞赛"
        sec = by_key.get(sec_key)
        if sec is None:
            sec = {"key": sec_key, "name": sec_name, "items": []}
            sections.append(sec)
            by_key[sec_key] = sec
        sec.setdefault("items", []).append(
            {"id": item_id, "name": name, "unit": unit, "src": src, "n": len(series), "last": last}
        )
        by_id[item_id] = (sec, sec["items"][-1])


def build_params(entry):
    tool = entry.get("tool", "get_edb_data")
    if "params" in entry and isinstance(entry["params"], dict):
        return dict(entry["params"])
    query = entry.get("query") or entry.get("name")
    start = entry.get("start", "200001")
    end = entry.get("end", DEFAULT_END)
    if tool == "get_edb_data":
        return {"query": f"{query}（{start}-{end}）"}
    return {"query": str(query)}


def main():
    token = os.environ.get("IFIND_MCP_KEY", "").strip()
    if not token:
        status = {
            "updated": now_bjt(),
            "source": "iFinD MCP",
            "ok": [],
            "failed": {},
            "skipped": "未配置 GitHub Secret IFIND_MCP_KEY，已保留及时免费公开源数据",
            "note": "及时免费 API 优先；滞后免费源才由 iFinD 替代；密钥不写入仓库",
        }
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        log("IFIND_MCP_SKIP: 未配置 GitHub Secret IFIND_MCP_KEY，保留免费源数据")
        return 0
    entries = load_config()
    cs = load_chart_series()
    cat = load_catalog()
    ms = load_macro_series()
    client = IFindMCP(token)
    status = {
        "updated": now_bjt(),
        "source": "iFinD MCP",
        "ok": [],
        "failed": {},
        "note": "iFinD 优先；失败时保留免费公开源旧数据；密钥不写入仓库",
    }
    updates = {}
    changed = set()
    delay = float(os.environ.get("IFIND_MCP_DELAY", "0.6"))
    only_selfcheck = "--selfcheck" in sys.argv

    # 先做一次轻量预检: 密钥/权限/网络失败时不重复打 21 次接口
    try:
        tools = client.list_tools("edb")
        status["available_tools"] = [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]
        log("iFinD MCP 预检通过: EDB工具数", len(status["available_tools"]))
    except Exception as exc:
        err = str(exc).replace(token, "***")[:500]
        status["failed"]["__preflight__"] = err
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        log("IFIND_MCP_PRECHECK_FAIL:", err)
        return 0

    for idx, entry in enumerate(entries, 1):
        item_id = entry["id"]
        server_type = entry.get("server_type", "edb")
        tool = entry.get("tool", "get_edb_data")
        name = entry.get("name", item_id)
        unit = entry.get("unit", "")
        try:
            params = build_params(entry)
            log(f"iFinD {idx}/{len(entries)} {item_id}: {tool} {params.get('query', '')[:70]}")
            result = client.call(server_type, tool, params)
            if only_selfcheck:
                status["ok"].append({"id": item_id, "tool": tool, "selfcheck": True})
                continue
            series = finish_series(extract_series(result), entry)
            if len(series) < int(entry.get("min_points", 3)):
                raise IFindMCPError(f"可解析数据点不足: {len(series)}")
            ids = [item_id] + list(entry.get("aliases") or [])
            old_latest = (cs.get(item_id) or [[None, None]])[-1]
            for target_id in ids:
                cs[target_id] = series
                upsert_catalog(cat, target_id, entry.get("alias_names", {}).get(target_id, name), unit)
                updates[target_id] = {
                    "name": entry.get("alias_names", {}).get(target_id, name),
                    "unit": unit,
                    "section": entry.get("section", "cn"),
                    "section_name": entry.get("section_name", "美中竞赛"),
                    "series": series,
                    "src": entry.get("src", "L1·iFinD MCP/EDB"),
                    "skip_append": target_id != item_id,
                }
                changed.add(target_id)
            status["ok"].append(
                {"id": item_id, "tool": tool, "points": len(series), "before": old_latest, "latest": series[-1]}
            )
            log(f"  ✓ {item_id}: {len(series)}点, 最新 {series[-1][0]} = {series[-1][1]}")
        except Exception as exc:
            err = str(exc).replace(token, "***")[:500]
            status["failed"][item_id] = err
            log(f"  x {item_id}: {err}")
        time.sleep(delay)

    if only_selfcheck:
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"自检完成: 成功{len(status['ok'])} 失败{len(status['failed'])}")
        return 0 if status["ok"] else 1

    if changed:
        save_chart_series(cs)
        save_catalog(cat)
        ms["updated"] = now_bjt()
        update_macro_series(ms, updates)
        save_macro_series(ms)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"完成: 成功{len(status['ok'])} 失败{len(status['failed'])} 更新键{len(changed)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        token = os.environ.get("IFIND_MCP_KEY", "")
        msg = str(exc)
        if token:
            msg = msg.replace(token, "***")
        log("IFIND_MCP_FATAL:", msg[:500])
        raise SystemExit(0)
