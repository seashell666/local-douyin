# -*- coding: utf-8 -*-
"""
指标监控模块
从 behavior_events 聚合日度/总体指标：
- 曝光数、播放开始、播放结束
- 喜欢率、收藏率、跳过率、早退率、完播率
- 平均观看时长
- 新作者发现率（从 peers 表）
- 按 algorithm_ver 分组（支持 A/B 对比）
"""
import sqlite3
from datetime import datetime, timedelta
from typing import Optional


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def compute_metrics(db_path: str, days: int = 7,
                    algorithm_ver: Optional[str] = None) -> dict:
    """计算最近 N 天的聚合指标"""
    conn = _get_conn(db_path)
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp())

    where = "created_at >= ?"
    params = [since]
    if algorithm_ver:
        where += " AND algorithm_ver = ?"
        params.append(algorithm_ver)

    # 按事件类型计数
    _cur = conn.execute(f"SELECT event_type, COUNT(*) as cnt FROM behavior_events WHERE {where} GROUP BY event_type", params)
    counts = {row["event_type"]: row["cnt"] for row in _cur.fetchall()}

    play_start = counts.get("play_start", 0)
    play_end = counts.get("play_end", 0)
    likes = counts.get("like", 0)
    collects = counts.get("collect", 0)
    skips = counts.get("skip", 0)
    early_exits = counts.get("early_exit", 0)
    impressions = counts.get("impression", 0)

    # 平均观看时长（从 play_start 事件的 position/duration 或 metadata）
    _cur = conn.execute(
        f"SELECT AVG(position) as avg_pos FROM behavior_events WHERE {where} AND event_type IN ('play_end','skip','early_exit') AND position > 0",
        params
    )
    row = _cur.fetchone()
    avg_watch_sec = row["avg_pos"] if row and row["avg_pos"] else 0

    # 总视频数和有行为的视频数
    total_videos = conn.execute("SELECT COUNT(*) as cnt FROM videos WHERE visible = 1").fetchone()["cnt"]
    watched_videos = conn.execute(f"SELECT COUNT(DISTINCT video_id) as cnt FROM behavior_events WHERE {where} AND event_type = 'play_start'", params).fetchone()["cnt"]

    # 同好网络指标
    total_peers = conn.execute("SELECT COUNT(*) as cnt FROM peers").fetchone()["cnt"]
    active_peers = conn.execute("SELECT COUNT(*) as cnt FROM peers WHERE status = 'active'").fetchone()["cnt"]
    exploring_peers = conn.execute("SELECT COUNT(*) as cnt FROM peers WHERE status = 'exploring'").fetchone()["cnt"]
    new_peers = conn.execute("SELECT COUNT(*) as cnt FROM peers WHERE added_at >= ?", [since]).fetchone()["cnt"]

    conn.close()

    denom = play_start if play_start > 0 else 1
    metrics = {
        "period_days": days,
        "algorithm_ver": algorithm_ver or "all",
        "impressions": impressions,
        "play_start": play_start,
        "play_end": play_end,
        "likes": likes,
        "collects": collects,
        "skips": skips,
        "early_exits": early_exits,
        "like_rate": round(likes / denom, 4),
        "collect_rate": round(collects / denom, 4),
        "skip_rate": round(skips / denom, 4),
        "early_exit_rate": round(early_exits / denom, 4),
        "completion_rate": round(play_end / denom, 4),
        "avg_watch_sec": round(avg_watch_sec, 1),
        "total_videos": total_videos,
        "watched_videos": watched_videos,
        "video_coverage": round(watched_videos / total_videos, 4) if total_videos > 0 else 0,
        "total_peers": total_peers,
        "active_peers": active_peers,
        "exploring_peers": exploring_peers,
        "new_peers_period": new_peers,
        "new_peer_discovery_rate": round(new_peers / max(days, 1), 2),
    }
    return metrics


def compute_daily_series(db_path: str, days: int = 14,
                         algorithm_ver: Optional[str] = None) -> list:
    """返回最近 N 天的日度指标序列，用于趋势图"""
    conn = _get_conn(db_path)
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp())

    where = "created_at >= ?"
    params = [since]
    if algorithm_ver:
        where += " AND algorithm_ver = ?"
        params.append(algorithm_ver)

    rows = conn.execute(
        f"""SELECT date(created_at, 'unixepoch', 'localtime') as dt,
                   event_type, COUNT(*) as cnt
            FROM behavior_events
            WHERE {where}
            GROUP BY dt, event_type
            ORDER BY dt""",
        params
    ).fetchall()
    conn.close()

    # 按日期聚合
    daily = {}
    for row in rows:
        dt = row["dt"]
        if dt not in daily:
            daily[dt] = {"play_start": 0, "like": 0, "collect": 0,
                         "skip": 0, "early_exit": 0, "play_end": 0, "impression": 0}
        daily[dt][row["event_type"]] = row["cnt"]

    series = []
    for dt in sorted(daily.keys()):
        d = daily[dt]
        ps = d["play_start"] if d["play_start"] > 0 else 1
        series.append({
            "date": dt,
            "play_start": d["play_start"],
            "likes": d["like"],
            "collects": d["collect"],
            "skips": d["skip"],
            "early_exits": d["early_exit"],
            "play_end": d["play_end"],
            "like_rate": round(d["like"] / ps, 4),
            "collect_rate": round(d["collect"] / ps, 4),
            "skip_rate": round(d["skip"] / ps, 4),
            "completion_rate": round(d["play_end"] / ps, 4),
        })
    return series


def compare_algorithms(db_path: str, ver_a: str, ver_b: str, days: int = 7) -> dict:
    """对比两个算法版本的指标"""
    a = compute_metrics(db_path, days, ver_a)
    b = compute_metrics(db_path, days, ver_b)
    diff_keys = ["like_rate", "collect_rate", "skip_rate", "early_exit_rate",
                 "completion_rate", "avg_watch_sec", "play_start"]
    diff = {}
    for k in diff_keys:
        va = a.get(k, 0)
        vb = b.get(k, 0)
        diff[k] = {
            "a": va,
            "b": vb,
            "delta": round(vb - va, 4),
            "delta_pct": round((vb - va) / va * 100, 1) if va != 0 else 0,
        }
    return {"a": a, "b": b, "diff": diff}


def get_health_score(metrics: dict) -> dict:
    """根据指标计算系统健康分（0-100）"""
    score = 50.0
    details = []

    # 喜欢率 > 5% 加分
    lr = metrics.get("like_rate", 0)
    if lr > 0.1:
        score += 15; details.append(f"喜欢率 {lr:.1%} 优秀 +15")
    elif lr > 0.05:
        score += 8; details.append(f"喜欢率 {lr:.1%} 良好 +8")
    elif lr > 0:
        details.append(f"喜欢率 {lr:.1%} 偏低")

    # 跳过率 < 30% 加分
    sr = metrics.get("skip_rate", 0)
    if sr < 0.2:
        score += 10; details.append(f"跳过率 {sr:.1%} 低 +10")
    elif sr < 0.4:
        score += 3; details.append(f"跳过率 {sr:.1%} 中等 +3")
    else:
        score -= 5; details.append(f"跳过率 {sr:.1%} 偏高 -5")

    # 完播率 > 20% 加分
    cr = metrics.get("completion_rate", 0)
    if cr > 0.3:
        score += 10; details.append(f"完播率 {cr:.1%} 优秀 +10")
    elif cr > 0.1:
        score += 5; details.append(f"完播率 {cr:.1%} 良好 +5")

    # 网络扩张
    npd = metrics.get("new_peer_discovery_rate", 0)
    if npd > 0.5:
        score += 5; details.append(f"日均新同好 {npd} +5")
    elif npd > 0:
        score += 2; details.append(f"日均新同好 {npd} +2")

    score = max(0, min(100, round(score, 1)))
    return {"score": score, "details": details}
