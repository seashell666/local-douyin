# -*- coding: utf-8 -*-
"""
候选片段提取器

基于用户点赞时间位置，生成 ±N 秒的候选片段。
这是 Daily Curation 的基础模块。

第一版：±2秒窗口，相邻点赞合并去重。
所有参数从 algorithm_config 读取。
"""
import time
from .. import db


def get_like_events(peer_id=None, start_ts=0, end_ts=0, limit=500):
    """
    获取点赞事件（含时间位置）。
    返回: [(event_id, video_id, peer_id, position, created_at), ...]
    """
    conn = db.get_conn()
    sql = ("SELECT id, video_id, peer_id, position, created_at "
           "FROM behavior_events WHERE event_type='like'")
    args = []
    if peer_id:
        sql += " AND peer_id=?"
        args.append(peer_id)
    if start_ts:
        sql += " AND created_at >= ?"
        args.append(start_ts)
    if end_ts:
        sql += " AND created_at <= ?"
        args.append(end_ts)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def generate_clip_candidates(config=None, start_ts=0, end_ts=0, limit=100):
    """
    生成候选片段列表。

    流程：
    1. 获取点赞事件（含position）
    2. 每个点赞生成 position ± window 秒的片段
    3. 同一视频相邻窗口合并（去重）
    4. 按同好权重排序
    5. 控制作者多样性

    返回: [{video_id, peer_id, start_sec, end_sec, like_position,
            peer_weight, score, author, title}, ...]
    """
    if config is None:
        config = db.get_active_config()

    clip_cfg = config.get("clip_extraction", {})
    window_before = clip_cfg.get("window_before_seconds", 2.0)
    window_after = clip_cfg.get("window_after_seconds", 2.0)
    ranking_cfg = config.get("ranking", {})
    diversity_cfg = config.get("diversity", {})
    author_penalty = diversity_cfg.get("author_repeat_penalty", 0.3)

    # 获取时间范围（默认最近24小时）
    now = int(time.time())
    if not end_ts:
        end_ts = now
    if not start_ts:
        start_ts = end_ts - 86400  # 最近24小时

    like_events = get_like_events(start_ts=start_ts, end_ts=end_ts, limit=2000)
    if not like_events:
        return []

    # 按视频分组
    video_likes = {}
    for event in like_events:
        vid = event[1]
        position = event[3] or 0
        if position <= 0:
            continue
        if vid not in video_likes:
            video_likes[vid] = []
        video_likes[vid].append({
            "position": position,
            "peer_id": event[2],
            "created_at": event[4],
        })

    # 获取视频信息
    video_ids = list(video_likes.keys())
    videos_info = {}
    conn = db.get_conn()
    for vid in video_ids:
        row = conn.execute(
            "SELECT id, title, author, sec_uid, duration FROM videos WHERE id=?",
            (vid,)
        ).fetchone()
        if row:
            videos_info[vid] = {
                "id": row[0], "title": row[1], "author": row[2],
                "sec_uid": row[3], "duration": row[4] or 0,
            }
    conn.close()

    # 获取同好权重
    peer_weights = {}
    peers, _ = db.list_peers(min_weight=0.0, limit=500)
    for p in peers:
        peer_weights[p[0]] = p[7]

    # 生成候选片段（同一视频内合并相邻窗口）
    candidates = []
    for vid, likes in video_likes.items():
        if vid not in videos_info:
            continue
        vinfo = videos_info[vid]
        duration = vinfo["duration"] or 0

        # 按位置排序
        likes.sort(key=lambda x: x["position"])

        # 合并相邻窗口
        merged = []
        for like in likes:
            pos = like["position"]
            start = max(0, pos - window_before)
            end = pos + window_after
            if duration > 0:
                end = min(end, duration)

            if merged and start <= merged[-1]["end"]:
                # 重叠，合并
                merged[-1]["end"] = max(merged[-1]["end"], end)
                merged[-1]["like_positions"].append(pos)
                merged[-1]["peer_ids"].add(like["peer_id"])
                merged[-1]["like_count"] += 1
            else:
                merged.append({
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "like_positions": [pos],
                    "peer_ids": {like["peer_id"]},
                    "like_count": 1,
                })

        # 为每个合并后的片段计算分数
        for clip in merged:
            # 取最高同好权重
            max_peer_w = 0.3
            for pid in clip["peer_ids"]:
                if pid in peer_weights:
                    max_peer_w = max(max_peer_w, peer_weights[pid])

            # 点赞数加成
            like_bonus = min(clip["like_count"] * 0.1, 0.5)

            score = (
                max_peer_w * ranking_cfg.get("peer_weight_factor", 0.5)
                + like_bonus * ranking_cfg.get("user_feedback_factor", 0.3)
            )

            candidates.append({
                "video_id": vid,
                "title": vinfo["title"],
                "author": vinfo["author"],
                "sec_uid": vinfo["sec_uid"],
                "start_sec": clip["start"],
                "end_sec": clip["end"],
                "duration_sec": round(clip["end"] - clip["start"], 2),
                "like_positions": clip["like_positions"],
                "like_count": clip["like_count"],
                "peer_ids": list(clip["peer_ids"]),
                "peer_weight": round(max_peer_w, 4),
                "score": round(score, 4),
            })

    # 按分数排序
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 作者多样性惩罚
    author_count = {}
    final = []
    for c in candidates:
        author = c["author"]
        author_count[author] = author_count.get(author, 0) + 1
        penalty = 0.0
        if author_count[author] > 1:
            penalty = author_penalty * (author_count[author] - 1)
        c["score"] = round(max(0, c["score"] - penalty), 4)
        c["duplicate_penalty"] = round(penalty, 4)
        final.append(c)

    final.sort(key=lambda x: x["score"], reverse=True)
    return final[:limit]


def get_clip_manifest(config=None, start_ts=0, end_ts=0):
    """
    生成 Daily Curation 的 manifest.json 数据结构。
    包含候选片段列表、统计信息、生成时间。
    """
    if config is None:
        config = db.get_active_config()

    now = int(time.time())
    if not end_ts:
        end_ts = now
    if not start_ts:
        start_ts = end_ts - 86400

    clips = generate_clip_candidates(config, start_ts, end_ts)

    total_duration = sum(c["duration_sec"] for c in clips)
    authors = set(c["author"] for c in clips)
    peers = set()
    for c in clips:
        peers.update(c["peer_ids"])

    manifest = {
        "generated_at": now,
        "period_start": start_ts,
        "period_end": end_ts,
        "algorithm_ver": config.get("version", "v001"),
        "stats": {
            "clip_count": len(clips),
            "total_duration_sec": round(total_duration, 2),
            "unique_authors": len(authors),
            "unique_peers": len(peers),
        },
        "clips": clips,
        "render_status": "pending",  # pending / rendering / done / failed
        "render_note": "ffmpeg not available, manifest only",
    }
    return manifest
