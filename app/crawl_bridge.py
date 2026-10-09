# -*- coding: utf-8 -*-
"""
crawl_bridge —— LocalDouyin × 火枭 采集服务对接桥

路由：
  POST /api/crawl/import    接收火枭采集 JSON 落库（节点/可见性/收藏/喜欢/作品/关注/粉丝）
  POST /api/crawl/schedule  LocalDouyin 编排：按节点+维度请求火枭并自动落库
  GET  /api/crawl/status    最近导入统计

约定（见 服务/火枭供给能力契约-for-LocalDouyin-v2.0.md）：
  - 火枭 BASE = http://192.168.0.105:8100  API_KEY = huoxiao-2026
  - 数据维度: node / visibility / collects / likes / posts / following / follower / comments
  - 错误码: 0=成功 401=鉴权 404=不存在 3002279=私密 500=上游失败 2096=风控冷却
"""
import time
import json
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import List, Optional

import requests

from . import db

router = APIRouter(prefix="/api/crawl")

HUOXIAO_BASE = "http://192.168.0.105:8100"
HUOXIAO_KEY = "huoxiao-2026"
_HX = {"X-Api-Key": HUOXIAO_KEY}


class ImportItem(BaseModel):
    type: str                    # node/visibility/collects/likes/posts/following/follower/comments
    sec_uid: str = ""
    data: dict = {}


class ImportBatch(BaseModel):
    batch_id: str = ""
    items: List[ImportItem] = []


class ScheduleNode(BaseModel):
    sec_uid: str
    nickname: str = ""
    weight: float = 0.5
    dims: List[str] = ["collects", "detail", "visibility"]  # 默认游客可采维度


class ScheduleReq(BaseModel):
    nodes: List[ScheduleNode] = []
    max_per_dim: int = 20


# ───────────────────────── 落库映射 ─────────────────────────

def _import_item(it: ImportItem) -> dict:
    """单条导入，返回 {imported, skipped, reason}"""
    t, sec, d = it.type, it.sec_uid, it.data or {}
    now = int(time.time())

    if t == "node":
        pid = db.upsert_peer(sec, nickname=d.get("nickname", ""), douyin_id=d.get("unique_id", ""),
                             avatar=d.get("avatar", ""), source="huoxiao", note=d.get("signature", "")[:200])
        return {"imported": 1, "peer_id": pid}

    if t == "visibility":
        pid = db.upsert_peer(sec, source="huoxiao")
        tags = []
        for k, v in d.items():
            if isinstance(v, str) and v.startswith("open"):
                tags.append(f"{k}:open")
            elif isinstance(v, str) and v.startswith("closed"):
                tags.append(f"{k}:closed")
        db.update_peer_tags(pid, ",".join(tags))
        return {"imported": 1, "peer_id": pid, "tags": tags}

    if t in ("collects", "likes", "posts"):
        items = d.get("items") or []
        imported, skipped = 0, 0
        pid = db.upsert_peer(sec, source="huoxiao")
        for v in items:
            aid = str(v.get("aweme_id") or "")
            if not aid:
                skipped += 1
                continue
            # 视频去重（按 aweme_id）
            conn = db.get_conn()
            row = conn.execute("SELECT id FROM videos WHERE aweme_id=?", (aid,)).fetchone()
            conn.close()
            if row:
                vid = row[0]
                # 计数更新（保留更全的）
                db.update_video(vid, like_count=v.get("stats", {}).get("digg", 0),
                                comment_count=v.get("stats", {}).get("comment", 0),
                                collect_count=v.get("stats", {}).get("collect", 0))
            else:
                au = v.get("author") or {}
                vid = db.insert_video(
                    title=(v.get("desc") or "")[:200],
                    author=au.get("nickname", ""),
                    file_name=f"{aid}.mp4",
                    file_size=0,
                    source="huoxiao",
                    sec_uid=au.get("sec_uid", ""),
                    avatar_url=v.get("cover", ""),
                    aweme_id=aid,
                    like_count=v.get("stats", {}).get("digg", 0),
                    comment_count=v.get("stats", {}).get("comment", 0),
                    collect_count=v.get("stats", {}).get("collect", 0),
                )
            # 视频-同好关联（共识信号）
            db.add_video_peer_source(vid, pid, source_type=t[:-1] if t != "posts" else "post")
            imported += 1
        return {"imported": imported, "skipped": skipped, "peer_id": pid}

    if t == "video_detail":
        """深采详情：单条完整视频/音频/图集元数据（含评论全字段），按 aweme_id 幂等"""
        items = d.get("items") or []
        imported, skipped, dup = 0, 0, 0
        for v in items:
            aid = str(v.get("aweme_id") or "")
            if not aid:
                skipped += 1
                continue
            au = v.get("author") or {}
            st = v.get("stats") or {}
            comments_json = json.dumps(v.get("comments") or [], ensure_ascii=False)
            common = dict(
                title=(v.get("desc") or "")[:200],
                author=au.get("nickname", ""),
                source="huoxiao",
                sec_uid=au.get("sec_uid", ""),
                avatar_url=au.get("avatar_url") or au.get("avatar", ""),
                music_title=v.get("music_title", ""),
                music_author=v.get("music_author", ""),
                like_count=st.get("digg", 0),
                comment_count=st.get("comment", 0),
                collect_count=st.get("collect", 0),
                media_type=v.get("media_type", ""),
                publish_time=v.get("create_time", 0) or 0,
                comments_json=comments_json,
                duration=v.get("duration_s", 0) or 0,
                cover_url=v.get("cover_url", ""),
                music_cover=v.get("music_cover", ""),
                is_note=1 if v.get("media_type") == "album" else 0,
                image_list=json.dumps(v.get("image_list") or [], ensure_ascii=False),
                music_file=v.get("music_file", ""),
            )
            conn = db.get_conn()
            row = conn.execute("SELECT id FROM videos WHERE aweme_id=?", (aid,)).fetchone()
            conn.close()
            if row:
                vid = row[0]
                db.update_video(vid, **common)
                dup += 1
            else:
                vid = db.insert_video(
                    title=common["title"], author=common["author"],
                    file_name=f"{aid}.mp4", file_size=0,
                    source="huoxiao", sec_uid=common["sec_uid"],
                    avatar_url=common["avatar_url"],
                    music_title=common["music_title"], music_author=common["music_author"],
                    aweme_id=aid,
                    like_count=common["like_count"], comment_count=common["comment_count"],
                    collect_count=common["collect_count"],
                    media_type=common["media_type"], publish_time=common["publish_time"],
                    comments_json=common["comments_json"], duration=common["duration"],
                    cover_url=common["cover_url"],
                    music_cover=common["music_cover"],
                    is_note=common["is_note"],
                    image_list=common["image_list"],
                    music_file=common["music_file"],
                )
            imported += 1
        return {"imported": imported, "skipped": skipped, "dup": dup}

    if t in ("following", "follower"):
        items = d.get("items") or []
        pid = db.upsert_peer(sec, source="huoxiao")
        imported = 0
        for u in items:
            us = u.get("sec_uid") or ""
            if not us:
                continue
            db.upsert_peer(us, nickname=u.get("nickname", ""), douyin_id=u.get("unique_id", ""),
                           source="huoxiao")
            upid = db.get_peer_by_sec_uid(us)[0]
            db.upsert_peer_relation(pid, upid, relation_type=t, strength=1.0)
            imported += 1
        return {"imported": imported, "peer_id": pid}

    if t == "comments":
        # 评论 C 类不落库（火枭契约），仅返回计数供审计
        items = d.get("items") or []
        return {"imported": 0, "received": len(items), "note": "comments C类不落库"}

    return {"imported": 0, "skipped": 0, "reason": f"unknown type:{t}"}


# ───────────────────────── 路由 ─────────────────────────

@router.post("/import")
def crawl_import(batch: ImportBatch):
    """接收火枭采集 JSON 落库（batch_id 幂等信封：已处理批次直接跳过）"""
    if batch.batch_id and db.has_batch(batch.batch_id):
        return {"code": 0, "data": {"batch_id": batch.batch_id, "skipped": True,
                                    "reason": "batch already imported", "ms": 0}}
    t0 = time.time()
    results = []
    total_imported = 0
    for it in batch.items:
        r = _import_item(it)
        r["type"] = it.type
        r["sec_uid"] = it.sec_uid
        total_imported += r.get("imported", 0)
        results.append(r)
    if batch.batch_id:
        db.mark_batch(batch.batch_id, len(batch.items), total_imported)
    return {"code": 0, "data": {"batch_id": batch.batch_id, "imported": total_imported,
                                "items": results, "ms": int((time.time() - t0) * 1000)}}


@router.post("/media")
async def crawl_media(request: Request):
    """接收媒体二进制流落盘（视频/音频/图集/封面/头像），按 aweme_id 回填 file_path

    参数（query）: aweme_id, kind=video|audio|album|cover|avatar, index(图集第几张), ext
    请求体: 原始字节流（Content-Type: application/octet-stream）
    """
    body = await request.body()
    q = dict(request.query_params)
    aid = (q.get("aweme_id") or "").strip()
    kind = q.get("kind") or "video"
    index = int(q.get("index") or 0)
    ext = (q.get("ext") or "").strip()
    if not body or not aid:
        return {"code": 400, "msg": "missing body or aweme_id"}
    base = db.DB_PATH.parent
    if kind == "video":
        d, p = base / "videos", base / "videos" / f"{aid}.mp4"
    elif kind == "audio":
        d, p = base / "music_files", base / "music_files" / f"{aid}.{ext or 'mp3'}"
    elif kind == "album":
        d = base / "note_images" / aid
        p = d / f"{index:02d}.{ext or 'jpg'}"
    elif kind == "cover":
        d, p = base / "music_covers", base / "music_covers" / f"{aid}.{ext or 'jpg'}"
    elif kind == "avatar":
        d, p = base / "avatars", base / "avatars" / f"{aid}.{ext or 'jpg'}"
    else:
        return {"code": 400, "msg": f"unknown kind {kind}"}
    d.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.stat().st_size != len(body):
        p.write_bytes(body)
    # 回填 file_path（video/audio 存文件路径，album 存目录）
    if kind in ("video", "audio", "album"):
        conn = db.get_conn()
        row = conn.execute("SELECT id FROM videos WHERE aweme_id=?", (aid,)).fetchone()
        if row:
            vid = row[0]
            if kind == "album":
                db.update_video_file(vid, str(d), len(body))
                # 累加 image_list（相对路径 作品id/序号.jpg），并标记图文
                rel = f"{aid}/{p.name}"
                old = conn.execute("SELECT image_list FROM videos WHERE id=?", (vid,)).fetchone()[0]
                try:
                    arr = json.loads(old) if old else []
                except Exception:
                    arr = []
                if rel not in arr:
                    arr.append(rel)
                arr.sort()
                conn.close()
                db.update_video(vid, is_note=1, image_list=json.dumps(arr, ensure_ascii=False))
            elif kind == "audio":
                conn.close()
                db.update_video_file(vid, str(p), len(body))
                db.update_video(vid, music_file=p.name)
            else:
                conn.close()
                db.update_video_file(vid, str(p), len(body))
        else:
            conn.close()
    return {"code": 0, "data": {"aweme_id": aid, "kind": kind, "path": str(p), "bytes": len(body)}}


@router.post("/schedule")
def crawl_schedule(req: ScheduleReq):
    """按节点+维度编排：请求火枭 → 自动落库（游客维度优先）"""
    summary = {"ok": 0, "fail": 0, "closed": 0, "detail": []}
    for nd in req.nodes:
        pid = db.upsert_peer(nd.sec_uid, nickname=nd.nickname, source="huoxiao",
                             initial_weight=nd.weight)
        node_report = {"sec_uid": nd.sec_uid, "dims": {}}
        for dim in nd.dims:
            try:
                r = requests.get(f"{HUOXIAO_BASE}/v1/user/{nd.sec_uid}/{dim}",
                                 headers=_HX, params={"limit": req.max_per_dim}, timeout=60)
                j = r.json()
            except Exception as e:
                node_report["dims"][dim] = {"err": f"{type(e).__name__}:{str(e)[:60]}"}
                summary["fail"] += 1
                continue
            code = j.get("code")
            if code == 0:
                imp = _import_item(ImportItem(type=dim, sec_uid=nd.sec_uid, data=j.get("data", {})))
                node_report["dims"][dim] = {"ok": imp.get("imported", 0)}
                summary["ok"] += 1
            elif code == 3002279:
                node_report["dims"][dim] = {"closed": True}
                summary["closed"] += 1
            else:
                node_report["dims"][dim] = {"code": code, "msg": (j.get("meta") or {}).get("msg", "")}
                summary["fail"] += 1
        summary["detail"].append(node_report)
    return {"code": 0, "data": summary}


@router.get("/status")
def crawl_status():
    """最近导入统计"""
    conn = db.get_conn()
    peers = conn.execute("SELECT COUNT(*) FROM peers WHERE source='huoxiao'").fetchone()[0]
    videos = conn.execute("SELECT COUNT(*) FROM videos WHERE source='huoxiao'").fetchone()[0]
    relations = conn.execute("SELECT COUNT(*) FROM peer_relations").fetchone()[0]
    conn.close()
    return {"code": 0, "data": {"peers_from_huoxiao": peers, "videos_from_huoxiao": videos,
                                "relations": relations, "huoxiao_base": HUOXIAO_BASE}}
