# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PATH = BASE / "tin-weekly" / "index.html"
text = PATH.read_text(encoding="utf-8")
match = re.search(r"const charts=(\{.*?\});\s*document", text, re.S)
charts = json.loads(match.group(1))


def set_month(key, label, values):
    chart = charts[key]
    index = chart["labels"].index(label)
    for dataset in chart["datasets"]:
        if not dataset["label"].startswith("2026年"):
            continue
        for suffix, value in values.items():
            if dataset["label"].endswith(suffix):
                dataset["data"][index] = value


def set_stats(key, label, value):
    global text
    pattern = r'(data-chart="' + re.escape(key) + r'"[^>]*></canvas></div></div><div class="cap">[^<]*</div><div class="stats">)最新标签 .*? ｜ 最新值 .*? ｜'
    text, count = re.subn(pattern, lambda m: m.group(1) + f"最新标签 {label} ｜ 最新值 {value} ｜", text, count=1)
    assert count == 1, (key, "stats")


set_month("px/p2s2c1.png", "10-31", {"进口量": 18095.0})
set_month("px/p2s2c4.png", "9.968", {"2026年": 4737.51})
set_stats("px/p2s2c4.png", "2026年 9.968", "4,738")
set_month("px/p2s2c5.png", "9.968", {"2026年": 2624.41})
set_stats("px/p2s2c5.png", "2026年 9.968", "2,624")
set_month("px/p2s2c6.png", "9.968", {"2026年": 18095.0})
set_stats("px/p2s2c6.png", "2026年 9.968", "18,095")
charts["px/p2s2c3.png"]["labels"] = ["刚果（金）", "缅甸", "尼日利亚", "澳大利亚", "玻利维亚"]
charts["px/p2s2c3.png"]["datasets"][0]["data"] = [17595, 13400, 8053, 7287, 2354]
text = text.replace("2026年1-9月中国锡精矿进口来源国（金属吨比）", "2026年1-10月中国锡精矿进口来源国（金属吨比）")
set_stats("px/p2s2c3.png", "玻利维亚", "2,354")
for key in ["t_refined.png", "px/p1s5c1.png"]:
    set_month(key, "10-31", {"进口": 3221.0, "出口": -1707.0})
    set_stats(key, "2026年｜出口 10-31", "-1,707")
set_month("px/p1s4c4.png", "9.968", {"2026年": 3221.0})
set_stats("px/p1s4c4.png", "2026年 9.968", "3,221")
for key in ["px/p1s4c5.png", "t_idnimp.png"]:
    set_month(key, "9.968", {"2026年": 2508.0})
    set_stats(key, "2026年 9.968", "2,508")
set_month("px/p1s4c6.png", "9.968", {"2026年": 150.0})
set_stats("px/p1s4c6.png", "2026年 9.968", "150")
set_month("s_bolimp.png", "9.968", {"2026年": 70.862})
set_stats("s_bolimp.png", "2026年 9.968", "70.9")
charts["px/p1s4c1.png"]["labels"] = ["印度尼西亚", "俄罗斯", "秘鲁", "马来西亚", "玻利维亚", "老挝", "其他"]
charts["px/p1s4c1.png"]["datasets"][0]["data"] = [2508, 352, 150, 80.525, 70.862, 32.21, 28.989]
text = text.replace("2026年1-9月锡锭主要进口国及占比", "2026年10月锡锭主要进口国及占比")
set_stats("px/p1s4c1.png", "其他", "29.0")

match = re.search(r"const charts=(\{.*?\});\s*document", text, re.S)
assert match
text = text[:match.start(1)] + json.dumps(charts, ensure_ascii=False, separators=(",", ":")) + text[match.end(1):]
match = re.search(r"const charts=(\{.*?\});\s*document", text, re.S)
parsed = json.loads(match.group(1))
chart = parsed["px/p2s2c6.png"]
index = chart["labels"].index("9.968")
dataset = next(ds for ds in chart["datasets"] if ds["label"] == "2026年")
assert dataset["data"][index] == 18095.0
PATH.write_text(text, encoding="utf-8")
print("TIN_CHART_JSON_VALID", len(parsed))
