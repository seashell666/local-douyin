# -*- coding: utf-8 -*-
"""
批量提取本地视频元数据（duration/width/height）并写入数据库
用法: python scripts/extract_metadata.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db
from app.mp4_metadata import parse_metadata

VIDEO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "videos")


def main():
    db.init_db()
    videos, total = db.list_videos(offset=0, limit=5000, visible_only=False)
    print(f"数据库中共有 {total} 个视频")

    success = 0
    failed = 0
    skipped = 0
    start = time.time()

    for row in videos:
        vid = row[0]
        file_name = row[3]
        # 检查是否已有元数据
        existing_duration = row[19] if len(row) > 19 else 0
        if existing_duration and existing_duration > 0:
            skipped += 1
            continue

        video_path = os.path.join(VIDEO_DIR, file_name)
        if not os.path.exists(video_path):
            failed += 1
            continue

        meta = parse_metadata(video_path)
        if meta and meta["duration"] > 0:
            db.update_video(vid, duration=meta["duration"],
                           width=meta["width"], height=meta["height"])
            success += 1
            if success % 10 == 0:
                print(f"  已处理 {success} 个...")
        else:
            failed += 1

    elapsed = time.time() - start
    print(f"\n完成: 成功={success}, 失败={failed}, 跳过(已有)={skipped}")
    print(f"耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
