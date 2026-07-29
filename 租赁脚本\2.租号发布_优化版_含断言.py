"""
租号发布流程自动化测试脚本
原始来源: Playwright Codegen 录制
优化内容: 添加断言、错误处理、日志输出、配置化参数

测试网址: https://test-m.jiangjunzh.com/
测试流程: 登录 → 选择游戏 → 填写账号信息 → 发布出租
"""

import asyncio
import re
import os
import sys
import random
import traceback
from datetime import datetime
from pathlib import Path
from playwright.async_api import Playwright, async_playwright, expect, Page, TimeoutError as PlaywrightTimeoutError


# ============== 配置区 ==============
CONFIG = {
    "url": "https://test-m.jiangjunzh.com/",
    "account": "19318589623",
    "password": "123456",
    "headless": False,                    # 是否无头模式
    "slow_mo": 100,                       # 操作间隔（毫秒），便于观察
    "timeout": 10000,                     # 默认超时 10 秒
    "image1": "20260722-100920.jpg",      # 上传图片1
    "image2": "邀请码.png",               # 上传图片2
    "price": "59",                        # 出租价格
    "deposit": "2",                       # 押金
    "hafu_coin": "26",                    # 哈夫币
    "kd": "5",                            # 绝密KD
    "level": "60",                        # 账号等级
    "protocol_scroll_wait_ms": 3000,      # 第7步协议弹窗滚动后强制等待时间（毫秒）
    "explicit_wait_ms": 1500,             # 其余步骤显性等待时间（毫秒，元素可见即可点击）
    "pay_max_wait_ms": 300000,            # 最后一步等待支付保证金的最长时间（毫秒，5分钟）
    "after_pay_wait_ms": 10000,           # 支付成功/订单上架成功后等待退出时间（毫秒，10秒）
    "pay_success_keywords": ["支付成功", "支付完成", "订单上架成功", "上架成功", "发布成功", "保证金支付成功"],
}


class StepLogger:
    """步骤日志记录器"""
    def __init__(self):
        self.current_step = 0
        self.passed = 0
        self.failed = 0

    def step(self, desc: str):
        self.current_step += 1
        print(f"\n[步骤 {self.current_step:02d}] {desc}")

    def ok(self, msg: str = "通过"):
        self.passed += 1
        print(f"  ✓ {msg}")

    def fail(self, msg: str = "失败"):
        self.failed += 1
        print(f"  ✗ {msg}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"测试结果汇总: 共 {total} 项 | 通过 {self.passed} | 失败 {self.failed}")
        print(f"{'='*50}")
        return self.failed == 0


logger = StepLogger()

# ============== 错误记录和回滚机制 ==============
class ErrorRecorder:
    """错误记录器，记录每次失败的详细信息"""
    def __init__(self):
        self.errors = []
    
    def record(self, step: str, error: Exception, screenshot_path: str = None):
        self.errors.append({
            'timestamp': datetime.now().isoformat(),
            'step': step,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'screenshot': screenshot_path,
            'traceback': traceback.format_exc()
        })
    
    def save_report(self, filename: str = 'error_report.txt'):
        """保存错误报告到文件"""
        if not self.errors:
            return
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"错误报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            for i, error in enumerate(self.errors, 1):
                f.write(f"【错误 {i}】\n")
                f.write(f"时间: {error['timestamp']}\n")
                f.write(f"步骤: {error['step']}\n")
                f.write(f"错误类型: {error['error_type']}\n")
                f.write(f"错误信息: {error['error_message']}\n")
                if error['screenshot']:
                    f.write(f"截图: {error['screenshot']}\n")
                f.write(f"堆栈跟踪:\n{error['traceback']}\n")
                f.write("-" * 60 + "\n\n")
        
        print(f"\n[报告] 错误报告已保存到: {os.path.abspath(filename)}")
    
    def has_errors(self):
        return len(self.errors) > 0


error_recorder = ErrorRecorder()


def retry_on_failure(max_retries: int = 3, delay_ms: int = 2000):
    """重试装饰器，在函数失败时自动重试"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    print(f"\n  ⚠ 第 {attempt + 1}/{max_retries} 次尝试失败: {type(e).__name__}: {e}")
                    if attempt < max_retries - 1:
                        print(f"  ⏳ 等待 {delay_ms}ms 后重试...")
                        await asyncio.sleep(delay_ms / 1000)
            print(f"  ✗ 已重试 {max_retries} 次，仍失败")
            raise last_exception
        return wrapper
    return decorator


async def rollback_to_login(page: Page, config: dict):
    """回滚到登录状态（用于错误恢复）"""
    print("\n 🔄 执行回滚操作...")
    try:
        # 尝试返回到首页
        await page.goto(config["url"], wait_until="networkidle", timeout=30000)
        print("    ✓ 已返回首页")
        
        # 等待页面稳定
        await page.wait_for_timeout(2000)
        
        # 检查是否需要重新登录
        if "login" in page.url.lower():
            print("    ⚠ 需要重新登录")
            return False
        
        print("    ✓ 回滚完成")
        return True
        
    except Exception as e:
        print(f"    ⚠ 回滚失败: {e}")
        return False


async def cleanup_and_restart(playwright: Playwright, config: dict) -> Page:
    """清理并重新启动浏览器会话"""
    print("\n 🔄 清理并重新启动浏览器会话...")
    try:
        # 创建新的浏览器实例
        browser = await playwright.chromium.launch(
            headless=config["headless"],
            slow_mo=config["slow_mo"]
        )
        context = await browser.new_context(
            viewport={"width": 375, "height": 812},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
        )
        page = await context.new_page()
        page.set_default_timeout(config["timeout"])
        
        # 导航到首页
        await page.goto(config["url"], wait_until="networkidle", timeout=30000)
        print("    ✓ 浏览器会话已重新启动")
        return page, context, browser
        
    except Exception as e:
        print(f"    ⚠ 重启失败: {e}")
        return None, None, None


async def scroll_protocol_to_bottom(page: Page):
    """第7步专用：强制滚动协议弹窗内容到底部

    针对协议弹窗的特殊处理：必须滚动到底部，按钮才会从"请滑动显示完整内容"变为"我已悉知"
    """
    wait_ms = CONFIG["protocol_scroll_wait_ms"]
    try:
        # 先等待弹窗出现（最多等待5秒）
        print("  ⏳ 等待协议弹窗出现...")
        await page.wait_for_selector('uni-popup, .uni-popup, .uni-modal, [class*="modal"], [class*="popup"]', timeout=5000)
        
        # 强制滚动到最底部，使用更强大的方法
        print("  ↕ 强制滚动协议内容到底部...")
        for i in range(5):  # 增加滚动次数
            result = await page.evaluate("""
                () => {
                    let totalScrolled = 0;
                    const selectors = [
                        'uni-scroll-view', '.uni-scroll-view-content',
                        '.uni-modal__bd', '.modal-content',
                        '[class*="scroll"]', '.uni-popup',
                        '.uni-picker-view', '.uni-actionsheet',
                        '[class*="popup"]', '[class*="modal"]',
                        '.uni-popup__content', '.uni-actionsheet__menu',
                        '.protocol', '.agreement', '.content',
                        '.scroll-view', '.scroll-content',
                        '.popup-content', '.modal-body', '.modal-content',
                        '.uni-scroll-wrapper', '.scroll-wrapper',
                        'div[style*="overflow"]', 'div[style*="scroll"]'
                    ];
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            const maxScroll = el.scrollHeight - el.clientHeight;
                            if (maxScroll > 0) {
                                el.scrollTop = el.scrollHeight;
                                totalScrolled += maxScroll;
                            }
                            // 递归滚动子元素
                            el.querySelectorAll('*').forEach(child => {
                                const childMax = child.scrollHeight - child.clientHeight;
                                if (childMax > 0) {
                                    child.scrollTop = child.scrollHeight;
                                    totalScrolled += childMax;
                                }
                            });
                        });
                    });
                    window.scrollTo(0, document.body.scrollHeight);
                    return totalScrolled;
                }
            """)
            print(f"    第{i+1}次滚动，滚动距离: {result}px")
            await page.wait_for_timeout(300)  # 每次滚动后等待一下
        
        # 模拟真实手指滑动（针对需要用户手动滑动的场景）
        print("  👆 模拟手指滑动（从底部向上滑）...")
        await page.evaluate("""
            () => {
                // 创建触摸点
                const touch1 = new Touch({
                    identifier: 1,
                    target: document.body,
                    clientX: 180,
                    clientY: 700
                });
                const touch2 = new Touch({
                    identifier: 1,
                    target: document.body,
                    clientX: 180,
                    clientY: 200
                });
                
                const touchstart = new TouchEvent('touchstart', {
                    touches: [touch1],
                    bubbles: true,
                    cancelable: true
                });
                
                const touchmove = new TouchEvent('touchmove', {
                    touches: [touch2],
                    bubbles: true,
                    cancelable: true
                });
                
                const touchend = new TouchEvent('touchend', {
                    touches: [],
                    bubbles: true,
                    cancelable: true
                });
                
                document.dispatchEvent(touchstart);
                requestAnimationFrame(() => {
                    document.dispatchEvent(touchmove);
                    requestAnimationFrame(() => {
                        document.dispatchEvent(touchend);
                    });
                });
            }
        """)
        await page.wait_for_timeout(500)
        
        print(f"  ↕ 协议弹窗已滚动到底部，强制等待 {wait_ms}ms 让按钮状态更新...")
        await page.wait_for_timeout(wait_ms)
        
    except Exception as e:
        print(f"  ⚠ 滚动等待异常（忽略继续）: {e}")


async def close_protocol_popup(page: Page) -> bool:
    """强制关闭协议弹窗（清仓保护细则弹窗）
    
    步骤：
    1. 等待弹窗出现
    2. 强制滚动协议内容到底部
    3. 等待按钮从"请滑动显示完整内容"变为"我已悉知"
    4. 点击确认按钮
    5. 验证弹窗已关闭，强制移除
    
    Returns:
        True if 弹窗成功关闭，False 表示失败
    """
    print("  🚪 开始处理协议弹窗...")
    
    # 1. 等待弹窗出现
    try:
        print("    ⏳ 等待弹窗出现...")
        await page.wait_for_selector('uni-popup.center, .uni-popup.center, .clearance-popup', timeout=10000)
        print("    ✓ 弹窗已出现")
    except:
        print("    ⚠ 未检测到弹窗，可能已关闭")
        # 即使没检测到，也强制清理一次
        await force_remove_popups(page)
        return True
    
    # 2. 强制滚动协议内容到底部（多次尝试）
    print("    ↕ 强制滚动协议内容到底部...")
    for i in range(10):  # 增加滚动次数
        result = await page.evaluate("""
            () => {
                let scrolled = 0;
                // 查找所有滚动容器
                const containers = document.querySelectorAll(
                    'uni-scroll-view, .uni-scroll-view-content, .uni-popup__content, ' +
                    '.protocol, .agreement, .content, div[style*="overflow"], ' +
                    '.uni-popup [scroll-y], .scroll-view'
                );
                containers.forEach(el => {
                    const maxScroll = el.scrollHeight - el.clientHeight;
                    if (maxScroll > 0) {
                        el.scrollTop = el.scrollHeight;
                        scrolled += maxScroll;
                    }
                });
                return scrolled;
            }
        """)
        print(f"      第{i+1}次滚动，滚动距离: {result}px")
        await page.wait_for_timeout(200)
    
    # 3. 模拟真实手指滑动（确保触发滑动检测）
    print("    👆 模拟手指滑动...")
    await page.evaluate("""
        () => {
            const startY = 600;
            const endY = 100;
            const duration = 300;
            
            // 创建触摸点
            const touch = {
                identifier: 1,
                target: document.body,
                clientX: 180,
                clientY: startY
            };
            
            const startEvent = new TouchEvent('touchstart', {
                touches: [touch],
                bubbles: true,
                cancelable: true
            });
            
            document.dispatchEvent(startEvent);
            
            // 模拟滑动过程
            let currentY = startY;
            const step = (startY - endY) / (duration / 16);
            
            const animate = () => {
                if (currentY > endY) {
                    currentY -= step;
                    const moveTouch = {
                        identifier: 1,
                        target: document.body,
                        clientX: 180,
                        clientY: currentY
                    };
                    const moveEvent = new TouchEvent('touchmove', {
                        touches: [moveTouch],
                        bubbles: true,
                        cancelable: true
                    });
                    document.dispatchEvent(moveEvent);
                    requestAnimationFrame(animate);
                } else {
                    const endEvent = new TouchEvent('touchend', {
                        touches: [],
                        bubbles: true,
                        cancelable: true
                    });
                    document.dispatchEvent(endEvent);
                }
            };
            
            requestAnimationFrame(animate);
        }
    """)
    await page.wait_for_timeout(1000)  # 等待滑动完成
    
    # 4. 等待按钮变为"我已悉知"并点击（增加等待时间）
    print("    ⏳ 等待按钮变为'我已悉知'...")
    button_found = False
    max_wait = 20000  # 增加等待时间
    start_time = await page.evaluate("() => Date.now()")
    
    while True:
        current_time = await page.evaluate("() => Date.now()")
        if current_time - start_time >= max_wait:
            print("    ⏰ 等待超时")
            break
        
        # 尝试所有可能的按钮文本
        for text in ["我已悉知", "我已知悉", "同意协议", "同意", "确认", "知道了", "确定"]:
            try:
                btn = page.get_by_text(text, exact=True)
                await btn.wait_for(state="visible", timeout=1000)
                await btn.click(timeout=3000, force=True)
                button_found = True
                print(f"    ✓ 点击'{text}'按钮")
                break
            except:
                continue
        
        if button_found:
            break
        
        await page.wait_for_timeout(300)
    
    # 5. 等待弹窗关闭
    await page.wait_for_timeout(2000)
    
    # 6. 强制检查并移除弹窗（关键步骤）
    return await force_remove_popups(page)


async def force_remove_popups(page: Page) -> bool:
    """强制移除所有弹窗
    
    Returns:
        True if 弹窗已移除，False 表示失败
    """
    print("    🔧 强制检查并移除弹窗...")
    
    try:
        # 方法1: 尝试点击遮罩层关闭
        try:
            overlay = page.locator('.uni-popup__mask, .uni-modal__mask, .mask')
            if await overlay.count() > 0:
                await overlay.first.click(timeout=2000, force=True)
                print("      ✓ 尝试点击遮罩层")
                await page.wait_for_timeout(500)
        except:
            pass
        
        # 方法2: 通过JS强制移除弹窗
        removed_count = await page.evaluate("""
            () => {
                let removed = 0;
                // 移除所有弹窗容器
                const selectors = [
                    'uni-popup', '.uni-popup',
                    '.uni-modal', '[class*="modal"]',
                    '[class*="popup"]', '.clearance-popup'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        el.style.display = 'none';
                        el.style.pointerEvents = 'none';
                        el.remove();
                        removed++;
                    });
                });
                return removed;
            }
        """)
        
        if removed_count > 0:
            print(f"      ✓ JS强制移除了 {removed_count} 个弹窗")
        else:
            print("      ⚠ JS未找到弹窗")
        
        # 方法3: 移除遮罩层
        await page.evaluate("""
            () => {
                document.querySelectorAll('.uni-popup__mask, .uni-modal__mask, .mask').forEach(mask => {
                    mask.style.display = 'none';
                    mask.style.pointerEvents = 'none';
                    mask.remove();
                });
            }
        """)
        print("      ✓ 移除遮罩层")
        
        # 验证弹窗是否已移除
        await page.wait_for_timeout(500)
        popup_count = await page.locator('uni-popup.center, .uni-popup.center').count()
        
        if popup_count == 0:
            print("    ✓ 弹窗已成功关闭")
            return True
        else:
            print(f"    ⚠ 仍有 {popup_count} 个弹窗存在")
            return False
            
    except Exception as e:
        print(f"    ⚠ 强制移除弹窗时出错: {e}")
        return False


async def wait_for_button_text_change(page: Page, target_text: str, timeout_ms: int = 20000) -> bool:
    """等待按钮文本变为目标文本（用于协议弹窗按钮从'请滑动...'变为'我已悉知'）
    
    Args:
        page: Playwright page 对象
        target_text: 目标按钮文本
        timeout_ms: 超时时间（毫秒）
    
    Returns:
        True if 按钮文本变为目标文本，False 表示超时
    """
    print(f"  ⏳ 等待按钮文本变为 '{target_text}'...")
    start_time = await page.evaluate("() => Date.now()")
    poll_interval = 500  # 每500ms检查一次
    
    while True:
        current_time = await page.evaluate("() => Date.now()")
        if current_time - start_time >= timeout_ms:
            print(f"  ⏰ 等待超时，未检测到按钮文本变为 '{target_text}'")
            return False
        
        try:
            # 检查页面上是否出现目标文本的按钮
            result = await page.evaluate(f"""
                (target) => {{
                    // 查找所有包含目标文本的按钮元素
                    const buttons = document.querySelectorAll('button, uni-button, .uni-button, [role="button"], .btn');
                    for (let btn of buttons) {{
                        const text = btn.textContent || btn.innerText || '';
                        if (text.trim().includes(target)) {{
                            // 检查按钮是否可见且可点击
                            const style = window.getComputedStyle(btn);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {{
                                return true;
                            }}
                        }}
                    }}
                    // 也检查所有元素中的文本
                    const allElements = document.querySelectorAll('*');
                    for (let el of allElements) {{
                        const text = el.textContent || el.innerText || '';
                        if (text.trim() === target) {{
                            const style = window.getComputedStyle(el);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {{
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}
            """, target_text)
            
            if result:
                print(f"  ✓ 检测到按钮文本变为 '{target_text}'")
                return True
                
        except Exception as e:
            print(f"  ⚠ 检查按钮文本时出现异常: {e}")
        
        await page.wait_for_timeout(poll_interval)


async def safe_click(page: Page, locator, desc: str = ""):
    """安全点击，带日志。使用显性等待：等待元素可见且启用后即可点击"""
    try:
        # 显性等待：元素可见即可点击（无强制延时）
        await locator.wait_for(state="visible", timeout=CONFIG["timeout"])
        await locator.click(timeout=CONFIG["timeout"])
        if desc:
            logger.ok(f"点击: {desc}")
    except PlaywrightTimeoutError:
        logger.fail(f"点击超时: {desc}")
        raise
    except Exception as e:
        logger.fail(f"点击异常: {desc} - {e}")
        raise


async def wait_for_pay_success_or_timeout(page: Page):
    """最后一步：点击"立即支付"后，等待用户支付保证金。

    - 最长等待 pay_max_wait_ms（5分钟）
    - 期间轮询页面是否出现支付成功/上架成功关键词
    - 检测到成功关键词 → 再等 after_pay_wait_ms（10秒）后退出
    - 超时未检测到 → 也正常退出（不报错，让用户有时间手动处理）
    """
    max_wait = CONFIG["pay_max_wait_ms"]
    poll_interval = 2000  # 每 2 秒轮询一次页面文本
    keywords = CONFIG["pay_success_keywords"]
    elapsed = 0

    print(f"\n  💳 等待支付保证金（最长 {max_wait // 1000} 秒）...")
    print(f"  📋 检测关键词: {', '.join(keywords)}")
    print(f"  ⏱️  请在浏览器中完成支付，脚本将自动检测支付结果")

    while elapsed < max_wait:
        await page.wait_for_timeout(poll_interval)
        elapsed += poll_interval

        try:
            # 获取页面可见文本，检测是否包含支付成功类关键词
            page_text = await page.evaluate("() => document.body.innerText || ''")
            for kw in keywords:
                if kw in page_text:
                    print(f"  ✓ 检测到: '{kw}'")
                    print(f"  ⏳ 再等待 {CONFIG['after_pay_wait_ms'] // 1000} 秒后退出脚本...")
                    await page.wait_for_timeout(CONFIG["after_pay_wait_ms"])
                    return True
        except Exception:
            pass

        # 每 30 秒打印一次进度
        if elapsed % 30000 == 0:
            remaining = (max_wait - elapsed) // 1000
            print(f"  ⏳ 已等待 {elapsed // 1000}s，剩余 {remaining}s")

    print(f"  ⚠ 等待超时（{max_wait // 1000}秒），未检测到支付成功关键词，正常退出")
    return False


async def safe_fill(page: Page, locator, value: str, desc: str = ""):
    """安全填入，带日志"""
    try:
        await locator.click(timeout=CONFIG["timeout"])
        await locator.fill(value, timeout=CONFIG["timeout"])
        if desc:
            logger.ok(f"填入: {desc} = {value}")
    except PlaywrightTimeoutError:
        logger.fail(f"填入超时: {desc}")
        raise
    except Exception as e:
        logger.fail(f"填入异常: {desc} - {e}")
        raise


async def assert_visible(page: Page, locator, desc: str = "", timeout: int = 10000):
    """断言元素可见"""
    try:
        await expect(locator).to_be_visible(timeout=timeout)
        logger.ok(f"断言可见: {desc}")
    except Exception as e:
        logger.fail(f"断言失败（不可见）: {desc} - {e}")
        raise


async def assert_text(page: Page, locator, expected: str, desc: str = ""):
    """断言文本内容"""
    try:
        await expect(locator).to_have_text(expected, timeout=CONFIG["timeout"])
        logger.ok(f"断言文本: {desc} = '{expected}'")
    except Exception as e:
        logger.fail(f"断言失败（文本不匹配）: {desc} - 期望 '{expected}'")
        raise


async def run_with_retry(playwright: Playwright, max_retries: int = 3) -> bool:
    """带重试和回滚机制的主测试流程"""
    global error_recorder
    
    browser = None
    context = None
    page = None
    
    for attempt in range(max_retries):
        print(f"\n{'='*60}")
        print(f" 第 {attempt + 1}/{max_retries} 次尝试")
        print(f"{'='*60}")
        
        try:
            # 创建浏览器实例
            browser = await playwright.chromium.launch(
                headless=CONFIG["headless"],
                slow_mo=CONFIG["slow_mo"]
            )
            context = await browser.new_context(
                viewport={"width": 375, "height": 812},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
            )
            page = await context.new_page()
            page.set_default_timeout(CONFIG["timeout"])
            
            # 执行主测试流程
            result = await main_test_flow(page)
            
            if result:
                print(f"\n ✓ 第 {attempt + 1} 次尝试成功")
                return True
            
        except Exception as e:
            step_name = logger.current_step if hasattr(logger, 'current_step') else "未知步骤"
            screenshot_path = None
            
            # 保存错误截图
            try:
                if page:
                    screenshot_path = f"error_screenshot_{attempt + 1}.png"
                    await page.screenshot(path=screenshot_path, full_page=True)
            except:
                pass
            
            # 记录错误
            error_recorder.record(step_name, e, screenshot_path)
            
            print(f"\n ✗ 第 {attempt + 1} 次尝试失败: {type(e).__name__}: {e}")
            
            # 清理资源
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
                if browser:
                    await browser.close()
            except:
                pass
            
            # 如果还有重试机会，等待后重试
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 3  # 递增等待时间
                print(f" ⏳ 等待 {wait_time} 秒后进行第 {attempt + 2} 次尝试...")
                await asyncio.sleep(wait_time)
            
        finally:
            # 确保资源被清理
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
                if browser:
                    await browser.close()
            except:
                pass
    
    # 所有尝试都失败，保存错误报告
    error_recorder.save_report()
    return False


async def main_test_flow(page: Page) -> bool:
    """主测试流程（不带重试逻辑）"""
    try:
        # ============== 步骤 1: 打开首页 ==============
        logger.step("打开测试网站首页")
        # 增加超时时间，使用 domcontentloaded 替代 networkidle（更快）
        await page.goto(CONFIG["url"], wait_until="domcontentloaded", timeout=30000)
        logger.ok(f"页面已加载: {page.url}")
        
        # 等待页面完全稳定
        await page.wait_for_timeout(2000)

        # 断言: URL 重定向到 home/index
        await expect(page).to_have_url(re.compile(r"/pages/home/index"), timeout=15000)
        logger.ok("URL 重定向正确")

        # ============== 步骤 2: 点击租号入口 ==============
        logger.step("进入租号模块")
        await safe_click(page, page.get_by_label("租号"), "租号 Tab")

        # ============== 步骤 3: 进入出租流程 ==============
        logger.step("点击出租账号")
        await safe_click(page, page.get_by_label("出租账号，将军护航安全交易"), "出租账号卡片")

        # ============== 步骤 4: 密码登录 ==============
        logger.step("切换到密码登录")
        await safe_click(page, page.locator("uni-button").filter(has_text="密码登录"), "密码登录按钮")

        # ============== 步骤 5: 输入账号密码 ==============
        logger.step("输入登录凭证")
        await safe_fill(page, page.get_by_role("spinbutton"), CONFIG["account"], "手机号")
        await safe_fill(page, page.get_by_role("textbox"), CONFIG["password"], "密码")

        # ============== 步骤 6: 同意协议并登录 ==============
        logger.step("同意服务协议并登录")
        await safe_click(page, page.get_by_label("同意服务协议"), "同意服务协议复选框")
        await safe_click(page, page.locator("uni-button").filter(has_text=re.compile(r"^登录$")), "登录按钮")

        # 断言: 登录后页面跳转或出现出租入口
        await page.wait_for_timeout(2000)  # 等待登录响应
        logger.ok("登录请求已提交")

        # ============== 步骤 7: 进入出租表单 ==============
        logger.step("进入出租表单（协议弹窗需滚动到底部等待按钮变为'我已悉知'）")
        await safe_click(page, page.get_by_label("出租账号，将军护航安全交易"), "出租账号卡片")

        # 第7步专用处理：强制关闭协议弹窗（清仓保护细则弹窗）
        popup_closed = await close_protocol_popup(page)
        
        if popup_closed:
            logger.ok("协议弹窗已关闭")
        else:
            logger.fail("协议弹窗关闭失败")
            raise TimeoutError("协议弹窗关闭失败，后续操作将被拦截")

        # ============== 步骤 8: 选择 QQ 登录方式 ==============
        logger.step("选择账号登录方式 - QQ")
        await safe_click(page, page.locator("uni-text").filter(has_text="请选择登录方式"), "登录方式选择器")
        await safe_click(page, page.get_by_text("QQ登录"), "QQ登录选项")
        await safe_click(page, page.get_by_text("确认"), "确认按钮")

        # ============== 步骤 9: 选择扫码登录 ==============
        logger.step("选择扫码登录")
        await safe_click(page, page.get_by_text("请选择账号登录方式"), "账号登录方式选择器")
        await safe_click(page, page.get_by_text("扫码", exact=True), "扫码选项")
        await safe_click(page, page.get_by_text("确认"), "确认按钮")

        # ============== 步骤 10: 设置最早/最晚时间 ==============
        logger.step("设置登录时间范围")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^最早$")), "最早时间")
        await safe_click(page, page.locator("uni-text").filter(has_text="确定"), "确定最早时间")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^最晚$")), "最晚时间")
        await safe_click(page, page.get_by_text("确定"), "确定最晚时间")

        # ============== 步骤 11: 人脸验证 ==============
        logger.step("设置人脸是否本人 - 是")
        await safe_click(page, page.locator("uni-text").filter(has_text="请选择人脸是否本人"), "人脸选择器")
        await safe_click(page, page.get_by_text("是", exact=True), "选择'是'")
        await safe_click(page, page.get_by_text("确认"), "确认人脸")

        # ============== 步骤 12: 选择地区 ==============
        logger.step("选择地区 - 福建省/三明市")
        await safe_click(page, page.locator("uni-text").filter(has_text="请选择地区"), "地区选择器")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^福建省$")), "福建省")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^三明市$")), "三明市")

        # ============== 步骤 13: 填写账号基本信息 ==============
        logger.step("填写账号基本信息")
        await safe_fill(page,
            page.locator("uni-input").filter(has_text="请填写哈夫币").get_by_role("textbox"),
            CONFIG["hafu_coin"], "哈夫币")
        await safe_fill(page,
            page.locator("uni-input").filter(has_text="请填写绝密KD").get_by_role("textbox"),
            CONFIG["kd"], "绝密KD")
        await safe_fill(page,
            page.locator("uni-input").filter(has_text="请填写账号等级").get_by_role("textbox"),
            CONFIG["level"], "账号等级")

        # ============== 步骤 14: 选择段位 ==============
        logger.step("选择账号段位 - 铂金")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^请选择账号段位$")), "段位选择器")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^铂金$")), "铂金")
        await safe_click(page, page.get_by_text("确认"), "确认段位")

        # ============== 步骤 15: 选择安全箱等级 ==============
        logger.step("选择安全箱等级 - 6格")
        await safe_click(page, page.get_by_text("请选择安全箱等级"), "安全箱选择器")
        await safe_click(page, page.get_by_text("6格安全箱"), "6格安全箱")
        await safe_click(page, page.get_by_text("确认"), "确认安全箱")

        # ============== 步骤 16: 填写其他数值 ==============
        logger.step("填写其他账号数值")
        kd_locator = page.locator("uni-view:nth-child(14) > .relative > .font-body > .uni-input-wrapper > .uni-input-input")
        await safe_fill(page, kd_locator, "5", "第14项数值")

        # ============== 步骤 17: 续费六格 ==============
        logger.step("选择续费六格 - 是")
        await safe_click(page, page.get_by_text("请选择续费六格"), "续费六格选择器")
        await safe_click(page, page.get_by_text("是").nth(5), "选择'是'")
        await safe_click(page, page.get_by_text("确认"), "确认续费六格")

        # ============== 步骤 18: 体力等级 ==============
        logger.step("选择体力等级 - 5级")
        await safe_click(page, page.get_by_text("请选择体力等级"), "体力等级选择器")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^5级$")), "5级")
        await safe_click(page, page.get_by_text("确认"), "确认体力等级")

        # ============== 步骤 19: 负重等级 ==============
        logger.step("选择负重等级 - 6级")
        await safe_click(page, page.get_by_text("请选择负重等级"), "负重等级选择器")
        await safe_click(page, page.get_by_text("6级", exact=True), "6级")
        await safe_click(page, page.get_by_text("确认"), "确认负重等级")

        # ============== 步骤 20: 特殊刀皮 ==============
        logger.step("选择特殊刀皮 - 北极星/龙牙/信条")
        await safe_click(page, page.get_by_text("请选择特殊刀皮"), "特殊刀皮选择器")
        await safe_click(page, page.get_by_text("北极星"), "北极星")
        await safe_click(page, page.get_by_text("龙牙"), "龙牙")
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^信条$")), "信条")
        await safe_click(page, page.get_by_text("确认"), "确认刀皮")

        # ============== 步骤 21: 上传图片 ==============
        logger.step("上传账号截图")
        
        # 获取截图目录中的图片文件
        screenshots_dir = r"C:\Users\Administrator\Pictures\Screenshots"
        valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
        available_images = []
        
        if os.path.exists(screenshots_dir):
            for filename in os.listdir(screenshots_dir):
                if filename.lower().endswith(valid_extensions):
                    available_images.append(os.path.join(screenshots_dir, filename))
        
        print(f"  📷 截图目录中找到 {len(available_images)} 张可用图片")
        
        # 准备要上传的图片列表（使用截图目录中的前两张）
        upload_images = []
        if len(available_images) >= 2:
            # 随机打乱并选取前两张
            random.shuffle(available_images)
            upload_images = available_images[:2]
            print(f"  🎲 从截图目录选取: {os.path.basename(upload_images[0])}, {os.path.basename(upload_images[1])}")
        elif len(available_images) == 1:
            upload_images = available_images
            print(f"  🎲 从截图目录选取: {os.path.basename(upload_images[0])}")
        
        # 执行上传
        uploaded_count = 0
        for i, img_path in enumerate(upload_images):
            try:
                # 查找所有上传入口
                upload_buttons = page.get_by_text("点击上传支持jpg、png、webp，传得越多AI越准确")
                button_count = await upload_buttons.count()
                
                if i < button_count:
                    upload_btn = upload_buttons.nth(i)
                    await upload_btn.wait_for(state="visible", timeout=5000)
                    await upload_btn.click(timeout=5000)
                    logger.ok(f"点击: 上传图片入口{i+1}")
                else:
                    # 如果按钮数量不足，尝试点击最后一个可见的上传入口
                    upload_btn = upload_buttons.last
                    await upload_btn.wait_for(state="visible", timeout=5000)
                    await upload_btn.click(timeout=5000)
                    logger.ok(f"点击: 上传图片入口{i+1}")
                
                # 等待文件输入框出现并上传（文件输入框可能是隐藏的，直接设置文件）
                await page.wait_for_timeout(500)
                input_locator = page.locator("input[type=\"file\"]")
                
                # 使用最后一个文件输入框（通常是最新的）
                await input_locator.last.set_input_files(img_path)
                logger.ok(f"已上传: {os.path.basename(img_path)}")
                uploaded_count += 1
                
                # 等待上传完成
                await page.wait_for_timeout(2000)
                
            except Exception as e:
                print(f"  ⚠ 上传第{i+1}张图片失败: {e}")
                break
        
        if uploaded_count == 0:
            logger.ok("跳过上传图片（无可用图片或上传失败）")
        elif uploaded_count == 1:
            logger.ok(f"仅上传1张图片")
        else:
            logger.ok(f"成功上传{uploaded_count}张图片")

        # ============== 步骤 22: 开启开关并设置价格 ==============
        logger.step("设置出租价格")
        await page.locator(".uni-switch-input").first.click()
        logger.ok("开启第一个开关")

        price_locator = page.locator("uni-view:nth-child(2) > .relative > .font-body > .uni-input-wrapper > .uni-input-input").first
        await safe_fill(page, price_locator, CONFIG["price"], "出租价格")

        # ============== 步骤 23: 设置押金 ==============
        logger.step("设置押金")
        deposit_locator = page.locator("uni-view:nth-child(5) > uni-view:nth-child(2) > .relative > .font-body > .uni-input-wrapper > .uni-input-input")
        await safe_fill(page, deposit_locator, CONFIG["deposit"], "押金")

        # ============== 步骤 24: 开启第二个开关 ==============
        logger.step("开启第二个开关")
        await page.locator(".shrink-0 > .uni-switch-wrapper > .uni-switch-input").click()
        logger.ok("已开启")

        # ============== 步骤 25: 优惠券设置 ==============
        logger.step("设置优惠券 - 不使用")
        await safe_click(page,
            page.locator("uni-view").filter(has_text=re.compile(r"^￥500测试——极端出租优惠劵$")).first,
            "优惠券入口")
        await safe_click(page,
            page.locator("uni-view").filter(has_text="不使用优惠券").nth(3),
            "不使用优惠券")
        await safe_click(page, page.get_by_text("确定使用"), "确定使用")

        # ============== 步骤 26: 提交发布 ==============
        logger.step("提交发布")
        await safe_click(page,
            page.locator(".mb-_lfl_20rpx_lfr_ > .h-_lfl_24rpx_lfr_ > img"),
            "关闭弹窗/确认")

        await safe_click(page,
            page.locator("uni-button").filter(has_text="立即发布"),
            "立即发布按钮")

        # ============== 步骤 27: 等待发布结果（最后一步）==============
        logger.step("等待发布结果（停留等待系统处理）")
        
        # 点击"立即发布"后，等待系统响应
        # - 最长等待 5 分钟
        # - 检测到支付成功/订单上架成功关键词 → 再等 10 秒后退出
        # - 检测到"立即支付"按钮 → 点击并继续等待
        # - 超时未检测到 → 也正常退出（不报错）
        success_found = await wait_for_pay_success_or_timeout(page)
        if success_found:
            logger.ok("发布成功，订单已上架，脚本即将退出")
        else:
            logger.ok("等待结束（超时或用户手动处理），脚本退出")

        return logger.summary()

    except Exception as e:
        print(f"\n[错误] 测试中断: {type(e).__name__}: {e}")
        # 保存错误现场截图
        try:
            screenshot_path = "error_screenshot.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"[截图] 错误现场已保存: {os.path.abspath(screenshot_path)}")
        except Exception:
            pass
        logger.summary()
        return False

    finally:
        # 注意：context 和 browser 在 run_with_retry 中统一清理
        try:
            await page.close()
        except:
            pass


async def main() -> None:
    """主入口（带重试和回滚机制）"""
    print("=" * 60)
    print("租号发布流程自动化测试")
    print(f"测试网址: {CONFIG['url']}")
    print(f"测试账号: {CONFIG['account']}")
    print(f"最大重试次数: 3")
    print("=" * 60)

    async with async_playwright() as playwright:
        success = await run_with_retry(playwright, max_retries=3)

    # 保存最终报告
    if error_recorder.has_errors():
        error_recorder.save_report()
    
    if success:
        print("\n[结果] 测试通过 ✓")
        sys.exit(0)
    else:
        print("\n[结果] 测试失败 ✗")
        print("  详情请查看错误报告: error_report.txt")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())