# -*- coding: utf-8 -*-
"""local-douyin 新交互 E2E：跟手滑动/阈值回弹/点击即点赞/音乐双态/预加载"""
import asyncio
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        await page.goto("http://127.0.0.1:8000/", timeout=15000)
        await page.wait_for_timeout(4000)
        cdp = await page.context.new_cdp_session(page)

        async def state(tag):
            info = await page.evaluate(
                """() => {
                    const s = document.querySelectorAll('.slide')[1]; // current = middle
                    const v = s && s.querySelector('video');
                    const m = s && s.querySelector('.music');
                    const like = s && s.querySelector('.act.like');
                    const nextVid = document.querySelectorAll('.slide')[2]?.querySelector('video');
                    return {
                        author: s && s.querySelector('.author')?.textContent,
                        playing: v ? !v.paused : null,
                        muted: v ? v.muted : null,
                        musicOn: m ? m.classList.contains('on') : null,
                        likeOn: like ? like.classList.contains('on') : null,
                        likeNum: like ? like.querySelector('.num').textContent : null,
                        nextHasSrc: !!(nextVid && nextVid.src),
                        topbar: !!document.getElementById('countBadge'),
                        hint: !!document.querySelector('.hint')
                    };
                }"""
            )
            print(tag, info)

        async def touch_drag(from_y, to_y, steps=10):
            """真实触摸拖拽（跟手）"""
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 195, "y": from_y}]})
            await page.wait_for_timeout(50)
            for i in range(1, steps + 1):
                y = from_y + (to_y - from_y) * i // steps
                await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 195, "y": y}]})
                await page.wait_for_timeout(20)
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            await page.wait_for_timeout(1800)

        await state("初始        ")
        # 短滑（50px < 阈值110）→ 应回弹，不切换
        await touch_drag(500, 450)
        await state("短滑(应回弹)")
        # 长滑（250px > 阈值）→ 切换到下一个
        await touch_drag(550, 300)
        await state("长滑(应下一个)")
        # 点击视频 → 点赞（不是暂停）
        await page.evaluate("""() => {
            const s = document.querySelectorAll('.slide')[1];
            s.querySelector('video').dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }""")
        await page.wait_for_timeout(500)
        await state("点视频(应点赞)")
        # 点右侧点赞按钮 → 取消
        await page.evaluate("""() => {
            const s = document.querySelectorAll('.slide')[1];
            s.querySelector('.act.like').click();
        }""")
        await page.wait_for_timeout(400)
        await state("点按钮(应取消)")
        # 音乐开关
        await page.evaluate("""() => {
            const s = document.querySelectorAll('.slide')[1];
            s.querySelector('.music').click();
        }""")
        await page.wait_for_timeout(400)
        await state("音乐关      ")
        await page.evaluate("""() => {
            const s = document.querySelectorAll('.slide')[1];
            s.querySelector('.music').click();
        }""")
        await page.wait_for_timeout(400)
        await state("音乐开      ")
        # 下滑回退
        await touch_drag(300, 550)
        await state("下滑回退    ")

        await browser.close()


asyncio.run(main())
