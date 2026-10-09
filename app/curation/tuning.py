# -*- coding: utf-8 -*-
"""
算法参数调优建议器

基于当前指标数据，分析算法参数表现，给出调优建议。
不自动修改配置，只输出建议供人工参考。
"""
from . import db
from .metrics import compute_metrics, get_health_score


# 目标阈值
TARGETS = {
    "like_rate": {"min": 0.05, "max": 0.20, "label": "喜欢率"},
    "collect_rate": {"min": 0.01, "max": 0.10, "label": "收藏率"},
    "skip_rate": {"min": 0.0, "max": 0.30, "label": "跳过率"},
    "early_exit_rate": {"min": 0.0, "max": 0.15, "label": "早退率"},
    "completion_rate": {"min": 0.05, "max": 0.30, "label": "完播率"},
    "avg_watch_sec": {"min": 5.0, "max": 30.0, "label": "平均观看时长"},
}


def analyze_metrics(metrics):
    """分析指标，返回每个指标的状态"""
    analysis = {}
    for key, target in TARGETS.items():
        value = metrics.get(key, 0)
        if value < target["min"]:
            status = "low"
        elif value > target["max"]:
            status = "high"
        else:
            status = "normal"
        analysis[key] = {
            "value": value,
            "target_min": target["min"],
            "target_max": target["max"],
            "status": status,
            "label": target["label"],
        }
    return analysis


def generate_suggestions(metrics, config=None):
    """
    基于指标和当前配置，生成调优建议。

    返回: [{parameter, current, suggested, reason, priority}, ...]
    """
    if config is None:
        config = db.get_active_config()

    analysis = analyze_metrics(metrics)
    suggestions = []
    ranking = config.get("ranking", {})
    feedback = config.get("feedback_weights", {})
    exploration = config.get("exploration", {})

    # 1. 跳过率过高 → 增加skip负反馈权重 或 增加探索
    if analysis["skip_rate"]["status"] == "high":
        current_skip = feedback.get("skip", -0.1)
        suggested_skip = round(current_skip * 1.5, 2)
        suggestions.append({
            "parameter": "feedback_weights.skip",
            "current": current_skip,
            "suggested": suggested_skip,
            "reason": "跳过率%.1f%%超过阈值%.0f%%，加强skip负反馈可降低低质量内容排名" % (
                analysis["skip_rate"]["value"] * 100, TARGETS["skip_rate"]["max"] * 100),
            "priority": "high",
        })
        # 也可以建议增加探索比例
        current_exp = exploration.get("exploration_ratio", 0.2)
        if current_exp < 0.3:
            suggestions.append({
                "parameter": "exploration.exploration_ratio",
                "current": current_exp,
                "suggested": round(min(current_exp + 0.1, 0.4), 2),
                "reason": "跳过率高可能是推荐内容同质化，增加探索比例引入新内容",
                "priority": "medium",
            })

    # 2. 喜欢率过低 → 增加同好权重因子 或 增加用户反馈权重
    if analysis["like_rate"]["status"] == "low":
        current_peer = ranking.get("peer_weight_factor", 0.5)
        if current_peer < 0.7:
            suggestions.append({
                "parameter": "ranking.peer_weight_factor",
                "current": current_peer,
                "suggested": round(min(current_peer + 0.1, 0.7), 2),
                "reason": "喜欢率%.1f%%低于阈值%.0f%%，提高同好权重因子可增加高权重同好内容曝光" % (
                    analysis["like_rate"]["value"] * 100, TARGETS["like_rate"]["min"] * 100),
                "priority": "high",
            })

    # 3. 完播率过低 → 增加long_watch正反馈权重
    if analysis["completion_rate"]["status"] == "low":
        current_lw = feedback.get("long_watch", 0.3)
        suggestions.append({
            "parameter": "feedback_weights.long_watch",
            "current": current_lw,
            "suggested": round(current_lw * 1.3, 2),
            "reason": "完播率%.1f%%低于阈值%.0f%%，加强long_watch正反馈可提升完整观看内容排名" % (
                analysis["completion_rate"]["value"] * 100, TARGETS["completion_rate"]["min"] * 100),
            "priority": "medium",
        })

    # 4. 收藏率过低 → 增加collect正反馈权重
    if analysis["collect_rate"]["status"] == "low":
        current_collect = feedback.get("collect", 1.5)
        suggestions.append({
            "parameter": "feedback_weights.collect",
            "current": current_collect,
            "suggested": round(current_collect * 1.2, 2),
            "reason": "收藏率%.1f%%低于阈值%.0f%%，加强collect正反馈可提升高价值内容排名" % (
                analysis["collect_rate"]["value"] * 100, TARGETS["collect_rate"]["min"] * 100),
            "priority": "low",
        })

    # 5. 平均观看时长过短 → 检查是否视频本身短 或 推荐质量差
    if analysis["avg_watch_sec"]["status"] == "low":
        suggestions.append({
            "parameter": "ranking.content_signal_factor",
            "current": ranking.get("content_signal_factor", 0.1),
            "suggested": round(min(ranking.get("content_signal_factor", 0.1) + 0.05, 0.2), 2),
            "reason": "平均观看%.1fs低于阈值%.0fs，提高内容信号因子可优先推荐高质量内容" % (
                analysis["avg_watch_sec"]["value"], TARGETS["avg_watch_sec"]["min"]),
            "priority": "medium",
        })

    # 6. 所有指标正常 → 保持当前配置
    normal_count = sum(1 for a in analysis.values() if a["status"] == "normal")
    if normal_count == len(analysis):
        suggestions.append({
            "parameter": "global",
            "current": "all normal",
            "suggested": "keep current",
            "reason": "所有指标在目标范围内，建议保持当前配置，继续观察",
            "priority": "info",
        })

    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    suggestions.sort(key=lambda x: priority_order.get(x["priority"], 9))
    return suggestions


def get_tuning_report(db_path, days=7):
    """生成完整的调优报告"""
    metrics = compute_metrics(db_path, days=days)
    health = get_health_score(metrics)
    analysis = analyze_metrics(metrics)
    suggestions = generate_suggestions(metrics)

    return {
        "period_days": days,
        "health_score": health["score"],
        "health_details": health["details"],
        "metrics_analysis": analysis,
        "suggestions": suggestions,
        "summary": {
            "total_suggestions": len(suggestions),
            "high_priority": sum(1 for s in suggestions if s["priority"] == "high"),
            "medium_priority": sum(1 for s in suggestions if s["priority"] == "medium"),
            "low_priority": sum(1 for s in suggestions if s["priority"] == "low"),
        },
    }
