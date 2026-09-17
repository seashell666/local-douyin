# -*- coding: utf-8 -*-
"""
抖音点赞采集器
使用 Playwright + Cookie 登录抖音网页版，抓取用户点赞视频列表。

用法：
  python main.py --mode real    # 真实模式（需要Cookie）
  python main.py --mode mock    # Mock模式（测试用）
  python main.py --mode real --limit 50  # 限制数量
"""
import os
import sys
import json
import time
import argparse
from datetime import datetime

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "douyin_cookies.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def load_cookies():
    """从文件加载Cookie，转换为Playwright格式"""
    if not os.path.exists(COOKIE_FILE):
        print("Cookie文件不存在: %s" % COOKIE_FILE)
        return []
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookie_str = f.read().strip()
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, value = pair.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".douyin.com",
                "path": "/",
            })
    return cookies


def fetch_likes_real(limit=50, headless=True):
    """真实模式：用Playwright抓取点赞列表"""
    from playwright.sync_api import sync_playwright

    cookies = load_cookies()
    if not cookies:
        print("无法加载Cookie，退出")
        return []

    print("启动浏览器...")
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies(cookies)
        page = context.new_page()

        print("访问抖音首页验证登录...")
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # 检查是否登录成功
        page_text = page.content()
        if "登录" in page_text and "登录后更精彩" in page_text:
            print("警告：可能未登录成功，页面显示登录提示")
        else:
            print("登录状态验证通过")

        # 跳转到个人主页的喜欢列表
        print("访问个人主页喜欢列表...")
        page.goto("https://www.douyin.com/user/self?showTab=like", wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        # 滚动加载更多
        print("滚动加载点赞视频...")
        last_count = 0
        scroll_attempts = 0
        max_attempts = 20

        while scroll_attempts < max_attempts and len(results) < limit:
            # 提取当前页面的视频卡片
            video_cards = page.query_selector_all("li[data-e2e='user-likes-list-item']")
            if not video_cards:
                video_cards = page.query_selector_all("div[class*='video-card']")
            if not video_cards:
                video_cards = page.query_selector_all("a[href*='/video/']")

            print("  当前找到 %d 个视频卡片" % len(video_cards))

            for card in video_cards:
                try:
                    href = card.get_attribute("href") or ""
                    if "/video/" in href:
                        video_id = href.split("/video/")[-1].split("?")[0]
                        if video_id and not any(r["video_id"] == video_id for r in results):
                            title = ""
                            author = ""
                            try:
                                title_el = card.query_selector("p[class*='title'], div[class*='desc']")
                                if title_el:
                                    title = title_el.inner_text()[:100]
                            except:
                                pass
                            results.append({
                                "video_id": video_id,
                                "url": "https://www.douyin.com" + href if href.startswith("/") else href,
                                "title": title,
                                "author": author,
                                "collected_at": int(time.time()),
                            })
                except Exception as e:
                    pass

            if len(results) >= limit:
                break

            # 滚动
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)
            scroll_attempts += 1

            if len(results) == last_count and scroll_attempts > 5:
                print("  没有新内容加载，停止滚动")
                break
            last_count = len(results)

        browser.close()

    print("共采集 %d 个点赞视频" % len(results))
    return results[:limit]


def fetch_likes_mock(limit=20):
    """Mock模式：生成测试数据"""
    print("Mock模式：生成 %d 条测试数据" % limit)
    mock_authors = ["测试作者A", "测试作者B", "测试作者C", "测试作者D", "测试作者E"]
    results = []
    for i in range(limit):
        results.append({
            "video_id": "mock_%d_%d" % (int(time.time()), i),
            "url": "https://www.douyin.com/video/mock_%d" % i,
            "title": "Mock测试视频 #%d" % (i + 1),
            "author": mock_authors[i % len(mock_authors)],
            "collected_at": int(time.time()),
        })
    return results


def save_results(results, mode="real"):
    """保存采集结果"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = "likes_%s_%s.json" % (mode, date_str)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "mode": mode,
            "count": len(results),
            "collected_at": int(time.time()),
            "videos": results,
        }, f, ensure_ascii=False, indent=2)
    print("结果已保存: %s" % filepath)
    return filepath


def main():
    parser = argparse.ArgumentParser(description="抖音点赞采集器")
    parser.add_argument("--mode", choices=["real", "mock"], default="real", help="采集模式")
    parser.add_argument("--limit", type=int, default=50, help="采集数量上限")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口（调试用）")
    args = parser.parse_args()

    if args.mode == "real":
        results = fetch_likes_real(limit=args.limit, headless=not args.no_headless)
    else:
        results = fetch_likes_mock(limit=args.limit)

    if results:
        save_results(results, mode=args.mode)
    else:
        print("未采集到任何数据")


if __name__ == "__main__":
    main()
