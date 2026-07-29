"""
Bug 复现脚本：安全箱字段显示对象字符串
=============================================
问题：订单详情页"安全箱"后面显示 GoodsAttributes(id=xxx, g... 而非正常文本
页面：https://test-m.jiangjunzh.com/pages/rent/goods/detail/index?id=2078729169096728578

使用方法：
    python reproduce_safety_box_bug.py
"""

import asyncio
from playwright.async_api import async_playwright

# 问题页面 URL
BUG_URL = "https://test-m.jiangjunzh.com/pages/rent/goods/detail/index?id=2078729169096728578"

# 截图保存路径
SCREENSHOT_FULL = "bug_safety_box_full.png"       # 整页截图
SCREENSHOT_VIEWPORT = "bug_safety_box_viewport.png"  # 可视区域截图
REPORT_FILE = "bug_report.txt"                     # 文本报告


async def main():
    async with async_playwright() as p:
        # 使用 Chromium 模拟手机访问（因为是 H5 页面）
        browser = await p.chromium.launch(headless=False)  # 有头模式方便观察
        context = await browser.new_context(
            viewport={"width": 375, "height": 812},  # iPhone 13 尺寸
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        )
        page = await context.new_page()

        print(f"[1/6] 访问页面: {BUG_URL}")
        await page.goto(BUG_URL, wait_until="networkidle")
        await page.wait_for_timeout(3000)  # 等待渲染

        print("[2/6] 截图：整页")
        await page.screenshot(path=SCREENSHOT_FULL, full_page=True)

        print("[3/6] 查找'安全箱'文本位置")
        # 查找包含"安全箱"的元素
        safety_box = page.locator("text=安全箱").first
        await safety_box.wait_for(state="visible", timeout=10000)

        # 滚动到安全箱位置
        await safety_box.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)

        print("[4/6] 截图：安全箱可视区域")
        await page.screenshot(path=SCREENSHOT_VIEWPORT)

        print("[5/6] 提取安全箱周围文本内容")
        # 获取安全箱元素及其后续文本
        safety_box_text = await page.evaluate("""
            () => {
                const allElements = document.querySelectorAll('*');
                const results = [];
                for (const el of allElements) {
                    const text = el.textContent || '';
                    if (text.includes('安全箱') && text.length < 500) {
                        results.push({
                            tag: el.tagName,
                            className: el.className,
                            text: text.trim(),
                            innerHTML: el.innerHTML.substring(0, 300)
                        });
                    }
                }
                return results;
            }
        """)

        print("[6/6] 生成 Bug 报告")
        report_lines = [
            "=" * 60,
            "Bug 复现报告",
            "=" * 60,
            f"页面 URL: {BUG_URL}",
            f"复现时间: {await page.evaluate('new Date().toLocaleString()')}",
            "",
            "【问题描述】",
            "订单详情页'安全箱'字段后面显示对象字符串，而非正常文本",
            "",
            "【预期结果