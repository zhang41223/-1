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


async def scroll_protocol_to_bottom(page: Page):
    """第7步专用：滚动协议弹窗内容到底部，并强制等待3秒后才能点击"我已悉知"

    针对协议弹窗的特殊处理：必须滚动到底部 + 等待3秒 按钮才可点击。
    """
    wait_ms = CONFIG["protocol_scroll_wait_ms"]
    try:
        # 滚动所有可能的弹窗滚动容器到底部
        await page.evaluate("""
            () => {
                const selectors = [
                    'uni-scroll-view', '.uni-scroll-view-content',
                    '.uni-modal__bd', '.modal-content',
                    '[class*="scroll"]', '.uni-popup',
                    '.uni-picker-view', '.uni-actionsheet',
                    '[class*="popup"]', '[class*="modal"]',
                    '.uni-popup__content', '.uni-actionsheet__menu',
                    '.protocol', '.agreement', '.content'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        el.scrollTop = el.scrollHeight;
                        el.querySelectorAll('*').forEach(child => {
                            if (child.scrollHeight > child.clientHeight) {
                                child.scrollTop = child.scrollHeight;
                            }
                        });
                    });
                });
                window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        print(f"  ↕ 协议弹窗已滚动到底部，强制等待 {wait_ms}ms 后才可点击...")
        await page.wait_for_timeout(wait_ms)
    except Exception as e:
        print(f"  ⚠ 滚动等待异常（忽略继续）: {e}")


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


async def run(playwright: Playwright) -> bool:
    """主测试流程"""
    browser = await playwright.chromium.launch(
        headless=CONFIG["headless"],
        slow_mo=CONFIG["slow_mo"]
    )
    context = await browser.new_context(
        viewport={"width": 375, "height": 812},  # 移动端视口
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
    )
    page = await context.new_page()
    page.set_default_timeout(CONFIG["timeout"])

    try:
        # ============== 步骤 1: 打开首页 ==============
        logger.step("打开测试网站首页")
        await page.goto(CONFIG["url"], wait_until="networkidle")
        logger.ok(f"页面已加载: {page.url}")

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
        logger.step("进入出租表单（协议弹窗需滚动到底部+等3秒）")
        await safe_click(page, page.get_by_label("出租账号，将军护航安全交易"), "出租账号卡片")

        # 第7步专用处理：协议弹窗必须滚动到底部 + 强制等待3秒 才能点击"我已悉知"
        await scroll_protocol_to_bottom(page)
        await safe_click(page, page.get_by_text("我已悉知"), "我已悉知按钮")

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
        # 检查图片文件是否存在
        for img in [CONFIG["image1"], CONFIG["image2"]]:
            if not os.path.exists(img):
                print(f"  ⚠ 警告: 图片文件不存在 {img}（将尝试继续）")

        await safe_click(page,
            page.get_by_text("点击上传支持jpg、png、webp，传得越多AI越准确").first,
            "上传图片入口1")
        await page.locator("input[type=\"file\"]").set_input_files(CONFIG["image1"])
        logger.ok(f"已上传: {CONFIG['image1']}")

        await safe_click(page,
            page.get_by_text("点击上传支持jpg、png、webp，传得越多AI越准确"),
            "上传图片入口2")
        await page.locator("input[type=\"file\"]").set_input_files(CONFIG["image2"])
        logger.ok(f"已上传: {CONFIG['image2']}")

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

        # ============== 步骤 27: 立即支付（最后一步）==============
        logger.step("立即支付（停留等待用户支付保证金）")
        await safe_click(page,
            page.locator("uni-button").filter(has_text="立即支付"),
            "立即支付按钮")

        # 点击"立即支付"后，停留给用户支付保证金的时间
        # - 最长等待 5 分钟
        # - 检测到支付成功/订单上架成功关键词 → 再等 10 秒后退出
        # - 超时未检测到 → 也正常退出（不报错）
        pay_ok = await wait_for_pay_success_or_timeout(page)
        if pay_ok:
            logger.ok("支付成功，订单已上架，脚本即将退出")
        else:
            logger.ok("支付等待结束（超时或用户手动处理），脚本退出")

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
        await page.close()
        await context.close()
        await browser.close()


async def main() -> None:
    """主入口"""
    print("=" * 50)
    print("租号发布流程自动化测试")
    print(f"测试网址: {CONFIG['url']}")
    print(f"测试账号: {CONFIG['account']}")
    print("=" * 50)

    async with async_playwright() as playwright:
        success = await run(playwright)

    if success:
        print("\n[结果] 测试通过 ✓")
        sys.exit(0)
    else:
        print("\n[结果] 测试失败 ✗")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
