# -*- coding: utf-8 -*-
"""三站消息快照抓取器: 金十(PLUS)+先讯(VIP实时)+CS财经 -> data/news_latest.json + news_fallback.js
   令牌优先读环境变量(GitHub Actions secrets), 沙箱内回退读 .cache 文件"""
import json, os, re, requests
from datetime import datetime, timezone, timedelta
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,'data','news_latest.json')
C='/mnt/agents/output/凭证与API档案'
BJT=timezone(timedelta(hours=8))
now=datetime.now(BJT).strftime('%Y-%m-%d %H:%M')
TAG=re.compile(r'<[^>]+>')
def clean(s): return TAG.sub('',s or '').replace('&nbsp;',' ').strip()
def _cache_token(name):
    try: return json.load(open(os.path.join(C,name)))['token']
    except Exception: return None

def fetch_jin10():
    tok=os.environ.get('JIN10_TOKEN') or _cache_token('jin10_token.json')
    r=requests.get('https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1&max_time=',
        headers={'x-app-id':'rU6QIu7JHe2gOUeR','x-version':'1.0.0','x-token':tok},timeout=25)
    items=[]
    for it in (r.json().get('data') or []):
        d=it.get('data') or {}
        content=clean(d.get('content') or d.get('title') or '')
        t=it.get('time') or ''
        if not t and it.get('id'):
            m=it['id']; t=f'{m[0:4]}-{m[4:6]}-{m[6:8]} {m[8:10]}:{m[10:12]}:{m[12:14]}'
        if not content: continue
        items.append({'src':'jin10','time':t,'ts':t,'content':content,
                      'important':it.get('important',0),'vip':1 if it.get('vip') else 0,
                      'tags':[k.get('name','') for k in (it.get('kinds') or []) if k.get('name')],
                      'id':it.get('id')})
    return items

def fetch_ah():
    sess=os.environ.get('AH_SESSION')
    ck={'session':sess} if sess else {}
    if not ck:
        for line in open(os.path.join(C,'ah_cookies.txt')):
            if line.startswith('#HttpOnly_'): line=line[len('#HttpOnly_'):]
            elif line.startswith('#') or not line.strip(): continue
            p=line.strip().split('\t')
            if len(p)>=7: ck[p[5]]=p[6]
    r=requests.get('https://api.alphaheartbeat.com:8443/api/news?page=1&size=30',cookies=ck,timeout=25)
    j=r.json(); items=[]
    for it in (j.get('items') or []):
        items.append({'src':'ah','time':it.get('time_str',''),'ts':'2026-'+it.get('time_str',''),
                      'content':it.get('title_cn',''),'logic':it.get('ai_logic',''),
                      'sentiment':it.get('sentiment',''),'level':it.get('level',''),
                      'source':it.get('source',''),'importance':it.get('importance_score',0)})
    return items, j.get('access_mode')

def fetch_cs():
    # 2026-10-08 本地改写：旧接口(api.cnthesims.com/index.php)已随站点重构下线，
    # 新站 FastAPI 匿名可取，但 /updates 需 X-Sign 签名（client-key + HMAC-SHA256，分隔符\n）
    import hashlib, hmac, time, binascii
    BASE='http://csme.cnthesims.com/api'
    ck=requests.get(BASE+'/client-key',headers={'User-Agent':'Mozilla/5.0'},timeout=10).json()
    key=ck['key']; off=ck.get('server_time',int(time.time()))-int(time.time())
    p={'since':0,'limit':40,'hasTitle':'true','since_id':0}
    ps='&'.join(sorted('%s=%s'%(k,v) for k,v in p.items()))
    ts=str(int(time.time())+off); nonce=binascii.hexlify(os.urandom(8)).decode()
    msg='\n'.join(['GET','/api/updates',ps,ts,nonce])
    sig=ts+'.'+nonce+'.'+hmac.new(key.encode(),msg.encode(),hashlib.sha256).hexdigest()
    r=requests.get(BASE+'/updates',params=p,headers={'X-Sign':sig,'User-Agent':'Mozilla/5.0'},timeout=25)
    j=r.json()
    ZW=re.compile('[​‌‍⁠﻿­︀-️]')  # 新站正文嵌零宽字符水印，须剥掉
    items=[]
    for ev in (j.get('events') or []):
        content=clean(ZW.sub('',ev.get('title') or ''))
        if not content: continue
        t=datetime.fromtimestamp(ev.get('published_at',0),BJT).strftime('%Y-%m-%d %H:%M')
        items.append({'src':'cs','time':t,'ts':t,'content':content,
                      'tags':ev.get('labels') or [],'id':ev.get('id')})
    return items

out={'asof':now,'sources':[],'jin10':[],'ah':[],'cs':[]}
# 保留本脚本不负责的增量源键（东财/新浪/LME 等由 fetch_extra_news.py 维护）
if os.path.exists(OUT):
    try:
        _prev=json.load(open(OUT,encoding='utf-8'))
        for _k,_v in _prev.items():
            if _k not in out:
                out[_k]=_v
    except Exception:
        pass
try:
    out['jin10']=fetch_jin10()
    out['sources'].append({'name':'金十·PLUS实时','ok':True,'n':len(out['jin10'])})
except Exception as e:
    out['sources'].append({'name':'金十','ok':False,'err':str(e)[:120]})
try:
    ah_items,mode=fetch_ah(); out['ah']=ah_items
    out['sources'].append({'name':'先讯·VIP实时' if mode=='realtime' else '先讯·延时','ok':True,'mode':mode,'n':len(ah_items)})
except Exception as e:
    out['sources'].append({'name':'先讯','ok':False,'err':str(e)[:120]})
try:
    out['cs']=fetch_cs()
    out['sources'].append({'name':'CS财经·实时','ok':True,'n':len(out['cs'])})
except Exception as e:
    out['sources'].append({'name':'CS财经','ok':False,'err':str(e)[:120]})
os.makedirs(os.path.dirname(OUT),exist_ok=True)
with open(OUT,'w',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False)
open(OUT.replace('news_latest.json','news_fallback.js'),'w',encoding='utf-8').write('window.NEWS_SNAP='+json.dumps(out,ensure_ascii=False)+';')
print(json.dumps({'asof':now,'sources':out['sources'],'counts':{k:len(out[k]) for k in ('jin10','ah','cs')}},ensure_ascii=False))
