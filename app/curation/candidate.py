# -*- coding: utf-8 -*-
"""
候选生成与排序引擎

候选来源：
  1. 高权重同好的内容（精准推荐）
  2. 中权重同好的内容
  3. 新发现同好的内容（探索）
  4. 无同好关联的内容（冷启动兜底）

排序公式（v001）：
  score = peer_weight × peer_weight_factor
        + user_feedback × user_feedback_factor
        + content_signal × content_signal_factor
        + novelty × novelty_factor
        - duplicate_penalty

所有参数从 algorithm_config 读取。
"""
from .. import db


def _get_content_signal(video_row):
    """
    内容质量信号：基于抖音点赞/评论/收藏数归一化。
    返回 0~1 的分数。
    """
    like_count = video_row[7] if len(video_row) > 7 else 0
    comment_count = video_row[8] if len(video_row) > 8 else 0
    collect_count = video_row[9] if len(video_row) > 9 else 0

    # 简单归一化：对数压缩后映射到 0~1
    import math
    total = like_count + comment_count * 2 + collect_count * 3
    if total <= 0:
        return 0.3  # 默认中等
    signal = min(1.0, math.log10(total + 1) / 6.0)  # 100万互动约=1.0
    return round(signal, 4)


def _get_user_feedback(video_id):
    """
    用户对该视频的历史反馈。
    有收藏=1.0，有点赞=0.7，有观看=0.5，无=0.5
    """
    events = db.get_behavior_by_video(video_id, limit=50)
    has_collect = any(e[3] == "collect" for e in events)
    has_like = any(e[3] == "like" for e in events)
    has_watch = any(e[3] in ("play_start", "watch_duration", "play_end") for e in events)

    if has_collect:
        return 1.0
    if has_like:
        return 0.7
    if has_watch:
        return 0.5
    return 0.5  # 未观看，默认中等


def _get_novelty(video_id):
    """
    新颖度：未观看=1.0，已观看=0.3
    """
    events = db.get_behavior_by_video(video_id, limit=10)
    has_watched = any(e[3] in ("play_start", "watch_duration", "play_end", "skip", "early_exit") for e in events)
    return 0.3 if has_watched else 1.0


def rank_videos(video_rows, config=None):
    """
    对一批视频进行排序评分。

    video_rows: 来自 db.list_videos 格式的行列表
    返回: [(score, video_row, detail_dict), ...] 按分数降序
    """
    if config is None:
        config = db.get_active_config()

    ranking_cfg = config.get("ranking", {})
    peer_weight_factor = ranking_cfg.get("peer_weight_factor", 0.5)
    user_feedback_factor = ranking_cfg.get("user_feedback_factor", 0.3)
    content_signal_factor = ranking_cfg.get("content_signal_factor", 0.1)
    novelty_factor = ranking_cfg.get("novelty_factor", 0.1)

    diversity_cfg = config.get("diversity", {})
    author_penalty = diversity_cfg.get("author_repeat_penalty", 0.3)

    scored = []
    author_count = {}

    for row in video_rows:
        vid = row[0]
        sec_uid = row[10] if len(row) > 10 else ""

        # 获取该视频的来源同好权重（取最高的）
        video_peers = db.get_video_peers(vid)
        if video_peers:
            peer_weight = max(vp[6] for vp in video_peers)  # current_weight
        else:
            peer_weight = 0.3  # 无同好关联，默认低权重

        user_fb = _get_user_feedback(vid)
        content_sig = _get_content_signal(row)
        novelty = _get_novelty(vid)

        # 作者重复惩罚
        author_count[sec_uid] = author_count.get(sec_uid, 0) + 1
        dup_penalty = 0.0
        if author_count[sec_uid] > 1:
            dup_penalty = author_penalty * (author_count[sec_uid] - 1)

        score = (
            peer_weight * peer_weight_factor
            + user_fb * user_feedback_factor
            + content_sig * content_signal_factor
            + novelty * novelty_factor
            - dup_penalty
        )
        score = round(max(0.0, score), 4)

        detail = {
            "peer_weight": peer_weight,
            "user_feedback": user_fb,
            "content_signal": content_sig,
            "novelty": novelty,
            "duplicate_penalty": dup_penalty,
            "total_score": score,
        }
        scored.append((score, row, detail))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def generate_recommendations(limit=20, offset=0, config=None):
    """
    生成推荐视频列表。

    策略：
    1. 从所有可见视频中取候选池（扩大采样）
    2. 按排序引擎评分
    3. 应用探索比例：前 (1-exploration_ratio) 为精准，后 exploration_ratio 为随机探索
    4. 返回分页结果

    返回: (items, total)  items 为带 score 和 detail 的视频 dict 列表
    """
    if config is None:
        config = db.get_active_config()

    exploration_ratio = config.get("exploration", {}).get("ratio", 0.2)

    # 取较大的候选池
    pool_size = max(limit * 5, 100)
    all_videos, total = db.list_videos(offset=0, limit=pool_size, visible_only=True)

    if not all_videos:
        return [], 0

    # 评分排序
    scored = rank_videos(all_videos, config)

    # 分离精准和探索
    n_precision = int(len(scored) * (1 - exploration_ratio))
    precision_items = scored[:n_precision]
    exploration_items = scored[n_precision:]

    # 探索部分打乱
    import random
    random.shuffle(exploration_items)

    # 合并
    final_scored = precision_items + exploration_items

    # 分页
    page = final_scored[offset:offset + limit]

    items = []
    for score, row, detail in page:
        item = {
            "id": row[0],
            "title": row[1],
            "author": row[2],
            "file_name": row[3],
            "file_size": row[4],
            "importance": row[5],
            "tags": row[6],
            "like_count": row[7],
            "comment_count": row[8],
            "collect_count": row[9],
            "sec_uid": row[10] or "",
            "avatar_url": f"/api/avatar/{row[11]}" if len(row) > 11 and row[11] else "",
            "music_title": row[12] if len(row) > 12 else "",
            "music_cover": f"/api/music-cover/{row[13]}" if len(row) > 13 and row[13] else "",
            "music_author": row[14] if len(row) > 14 else "",
            "aweme_id": row[15] if len(row) > 15 else "",
            "is_note": bool(row[16]) if len(row) > 16 else False,
            "image_list": row[17] if len(row) > 17 and row[17] else "",
            "music_file": row[18] if len(row) > 18 and row[18] else "",
            "duration": row[19] if len(row) > 19 else 0,
            "width": row[20] if len(row) > 20 else 0,
            "height": row[21] if len(row) > 21 else 0,
            "source_peer_id": row[22] if len(row) > 22 else 0,
            "url": f"/api/videos/{row[0]}/stream",
            "curation_score": score,
            "curation_detail": detail,
        }
        items.append(item)

    return items, len(final_scored)


def get_recommendation_explanation(video_id):
    """
    生成推荐可解释文本。
    回答："为什么这个视频被推荐？"
    """
    video = db.get_video(video_id)
    if not video:
        return "视频不存在"

    config = db.get_active_config()
    video_peers = db.get_video_peers(video_id)

    lines = [f"视频「{video[1]}」推荐原因分析"]
    lines.append(f"作者：{video[2]}")
    lines.append("")

    if video_peers:
        lines.append("发现该视频的同好：")
        for vp in video_peers:
            lines.append(f"  - {vp[5]}（权重 {vp[6]:.4f}，通过 {vp[3]}）")
        max_peer_weight = max(vp[6] for vp in video_peers)
        lines.append(f"  最高同好权重：{max_peer_weight:.4f}")
    else:
        lines.append("无同好关联（冷启动/兜底推荐）")

    lines.append("")

    # 评分明细
    scored = rank_videos([video], config)
    if scored:
        _, _, detail = scored[0]
        lines.append("评分明细：")
        lines.append(f"  同好权重分：{detail['peer_weight']:.4f}")
        lines.append(f"  用户反馈分：{detail['user_feedback']:.4f}")
        lines.append(f"  内容质量分：{detail['content_signal']:.4f}")
        lines.append(f"  新颖度分：{detail['novelty']:.4f}")
        lines.append(f"  重复惩罚：-{detail['duplicate_penalty']:.4f}")
        lines.append(f"  总分：{detail['total_score']:.4f}")

    return "\n".join(lines)
