# -*- coding: utf-8 -*-
"""P6 全链路验收：LocalDouyin /api/crawl/schedule → 火枭采集 → 落库"""
import json
import sys
import time

import requests

LD = "http://127.0.0.1:8123"
SEC = "MS4wLjABAAAAWMDSHY8f0C6DdNGkj7XJJvAda4BhoL4bfMOYrtVr2gw"  # 小满（公开收藏+喜欢）

# 1. LocalDouyin 编排：请求火枭采小满的 visibility + collects（游客维度）
body = {"nodes": [{"sec_uid": SEC, "nickname": "小满", "weight": 0.8,
                   "dims": ["visibility", "collects"]}], "max_per_dim": 20}
print("== schedule 请求 ==")
r = requests.post(f"{LD}/api/crawl/schedule", json=body, timeout=180)
print("http:", r.status_code)
j = r.json()
print("summary:", json.dumps(j.get("data", {}), ensure_ascii=False)[:600])

# 2. 验证落库
print("\n== 落库验证 ==")
s = requests.get(f"{LD}/api/crawl/status", timeout=10).json()
print("status:", json.dumps(s["data"], ensure_ascii=False))
