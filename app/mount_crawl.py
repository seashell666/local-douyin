# -*- coding: utf-8 -*-
"""main.py 挂载 crawl_bridge router"""
import io

p = r"F:\D\Android-Hook\LocalDouyin\local-douyin\app\main.py"
s = io.open(p, encoding="utf-8").read()

# 1. import
old_imp = "from . import db"
new_imp = "from . import db\nfrom .crawl_bridge import router as crawl_router"
if "crawl_bridge" not in s:
    assert old_imp in s, "import pattern missing"
    s = s.replace(old_imp, new_imp, 1)

# 2. include 在 app 定义后
old_app = 'app = FastAPI(title="local-douyin", version="0.2.0")'
new_app = old_app + '\napp.include_router(crawl_router)'
if "crawl_router" not in s.split(old_app, 1)[1].split("\n", 2)[1] if old_app in s else "":
    # 简单方式：在 app= 行后插 include
    if "app.include_router(crawl_router)" not in s:
        assert old_app in s, "app pattern missing"
        s = s.replace(old_app, new_app, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("OK: crawl_bridge mounted")
