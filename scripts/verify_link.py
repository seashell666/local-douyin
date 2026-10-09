# -*- coding: utf-8 -*-
"""107（TOPAZ）侧联动验证脚本 —— 放到 107 电脑上运行

用法:  python verify_link.py
检测: 1) 105 火枭是否可达  2) 本机 LocalDouyin 是否已带 crawl 对接路由
"""
import json
import urllib.request

KEY = "huoxiao-2026"
HUOXIAO = "http://192.168.0.105:8100"
LOCAL_LD = "http://127.0.0.1:8000"


def get(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {str(e)[:120]}"


print("=== 火枭联动验证（在 107 上运行） ===\n")
s, body = get(f"{HUOXIAO}/v1/health", {"X-Api-Key": KEY})
print(f"[1] 105 火枭 /v1/health  -> HTTP {s}")
if s == 200:
    try:
        j = json.loads(body)
        print(f"    data: {j.get('data')}  => 数据链路 OK（107 可以调 105 拿数据）")
    except Exception:
        print(f"    body: {body[:150]}")
else:
    print("    => 数据链路不通：请检查 105 火枭是否在跑、105 防火墙是否放行 8100")

print()
s, body = get(f"{LOCAL_LD}/api/health")
print(f"[2] 本机 LocalDouyin /api/health -> HTTP {s}  body: {body[:80]}")
s, body = get(f"{LOCAL_LD}/api/crawl/status")
print(f"[3] 本机 /api/crawl/status       -> HTTP {s}")
if s == 200:
    print(f"    {body[:160]}")
    print("    => 对接桥已生效：LocalDouyin 已能经 /api/crawl/schedule 调火枭")
else:
    print("    => 对接桥未生效：crawl_bridge.py 还没部署，或服务没重启（见部署手册）")
