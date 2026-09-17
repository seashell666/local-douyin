# ARCHITECTURE · 系统架构

## 分层

```
移动端 UI (原生 JS)
  ↕ HTTP / WebSocket
FastAPI 后端
  ├─ 视频服务 stream / list
  ├─ 博主/朋友 authors / friends
  └─ 策展引擎核心
       ├─ Peer Graph      同好节点图谱
       ├─ Behavior         行为遥测
       ├─ Weight Engine    同好权重引擎（sigmoid + 时间衰减）
       ├─ Candidate        候选生成
       ├─ Ranking          排序引擎
       ├─ Discovery        新同好发现
       └─ Algorithm Config  算法配置版本化
SQLite
  videos / authors / friends / peers / behavior_events
  peer_weights / peer_relations / algorithm_config
  algorithm_versions / experiments / daily_curation
外部采集层：video-download / likes-monitor / Playwright / FFmpeg
```

## 设计原则

1. 接口先行：先定义模块间 API，再替换内部实现
2. Mock 可用：真实采集器未完成时用 Mock 数据跑通闭环
3. 可解释：第一版算法宁可简单，必须说清"为什么推荐这个"
4. 参数配置化：所有魔法数字进入 algorithm_config
5. 全链路日志：每个重要行为留下可追溯记录
