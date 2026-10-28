# -*- coding: utf-8 -*-
"""地缘事件链自动追加（2026-10-14 建，挂 _refresh_all.py 全链尾部 _daily_report 之前）
背景：data/geopolitics.json 原是人工汇编层（L2），9/15 后无人维护致日报「三条边际变化」
事件链冻结一个月。本脚本从每日新闻快照（news_latest.json: cs/eastmoney/sina/jin10/lme）
按线别关键词提取候选事件追加，人工汇编仍可直改本文件（去重按 日期+标题前10字）。
口径：标题=【】内文本，无则取前 24 字；detail=正文前 60 字；tag 按关键词启发式
（esc=升级/ease=缓和/game=博弈），人工可事后改 tag。每条线每次最多追加 2 条，
每线保留最近 40 条。低置信来源（自媒体）不进——快照源本身已是金十/CS/东财/新浪快讯。
用法: python _geo_events.py
"""
import os, re, json, io, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, 'data', 'geopolitics.json')
NEWS = os.path.join(BASE, 'data', 'news_latest.json')

LINE_RULES = {
    'usiran': re.compile(r'霍尔木兹|伊朗.{0,12}(海峡|油轮|封锁|革命卫队)|革命卫队.{0,12}(海峡|船只|油轮|商船)'),
    'gulf': re.compile(r'胡塞|曼德海峡|红海.{0,10}(袭|船|港口)|也门.{0,10}(政府军|沙特|联军)|沙特.{0,10}(胡塞|也门|空袭)'),
}
ESC_KW = re.compile(r'袭击|打击|击中|击沉|封锁|关闭|扣押|登船|导弹|无人机|空袭|攻占|沦陷')
EASE_KW = re.compile(r'停火|协议|谈判|重开|复航|恢复通航|解除|缓和|停攻|夺回|收复|反攻|回升')
DIGEST_KW = re.compile(r'新闻精选|早间|午间|晚间|早报|晚报|日报|汇编|要闻')
MAX_ADD_PER_LINE = 2
KEEP_EVENTS = 40


def title_of(content):
    m = re.search(r'【(.{4,60}?)】', content or '')
    if m:
        return m.group(1)
    return re.sub(r'\s+', '', (content or ''))[:24]


def main():
    geo = json.load(io.open(GEO, encoding='utf-8'))
    news = json.load(io.open(NEWS, encoding='utf-8'))
    items = []
    for k in ('cs', 'eastmoney', 'sina', 'jin10', 'lme'):
        for it in (news.get(k) or []):
            if it.get('content') and it.get('time'):
                items.append(it)
    added = 0
    for line in geo.get('lines', []):
        rule = LINE_RULES.get(line.get('id'))
        if not rule:
            continue
        existing_keys = {(e[0], re.sub(r'\s+', '', e[1])[:10]) for e in line['events']}
        n = 0
        for it in items:
            if n >= MAX_ADD_PER_LINE:
                break
            c = it['content']
            t = title_of(c)
            # 标题优先；具体单条允许正文命中，但新闻精选/早报等汇编仍排除
            if not (rule.search(t) or (rule.search(c) and not DIGEST_KW.search(t))):
                continue
            date = (it.get('time') or '')[:10]
            if not re.match(r'\d{4}-\d{2}-\d{2}$', date):
                continue
            key = (date, re.sub(r'\s+', '', t)[:10])
            if key in existing_keys:
                continue
            if any(key[1] and key[1] in re.sub(r'\s+', '', e[1]) for e in line['events']):
                continue
            tag = 'esc' if ESC_KW.search(c) else ('ease' if EASE_KW.search(c) else 'game')
            body_source = re.sub(r'【.{4,60}?】', '', c).replace(t, '', 1)
            body = re.sub(r'\s+', '', re.sub(r'^\s*[｜|]\s*', '', body_source))[:90]
            line['events'].append([date, t[:30], tag, body + '（⚙️' + it.get('src', '') + '快讯）'])
            existing_keys.add(key)
            n += 1
            added += 1
        line['events'].sort(key=lambda e: e[0])
        if len(line['events']) > KEEP_EVENTS:
            line['events'] = line['events'][-KEEP_EVENTS:]
    if added:
        geo['updated'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M') + ' 北京(⚙️快讯自动追加%d条)' % added
        json.dump(geo, io.open(GEO, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('geo_events: added=%d' % added)


if __name__ == '__main__':
    main()
