# -*- coding: utf-8 -*-
"""
每日自动运行脚本 — 系统飞轮自维护

执行流程（对应指南第25节每日开发循环）：
1. 关系网络自动扩张（发现新同好候选）
2. 低权重同好清理（防止膨胀）
3. 全量权重重算
4. 生成每日策展 manifest

用法: python scripts/daily_maintenance.py
可配合 Windows 任务计划程序每天定时运行。
"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db
from app.curation import recalculate_all_weights
from app.curation.clip_extractor import get_clip_manifest


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def main():
    db.init_db()
    log("=== 每日系统维护开始 ===")

    # 1. 关系网络自动扩张
    log("1/4 关系网络自动扩张...")
    try:
        from app.main import api_auto_expand
        result = api_auto_expand(max_new=5)
        log(f"    新增同好候选: {result.get('added', 0)}")
    except Exception as e:
        log(f"    扩张失败: {e}")

    # 2. 低权重清理
    log("2/4 低权重同好清理...")
    try:
        from app.main import api_cleanup_low_weight
        result = api_cleanup_low_weight()
        log(f"    暂停低权重同好: {result.get('paused', 0)}")
    except Exception as e:
        log(f"    清理失败: {e}")

    # 3. 全量权重重算
    log("3/4 全量权重重算...")
    try:
        results = recalculate_all_weights()
        log(f"    重算 {len(results)} 个同好权重")
        for r in results[:5]:
            log(f"    {r['nickname']}: {r['old_weight']:.4f} -> {r['new_weight']:.4f}")
    except Exception as e:
        log(f"    重算失败: {e}")

    # 4. 生成每日策展
    log("4/4 生成每日策展 manifest...")
    try:
        manifest = get_clip_manifest()
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "curation")
        os.makedirs(out_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(out_dir, f"curation_{date_str}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        stats = manifest["stats"]
        log(f"    候选片段: {stats['clip_count']}个, "
            f"总时长: {stats['total_duration_sec']}s, "
            f"作者: {stats['unique_authors']}个")
        log(f"    已保存: {path}")
    except Exception as e:
        log(f"    策展生成失败: {e}")

    # 统计
    peers, total = db.list_peers(min_weight=0.0, limit=1000)
    active = sum(1 for p in peers if p[9] == "active")
    exploring = sum(1 for p in peers if p[9] == "exploring")
    paused = sum(1 for p in peers if p[9] == "paused")

    log("=== 维护完成 ===")
    log(f"同好总数: {total} (活跃:{active} 探索中:{exploring} 已暂停:{paused})")


if __name__ == "__main__":
    main()
