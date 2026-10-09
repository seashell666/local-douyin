# -*- coding: utf-8 -*-
"""
新同好发现模块

策略：
1. 从 friends 表导入为 peers（手动添加的朋友）
2. 从已关注的 authors 中发现高价值同好
3. 从高权重 peer 的关系网络发现新节点（P4，需真实采集）
4. 第一版主要用 Mock/导入方式，真实网络发现待采集器完成
"""
from .. import db


def import_friends_as_peers():
    """
    将 friends 表中的所有朋友导入为 peers（同好节点）。
    已存在的跳过，新增的使用初始权重 0.5。

    返回: {added: int, skipped: int, peers: [...]}
    """
    friends = db.list_friends()
    added = 0
    skipped = 0
    new_peers = []

    for f in friends:
        sec_uid = f[1]
        nickname = f[3]
        douyin_id = f[2]
        avatar = f[4]

        # 检查是否已存在
        existing = db.get_peer_by_sec_uid(sec_uid)
        if existing:
            skipped += 1
            continue

        pid = db.upsert_peer(
            sec_uid=sec_uid,
            nickname=nickname,
            douyin_id=douyin_id,
            avatar=avatar,
            source="friend_import",
            initial_weight=0.5,
            status="active",
            note=f"从朋友列表导入（原friend_id={f[0]}）",
        )
        added += 1
        new_peers.append({"peer_id": pid, "nickname": nickname, "sec_uid": sec_uid})

    return {"added": added, "skipped": skipped, "peers": new_peers}


def import_followed_authors_as_peers():
    """
    将已关注的 authors 导入为 peers。
    关注的博主可能是内容创作者，也可能是同好。
    第一版全部导入，用户可在面板中调整。

    返回: {added: int, skipped: int}
    """
    authors = db.list_followed_authors()
    added = 0
    skipped = 0

    for a in authors:
        sec_uid = a[0]
        nickname = a[1]
        unique_id = a[2]
        avatar = a[3]

        existing = db.get_peer_by_sec_uid(sec_uid)
        if existing:
            skipped += 1
            continue

        pid = db.upsert_peer(
            sec_uid=sec_uid,
            nickname=nickname,
            douyin_id=unique_id,
            avatar=avatar,
            source="followed_author",
            initial_weight=0.4,  # 关注的作者默认权重略低，可能是创作者而非同好
            status="exploring",
            note="从关注博主导入",
        )
        added += 1

    return {"added": added, "skipped": skipped}


def discover_peers_from_relations(peer_id, max_candidates=10):
    """
    从高权重同好的关系网络发现新同好。

    第一版：基于 peer_relations 表查询。
    真实采集（爬取关注列表）待 likes-monitor 完成后接入。

    返回: [candidate_peer_info, ...]
    """
    peer = db.get_peer(peer_id)
    if not peer:
        return []

    relations = db.get_peer_relations(peer_id, direction="from")
    candidates = []

    for rel in relations:
        to_peer_id = rel[2]
        relation_type = rel[3]
        strength = rel[4]

        to_peer = db.get_peer(to_peer_id)
        if to_peer:
            candidates.append({
                "peer_id": to_peer_id,
                "nickname": to_peer[2],
                "sec_uid": to_peer[1],
                "relation_type": relation_type,
                "strength": strength,
                "discovered_by": peer_id,
                "discovered_by_nickname": peer[2],
                "current_weight": to_peer[7],
                "status": to_peer[8],
            })

    # 按关系强度排序
    candidates.sort(key=lambda x: x["strength"], reverse=True)
    return candidates[:max_candidates]


def auto_discover_from_top_peers(top_n=3, max_per_peer=5):
    """
    自动从权重最高的 N 个同好的关系网络发现新节点。

    返回: {discovered: [...], total: int}
    """
    peers, _ = db.list_peers(min_weight=0.5, status="active", limit=top_n)
    all_candidates = []

    for peer in peers:
        pid = peer[0]
        candidates = discover_peers_from_relations(pid, max_candidates=max_per_peer)
        for c in candidates:
            # 只返回尚未成为 active peer 的候选
            if c["status"] != "active":
                all_candidates.append(c)

    return {"discovered": all_candidates, "total": len(all_candidates)}


def add_discovery_candidate(sec_uid, nickname, discovered_by, source="relation",
                            initial_weight=0.3):
    """
    将发现的候选节点加入 peers 表（status=exploring）。

    返回: peer_id
    """
    pid = db.upsert_peer(
        sec_uid=sec_uid,
        nickname=nickname,
        source=source,
        discovered_by=discovered_by,
        initial_weight=initial_weight,
        status="exploring",
        note=f"由 peer_id={discovered_by} 发现",
    )

    # 建立关系
    if discovered_by:
        db.upsert_peer_relation(discovered_by, pid, relation_type="discovered", strength=1.0)

    return pid


def link_videos_to_peers_by_author():
    """
    根据视频的 sec_uid（作者）匹配同好，建立 video_peer_sources 关联。

    逻辑：如果一个视频的作者就是某个 peer，那么这个视频由该 peer"创作/发现"。
    这是第一版的简化关联，真实场景应该是 peer 点赞了这个视频。

    返回: {linked: int, already_linked: int}
    """
    peers, _ = db.list_peers(min_weight=0.0, limit=1000)
    peer_sec_uids = {p[1]: p[0] for p in peers if p[1]}  # sec_uid -> peer_id

    if not peer_sec_uids:
        return {"linked": 0, "already_linked": 0}

    videos, total = db.list_videos(offset=0, limit=5000, visible_only=True)
    linked = 0
    already = 0

    for v in videos:
        vid = v[0]
        sec_uid = v[10] if len(v) > 10 else ""
        if sec_uid and sec_uid in peer_sec_uids:
            pid = peer_sec_uids[sec_uid]
            # 检查是否已关联
            existing = db.get_video_peers(vid)
            if any(e[2] == pid for e in existing):
                already += 1
                continue
            db.add_video_peer_source(vid, pid, source_type="author_match")
            linked += 1

    return {"linked": linked, "already_linked": already}
