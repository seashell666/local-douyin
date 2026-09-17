#!/usr/bin/env python3
"""
抖音视频下载极简版 v3 - 彻底省积分
每个视频独立文件夹：视频.mp4 + info.md
批量链接支持，一次性上传项目空间
v3: 移除a_bogus签名API(最大省积分点) + 修复上传文件夹结构
"""

import os
import re
import sys
import json
import time
import argparse

import requests  # 本地化改造：扣子运行时专属模块 coze_workload_identity → 标准 requests
import urllib3

# 关闭 verify=False 产生的 InsecureRequestWarning 噪音（不影响功能）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "com.ss.android.ugc.aweme/110101 "
    "(Linux; U; Android 12; zh_CN; Pixel 4; "
    "Build/SQ3A.220705.003.A1; Cronet/TTNetVersion:b4d74d15 2020-04-23 QuicVersion:0144d358 2020-03-24)"
)

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "douyin_cookies.txt")

# 圆圈数字序号，按链接顺序标注文件夹
CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

def _circled(n):
    """返回圆圈数字，如 ①②③"""
    if 0 < n <= len(CIRCLED_NUMS):
        return CIRCLED_NUMS[n - 1]
    return f"[{n}]"


def save_cookie(cookie_str):
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        f.write(cookie_str.strip())


def load_cookie():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie = f.read().strip()
        if cookie:
            return cookie
    return None


def extract_urls(text):
    pattern = r'https?://[^\s<>"\')\]，。！？、；：\u3000]+'
    urls = re.findall(pattern, text)
    seen = set()
    result = []
    for url in urls:
        url = url.rstrip('.,;!?')
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def extract_video_id(url):
    """从直达链接提取视频ID"""
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/note/(\d+)', url)
    if m:
        return m.group(1)
    # 短链接跟随重定向
    try:
        resp = requests.head(url, allow_redirects=True, timeout=6, headers={"User-Agent": DESKTOP_UA})
        final_url = str(resp.url)
        m = re.search(r'/video/(\d+)', final_url)
        if m:
            return m.group(1)
        m = re.search(r'/note/(\d+)', final_url)
        if m:
            return m.group(1)
        m = re.search(r'(\d{15,})', final_url)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


# ===== 视频信息获取 - 优先带cookie的web API，免费接口兜底 =====

def fetch_video_info(video_id, cookie_str=None):
    """获取视频信息 - web API最可靠（带cookie），被风控间歇拦截时自动重试；免费接口兜底"""
    # 方式1: Web API（带cookie，最可靠）→ 失败重试3次，抖音风控是"按请求概率抽检"，多试几次能显著提高成功率
    if cookie_str:
        for attempt in range(4):
            result = _try_web_api(video_id, cookie_str)
            if result:
                return result
            if attempt < 3:
                time.sleep(2 * (attempt + 1))  # 退避等待：2s、4s、6s
    # 方式2: iesdouyin（完全免费）
    result = _try_iesdouyin(video_id, cookie_str)
    if result:
        return result
    # 方式3: 移动端API（模拟APP，免费无需签名）
    return _try_mobile_api(video_id, cookie_str)


def _try_iesdouyin(video_id, cookie_str=None):
    """iesdouyin API - 免费无需签名"""
    url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"
    headers = {"User-Agent": DESKTOP_UA}
    if cookie_str:
        headers["Cookie"] = cookie_str
    try:
        resp = requests.get(url, headers=headers, timeout=8, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("item_list", [])
            if items:
                return items[0]
    except Exception:
        pass
    return None


def _try_mobile_api(video_id, cookie_str=None):
    """移动端API - 模拟抖音APP请求，无需a_bogus签名"""
    url = f"https://www.iesdouyin.com/share/video/{video_id}"
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "application/json",
        "Referer": "https://www.douyin.com/",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str
    try:
        resp = requests.get(url, headers=headers, timeout=8, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status_code") == 0:
                items = data.get("item_list", [])
                if items:
                    return items[0]
                aweme = data.get("aweme_detail", {})
                if aweme:
                    return aweme
    except Exception:
        pass
    return None


def _try_web_api(video_id, cookie_str=None):
    """Web API - 仅带cookie，不额外调用签名API"""
    if not cookie_str:
        return None
    url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
    params = {"aid": "6383", "aweme_id": video_id}
    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json",
        "Cookie": cookie_str,
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8, verify=False)
        if resp.status_code == 200:
            body = resp.text
            if body and len(body) > 50:
                data = json.loads(body)
                if data.get("status_code") == 0:
                    detail = data.get("aweme_detail", {})
                    if detail:
                        return detail
    except Exception:
        pass
    return None


# ===== 信息提取 =====

def extract_video_meta(video_info):
    desc = video_info.get("desc", "")
    author = ""
    author_info = video_info.get("author", {}) or {}
    if author_info:
        author = author_info.get("nickname", "") or ""

    tags = []
    text_extra = video_info.get("text_extra", [])
    if text_extra and isinstance(text_extra, list):
        for item in text_extra:
            if isinstance(item, dict):
                tag_name = item.get("hashtag_name", "")
                if tag_name and tag_name not in tags and len(tag_name) > 1:
                    tags.append(tag_name)

    if desc:
        hashtags = re.findall(r'#([^\s#@]+)', desc)
        for t in hashtags:
            t = t.strip()
            if t and t not in tags and len(t) > 1:
                tags.append(t)

    return desc.strip(), author.strip(), tags


def extract_video_url(video_info):
    video = video_info.get("video", {}) or {}
    play_addr = video.get("play_addr", {}) or {}
    url_list = play_addr.get("url_list", [])
    if url_list:
        return url_list[0].replace("playwm", "play")
    download_addr = video.get("download_addr", {}) or {}
    url_list = download_addr.get("url_list", [])
    if url_list:
        return url_list[0]
    return None


def extract_cover_url(video_info):
    """提取封面图URL - 从已有API返回数据中获取，不额外调API"""
    video = video_info.get("video", {}) or {}
    # 优先用 origin_cover（原始封面），其次 cover
    for key in ("origin_cover", "cover", "dynamic_cover"):
        cover = video.get(key, {}) or {}
        url_list = cover.get("url_list", [])
        if url_list:
            return url_list[0]
    return None


def sanitize_filename(name, max_length=80):
    if not name:
        return ""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip().strip('.')
    if len(name) > max_length:
        name = name[:max_length].rstrip()
    return name or "untitled"


def sanitize_video_name(name, max_length=100):
    """轻量清理 - 只去掉Windows禁用的字符，保留#和空格"""
    if not name:
        return ""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '', name)
    name = name.strip().strip('.')
    if len(name) > max_length:
        name = name[:max_length].rstrip()
    return name or "untitled"


def download_file(url, save_path):
    headers = {"User-Agent": DESKTOP_UA, "Referer": "https://www.douyin.com/"}
    try:
        resp = requests.get(url, headers=headers, timeout=60, stream=True, verify=False)
        if resp.status_code in (200, 206):
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            size = os.path.getsize(save_path)
            if size > 1000:
                return True
            else:
                os.remove(save_path)
    except Exception:
        pass
    return False


def process_single(url, base_output_dir, cookie_str=None, index=0):
    """处理单个视频，创建独立文件夹，index为链接顺序序号"""
    result = {
        "success": False,
        "url": url,
        "video_id": "",
        "title": "",
        "author": "",
        "tags": [],
        "video_path": None,
        "cover_path": None,
        "folder_name": "",
        "error": None,
        "raw_info": None,
    }

    video_id = extract_video_id(url)
    if not video_id:
        result["error"] = f"无法提取视频ID: {url}"
        return result
    result["video_id"] = video_id

    video_info = fetch_video_info(video_id, cookie_str)
    if not video_info:
        result["error"] = "无法获取视频信息"
        return result
    result["raw_info"] = video_info

    title, author, tags = extract_video_meta(video_info)
    if not title:
        title = f"video_{video_id}"
    if not author:
        author = "unknown"
    result["title"] = title
    result["author"] = author
    result["tags"] = tags

    safe_title = sanitize_filename(title)
    safe_author = sanitize_filename(author, max_length=30)
    base_name = f"{safe_author}_{safe_title}" if safe_author else safe_title
    # 按链接顺序加圆圈数字前缀（如 ①②③）
    prefix = _circled(index) if index > 0 else ""
    folder_name = f"{prefix}{base_name}" if prefix else base_name
    if len(folder_name) > 100:
        folder_name = folder_name[:100]
    result["folder_name"] = folder_name

    # 创建独立文件夹
    folder_path = os.path.join(base_output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    video_url = extract_video_url(video_info)
    if not video_url:
        result["error"] = "无法获取视频下载地址"
        return result

    # 构建视频文件名：序号 + 标题 + 标签（原info.md内容）
    video_parts = []
    if title:
        video_parts.append(title)
    if tags:
        video_parts.append(" ".join([f"#{t}" for t in tags]))
    video_content = " ".join(video_parts) if video_parts else f"video_{video_id}"
    safe_video_name = sanitize_video_name(video_content, max_length=80)
    video_file_base = f"{prefix}{safe_video_name}" if prefix else safe_video_name

    # 下载视频到独立文件夹
    video_path = os.path.join(folder_path, f"{video_file_base}.mp4")
    if download_file(video_url, video_path):
        result["video_path"] = video_path
        result["success"] = True
    else:
        result["error"] = "视频下载失败"
        return result

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抖音视频下载极简版")
    parser.add_argument("text", nargs="?", default="", help="抖音链接（多条时每行一条）")
    parser.add_argument("--output", "-o", default="./douyin_download", help="下载目录")
    parser.add_argument("--cookie", "-c", default=None, help="cookie字符串")
    parser.add_argument("--set-cookie", default=None, help="保存cookie")
    args = parser.parse_args()

    if args.set_cookie:
        save_cookie(args.set_cookie)
        if not args.text:
            sys.exit(0)

    if not args.text:
        parser.error("请提供抖音链接")

    urls = extract_urls(args.text)
    if not urls:
        print("ERROR: 未找到有效链接")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    cookie_str = args.cookie or load_cookie()

    results = []
    for i, url in enumerate(urls, 1):
        r = process_single(url, args.output, cookie_str, index=i)
        results.append(r)
        if r["success"]:
            print(f"[OK] {i}/{len(urls)}: {r['title'][:30]}")
        else:
            print(f"[FAIL] {i}/{len(urls)}: {r['error']}")
        if i < len(urls):
            time.sleep(0.5)

    print("确认已完成")
