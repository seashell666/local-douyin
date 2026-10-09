# -*- coding: utf-8 -*-
"""
local-douyin 数据库层（SQLite，零配置，单文件）
v2: 新增 authors 表 + videos 表扩展 sec_uid/avatar/music 字段
"""
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "videos.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT DEFAULT '',
    author          TEXT DEFAULT '',
    file_name       TEXT NOT NULL,
    file_size       INTEGER DEFAULT 0,
    visible         INTEGER DEFAULT 1,
    importance      INTEGER DEFAULT 0,
    tags            TEXT DEFAULT '',
    source          TEXT DEFAULT '',
    like_count      INTEGER DEFAULT 0,
    comment_count   INTEGER DEFAULT 0,
    collect_count   INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT '',
    sec_uid         TEXT DEFAULT '',
    avatar_url      TEXT DEFAULT '',
    music_title     TEXT DEFAULT '',
    music_cover     TEXT DEFAULT '',
    music_author    TEXT DEFAULT '',
    aweme_id        TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_videos_visible ON videos(visible);

CREATE TABLE IF NOT EXISTS import_batches (
    batch_id    TEXT PRIMARY KEY,
    total       INTEGER DEFAULT 0,
    imported    INTEGER DEFAULT 0,
    dup         INTEGER DEFAULT 0,
    created_at  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS authors (
    sec_uid         TEXT PRIMARY KEY,
    nickname        TEXT DEFAULT '',
    unique_id       TEXT DEFAULT '',
    avatar_url      TEXT DEFAULT '',
    signature       TEXT DEFAULT '',
    follower_count  INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,
    total_favorited INTEGER DEFAULT 0,
    ip_location     TEXT DEFAULT '',
    is_following    INTEGER DEFAULT 0,
    fetched_at      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS friends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_uid         TEXT UNIQUE,
    douyin_id       TEXT DEFAULT '',
    nickname        TEXT DEFAULT '',
    avatar          TEXT DEFAULT '',
    last_visit_time INTEGER DEFAULT 0,
    created_at      INTEGER DEFAULT 0,
    source          TEXT DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_friends_sec_uid ON friends(sec_uid);

-- ═══════════════════════════════════════════════════════════════
-- 策展引擎核心表（P0 闭环）
-- ═══════════════════════════════════════════════════════════════

-- 同好节点：和用户审美相近的人
CREATE TABLE IF NOT EXISTS peers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_uid         TEXT UNIQUE,
    nickname        TEXT DEFAULT '',
    douyin_id       TEXT DEFAULT '',
    avatar          TEXT DEFAULT '',
    source          TEXT DEFAULT 'manual',
    discovered_by   INTEGER DEFAULT 0,
    current_weight  REAL DEFAULT 0.5,
    initial_weight  REAL DEFAULT 0.5,
    status          TEXT DEFAULT 'active',
    added_at        INTEGER DEFAULT 0,
    last_active_at  INTEGER DEFAULT 0,
    total_content   INTEGER DEFAULT 0,
    note            TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_peers_weight ON peers(current_weight);
CREATE INDEX IF NOT EXISTS idx_peers_status ON peers(status);

-- 用户行为事件流（不可变，权重计算的数据源）
CREATE TABLE IF NOT EXISTS behavior_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT DEFAULT 'local',
    video_id        INTEGER NOT NULL,
    peer_id         INTEGER DEFAULT 0,
    event_type      TEXT NOT NULL,
    position        REAL DEFAULT 0,
    duration        REAL DEFAULT 0,
    session_id      TEXT DEFAULT '',
    algorithm_ver   TEXT DEFAULT 'v001',
    metadata        TEXT DEFAULT '',
    created_at      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_behavior_video ON behavior_events(video_id);
CREATE INDEX IF NOT EXISTS idx_behavior_peer ON behavior_events(peer_id);
CREATE INDEX IF NOT EXISTS idx_behavior_type ON behavior_events(event_type);
CREATE INDEX IF NOT EXISTS idx_behavior_time ON behavior_events(created_at);

-- 同好权重历史（每次变化留痕，可追溯）
CREATE TABLE IF NOT EXISTS peer_weights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_id         INTEGER NOT NULL,
    weight          REAL NOT NULL,
    reason          TEXT DEFAULT '',
    algorithm_ver   TEXT DEFAULT 'v001',
    event_count     INTEGER DEFAULT 0,
    calculated_at   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_peer_weights_peer ON peer_weights(peer_id);

-- 同好关系网络（用于发现新同好）
CREATE TABLE IF NOT EXISTS peer_relations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_peer_id    INTEGER NOT NULL,
    to_peer_id      INTEGER NOT NULL,
    relation_type   TEXT DEFAULT 'follow',
    strength        REAL DEFAULT 1.0,
    discovered_at   INTEGER DEFAULT 0,
    UNIQUE(from_peer_id, to_peer_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_from ON peer_relations(from_peer_id);
CREATE INDEX IF NOT EXISTS idx_relations_to ON peer_relations(to_peer_id);

-- 视频-同好多对多关系（一个视频可被多个同好发现=共识信号）
CREATE TABLE IF NOT EXISTS video_peer_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        INTEGER NOT NULL,
    peer_id         INTEGER NOT NULL,
    source_type     TEXT DEFAULT 'like',
    discovered_at   INTEGER DEFAULT 0,
    UNIQUE(video_id, peer_id, source_type)
);
CREATE INDEX IF NOT EXISTS idx_vps_video ON video_peer_sources(video_id);
CREATE INDEX IF NOT EXISTS idx_vps_peer ON video_peer_sources(peer_id);

-- 算法配置（所有参数集中管理，版本化）
CREATE TABLE IF NOT EXISTS algorithm_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT UNIQUE,
    config_json     TEXT NOT NULL,
    is_active       INTEGER DEFAULT 0,
    change_reason   TEXT DEFAULT '',
    created_at      INTEGER DEFAULT 0
);

-- 用户/设备设置（毛玻璃弹窗等UI偏好）
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT DEFAULT '',
    updated_at      INTEGER DEFAULT 0
);
"""

# 老库迁移：补充新增列（幂等）
MIGRATIONS = {
    "like_count": "ALTER TABLE videos ADD COLUMN like_count INTEGER DEFAULT 0",
    "comment_count": "ALTER TABLE videos ADD COLUMN comment_count INTEGER DEFAULT 0",
    "collect_count": "ALTER TABLE videos ADD COLUMN collect_count INTEGER DEFAULT 0",
    "sec_uid": "ALTER TABLE videos ADD COLUMN sec_uid TEXT DEFAULT ''",
    "avatar_url": "ALTER TABLE videos ADD COLUMN avatar_url TEXT DEFAULT ''",
    "music_title": "ALTER TABLE videos ADD COLUMN music_title TEXT DEFAULT ''",
    "music_cover": "ALTER TABLE videos ADD COLUMN music_cover TEXT DEFAULT ''",
    "music_author": "ALTER TABLE videos ADD COLUMN music_author TEXT DEFAULT ''",
    "aweme_id": "ALTER TABLE videos ADD COLUMN aweme_id TEXT DEFAULT ''",
    "import_time": "ALTER TABLE videos ADD COLUMN import_time INTEGER DEFAULT 0",
    "friend_id": "ALTER TABLE videos ADD COLUMN friend_id INTEGER DEFAULT 0",
    "duration": "ALTER TABLE videos ADD COLUMN duration REAL DEFAULT 0",
    "width": "ALTER TABLE videos ADD COLUMN width INTEGER DEFAULT 0",
    "height": "ALTER TABLE videos ADD COLUMN height INTEGER DEFAULT 0",
    "source_peer_id": "ALTER TABLE videos ADD COLUMN source_peer_id INTEGER DEFAULT 0",
    "peer_tags": "ALTER TABLE peers ADD COLUMN tags TEXT DEFAULT ''",
    # 2026-10-01 深采导入扩展（幂等信封 + 全字段）
    "media_type": "ALTER TABLE videos ADD COLUMN media_type TEXT DEFAULT ''",
    "publish_time": "ALTER TABLE videos ADD COLUMN publish_time INTEGER DEFAULT 0",
    "comments_json": "ALTER TABLE videos ADD COLUMN comments_json TEXT DEFAULT ''",
    "file_path": "ALTER TABLE videos ADD COLUMN file_path TEXT DEFAULT ''",
    "cover_url": "ALTER TABLE videos ADD COLUMN cover_url TEXT DEFAULT ''",
    "is_note": "ALTER TABLE videos ADD COLUMN is_note INTEGER DEFAULT 0",
    "image_list": "ALTER TABLE videos ADD COLUMN image_list TEXT DEFAULT ''",
    "music_file": "ALTER TABLE videos ADD COLUMN music_file TEXT DEFAULT ''",
}


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # 迁移：检查缺失列并补充
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)").fetchall()}
    for col, sql in MIGRATIONS.items():
        if col not in cols:
            try:
                conn.execute(sql)
            except Exception:
                pass  # 列可能已存在（跨表迁移）
    # 迁移后再建新列索引（老库没有这些列时不能提前建索引）
    conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_sec_uid ON videos(sec_uid)")
    conn.commit()
    conn.close()
    # 初始化算法默认配置
    init_algorithm_config()


def get_conn():
    return sqlite3.connect(DB_PATH)


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ── videos ─────────────────────────────────────────────────────────────────

def insert_video(title, author, file_name, file_size, source="",
                 sec_uid="", avatar_url="", music_title="", music_cover="",
                 music_author="", aweme_id="", tags="",
                 like_count=0, comment_count=0, collect_count=0,
                 media_type="", publish_time=0, comments_json="", duration=0, cover_url="",
                 is_note=0, image_list="", music_file=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO videos (title, author, file_name, file_size, source, created_at, "
        "sec_uid, avatar_url, music_title, music_cover, music_author, aweme_id, "
        "tags, like_count, comment_count, collect_count, "
        "media_type, publish_time, comments_json, duration, cover_url, "
        "is_note, image_list, music_file) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, author, file_name, file_size, source, now_str(),
         sec_uid, avatar_url, music_title, music_cover, music_author, aweme_id,
         tags, like_count, comment_count, collect_count,
         media_type, publish_time, comments_json, duration, cover_url,
         is_note, image_list, music_file),
    )
    conn.commit()
    vid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return vid


def list_videos(offset=0, limit=20, visible_only=True):
    conn = get_conn()
    cols = ("id, title, author, file_name, file_size, importance, tags, "
            "like_count, comment_count, collect_count, sec_uid, avatar_url, "
            "music_title, music_cover, music_author, aweme_id, is_note, image_list, music_file, "
            "duration, width, height, source_peer_id, cover_url, media_type")
    if visible_only:
        rows = conn.execute(
            f"SELECT {cols} FROM videos WHERE visible=1 AND file_path IS NOT NULL AND file_path != '' ORDER BY CASE media_type WHEN 'album' THEN 0 WHEN 'audio' THEN 1 ELSE 2 END, CASE WHEN cover_url != '' THEN 0 ELSE 1 END, file_size DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM videos WHERE visible=1 AND file_path IS NOT NULL AND file_path != ''").fetchone()[0]
    else:
        rows = conn.execute(
            f"SELECT {cols} FROM videos ORDER BY CASE media_type WHEN 'album' THEN 0 WHEN 'audio' THEN 1 ELSE 2 END, CASE WHEN cover_url != '' THEN 0 ELSE 1 END, file_size DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    conn.close()
    return rows, total


def get_video(vid):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, title, author, file_name, file_size, visible, importance, tags, "
        "like_count, comment_count, collect_count, sec_uid, avatar_url, "
        "music_title, music_cover, music_author, aweme_id FROM videos WHERE id=?",
        (vid,),
    ).fetchone()
    conn.close()
    return row


def list_videos_by_author(sec_uid, offset=0, limit=50):
    conn = get_conn()
    cols = ("id, title, author, file_name, file_size, like_count, comment_count, "
            "collect_count, created_at, aweme_id")
    rows = conn.execute(
        f"SELECT {cols} FROM videos WHERE sec_uid=? AND visible=1 ORDER BY CASE media_type WHEN 'album' THEN 0 WHEN 'audio' THEN 1 ELSE 2 END, CASE WHEN cover_url != '' THEN 0 ELSE 1 END, file_size DESC, id DESC LIMIT ? OFFSET ?",
        (sec_uid, limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM videos WHERE sec_uid=? AND visible=1", (sec_uid,)
    ).fetchone()[0]
    conn.close()
    return rows, total


def update_video(vid, **fields):
    """更新 visible/importance/tags/计数/头像/音乐等"""
    allowed = {"visible", "importance", "tags", "title", "like_count",
               "comment_count", "collect_count", "sec_uid", "avatar_url",
               "music_title", "music_cover", "music_author",
               "duration", "width", "height", "source_peer_id",
               "media_type", "publish_time", "comments_json", "cover_url", "is_note",
               "image_list", "music_file"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(vid)
    conn = get_conn()
    conn.execute(f"UPDATE videos SET {','.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()


def update_video_file(vid, file_path, file_size):
    """媒体文件落盘后更新 file_path / file_size"""
    conn = get_conn()
    conn.execute("UPDATE videos SET file_path=?, file_size=? WHERE id=?", (file_path, file_size, vid))
    conn.commit()
    conn.close()


def has_batch(batch_id):
    """幂等信封：batch_id 是否已处理"""
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM import_batches WHERE batch_id=?", (batch_id,)).fetchone()
    conn.close()
    return row is not None


def mark_batch(batch_id, total, imported, dup=0):
    """记录已处理的批次"""
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO import_batches(batch_id, total, imported, dup, created_at) VALUES(?,?,?,?,?)",
                 (batch_id, total, imported, dup, int(time.time())))
    conn.commit()
    conn.close()


# ── authors ─────────────────────────────────────────────────────────────────

def upsert_author(sec_uid, nickname="", unique_id="", avatar_url="",
                   signature="", follower_count=0, following_count=0,
                   total_favorited=0, ip_location="", cover_url="",
                 is_note=0, image_list="", music_file=""):
    """插入或更新博主信息（不改变 is_following 状态）"""
    conn = get_conn()
    conn.execute(
        """INSERT INTO authors (sec_uid, nickname, unique_id, avatar_url, signature,
           follower_count, following_count, total_favorited, ip_location, cover_url, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(sec_uid) DO UPDATE SET
             nickname=excluded.nickname,
             unique_id=excluded.unique_id,
             avatar_url=excluded.avatar_url,
             signature=excluded.signature,
             follower_count=excluded.follower_count,
             following_count=excluded.following_count,
             total_favorited=excluded.total_favorited,
             ip_location=excluded.ip_location,
             cover_url=excluded.cover_url,
             fetched_at=excluded.fetched_at""",
        (sec_uid, nickname, unique_id, avatar_url, signature,
         follower_count, following_count, total_favorited, ip_location, cover_url, now_str()),
    )
    conn.commit()
    conn.close()


def get_author(sec_uid):
    conn = get_conn()
    row = conn.execute(
        "SELECT sec_uid, nickname, unique_id, avatar_url, signature, "
        "follower_count, following_count, total_favorited, ip_location, "
        "cover_url, is_following, fetched_at FROM authors WHERE sec_uid=?",
        (sec_uid,),
    ).fetchone()
    conn.close()
    return row


def set_following(sec_uid, is_following):
    conn = get_conn()
    # 确保记录存在
    conn.execute(
        "INSERT OR IGNORE INTO authors (sec_uid, is_following) VALUES (?, ?)",
        (sec_uid, 1 if is_following else 0),
    )
    conn.execute("UPDATE authors SET is_following=? WHERE sec_uid=?",
                 (1 if is_following else 0, sec_uid))
    conn.commit()
    conn.close()


def list_followed_authors():
    conn = get_conn()
    rows = conn.execute(
        "SELECT sec_uid, nickname, unique_id, avatar_url, signature, "
        "follower_count, following_count, total_favorited, ip_location, "
        "is_following, fetched_at FROM authors WHERE is_following=1 ORDER BY nickname"
    ).fetchall()
    conn.close()
    return rows


# ── friends ─────────────────────────────────────────────────────────────────

def upsert_friend(sec_uid, douyin_id="", nickname="", avatar="", source="manual"):
    """插入或更新朋友信息"""
    conn = get_conn()
    now = int(time.time())
    existing = conn.execute("SELECT id FROM friends WHERE sec_uid=?", (sec_uid,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE friends SET douyin_id=?, nickname=?, avatar=?, source=? WHERE sec_uid=?",
            (douyin_id, nickname, avatar, source, sec_uid),
        )
        fid = existing[0]
    else:
        conn.execute(
            "INSERT INTO friends (sec_uid, douyin_id, nickname, avatar, last_visit_time, created_at, source) "
            "VALUES (?,?,?,?,?,?,?)",
            (sec_uid, douyin_id, nickname, avatar, 0, now, source),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return fid


def get_friend_by_sec_uid(sec_uid):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, sec_uid, douyin_id, nickname, avatar, last_visit_time, created_at, source "
        "FROM friends WHERE sec_uid=?",
        (sec_uid,),
    ).fetchone()
    conn.close()
    return row


def list_friends():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, sec_uid, douyin_id, nickname, avatar, last_visit_time, created_at, source "
        "FROM friends ORDER BY last_visit_time DESC, created_at DESC"
    ).fetchall()
    conn.close()
    return rows


def update_friend_visit(sec_uid):
    """更新朋友的最后访问时间为当前时间"""
    conn = get_conn()
    now = int(time.time())
    conn.execute("UPDATE friends SET last_visit_time=? WHERE sec_uid=?", (now, sec_uid))
    conn.commit()
    conn.close()


def delete_friend(fid):
    conn = get_conn()
    conn.execute("DELETE FROM friends WHERE id=?", (fid,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════
# peers（同好节点）
# ═══════════════════════════════════════════════════════════════

def upsert_peer(sec_uid, nickname="", douyin_id="", avatar="",
                source="manual", discovered_by=0, initial_weight=0.5,
                status="active", note=""):
    """插入或更新同好节点，返回 peer_id"""
    conn = get_conn()
    now = int(time.time())
    existing = conn.execute("SELECT id FROM peers WHERE sec_uid=?", (sec_uid,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE peers SET nickname=?, douyin_id=?, avatar=?, source=?, "
            "discovered_by=?, status=?, note=? WHERE sec_uid=?",
            (nickname, douyin_id, avatar, source, discovered_by, status, note, sec_uid),
        )
        pid = existing[0]
    else:
        conn.execute(
            "INSERT INTO peers (sec_uid, nickname, douyin_id, avatar, source, "
            "discovered_by, current_weight, initial_weight, status, added_at, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sec_uid, nickname, douyin_id, avatar, source, discovered_by,
             initial_weight, initial_weight, status, now, note),
        )
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return pid


def get_peer(pid):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, sec_uid, nickname, douyin_id, avatar, source, discovered_by, "
        "current_weight, initial_weight, status, added_at, last_active_at, "
        "total_content, note FROM peers WHERE id=?",
        (pid,),
    ).fetchone()
    conn.close()
    return row


def get_peer_by_sec_uid(sec_uid):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, sec_uid, nickname, douyin_id, avatar, source, discovered_by, "
        "current_weight, initial_weight, status, added_at, last_active_at, "
        "total_content, note FROM peers WHERE sec_uid=?",
        (sec_uid,),
    ).fetchone()
    conn.close()
    return row


def list_peers(min_weight=0.0, status=None, limit=100, offset=0):
    conn = get_conn()
    sql = ("SELECT id, sec_uid, nickname, douyin_id, avatar, source, discovered_by, "
           "current_weight, initial_weight, status, added_at, last_active_at, "
           "total_content, note FROM peers WHERE current_weight >= ?")
    args = [min_weight]
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY current_weight DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    rows = conn.execute(sql, args).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM peers WHERE current_weight >= ?" +
        (" AND status=?" if status else ""),
        [min_weight] + ([status] if status else []),
    ).fetchone()[0]
    conn.close()
    return rows, total


def update_peer_weight(pid, new_weight):
    conn = get_conn()
    conn.execute("UPDATE peers SET current_weight=? WHERE id=?", (new_weight, pid))
    conn.commit()
    conn.close()


def update_peer_status(pid, status):
    conn = get_conn()
    conn.execute("UPDATE peers SET status=? WHERE id=?", (status, pid))
    conn.commit()
    conn.close()


def delete_peer(pid):
    conn = get_conn()
    conn.execute("DELETE FROM peers WHERE id=?", (pid,))
    conn.commit()
    conn.close()


def update_peer_tags(pid, tags):
    """更新同好标签（逗号分隔字符串）"""
    conn = get_conn()
    conn.execute("UPDATE peers SET tags=? WHERE id=?", (tags, pid))
    conn.commit()
    conn.close()


def get_peer_groups():
    """
    按标签聚合同好，计算群组权重。
    返回: [{tag, peer_count, avg_weight, max_weight, total_content, peers: [...]}, ...]
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, nickname, current_weight, total_content, tags, status "
        "FROM peers WHERE tags != '' AND tags IS NOT NULL"
    ).fetchall()
    conn.close()

    groups = {}
    for row in rows:
        pid, nick, weight, content, tags, status = row
        if not tags:
            continue
        for tag in [t.strip() for t in tags.split(",") if t.strip()]:
            if tag not in groups:
                groups[tag] = {"tag": tag, "peer_count": 0, "weights": [],
                                "total_content": 0, "peers": []}
            groups[tag]["peer_count"] += 1
            groups[tag]["weights"].append(weight)
            groups[tag]["total_content"] += content or 0
            groups[tag]["peers"].append({"id": pid, "nickname": nick,
                                         "weight": weight, "status": status})

    result = []
    for tag, g in groups.items():
        avg_w = sum(g["weights"]) / len(g["weights"]) if g["weights"] else 0
        max_w = max(g["weights"]) if g["weights"] else 0
        # 群组权重 = 平均权重 × sqrt(同好数)（人多的群组影响力更大）
        import math
        group_weight = round(avg_w * math.sqrt(g["peer_count"]), 4)
        result.append({
            "tag": tag,
            "peer_count": g["peer_count"],
            "avg_weight": round(avg_w, 4),
            "max_weight": round(max_w, 4),
            "group_weight": group_weight,
            "total_content": g["total_content"],
            "peers": g["peers"],
        })
    result.sort(key=lambda x: x["group_weight"], reverse=True)
    return result


# ═══════════════════════════════════════════════════════════════
# behavior_events（用户行为事件）
# ═══════════════════════════════════════════════════════════════

def insert_behavior(video_id, peer_id=0, event_type="impression",
                    position=0.0, duration=0.0, session_id="",
                    algorithm_ver="v001", metadata="", user_id="local"):
    """记录一条用户行为事件，返回 event_id"""
    conn = get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT INTO behavior_events (user_id, video_id, peer_id, event_type, "
        "position, duration, session_id, algorithm_ver, metadata, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id, video_id, peer_id, event_type, position, duration,
         session_id, algorithm_ver, metadata, now),
    )
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return eid


def get_behavior_by_peer(peer_id, start_ts=0, end_ts=0, limit=1000):
    """获取某个同好相关的所有行为事件"""
    conn = get_conn()
    sql = ("SELECT id, user_id, video_id, peer_id, event_type, position, "
           "duration, session_id, algorithm_ver, metadata, created_at "
           "FROM behavior_events WHERE peer_id=?")
    args = [peer_id]
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


def get_behavior_by_video(video_id, limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, user_id, video_id, peer_id, event_type, position, "
        "duration, session_id, algorithm_ver, metadata, created_at "
        "FROM behavior_events WHERE video_id=? ORDER BY created_at DESC LIMIT ?",
        (video_id, limit),
    ).fetchall()
    conn.close()
    return rows


def get_behavior_summary_by_peer(peer_id):
    """按事件类型统计某个同好的行为数量"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT event_type, COUNT(*) as cnt FROM behavior_events "
        "WHERE peer_id=? GROUP BY event_type",
        (peer_id,),
    ).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_all_behavior_summary():
    """统计所有 peer 的行为数量（用于批量权重计算）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT peer_id, event_type, COUNT(*) as cnt "
        "FROM behavior_events WHERE peer_id > 0 "
        "GROUP BY peer_id, event_type",
    ).fetchall()
    conn.close()
    result = {}
    for peer_id, event_type, cnt in rows:
        result.setdefault(peer_id, {})[event_type] = cnt
    return result


# ═══════════════════════════════════════════════════════════════
# peer_weights（权重历史）
# ═══════════════════════════════════════════════════════════════

def insert_peer_weight_history(peer_id, weight, reason="", algorithm_ver="v001", event_count=0):
    conn = get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT INTO peer_weights (peer_id, weight, reason, algorithm_ver, event_count, calculated_at) "
        "VALUES (?,?,?,?,?,?)",
        (peer_id, weight, reason, algorithm_ver, event_count, now),
    )
    conn.commit()
    conn.close()


def get_peer_weight_history(peer_id, limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, peer_id, weight, reason, algorithm_ver, event_count, calculated_at "
        "FROM peer_weights WHERE peer_id=? ORDER BY calculated_at DESC LIMIT ?",
        (peer_id, limit),
    ).fetchall()
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════════
# peer_relations（同好关系网络）
# ═══════════════════════════════════════════════════════════════

def upsert_peer_relation(from_peer_id, to_peer_id, relation_type="follow", strength=1.0):
    conn = get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO peer_relations (from_peer_id, to_peer_id, relation_type, strength, discovered_at) "
        "VALUES (?,?,?,?,?)",
        (from_peer_id, to_peer_id, relation_type, strength, now),
    )
    conn.execute(
        "UPDATE peer_relations SET strength=? WHERE from_peer_id=? AND to_peer_id=? AND relation_type=?",
        (strength, from_peer_id, to_peer_id, relation_type),
    )
    conn.commit()
    conn.close()


def get_peer_relations(peer_id, direction="both"):
    """获取同好的关系网络。direction: from / to / both"""
    conn = get_conn()
    rows = []
    if direction in ("from", "both"):
        rows += conn.execute(
            "SELECT id, from_peer_id, to_peer_id, relation_type, strength, discovered_at "
            "FROM peer_relations WHERE from_peer_id=?",
            (peer_id,),
        ).fetchall()
    if direction in ("to", "both"):
        rows += conn.execute(
            "SELECT id, from_peer_id, to_peer_id, relation_type, strength, discovered_at "
            "FROM peer_relations WHERE to_peer_id=?",
            (peer_id,),
        ).fetchall()
    conn.close()
    return rows


# ═══════════════════════════════════════════════════════════════
# video_peer_sources（视频-同好关联）
# ═══════════════════════════════════════════════════════════════

def add_video_peer_source(video_id, peer_id, source_type="like"):
    conn = get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO video_peer_sources (video_id, peer_id, source_type, discovered_at) "
        "VALUES (?,?,?,?)",
        (video_id, peer_id, source_type, now),
    )
    conn.execute("UPDATE peers SET total_content = total_content + 1 WHERE id=?", (peer_id,))
    conn.commit()
    conn.close()


def get_video_peers(video_id):
    """获取发现这个视频的所有同好（共识信号）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT vps.id, vps.video_id, vps.peer_id, vps.source_type, vps.discovered_at, "
        "p.nickname, p.current_weight "
        "FROM video_peer_sources vps JOIN peers p ON vps.peer_id = p.id "
        "WHERE vps.video_id=?",
        (video_id,),
    ).fetchall()
    conn.close()
    return rows


def get_peer_videos(peer_id, limit=100, offset=0):
    """获取某个同好发现的所有视频"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT v.id, v.title, v.author, v.file_name, v.file_size, v.like_count, "
        "v.comment_count, v.collect_count, v.sec_uid, v.aweme_id, vps.source_type "
        "FROM video_peer_sources vps JOIN videos v ON vps.video_id = v.id "
        "WHERE vps.peer_id=? AND v.visible=1 "
        "ORDER BY vps.discovered_at DESC LIMIT ? OFFSET ?",
        (peer_id, limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM video_peer_sources vps JOIN videos v ON vps.video_id = v.id "
        "WHERE vps.peer_id=? AND v.visible=1",
        (peer_id,),
    ).fetchone()[0]
    conn.close()
    return rows, total


# ═══════════════════════════════════════════════════════════════
# algorithm_config（算法配置）
# ═══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "version": "v001",
    "description": "第一版：简单规则权重 + 基础排序",
    "weight_positive": {
        "like": 1.0, "collect": 1.5, "replay": 0.5,
        "long_watch": 0.3, "play_end": 0.2,
    },
    "weight_negative": {
        "skip": -0.1, "early_exit": -0.2, "not_interested": -1.0,
    },
    "weight_normalization": {
        "method": "sigmoid", "scale": 10.0, "initial_weight": 0.5,
    },
    "ranking": {
        "peer_weight_factor": 0.5,
        "user_feedback_factor": 0.3,
        "content_signal_factor": 0.1,
        "novelty_factor": 0.1,
    },
    "exploration": {
        "ratio": 0.2, "new_peer_weight": 0.3, "low_weight_threshold": 0.3,
    },
    "diversity": {
        "author_repeat_penalty": 0.3,
        "topic_repeat_penalty": 0.2,
        "max_consecutive_same_author": 2,
    },
    "limits": {
        "max_daily_new_peers": 200,
        "max_content_per_peer": 200,
        "min_peer_weight": 0.1,
    },
    "clip_extraction": {
        "window_before_seconds": 2.0,
        "window_after_seconds": 2.0,
    },
    "weight_decay": {
        "enabled": False,
        "half_life_days": 30,
        "min_factor": 0.1,
    },
}


def init_algorithm_config():
    """确保默认配置存在并激活"""
    import json
    conn = get_conn()
    now = int(time.time())
    existing = conn.execute("SELECT COUNT(*) FROM algorithm_config WHERE version='v001'").fetchone()[0]
    if not existing:
        conn.execute(
            "INSERT INTO algorithm_config (version, config_json, is_active, change_reason, created_at) "
            "VALUES (?,?,?,?,?)",
            ("v001", json.dumps(DEFAULT_CONFIG, ensure_ascii=False), 1, "初始默认配置", now),
        )
        conn.commit()
    else:
        # 确保 v001 是激活的
        conn.execute("UPDATE algorithm_config SET is_active=1 WHERE version='v001'")
        conn.execute("UPDATE algorithm_config SET is_active=0 WHERE version!='v001'")
        conn.commit()
    conn.close()


def get_active_config():
    """获取当前激活的算法配置"""
    import json
    conn = get_conn()
    row = conn.execute(
        "SELECT version, config_json FROM algorithm_config WHERE is_active=1 LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return {"version": row[0], **json.loads(row[1])}
    return DEFAULT_CONFIG


def save_config(version, config_dict, change_reason="", set_active=True):
    """保存新版本配置"""
    import json
    conn = get_conn()
    now = int(time.time())
    if set_active:
        conn.execute("UPDATE algorithm_config SET is_active=0")
    conn.execute(
        "INSERT OR REPLACE INTO algorithm_config (version, config_json, is_active, change_reason, created_at) "
        "VALUES (?,?,?,?,?)",
        (version, json.dumps(config_dict, ensure_ascii=False), 1 if set_active else 0, change_reason, now),
    )
    conn.commit()
    conn.close()


def list_configs():
    conn = get_conn()
    rows = conn.execute(
        "SELECT version, is_active, change_reason, created_at FROM algorithm_config ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return rows


def get_config_by_version(version):
    """按版本号获取配置"""
    import json
    conn = get_conn()
    row = conn.execute(
        "SELECT version, config_json, is_active, change_reason, created_at FROM algorithm_config WHERE version=?",
        (version,)
    ).fetchone()
    conn.close()
    if row:
        return {"version": row[0], "config": json.loads(row[1]),
                "is_active": bool(row[2]), "change_reason": row[3], "created_at": row[4]}
    return None


def activate_config(version):
    """激活指定版本（回滚）"""
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM algorithm_config WHERE version=?", (version,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("UPDATE algorithm_config SET is_active=0")
    conn.execute("UPDATE algorithm_config SET is_active=1 WHERE version=?", (version,))
    conn.commit()
    conn.close()
    return True



# ═══════════════════════════════════════════════════════════
# 设置（settings）CRUD
# ═══════════════════════════════════════════════════════════

def get_all_settings():
    """获取所有设置，返回dict"""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def get_setting(key, default=None):
    """获取单个设置"""
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if row:
        return row[0]
    return default


def set_setting(key, value):
    """保存单个设置"""
    import time
    conn = get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
        (key, str(value), now)
    )
    conn.commit()
    conn.close()
    return True
