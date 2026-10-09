# CURRENT_STATUS · 当前项目状态

> 最后更新：2026-10-09 · 前端版本 v8（__VER=v8-20261009）· APK v5
> 配套文档：README.md、ARCHITECTURE.md、ROADMAP.md、硬骨头巨坑bug.md

---

## 一、当前运行环境（两台机器）

| 机器 | 角色 | 地址/服务 | 关键路径 |
|---|---|---|---|
| **105** DESKTOP-RR31TH | 火枭采集端（开发/业务主机） | 火枭 :8100（nssm 服务 `HuoXiao`） | `F:\D\20-火枭` |
| **107** TOPAZ | 策展中心 + local枭枭服务端 | LocalDouyin :8000（nssm 服务 `LocalDouyin`） | 实例 `D:\LocalDouyin\local-douyin`，库 `data\videos.db`，venv `D:\LocalDouyin\venv` |

- 开发期业务集中在单机，避免 SQLite 跨网络读；部署生产阶段再做负载均衡分机。
- 抖音请求必须走代理 `HTTPS_PROXY=http://127.0.0.1:10809`。
- WinRM 连 107：账号 `TOPAZ\topaz` / 密码 `000`。

---

## 二、数据规模（以每日对账为准）

- **videos 644 条**：图文 album 41 / 音频 audio 59 / 视频 video 544
- **file_path 629 条**，missing_count=0（视频、图集图片、音乐文件本地齐全）
- **authors 605 条**
- **飞轮成果**：behavior_events 3209、peer_weights 46、peer_relations 107
- **import_batches 7 个**（幂等批次，全 0 错误）
- 每日 06:00 自动对账（107 跑完整性脚本，ok=true 且 missing_count=0 静默；差异必须报告）。

---

## 三、本轮（2026-10-07 ~ 10-09）已完成

1. **主页串号根治（v8）**：根因是"更多"按钮 bioMore 初始在简介框内部，第一次打开无简介博主时被 textContent 销毁且未挂回，第二次起 `getElementById` 返回 null → `null.style` 抛错、渲染在设置名字后中断，头像/背景停在第一位。修复：bioMore 移出简介框为兄弟节点（wrapper），加 null 防护与 try/catch。Web 连测 6 博主通过。
2. **HEIC 音乐封面兜底**：111/666 封面是 HEIC（HTTP 200 但浏览器不解码、onerror 不触发）；前端 load 后判 naturalWidth===0 自动三级降级（music_cover→cover_url→avatar）。
3. **双重前缀头像 / 后端列序错位修复**：`_norm_avatar()` + `_author_row_to_dict` 按 SELECT 实际列序映射（cover_url=r9/is_following=r10/fetched_at=r11）。
4. **客户展示1 排序（customer1）**：全库加权随机（互动分 like×1+collect×1.5+comment×0.2+1，score^0.75），高互动 80% 靠前、每 3 视频 80% 插 1 音频/图集；全库一次排序再分页；APK 默认即 customer1，`?mode=normal` 回原排序。
5. **分享按钮**：图标开源自 zyronon/douyin；单击=复制口令+调起官方抖音，长按=复制链接。
6. **图集交互**：单击暂停/继续（含背景音乐联动）、左右滑动+惯性缓出、长按菜单保留。
7. **音频界面**：旋转唱片、毛玻璃背景随封面变色、大小唱片三级兜底；无封面用博主头像代替。
8. **评论全字段重抓 646/646**（头像/时间/IP/赞/楼中楼）。
9. **行为上报加固**：fetch keepalive 优先 + sendBeacon 兜底（点赞/收藏/图集/音频事件）。
10. **APK v3→v5**：防黑屏（非 http(s) 交系统、RenderProcessGone 自动重载）。
11. 视频原画无水印链路：游客 bitrate 原画档；桌面 H.264/HEVC 统一调 PotPlayer 播原画（不转码不降质）。

---

## 四、待完成 / 阻塞项

- [ ] **APK（小米 11 WebView）HEVC 真机播放实测**：v5 已发飞书，人工连续点博主、看视频/图集/音频。
- [ ] **火枭回马枪**（见 `火枭采集端待解决问题清单.md`，10 条）：分享数 share_count、111 个 HEIC 转 JPEG 重推、图文误判音频、评论字段、音频真实 URL、无音乐图集等。
- [ ] **541/605 博主 follower_count/total_favorited 为 0**：接口显示 0（非串号），补数来源与方式待拍板。
- [ ] local枭枭图集/音频完整展示仍在迭代（图集翻页缓动手感、无简介音乐页兜底等）。
- [ ] 分享口令调起抖音识别原内容的可靠性需再验证（必要时查开源/逆向方案）。
- [ ] P3 多源候选融合 + 多样性控制；P4 从高权重 peer 关注列表自动发现新节点。

---

## 五、给接手 AI（Claude 等）的速览

- 权威后端代码在仓库根 `app/`（main.py 路由、db.py 数据库、crawl_bridge.py 采集桥、curation/ 策展引擎、static/ 前端）。
- 前端是单文件 `app/static/index.html`（无框架，逻辑全内联；调试用 window.__VER / goTo / __visualIdx）。
- Android 壳源码在 `apk/`（WebView 加载 107:8000）。
- `likes-monitor/`、`video-download/` 为 9/17 早期独立组件，已被根 `app/` 整合，保留备查。
- 难坑排查先读 `硬骨头巨坑bug.md`，避免重复劳动；数据问题读火枭清单。
