# Local Douyin · 个人美学策展引擎

> 以人为节点、以公开内容劳动为供应链、以用户自身审美判断为最终监督的本地化个人信息系统。

## 核心一句话

不是让 AI 替我选择内容，而是让 AI 帮我建立一套越来越懂我的"审美供应链"。

## 技术栈

- 后端：Python 3 + FastAPI + Uvicorn
- 数据库：SQLite
- 前端：原生 HTML/CSS/JS（移动端优先）
- 采集：Playwright / 视频处理：FFmpeg

## 当前状态

- 版本：v0.5.0（2026-09-07）
- P0 策展飞轮 12 步验收：全通过
- 同好节点 8 个 / 本地视频 123 个 / 行为事件 49+
- 卡点：ffmpeg 未安装、likes-monitor 真实采集需登录态

## 开发管理

- 项目管理：Linear（团队：美学策展引擎）
- 分支命名：`feature/<issue-id>-<slug>`
- Commit 规范：`<type>: <summary> (#<linear-issue-id>)`
- PR 描述必须反向链接 Linear issue
