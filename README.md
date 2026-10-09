# local-douyin · 本地家庭抖音（MVP）

在自家服务器上跑一个"只有你能看到"的抖音：手机浏览器打开即刷，上下滑动看视频，内容完全由你管控。

## 当前状态（MVP 已跑通）

- 后端：FastAPI + SQLite（零配置单文件数据库）
- 前端：手机端类抖音滑动 UI（触摸上下滑、自动播放、静音循环、预加载下一屏、点击开声音）
- 内容：视频文件 + 元数据（作者/标题自动从文件名解析）
- 视频流支持 Range（可拖动进度条）

## 一、本机（topaz）直接跑

```powershell
# 首次
venv\Scripts\pip install -r requirements.txt
# 导入视频（把文件夹里的 mp4 移入 data/videos 并入库）
venv\Scripts\python scripts\import_videos.py "C:\你的视频文件夹"
# 启动
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

手机和服务器在同一局域网时，手机浏览器打开 `http://<本机IP>:8000` 即可刷视频。

## 二、Ubuntu + Docker 部署（正式形态）

把整个 `local-douyin/` 文件夹同步到 Ubuntu（网盘/移动硬盘均可），然后：

```bash
cd local-douyin
# 导入视频（把视频文件夹拷到 Ubuntu 后）
python3 scripts/import_videos.py /path/to/你的视频文件夹   # 或直接往 data/videos 里放文件
# 一键启动
docker compose up -d --build
```

手机浏览器访问 `http://192.168.0.27:8000`（你的 Ubuntu IP）。

> 提示：Docker 部署时 `data/` 是挂载卷，往宿主机的 `data/videos/` 里放视频文件后，还需要在数据库登记一条记录（或等阶段 2 的自动抓取管道接管）。

## 三、常用操作

| 操作 | 命令/说明 |
|---|---|
| 导入新视频 | `python scripts/import_videos.py <文件夹>`（自动解析作者/标题，跳过重复） |
| 只登记不移动 | `python scripts/import_videos.py --move=no <文件夹>` |
| 查看全部视频 | `GET /api/videos?offset=0&limit=20` |
| 视频流 | `GET /api/videos/{id}/stream`（支持 Range） |
| 健康检查 | `GET /api/health` |

## 四、目录结构（2026-10-09）

```
local-douyin/
├── app/                  # 当前权威整合后端
│   ├── main.py           # FastAPI 路由（列表/作者/视频流/行为上报/静态页）
│   ├── db.py             # SQLite（videos/authors/behavior_events/peer_* /幂等批次）
│   ├── crawl_bridge.py   # 采集桥（详情/评论/媒体 + 幂等）
│   ├── mp4_metadata.py / mount_crawl.py
│   ├── curation/         # 策展引擎（权重/候选/发现/AB/调优/渲染）
│   └── static/           # 前端单文件 index.html（v8）+ metrics/peers + 图标
├── apk/                  # local枭枭 Android WebView 壳源码（产物走 release/飞书）
├── scripts/              # 导入、对账、E2E 测试、每日维护
├── likes-monitor/        # 9/17 早期组件（已整合进 app，保留备查）
├── video-download/       # 9/17 早期组件（已整合进 app，保留备查）
├── data/                 # 视频/图集/音乐 + videos.db（git 忽略，本地挂载）
├── requirements.txt / Dockerfile / docker-compose.yml
└── CURRENT_STATUS.md     # ★最新状态（接手先看）；硬骨头巨坑bug.md（避坑）
```

## 五、用 Trae 怎么维护

把下面这段复制给 Trae，它就知道项目结构：

```
项目：C:\Users\Administrator\Doubao\chats\2026-09-05\new-chat\douyin-topaz-pack\local-douyin
技术栈：FastAPI + SQLite + 原生 JS 手机端（无框架）
入口：app/main.py（API），app/static/index.html（UI），app/db.py（数据库）
视频导入：scripts/import_videos.py
启动：venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
改 UI 交互逻辑在 index.html 的 <script> 里；加 API 在 main.py；加字段在 db.py
```

## 六、路线图

- ✅ **阶段1 MVP**：手机刷视频（本次交付）
- ⏳ 阶段2：video-download / likes-monitor 改造为自动抓取管道，定时入库
- ⏳ 阶段3：Web 后台管控（上架/下架/打标/重要性打分）——数据库字段已预留
- ⏳ 阶段4：AI 打标/总结/价值筛选
- ⏳ 阶段5：多用户 + 个性化推荐

## 合规边界

仅限个人/家庭学习用途，下载内容不公开传播。
