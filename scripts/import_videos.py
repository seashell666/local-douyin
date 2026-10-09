# -*- coding: utf-8 -*-
"""
视频导入脚本：扫描一个文件夹里的 mp4，解析文件名 → 移入 data/videos → 入库
用法:
    python scripts/import_videos.py "C:\某个文件夹"
    python scripts/import_videos.py --move=no "C:\某个文件夹"   # 不移动只登记
"""
import re
import shutil
import sys
from pathlib import Path

# 让脚本能 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

VIDEO_DIR = Path(__file__).resolve().parent.parent / "data" / "videos"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}


def parse_name(file_stem):
    """从文件名解析 (作者, 标题)
    规则：第一个下划线前是作者，其余是标题；无下划线则整名作标题
    """
    stem = re.sub(r"\.sync-conflict-.*$", "", file_stem)  # 去掉同步冲突后缀
    if "_" in stem:
        author, _, title = stem.partition("_")
        return author.strip(), (title.strip() or author.strip())
    return "", stem.strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法: python scripts/import_videos.py <视频文件夹路径>")
        return
    src_dir = Path(args[0])
    if not src_dir.is_dir():
        print(f"文件夹不存在: {src_dir}")
        return
    move = "--move=no" not in sys.argv

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()

    files = sorted([f for f in src_dir.iterdir() if f.suffix.lower() in VIDEO_EXTS])
    print(f"发现 {len(files)} 个视频")

    ok, skipped = 0, 0
    for f in files:
        # 已存在同名文件则跳过（避免重复入库）
        target = VIDEO_DIR / f.name
        if target.exists() and target.stat().st_size == f.stat().st_size:
            skipped += 1
            continue
        author, title = parse_name(f.stem)
        if move:
            shutil.move(str(f), str(target))
        else:
            target = f  # 不移动，直接用原路径登记（Docker 部署时慎用）
        vid = db.insert_video(title, author, target.name, target.stat().st_size, source="manual")
        print(f"  [{vid}] {author or '?'} / {title[:30]}")
        ok += 1

    print(f"\n完成：导入 {ok} 条，跳过 {skipped} 条（已存在）")
    print(f"视频目录: {VIDEO_DIR}")


if __name__ == "__main__":
    main()
