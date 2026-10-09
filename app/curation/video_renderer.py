# -*- coding: utf-8 -*-
"""
视频渲染器：将每日策展的候选片段用 ffmpeg 拼接成最终视频。

流程：
1. 从 manifest 读取片段列表（video_id, start_sec, end_sec）
2. 查数据库获取每个视频的文件路径
3. 用 ffmpeg 提取每个片段并统一转码（1080x1920, h264, aac）
4. 用 concat demuxer 拼接所有片段
5. 输出最终 mp4 到 data/curation/ 目录
"""
import os
import subprocess
import tempfile
import json
from .. import db

# ffmpeg 路径：优先环境变量，其次项目 tools 目录
def get_ffmpeg_path():
    env = os.environ.get("FFMPEG_PATH")
    if env and os.path.exists(env):
        return env
    # 项目根目录/tools/ffmpeg/bin/ffmpeg.exe
    # __file__ = local-douyin/app/curation/video_renderer.py
    # 往上4层到项目根目录 douyin-topaz-pack/
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidate = os.path.join(project_root, "tools", "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.exists(candidate):
        return candidate
    # 最后尝试系统 PATH
    return "ffmpeg"


def get_video_dir():
    """视频文件目录：local-douyin/data/videos/"""
    # __file__ = local-douyin/app/curation/video_renderer.py
    # 往上3层到 local-douyin/
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "videos")


def get_video_path(video_id):
    """根据 video_id 获取视频文件路径"""
    conn = db.get_conn()
    row = conn.execute("SELECT file_name FROM videos WHERE id=?", (video_id,)).fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    return os.path.join(get_video_dir(), row[0])


def extract_clip(ffmpeg, src_path, start_sec, end_sec, output_path):
    """
    用 ffmpeg 提取片段并统一转码。
    统一输出：1080x1920, h264, aac, 30fps，确保拼接兼容。
    """
    duration = max(0.1, end_sec - start_sec)
    cmd = [
        ffmpeg, "-y",
        "-ss", str(start_sec),
        "-i", src_path,
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0, result.stderr[-500:] if result.stderr else ""


def concat_clips(ffmpeg, clip_paths, output_path):
    """用 ffmpeg concat demuxer 拼接多个片段"""
    # 写 concat 列表文件
    list_file = output_path + ".txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write("file '%s'\n" % p.replace("\\", "/"))

    cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    os.remove(list_file)
    return result.returncode == 0, result.stderr[-500:] if result.stderr else ""


def render_manifest(manifest, output_dir=None):
    """
    将 manifest 中的片段渲染成最终视频。

    返回: (success, output_path_or_error, details)
    """
    ffmpeg = get_ffmpeg_path()

    # 检查 ffmpeg 是否可用
    try:
        subprocess.run([ffmpeg, "-version"], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "ffmpeg not found at: %s" % ffmpeg, {}

    clips = manifest.get("clips", [])
    if not clips:
        return False, "no clips in manifest", {}

    if output_dir is None:
        # local-douyin/data/curation/
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "curation")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    final_output = os.path.join(output_dir, "curation_%s.mp4" % date_str)

    # 临时目录存放单个片段
    tmp_dir = tempfile.mkdtemp(prefix="curation_")
    clip_paths = []
    details = {"extracted": 0, "failed": [], "ffmpeg": ffmpeg}

    try:
        # 提取每个片段
        for i, clip in enumerate(clips):
            vid = clip["video_id"]
            src = get_video_path(vid)
            if not src or not os.path.exists(src):
                details["failed"].append({"video_id": vid, "reason": "file not found"})
                continue

            clip_out = os.path.join(tmp_dir, "clip_%03d.mp4" % i)
            ok, err = extract_clip(ffmpeg, src, clip["start_sec"], clip["end_sec"], clip_out)
            if ok and os.path.exists(clip_out):
                clip_paths.append(clip_out)
                details["extracted"] += 1
            else:
                details["failed"].append({"video_id": vid, "reason": err[:200]})

        if not clip_paths:
            return False, "no clips could be extracted", details

        # 拼接
        ok, err = concat_clips(ffmpeg, clip_paths, final_output)
        if not ok:
            return False, "concat failed: %s" % err[:300], details

        if not os.path.exists(final_output):
            return False, "output file not created", details

        details["final_size"] = os.path.getsize(final_output)
        return True, final_output, details

    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
