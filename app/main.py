# -*- coding: utf-8 -*-
"""
local-douyin —— 本地家庭抖音 · 后端服务 v2（FastAPI）
启动: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .crawl_bridge import router as crawl_router
from .curation import (
    recalculate_peer_weight, recalculate_all_weights,
    generate_recommendations, rank_videos,
    discover_peers_from_relations, import_friends_as_peers,
)
from .curation.weight_engine import get_peer_weight_explanation
from .curation.candidate import get_recommendation_explanation
from .curation.clip_extractor import generate_clip_candidates, get_clip_manifest
from .curation.video_renderer import render_manifest, get_ffmpeg_path
from .curation.discovery import (
    import_followed_authors_as_peers,
    link_videos_to_peers_by_author,
    add_discovery_candidate,
    auto_discover_from_top_peers,
)
from .curation.metrics import (
    compute_metrics, compute_daily_series,
    compare_algorithms, get_health_score,
)
from .curation.ab_test import (
    create_ab_test, get_active_ab_test, get_user_variant,
    end_ab_test, list_ab_tests,
)

BASE_DIR = Path(__file__).resolve().parent.parent
VIDEO_DIR = BASE_DIR / "data" / "videos"
AVATAR_DIR = BASE_DIR / "data" / "avatars"
MUSIC_DIR = BASE_DIR / "data" / "music_covers"
NOTE_IMAGE_DIR = BASE_DIR / "data" / "note_images"
MUSIC_FILE_DIR = BASE_DIR / "data" / "music_files"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 让后端能 import 项目根目录的 author_fetcher
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

app = FastAPI(title="local-douyin", version="0.2.0")
app.include_router(crawl_router)

# 启动时确保目录存在
db.init_db()
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)
NOTE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_FILE_DIR.mkdir(parents=True, exist_ok=True)


# ── 工具 ──────────────────────────────────────────────────────────────────
def _video_row_to_dict(r):
    """把 list_videos 的行转成 API dict（含博主/音乐字段）"""
    return {
        "id": r[0],
        "title": r[1],
        "author": r[2],
        "file_name": r[3],
        "file_size": r[4],
        "importance": r[5],
        "tags": r[6],
        "like_count": r[7],
        "comment_count": r[8],
        "collect_count": r[9],
        "sec_uid": r[10] or "",
        "avatar_url": r[11] or "",
        "music_title": r[12] or "",
        "music_cover": f"/api/music-cover/{r[13]}" if r[13] else "",
        "music_author": r[14] or "",
        "aweme_id": r[15] or "",
        "cover_url": r[23] or "",
        "is_note": bool(r[16]) if len(r) > 16 else False,
        "image_list": r[17] if len(r) > 17 and r[17] else "",
        "music_file": r[18] if len(r) > 18 and r[18] else "",
        "media_type": r[24] if len(r) > 24 and r[24] else "",
        "duration": r[19] if len(r) > 19 and r[19] else 0,
        "url": f"/api/videos/{r[0]}/stream",
    }


def _norm_avatar(v):
    """头像路径规范化：库内可能是 /api/avatar/{file}（本地）、裸文件名（本地 avatars 目录多有）、
    双重前缀、远端 URL 或脏数据。本地类统一 /api/avatar/{name}；远端 URL 保留；无扩展名视为脏数据
    返回空（前端用同博主 feed 头像兜底）。文件名不做长度限制（本地头像文件名为 sec_uid.jpg 较长）。"""
    if not v:
        return ""
    v = str(v).strip()
    if v.startswith("/api/avatar/"):
        v = v[len("/api/avatar/"):].lstrip("/")
    elif v.startswith("http://") or v.startswith("https://"):
        # 远端 URL（douyinpic 等）：保留原样（浏览器/WebView 可直接加载）
        return v.split(" ")[0].split("#")[0]
    name = v.split("?")[0].split("/")[-1]
    if name and name.lower().endswith((".webp", ".jpg", ".jpeg", ".png", ".gif")):
        return "/api/avatar/" + name
    return ""


def _author_row_to_dict(r):
    if not r:
        return None
    # get_author SELECT 列序（db.py 实测）：sec_uid, nickname, unique_id, avatar_url, signature,
    # follower_count, following_count, total_favorited, ip_location, cover_url, is_following, fetched_at
    return {
        "sec_uid": r[0],
        "nickname": r[1],
        "unique_id": r[2],
        "avatar_url": _norm_avatar(r[3]),
        "signature": r[4],
        "follower_count": r[5],
        "following_count": r[6],
        "total_favorited": r[7],
        "ip_location": r[8],
        "cover_url": r[9] if len(r) > 9 else "",
        "is_following": bool(r[10]) if len(r) > 10 else False,
        "fetched_at": r[11] if len(r) > 11 else "",
    }


# ── 基础 API ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


def _customer1_sort(items):
    """客户展示1排序：加权随机（互动高的大概率靠前）+ 每3个视频后80%插1个音频/图集"""
    import random
    def score(x):
        like = float(x.get("like_count") or 0)
        col = float(x.get("collect_count") or 0)
        com = float(x.get("comment_count") or 0)
        return like * 1.0 + col * 1.5 + com * 0.2 + 1.0
    def wshuffle(pool):
        pool = list(pool)
        out = []
        while pool:
            scores = [score(p) ** 0.75 for p in pool]
            tot = sum(scores)
            r = random.uniform(0, tot)
            acc = 0
            pick = 0
            for i, s in enumerate(scores):
                acc += s
                if r <= acc:
                    pick = i
                    break
            out.append(pool.pop(pick))
        return out
    vids = wshuffle([x for x in items if x.get("media_type") == "video"])
    nonv = wshuffle([x for x in items if x.get("media_type") != "video"])
    result = []
    vi = 0
    ni = 0
    while vi < len(vids):
        result.append(vids[vi])
        vi += 1
        if vi % 3 == 0 and ni < len(nonv):
            if random.random() < 0.8:
                result.append(nonv[ni])
                ni += 1
            elif vi < len(vids):
                # 20% 推迟：第4个视频后再插
                result.append(vids[vi])
                vi += 1
                result.append(nonv[ni])
                ni += 1
    while ni < len(nonv):
        result.append(nonv[ni])
        ni += 1
    return result


@app.get("/api/videos")
def api_videos(offset: int = 0, limit: int = 20, mode: str = ""):
    """可见视频列表（分页，含博主头像/音乐封面）；mode=customer1 时按客户展示1全局排序再切片"""
    limit = min(max(limit, 1), 200)
    if mode == "customer1":
        # 全量（600+）排序一次，再按 offset/limit 切片 → 翻页顺序全局连续稳定
        rows, total = db.list_videos(offset=0, limit=100000)
        items = [_video_row_to_dict(r) for r in rows]
        items = _customer1_sort(items)
        page = items[offset:offset + limit]
        return {"items": page, "total": len(items), "offset": offset,
                "has_more": offset + len(page) < len(items)}
    rows, total = db.list_videos(offset=offset, limit=limit)
    items = [_video_row_to_dict(r) for r in rows]
    return {"items": items, "total": total, "offset": offset,
            "has_more": offset + len(items) < total}


@app.get("/api/videos/{vid}/stream")
def stream_video(vid: int):
    """视频流（FileResponse 自动支持 Range）"""
    row = db.get_video(vid)
    if not row or not row[5]:
        return JSONResponse({"error": "视频不存在或不可见"}, status_code=404)
    video_path = VIDEO_DIR / row[3]
    if not video_path.exists():
        return JSONResponse({"error": "视频文件缺失"}, status_code=404)
    return FileResponse(video_path, media_type="video/mp4")


# ── 头像/音乐封面（本地文件代理）──────────────────────────────────────────
@app.get("/api/avatar/{filename}")
def get_avatar(filename: str):
    """返回本地头像文件"""
    path = AVATAR_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    media_type = "image/webp" if filename.endswith(".webp") else "image/jpeg"
    return FileResponse(path, media_type=media_type)


@app.get("/api/music-cover/{filename}")
def get_music_cover(filename: str):
    """返回本地音乐封面文件"""
    path = MUSIC_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/note-image/{filename:path}")
def get_note_image(filename: str):
    """返回本地图文作品图片文件（支持 作品id/序号.jpg 子路径）"""
    path = NOTE_IMAGE_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    media_type = "image/webp" if filename.endswith(".webp") else "image/jpeg"
    return FileResponse(path, media_type=media_type)


@app.get("/api/music-file/{filename}")
def get_music_file(filename: str):
    """返回本地音乐文件（.mp3→audio/mpeg，.mp4→audio/mp4）"""
    path = MUSIC_FILE_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    mime = "audio/mpeg" if path.suffix.lower() in (".mp3", ".mpeg") else "audio/mp4"
    return FileResponse(path, media_type=mime)


# ── 博主 API ──────────────────────────────────────────────────────────────
@app.get("/api/authors/{sec_uid}")
def api_author(sec_uid: str, refresh: bool = False):
    """获取博主资料。优先本地缓存，没有或refresh=true时从抖音抓取。"""
    row = db.get_author(sec_uid)

    # 本地有缓存且不强制刷新 → 直接返回
    if row and not refresh:
        author = _author_row_to_dict(row)
        # 补充本地视频数
        _, vcount = db.list_videos_by_author(sec_uid, limit=1)
        author["local_video_count"] = vcount
        return author

    # 从抖音抓取（Playwright，较慢）
    try:
        from author_fetcher import fetch_author_profile
        profile = fetch_author_profile(sec_uid)
        if "error" in profile:
            # 抓取失败，返回本地缓存（如果有）
            if row:
                author = _author_row_to_dict(row)
                _, vcount = db.list_videos_by_author(sec_uid, limit=1)
                author["local_video_count"] = vcount
                author["fetch_error"] = profile["error"]
                return author
            return JSONResponse({"error": profile["error"]}, status_code=502)

        # 写入/更新本地缓存
        db.upsert_author(
            sec_uid=sec_uid,
            nickname=profile.get("nickname", ""),
            unique_id=profile.get("unique_id", ""),
            avatar_url="",  # 头像URL暂不存本地文件名，前端用远端URL
            signature=profile.get("signature", ""),
            follower_count=profile.get("follower_count", 0),
            following_count=profile.get("following_count", 0),
            total_favorited=profile.get("total_favorited", 0),
            ip_location=profile.get("ip_location", ""),
            cover_url=profile.get("cover_url", ""),
        )

        # 返回（用远端头像URL）
        row = db.get_author(sec_uid)
        author = _author_row_to_dict(row)
        author["avatar_url"] = profile.get("avatar_url", "")  # 覆盖为远端URL
        author["cover_url"] = profile.get("cover_url", "")  # 远端封面图
        author["aweme_count"] = profile.get("aweme_count", 0)
        _, vcount = db.list_videos_by_author(sec_uid, limit=1)
        author["local_video_count"] = vcount
        return author

    except Exception as e:
        if row:
            author = _author_row_to_dict(row)
            _, vcount = db.list_videos_by_author(sec_uid, limit=1)
            author["local_video_count"] = vcount
            author["fetch_error"] = str(e)
            return author
        return JSONResponse({"error": f"抓取失败: {e}"}, status_code=502)


@app.get("/api/authors/{sec_uid}/videos")
def api_author_videos(sec_uid: str, offset: int = 0, limit: int = 50, source: str = "local"):
    """获取博主的视频列表。
    source=local: 只返回本地已下载的视频
    source=remote: 从抖音抓取该博主的视频列表（含未下载的）
    """
    if source == "remote":
        try:
            from author_fetcher import fetch_author_videos
            videos = fetch_author_videos(sec_uid, count=limit)
            if isinstance(videos, dict) and "error" in videos:
                return JSONResponse({"error": videos["error"]}, status_code=502)
            return {"items": videos, "total": len(videos), "source": "remote"}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=502)

    # 默认：本地视频
    rows, total = db.list_videos_by_author(sec_uid, offset=offset, limit=limit)
    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "title": r[1],
            "author": r[2],
            "file_name": r[3],
            "file_size": r[4],
            "like_count": r[5],
            "comment_count": r[6],
            "collect_count": r[7],
            "created_at": r[8],
            "aweme_id": r[9],
            "url": f"/api/videos/{r[0]}/stream",
        })
    return {"items": items, "total": total, "offset": offset, "source": "local"}


@app.post("/api/authors/{sec_uid}/follow")
def api_follow_author(sec_uid: str):
    """关注/取关博主（切换状态）。取关时清除懒加载的远程数据。"""
    row = db.get_author(sec_uid)
    current = bool(row[10]) if row and len(row) > 10 else False
    new_state = not current
    db.set_following(sec_uid, new_state)
    # 取关时清除懒加载的远程数据（保留基本信息供视频显示）
    if not new_state:
        conn = db.get_conn()
        conn.execute(
            "UPDATE authors SET cover_url='', signature='', follower_count=0, "
            "following_count=0, total_favorited=0, ip_location='', fetched_at='' "
            "WHERE sec_uid=?",
            (sec_uid,),
        )
        conn.commit()
        conn.close()
    return {"sec_uid": sec_uid, "is_following": new_state}


@app.get("/api/follows")
def api_list_follows():
    """列出所有已关注的博主"""
    rows = db.list_followed_authors()
    items = [_author_row_to_dict(r) for r in rows]
    return {"items": items, "total": len(items)}


# ── 朋友 ─────────────────────────────────────────────────────────────────

def _friend_row_to_dict(r):
    return {
        "id": r[0],
        "sec_uid": r[1],
        "douyin_id": r[2],
        "nickname": r[3],
        "avatar": r[4],
        "last_visit_time": r[5],
        "created_at": r[6],
        "source": r[7],
    }


@app.get("/api/friends")
def api_list_friends():
    """获取朋友列表（按最后访问时间倒序）"""
    rows = db.list_friends()
    items = [_friend_row_to_dict(r) for r in rows]
    return {"items": items, "total": len(items)}


@app.post("/api/friends")
async def api_add_friend(request: Request):
    """添加朋友（抖音号→爬取头像昵称→入库）"""
    body = await request.json()
    douyin_id = body.get("douyin_id", "").strip()
    if not douyin_id:
        return {"ok": False, "error": "抖音号不能为空"}
    # 先从authors表查找（已关注的博主直接用现有数据）
    # TODO: 后续接入用户信息爬虫，通过抖音号获取sec_uid、昵称、头像
    # 临时实现：如果authors表中有匹配的unique_id，直接添加为朋友
    conn = db.get_conn()
    author = conn.execute(
        "SELECT sec_uid, nickname, unique_id, avatar_url FROM authors WHERE unique_id=? OR nickname=?",
        (douyin_id, douyin_id),
    ).fetchone()
    conn.close()
    if author:
        sec_uid, nickname, unique_id, avatar_url = author
        fid = db.upsert_friend(sec_uid, douyin_id=unique_id or douyin_id,
                                nickname=nickname, avatar=avatar_url, source="follow")
        return {"ok": True, "friend_id": fid, "nickname": nickname}
    return {"ok": False, "error": "未找到该用户，爬虫功能开发中"}


@app.post("/api/friends/{sec_uid}/visit")
def api_friend_visit(sec_uid: str):
    """更新朋友的最后访问时间"""
    db.update_friend_visit(sec_uid)
    return {"ok": True}


@app.delete("/api/friends/{fid}")
def api_delete_friend(fid: int):
    """删除朋友"""
    db.delete_friend(fid)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# 策展引擎 API（P0 闭环核心）
# ═══════════════════════════════════════════════════════════════

def _peer_row_to_dict(r):
    if not r:
        return None
    return {
        "id": r[0],
        "sec_uid": r[1],
        "nickname": r[2],
        "douyin_id": r[3],
        "avatar": r[4],
        "source": r[5],
        "discovered_by": r[6],
        "current_weight": r[7],
        "initial_weight": r[8],
        "status": r[9],
        "added_at": r[10],
        "last_active_at": r[11],
        "total_content": r[12],
        "note": r[13],
    }


# ── 同好节点管理 ────────────────────────────────────────────────

@app.get("/api/peers")
def api_list_peers(min_weight: float = 0.0, status: str = None, limit: int = 100, offset: int = 0):
    """列出同好节点（按权重降序）"""
    rows, total = db.list_peers(min_weight=min_weight, status=status, limit=limit, offset=offset)
    items = [_peer_row_to_dict(r) for r in rows]
    return {"items": items, "total": total, "offset": offset}


@app.get("/api/peers/{pid}")
def api_get_peer(pid: int):
    """获取单个同好详情"""
    row = db.get_peer(pid)
    if not row:
        return JSONResponse({"error": "同好不存在"}, status_code=404)
    return _peer_row_to_dict(row)


@app.post("/api/peers")
async def api_add_peer(request: Request):
    """添加同好节点"""
    body = await request.json()
    sec_uid = body.get("sec_uid", "").strip()
    if not sec_uid:
        return {"ok": False, "error": "sec_uid 不能为空"}
    pid = db.upsert_peer(
        sec_uid=sec_uid,
        nickname=body.get("nickname", ""),
        douyin_id=body.get("douyin_id", ""),
        avatar=body.get("avatar", ""),
        source=body.get("source", "manual"),
        discovered_by=body.get("discovered_by", 0),
        initial_weight=body.get("initial_weight", 0.5),
        note=body.get("note", ""),
    )
    return {"ok": True, "peer_id": pid}


@app.delete("/api/peers/{pid}")
def api_delete_peer(pid: int):
    """删除同好节点"""
    db.delete_peer(pid)
    return {"ok": True}


@app.get("/api/peers/{pid}/videos")
def api_peer_videos(pid: int, limit: int = 50, offset: int = 0):
    """获取该同好发现的所有视频"""
    rows, total = db.get_peer_videos(pid, limit=limit, offset=offset)
    items = []
    for r in rows:
        items.append({
            "id": r[0], "title": r[1], "author": r[2], "file_name": r[3],
            "file_size": r[4], "like_count": r[5], "comment_count": r[6],
            "collect_count": r[7], "sec_uid": r[8], "aweme_id": r[9],
            "source_type": r[10], "url": f"/api/videos/{r[0]}/stream",
        })
    return {"items": items, "total": total}


@app.post("/api/peers/{pid}/videos/{vid}")
def api_link_video_to_peer(pid: int, vid: int, source_type: str = "like"):
    """建立视频-同好关联（标记该视频由这个同好发现）"""
    db.add_video_peer_source(vid, pid, source_type=source_type)
    return {"ok": True, "peer_id": pid, "video_id": vid, "source_type": source_type}


# ── 行为遥测 ────────────────────────────────────────────────────

@app.post("/api/behavior")
async def api_log_behavior(request: Request):
    """
    记录用户行为事件。
    body: {video_id, peer_id, event_type, position, duration, session_id, metadata}
    event_type: impression/play_start/play_end/watch_duration/skip/early_exit/replay/like/unlike/collect/uncollect/not_interested
    """
    body = await request.json()
    video_id = body.get("video_id")
    if not video_id:
        return {"ok": False, "error": "video_id 必填"}

    config = db.get_active_config()
    eid = db.insert_behavior(
        video_id=video_id,
        peer_id=body.get("peer_id", 0),
        event_type=body.get("event_type", "impression"),
        position=body.get("position", 0.0),
        duration=body.get("duration", 0.0),
        session_id=body.get("session_id", ""),
        algorithm_ver=config.get("version", "v001"),
        metadata=body.get("metadata", ""),
    )

    # 如果是强反馈事件（like/collect/not_interested），自动触发该 peer 权重重算
    peer_id = body.get("peer_id", 0)
    event_type = body.get("event_type", "")
    if peer_id and event_type in ("like", "collect", "not_interested", "skip"):
        recalculate_peer_weight(peer_id, config)

    return {"ok": True, "event_id": eid}


@app.get("/api/behavior/peer/{pid}")
def api_behavior_by_peer(pid: int, limit: int = 200):
    """获取某个同好相关的行为事件"""
    rows = db.get_behavior_by_peer(pid, limit=limit)
    items = [{
        "id": r[0], "video_id": r[2], "peer_id": r[3], "event_type": r[4],
        "position": r[5], "duration": r[6], "session_id": r[7],
        "algorithm_ver": r[8], "created_at": r[10],
    } for r in rows]
    return {"items": items, "total": len(items)}


@app.get("/api/behavior/video/{vid}")
def api_behavior_by_video(vid: int, limit: int = 100):
    """获取某个视频的行为事件"""
    rows = db.get_behavior_by_video(vid, limit=limit)
    items = [{
        "id": r[0], "video_id": r[2], "peer_id": r[3], "event_type": r[4],
        "position": r[5], "duration": r[6], "created_at": r[10],
    } for r in rows]
    return {"items": items, "total": len(items)}


# ── 同好权重引擎 ────────────────────────────────────────────────

@app.post("/api/weights/recalculate")
def api_recalculate_weights(peer_id: int = None):
    """重新计算权重。不传 peer_id 则计算全部。"""
    config = db.get_active_config()
    if peer_id:
        new_weight, reason, count = recalculate_peer_weight(peer_id, config)
        return {"ok": True, "peer_id": peer_id, "new_weight": new_weight,
                "reason": reason, "event_count": count}
    results = recalculate_all_weights(config)
    return {"ok": True, "updated": len(results), "results": results}


@app.get("/api/weights/{pid}/history")
def api_weight_history(pid: int, limit: int = 50):
    """获取同好权重变化历史"""
    rows = db.get_peer_weight_history(pid, limit=limit)
    items = [{
        "id": r[0], "weight": r[2], "reason": r[3],
        "algorithm_ver": r[4], "event_count": r[5], "calculated_at": r[6],
    } for r in rows]
    return {"items": items, "total": len(items)}


@app.get("/api/weights/{pid}/explanation")
def api_weight_explanation(pid: int):
    """获取权重可解释文本"""
    text = get_peer_weight_explanation(pid)
    return {"peer_id": pid, "explanation": text}


# ── 推荐引擎 ────────────────────────────────────────────────────

@app.get("/api/recommendations")
def api_recommendations(limit: int = 20, offset: int = 0):
    """
    获取推荐视频列表（基于同好权重排序）。
    这是策展引擎的核心输出，替代原 /api/videos 的简单列表。
    """
    config = db.get_active_config()
    items, total = generate_recommendations(limit=limit, offset=offset, config=config)
    return {"items": items, "total": total, "offset": offset,
            "has_more": offset + len(items) < total,
            "algorithm_ver": config.get("version", "v001")}


@app.get("/api/recommendations/{vid}/explanation")
def api_recommendation_explanation(vid: int):
    """获取推荐可解释文本"""
    text = get_recommendation_explanation(vid)
    return {"video_id": vid, "explanation": text}


# ── 新同好发现 ──────────────────────────────────────────────────

@app.post("/api/discovery/import-friends")
def api_import_friends():
    """将 friends 表导入为 peers"""
    result = import_friends_as_peers()
    return {"ok": True, **result}


@app.post("/api/discovery/import-authors")
def api_import_authors():
    """将已关注 authors 导入为 peers"""
    result = import_followed_authors_as_peers()
    return {"ok": True, **result}


@app.post("/api/discovery/link-videos")
def api_link_videos():
    """根据作者 sec_uid 匹配视频与同好，建立 video_peer_sources 关联"""
    result = link_videos_to_peers_by_author()
    return {"ok": True, **result}


@app.get("/api/discovery/from-peer/{pid}")
def api_discover_from_peer(pid: int, max: int = 10):
    """从某个同好的关系网络发现新同好候选"""
    candidates = discover_peers_from_relations(pid, max_candidates=max)
    return {"candidates": candidates, "total": len(candidates)}


@app.get("/api/discovery/auto")
def api_auto_discover(top_n: int = 3, max_per_peer: int = 5):
    """自动从高权重同好的关系网络发现新节点"""
    result = auto_discover_from_top_peers(top_n=top_n, max_per_peer=max_per_peer)
    return {"ok": True, **result}


@app.post("/api/discovery/add-candidate")
async def api_add_discovery_candidate(request: Request):
    """将发现的候选节点加入 peers（exploring 状态）"""
    body = await request.json()
    sec_uid = body.get("sec_uid", "").strip()
    if not sec_uid:
        return {"ok": False, "error": "sec_uid 必填"}
    pid = add_discovery_candidate(
        sec_uid=sec_uid,
        nickname=body.get("nickname", ""),
        discovered_by=body.get("discovered_by", 0),
        source=body.get("source", "relation"),
        initial_weight=body.get("initial_weight", 0.3),
    )
    return {"ok": True, "peer_id": pid}


# ── 算法配置 ────────────────────────────────────────────────────

@app.get("/api/config")
def api_get_config():
    """获取当前激活的算法配置"""
    config = db.get_active_config()
    return config


@app.put("/api/config")
async def api_update_config(request: Request):
    """更新算法配置（保存为新版本并激活）"""
    body = await request.json()
    version = body.get("version", "v001")
    config_dict = body.get("config", {})
    reason = body.get("change_reason", "")
    if not config_dict:
        return {"ok": False, "error": "config 不能为空"}
    db.save_config(version, config_dict, change_reason=reason, set_active=True)
    return {"ok": True, "version": version}


@app.get("/api/config/versions")
def api_list_config_versions():
    """列出所有算法配置版本"""
    rows = db.list_configs()
    items = [{
        "version": r[0], "is_active": bool(r[1]),
        "change_reason": r[2], "created_at": r[3],
    } for r in rows]
    return {"versions": items}


@app.get("/api/config/versions/{version}")
def api_get_config_version(version: str):
    """获取指定版本的配置详情"""
    cfg = db.get_config_by_version(version)
    if not cfg:
        return JSONResponse({"error": "版本不存在"}, status_code=404)
    return cfg


@app.post("/api/config/versions/{version}/activate")
def api_activate_config(version: str):
    """激活指定版本（回滚）"""
    ok = db.activate_config(version)
    if not ok:
        return JSONResponse({"error": "版本不存在"}, status_code=404)
    return {"ok": True, "active_version": version}


# ═══════════════════════════════════════════════════════════
# 片段提取 & 每日策展（P5）
# ═══════════════════════════════════════════════════════════

@app.get("/api/clips")
def api_get_clips(start_ts: int = 0, end_ts: int = 0, limit: int = 50):
    """获取候选片段列表（基于点赞时间窗口）"""
    clips = generate_clip_candidates(start_ts=start_ts, end_ts=end_ts, limit=limit)
    return {"items": clips, "total": len(clips)}


@app.get("/api/daily-curation")
def api_daily_curation(start_ts: int = 0, end_ts: int = 0):
    """生成每日策展 manifest（含候选片段和统计）"""
    manifest = get_clip_manifest(start_ts=start_ts, end_ts=end_ts)
    return manifest


@app.post("/api/daily-curation/generate")
def api_generate_daily_curation(start_ts: int = 0, end_ts: int = 0, render: bool = False):
    """生成每日策展 manifest，可选渲染视频"""
    manifest = get_clip_manifest(start_ts=start_ts, end_ts=end_ts)
    # 保存 manifest 到文件
    import json, os
    from datetime import datetime
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "curation")
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    manifest_path = os.path.join(out_dir, f"curation_{date_str}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    manifest["saved_to"] = manifest_path
    # 可选渲染视频
    if render:
        ok, result, details = render_manifest(manifest, out_dir)
        manifest["render_status"] = "done" if ok else "failed"
        manifest["render_note"] = result if not ok else "rendered successfully"
        manifest["render_details"] = details
        if ok:
            manifest["video_url"] = "/api/curation/video/" + os.path.basename(result)
    else:
        manifest["render_status"] = "pending"
        manifest["render_note"] = "call with render=true or POST /api/daily-curation/render to render video"
    return manifest


@app.post("/api/daily-curation/render")
def api_render_daily_curation(start_ts: int = 0, end_ts: int = 0):
    """渲染每日策展视频（用 ffmpeg 拼接片段）"""
    manifest = get_clip_manifest(start_ts=start_ts, end_ts=end_ts)
    out_dir = os.path.join(str(BASE_DIR), "data", "curation")
    os.makedirs(out_dir, exist_ok=True)
    ok, result, details = render_manifest(manifest, out_dir)
    return {
        "success": ok,
        "output": result,
        "details": details,
        "video_url": ("/api/curation/video/" + os.path.basename(result)) if ok else None,
    }


@app.get("/api/curation/video/{filename}")
def api_get_curation_video(filename: str):
    """获取已渲染的策展视频"""
    import os
    video_dir = os.path.join(str(BASE_DIR), "data", "curation")
    filepath = os.path.join(video_dir, filename)
    if not os.path.exists(filepath):
        return JSONResponse(status_code=404, content={"error": "video not found"})
    return FileResponse(filepath, media_type="video/mp4")


# ═══════════════════════════════════════════════════════════
# 指标监控（P6）
# ═══════════════════════════════════════════════════════════

DB_PATH = str(BASE_DIR / "data" / "videos.db")


@app.get("/api/metrics")
def api_metrics(days: int = 7, algorithm_ver: str = ""):
    """聚合指标：喜欢率/收藏率/跳过率/完播率/网络扩张"""
    ver = algorithm_ver if algorithm_ver else None
    m = compute_metrics(DB_PATH, days=days, algorithm_ver=ver)
    health = get_health_score(m)
    m["health"] = health
    return m


@app.get("/api/metrics/daily")
def api_metrics_daily(days: int = 14, algorithm_ver: str = ""):
    """日度指标序列（趋势图用）"""
    ver = algorithm_ver if algorithm_ver else None
    series = compute_daily_series(DB_PATH, days=days, algorithm_ver=ver)
    return {"items": series, "total": len(series)}


@app.get("/api/metrics/compare")
def api_metrics_compare(ver_a: str = "v001", ver_b: str = "v002", days: int = 7):
    """对比两个算法版本的指标差异"""
    return compare_algorithms(DB_PATH, ver_a, ver_b, days=days)


@app.get("/api/metrics/health")
def api_metrics_health(days: int = 7):
    """系统健康分（0-100）"""
    m = compute_metrics(DB_PATH, days=days)
    return get_health_score(m)


# ═══════════════════════════════════════════════════════════
# A/B 测试（P6）
# ═══════════════════════════════════════════════════════════

@app.post("/api/ab-tests")
async def api_create_ab_test(request: Request):
    """创建A/B测试"""
    body = await request.json()
    name = body.get("name", "未命名测试")
    version_a = body.get("version_a", "v001")
    version_b = body.get("version_b", "v002")
    return create_ab_test(DB_PATH, name, version_a, version_b)


@app.get("/api/ab-tests/active")
def api_get_active_ab_test():
    """获取当前运行的A/B测试"""
    test = get_active_ab_test(DB_PATH)
    return test or {"active": False}


@app.get("/api/ab-tests/variant")
def api_get_user_variant(user_id: str = "local"):
    """获取当前用户的A/B分配"""
    v = get_user_variant(DB_PATH, user_id)
    return v or {"assigned": False}


@app.post("/api/ab-tests/{test_id}/end")
def api_end_ab_test(test_id: int):
    """结束A/B测试"""
    return end_ab_test(DB_PATH, test_id)


@app.get("/api/ab-tests")
def api_list_ab_tests(limit: int = 20):
    """列出A/B测试历史"""
    return {"items": list_ab_tests(DB_PATH, limit)}


# ═══════════════════════════════════════════════════════════
# 群组权重（P2）
# ═══════════════════════════════════════════════════════════

@app.get("/api/groups")
def api_get_groups():
    """按标签聚合的群组权重列表"""
    groups = db.get_peer_groups()
    return {"groups": groups, "total": len(groups)}


@app.post("/api/peers/{pid}/tags")
async def api_update_peer_tags(pid: int, request: Request):
    """更新同好标签"""
    body = await request.json()
    tags = body.get("tags", "")
    db.update_peer_tags(pid, tags)
    return {"ok": True, "peer_id": pid, "tags": tags}


# ═══════════════════════════════════════════════════════════
# 关系网络自动扩张 & 系统维护（P4）
# ═══════════════════════════════════════════════════════════

@app.post("/api/discovery/auto-expand")
def api_auto_expand(max_new: int = 5):
    """
    自动扩张关系网络（Mock模式）。
    从高权重同好关联的视频作者中发现新同好候选。
    """
    import random
    config = db.get_active_config()
    limits = config.get("limits", {})
    max_daily = limits.get("max_daily_new_peers", 5)
    max_new = min(max_new, max_daily)

    # 获取高权重同好（>=0.5）
    peers, _ = db.list_peers(min_weight=0.5, limit=50)
    if not peers:
        return {"added": 0, "candidates": [], "reason": "no high-weight peers"}

    # 收集这些同好关联的视频的作者
    candidate_authors = {}
    conn = db.get_conn()
    for p in peers:
        pid = p[0]
        rows = conn.execute(
            "SELECT v.id, v.author, v.sec_uid FROM video_peer_sources vps "
            "JOIN videos v ON v.id = vps.video_id WHERE vps.peer_id=? "
            "AND v.sec_uid != '' AND v.sec_uid IS NOT NULL",
            (pid,)
        ).fetchall()
        for vid, author, sec_uid in rows:
            if sec_uid and sec_uid not in candidate_authors:
                # 检查是否已是同好
                existing = conn.execute("SELECT id FROM peers WHERE sec_uid=?", (sec_uid,)).fetchone()
                if not existing:
                    candidate_authors[sec_uid] = {"author": author, "sec_uid": sec_uid,
                                                  "source_peer": pid, "source_peer_weight": p[7]}
    conn.close()

    if not candidate_authors:
        return {"added": 0, "candidates": [], "reason": "no new authors found"}

    # 按来源同好权重排序，取前 max_new 个
    candidates = sorted(candidate_authors.values(),
                       key=lambda x: x["source_peer_weight"], reverse=True)[:max_new]

    added = 0
    results = []
    for c in candidates:
        pid = db.upsert_peer(
            sec_uid=c["sec_uid"],
            nickname=c["author"],
            source="auto_discovered",
            discovered_by=c["source_peer"],
            initial_weight=0.3,
            status="exploring",
        )
        # 记录关系
        db.upsert_peer_relation(c["source_peer"], pid, "discovered",
                                strength=c["source_peer_weight"])
        added += 1
        results.append({"peer_id": pid, "nickname": c["author"],
                       "source_peer": c["source_peer"]})

    return {"added": added, "candidates": results}


@app.post("/api/maintenance/cleanup-low-weight")
def api_cleanup_low_weight():
    """
    清理低权重同好（防止关系网络无限膨胀）。
    权重 < min_peer_weight 且 status=exploring 且无内容的同好标记为 paused。
    """
    config = db.get_active_config()
    min_w = config.get("limits", {}).get("min_peer_weight", 0.1)

    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, nickname, current_weight, total_content, status FROM peers "
        "WHERE current_weight < ? AND status='exploring'",
        (min_w,)
    ).fetchall()

    paused = 0
    for row in rows:
        pid, nick, weight, content, status = row
        # 只暂停没有内容的探索中同好
        if (content or 0) == 0:
            conn.execute("UPDATE peers SET status='paused' WHERE id=?", (pid,))
            paused += 1

    conn.commit()
    conn.close()
    return {"paused": paused, "min_weight_threshold": min_w}




# ═══════════════════════════════════════════════════════════
# 设置持久化API（毛玻璃弹窗等UI偏好）
# ═══════════════════════════════════════════════════════════

@app.get("/api/settings")
def api_get_settings():
    """获取所有设置"""
    return db.get_all_settings()


@app.post("/api/settings")
async def api_save_settings(request: Request):
    """批量保存设置，body为 {"key1": "value1", "key2": "value2"}"""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})
    for key, value in data.items():
        db.set_setting(key, value)
    return {"success": True, "saved": list(data.keys())}


@app.get("/api/settings/{key}")
def api_get_setting(key: str):
    """获取单个设置"""
    value = db.get_setting(key)
    if value is None:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"key": key, "value": value}

# 静态资源（手机端 UI）—— 必须放在最后
# 首页显式路由优先于 mount：强制 no-store，保证 APK WebView 每次拉最新前端（串号修复验收依赖）
@app.get("/", include_in_schema=False)
def _serve_index():
    return FileResponse(STATIC_DIR / "index.html",
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
