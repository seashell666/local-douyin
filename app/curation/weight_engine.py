# -*- coding: utf-8 -*-
"""
同好权重计算引擎

  raw_score = Σ(event_weight × time_decay)
  weight = sigmoid(raw_score / scale)

支持时间衰减：越久的行为事件权重越低。
所有参数从 algorithm_config 读取，禁止硬编码。
"""
import math
import json
import time as _time
from .. import db


def _sigmoid(x):
    """数值稳定的 sigmoid"""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        ex = math.exp(x)
        return ex / (1.0 + ex)


def _decay_factor(event_timestamp, now_ts, config):
    """
    计算事件的时间衰减因子。
    配置：weight_decay.enabled / half_life_days / min_factor
    """
    decay_cfg = config.get("weight_decay", {})
    if not decay_cfg.get("enabled", False):
        return 1.0
    half_life_days = decay_cfg.get("half_life_days", 30)
    if half_life_days <= 0:
        return 1.0
    age_seconds = now_ts - event_timestamp
    if age_seconds <= 0:
        return 1.0
    age_days = age_seconds / 86400.0
    factor = 0.5 ** (age_days / half_life_days)
    return round(max(factor, decay_cfg.get("min_factor", 0.1)), 4)


def recalculate_peer_weight(peer_id, config=None):
    """
    重新计算单个同好的权重（含时间衰减）。
    返回: (new_weight, reason_dict, event_count)
    """
    if config is None:
        config = db.get_active_config()

    events = db.get_behavior_by_peer(peer_id, limit=5000)
    if not events:
        return None, {}, 0

    pos_weights = config.get("weight_positive", {})
    neg_weights = config.get("weight_negative", {})
    scale = config.get("weight_normalization", {}).get("scale", 10.0)
    initial = config.get("weight_normalization", {}).get("initial_weight", 0.5)
    now_ts = int(_time.time())

    raw_score = 0.0
    reason = {}
    event_type_counts = {}

    for event in events:
        event_type = event[4]
        created_at = event[10] if len(event) > 10 else 0

        base_w = 0.0
        if event_type in pos_weights:
            base_w = pos_weights[event_type]
        elif event_type in neg_weights:
            base_w = neg_weights[event_type]
        else:
            continue

        decay = _decay_factor(created_at, now_ts, config)
        contribution = base_w * decay
        raw_score += contribution

        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        key = f"{event_type}_decayed"
        reason[key] = round(reason.get(key, 0) + contribution, 3)

    event_count = len(events)

    if event_count == 0:
        new_weight = initial
    else:
        new_weight = _sigmoid(raw_score / scale)

    new_weight = round(max(0.0, min(1.0, new_weight)), 4)

    db.update_peer_weight(peer_id, new_weight)

    reason_str = json.dumps({
        "raw_score": round(raw_score, 3),
        "event_counts": event_type_counts,
        **reason,
    }, ensure_ascii=False)
    db.insert_peer_weight_history(
        peer_id=peer_id,
        weight=new_weight,
        reason=reason_str,
        algorithm_ver=config.get("version", "v001"),
        event_count=event_count,
    )

    return new_weight, reason, event_count


def recalculate_all_weights(config=None):
    """重新计算所有同好的权重。"""
    if config is None:
        config = db.get_active_config()

    peers, _ = db.list_peers(min_weight=0.0, limit=1000)
    results = []

    for peer in peers:
        pid = peer[0]
        old_weight = peer[7]
        nickname = peer[2]

        new_weight, reason, event_count = recalculate_peer_weight(pid, config)
        if new_weight is not None:
            results.append({
                "peer_id": pid,
                "nickname": nickname,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "event_count": event_count,
                "reason": reason,
            })

    return results


def get_peer_weight_explanation(peer_id):
    """生成权重可解释文本。"""
    peer = db.get_peer(peer_id)
    if not peer:
        return "同好不存在"

    config = db.get_active_config()
    pos_weights = config.get("weight_positive", {})
    neg_weights = config.get("weight_negative", {})
    decay_cfg = config.get("weight_decay", {})
    now_ts = int(_time.time())

    lines = [f"同好「{peer[2]}」当前权重：{peer[7]:.4f}"]
    lines.append(f"初始权重：{peer[8]:.4f}")
    if decay_cfg.get("enabled"):
        lines.append(f"时间衰减：已启用（半衰期 {decay_cfg.get('half_life_days', 30)} 天）")
    lines.append("")

    events = db.get_behavior_by_peer(peer_id, limit=5000)
    if not events:
        lines.append("暂无行为数据，使用初始权重。")
        return "\n".join(lines)

    lines.append(f"行为事件总数：{len(events)}")
    lines.append("")

    # 按类型聚合（含衰减）
    type_stats = {}
    raw_score = 0.0
    for event in events:
        et = event[4]
        ts = event[10] if len(event) > 10 else 0
        base_w = pos_weights.get(et, neg_weights.get(et, 0))
        if base_w == 0:
            continue
        decay = _decay_factor(ts, now_ts, config)
        contrib = base_w * decay
        raw_score += contrib
        if et not in type_stats:
            type_stats[et] = {"count": 0, "raw_contrib": 0.0, "decayed_contrib": 0.0}
        type_stats[et]["count"] += 1
        type_stats[et]["raw_contrib"] += base_w
        type_stats[et]["decayed_contrib"] += contrib

    lines.append("行为贡献明细（含衰减）：")
    for et, st in sorted(type_stats.items()):
        lines.append(
            f"  {et}: {st['count']}次 "
            f"原始贡献={st['raw_contrib']:+.3f} "
            f"衰减后={st['decayed_contrib']:+.3f}"
        )

    scale = config.get("weight_normalization", {}).get("scale", 10.0)
    lines.append("")
    lines.append(f"原始分数（衰减后）：{raw_score:.3f}")
    lines.append(f"归一化：sigmoid({raw_score:.3f}/{scale}) = {peer[7]:.4f}")

    history = db.get_peer_weight_history(peer_id, limit=5)
    if history:
        lines.append("")
        lines.append("最近权重变化：")
        for h in history:
            ts = _time.strftime("%m-%d %H:%M", _time.localtime(h[6]))
            lines.append(f"  {ts}: {h[2]:.4f}（基于{h[5]}个事件）")

    return "\n".join(lines)
