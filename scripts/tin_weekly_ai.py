import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CACHE = BASE / 'data' / 'tin_weekly_ai_cache.json'
NW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LABELS = ['价格', '供应', '需求', '库存', '策略', '关注点']
METRIC_NAMES = ['本周价格', '库存与结构', '需求与成交', '本周策略']


def source_hash(ppt, table_text, strategy):
    digest = hashlib.sha256()
    digest.update(ppt.read_bytes())
    digest.update(table_text.encode('utf-8'))
    digest.update('\n'.join(strategy).encode('utf-8'))
    return digest.hexdigest()


def prompt(table_text, strategy, asof):
    schema = '''{
  "headline": "完整的一段本周定调",
  "metrics": [
    {"name": "本周价格", "value": "价格周度表现及原因"},
    {"name": "库存与结构", "value": "库存与升贴水结构"},
    {"name": "需求与成交", "value": "需求与现货成交"},
    {"name": "本周策略", "value": "可执行策略与失效条件"}
  ],
  "summary": [
    {"label": "价格", "datum": "数据与边际", "conclusion": "判断", "direction": "方向"},
    {"label": "供应", "datum": "数据与边际", "conclusion": "判断", "direction": "方向"},
    {"label": "需求", "datum": "数据与边际", "conclusion": "判断", "direction": "方向"},
    {"label": "库存", "datum": "数据与边际", "conclusion": "判断", "direction": "方向"},
    {"label": "策略", "datum": "策略", "conclusion": "执行条件", "direction": "方向"},
    {"label": "关注点", "datum": "下周验证点", "conclusion": "跟踪重点", "direction": "方向"}
  ]
}'''
    return f'''你是永安期货有色金属研究员。请基于下面给定的事实，为 {asof} 这期锡周报重新创作中文摘要。
要求：
1. 必须重新组织句式，不得复述给定原文；观点由数据推导，不使用固定结论。
2. 只能使用输入中已有的数字、日期和事实。不得创造新数字、新闻、项目、政策或供需事件。缺数据就写“未提供”，不要猜测。
3. 同时检查价格、库存、升贴水、供给、需求和成交，给出明确但审慎的方向，以及可执行策略和失效条件。
4. 保留“价格/供应/需求/库存/策略/关注点”六个层级，文字适合网站展示，每格不超过160字。
5. 只输出一个合法 JSON 对象，不要 Markdown、注释、代码围栏或解释。JSON 结构如下：
{schema}

【PPT 综述表原文，仅供事实参考，禁止照抄】
{table_text}

【PPT 策略段原文，仅供事实参考，禁止照抄】
{chr(10).join(strategy)}
'''


def numeric_tokens(text):
    return [token.replace(',', '') for token in re.findall(r'-?\d[\d,]*(?:\.\d+)?', text)]


def validate_narrative(result, source_text):
    assert isinstance(result, dict), '结果不是 JSON 对象'
    assert isinstance(result.get('headline'), str) and len(result['headline']) >= 30, '定调过短'
    metrics = result.get('metrics')
    summary = result.get('summary')
    assert isinstance(metrics, list) and len(metrics) == 4, 'metrics 必须为4段'
    assert [item.get('name') for item in metrics] == METRIC_NAMES, 'metrics 名称或顺序错误'
    assert isinstance(summary, list) and len(summary) == 6, 'summary 必须为6行'
    assert [item.get('label') for item in summary] == LABELS, 'summary 标签或顺序错误'
    allowed = set(numeric_tokens(source_text))
    generated = numeric_tokens(json.dumps(result, ensure_ascii=False))
    unknown = sorted(set(generated) - allowed)
    assert not unknown, f'模型生成了输入外数字：{unknown[:12]}'


def generate_ai_narrative(ppt, table_text, strategy, asof):
    key = source_hash(ppt, table_text, strategy)
    if os.environ.get('TIN_AI_FORCE') != '1' and CACHE.exists():
        cached = json.loads(CACHE.read_text(encoding='utf-8'))
        if cached.get('key') == key:
            return cached['narrative'], cached.get('model', 'kimi-code-cli')
    source_text = table_text + '\n' + '\n'.join(strategy) + '\n' + asof
    request = prompt(table_text, strategy, asof)
    narrative = None
    errors = []
    for attempt in range(2):
        result = subprocess.run(['kimi', '-p', request], cwd=BASE, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=300, creationflags=NW)
        if result.returncode:
            raise RuntimeError('AI 综述生成失败：' + (result.stderr or result.stdout)[-500:])
        raw = result.stdout.strip()
        (BASE / '_logs' / 'tin_weekly_ai_last_raw.txt').write_text(raw, encoding='utf-8')
        start, end = raw.find('{'), raw.rfind('}')
        if start < 0 or end <= start:
            errors.append('未返回 JSON')
            continue
        try:
            candidate = json.loads(raw[start:end + 1])
            validate_narrative(candidate, source_text)
            narrative = candidate
            break
        except Exception as exc:
            errors.append(str(exc))
            request = request + '\n【上次输出的校验错误】' + errors[-1] + '\n请纠正所有输入外数字并重新输出完整 JSON，不得解释。\n'
    if narrative is None:
        raise RuntimeError('AI 综述两次校验均未通过：' + '；'.join(errors))
    model = 'kimi-code-cli'
    CACHE.write_text(json.dumps({'key': key, 'model': model, 'narrative': narrative}, ensure_ascii=False, indent=2), encoding='utf-8')
    log = BASE / '_logs' / f'tin_weekly_ai_{asof.replace("-", "")}.json'
    log.write_text(json.dumps({'model': model, 'prompt': request, 'response': narrative}, ensure_ascii=False, indent=2), encoding='utf-8')
    return narrative, model
