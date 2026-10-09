# -*- coding: utf-8 -*-
"""本地补丁（2026-10-08）：Yahoo Finance 在本机直连 403，走本机 Clash 代理(7897)可通。
各 fetch 脚本 import 本模块拿 YAHOO_SESSION；RW_PROXY 环境变量可覆盖代理地址。"""
import os

PROXY = os.environ.get('RW_PROXY', 'http://127.0.0.1:7897')
_PROXIES = {'http': PROXY, 'https': PROXY}

try:
    from curl_cffi import requests as _creq
    YAHOO_SESSION = _creq.Session(impersonate='chrome', proxies=_PROXIES)
except Exception:
    import requests as _req
    YAHOO_SESSION = _req.Session()
    YAHOO_SESSION.proxies = _PROXIES
