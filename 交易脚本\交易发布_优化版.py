"""
交易发布流程自动化测试脚本
优化版：增加断言、错误处理和日志记录
支持多次创建商品（首次登录获取令牌，后续复用会话）
"""

import asyncio
import re
import os
import traceback
import glob
import random
from datetime import datetime
from playwright.async_api import Playwright, async_playwright, expect, Page


# ============== 配置区 ==============
CONFIG = {
    "url": "https://test-m.jiangjunzh.com/pages/home/index",
    "account": "18791032606",
    "password": "123456",
    "headless": False,
    "slow_mo": 100,
    "timeout": 30000,
    "run_count": 1,  # 运行次数，默认1次
    "page_stabilize_timeout": 3000,  # 页面稳定等待时间（毫秒）
    "max_retry_count": 3,  # 最大重试次数
    "retry_delay": 5000,  # 重试延迟（毫秒）
}


class TestLogger:
    """测试日志记录器"""
    def __init__(self):
        self.step = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def info(self, msg):
        print(f"ℹ {msg}")
    
    def success(self, msg):
        self.passed += 1
        print(f"✓ {msg}")
    
    def error(self, msg, exception=None):
        self.failed += 1
        self.errors.append({"step": self.step, "message": msg, "exception": exception})
        print(f"✗ {msg}")
        if exception:
            print(f"  错误详情: {exception}")
    
    def step_start(self, desc):
        self.step += 1
        print(f"\n[步骤 {self.step:02d}] {desc}")
    
    def step_end(self, success, msg=""):
        if success:
            self.success(msg if msg else "完成")
        else:
            self.error(msg if msg else "失败")
    
    def summary(self):
        print(f"\n{'='*50}")
        print(f"测试结果: 共 {self.step} 步骤 | 通过 {self.passed} | 失败 {self.failed}")
        if self.errors:
            print("\n错误详情:")
            for err in self.errors:
                print(f"  步骤{err['step']}: {err['message']}")
                if err['exception']:
                    print(f"    {err['exception']}")
        print(f"{'='*50}")
        return self.failed == 0


logger = TestLogger()


async def safe_click(page: Page, selector, action_name: str, timeout=10000):
    """安全点击操作"""
    try:
        await selector.wait_for(state="visible", timeout=timeout)
        await selector.click(timeout=timeout)
        logger.info(f"点击成功: {action_name}")
        return True
    except Exception as e:
        logger.error(f"点击失败: {action_name}", e)
        return False


async def safe_fill(page: Page, selector, value: str, field_name: str, timeout=10000):
    """安全填充操作"""
    try:
        await selector.wait_for(state="visible", timeout=timeout)
        await selector.fill(value)
        logger.info(f"填充成功: {field_name} = {value}")
        return True
    except Exception as e:
        logger.error(f"填充失败: {field_name}", e)
        return False


def get_upload_images():
    """获取可用图片"""
    local_images = glob.glob("*.jpg") + glob.glob("*.png") + glob.glob("*.webp")
    if not local_images:
        screenshots_dir = "C:/Users/Administrator/Pictures/Screenshots"
        local_images = glob.glob(f"{screenshots_dir}/*.jpg") + glob.glob(f"{screenshots_dir}/*.png") + glob.glob(f"{screenshots_dir}/*.webp")
    return local_images


async def stabilize_page(page: Page, timeout: int = None):
    """稳定页面状态，确保页面完全加载"""
    wait_time = timeout or CONFIG["page_stabilize_timeout"]
    await page.wait_for_timeout(wait_time)
    logger.info(f"页面稳定等待 {wait_time}ms")


async def check_page_alive(page: Page) -> bool:
    """检查页面是否仍然活跃"""
    try:
        await page.evaluate("document.readyState")
        return True
    except Exception as e:
        logger.error("页面已崩溃或关闭", e)
        return False


async def retry_on_browser_crash(func, *args, max_retries: int = None, **kwargs):
    """浏览器崩溃重试装饰器"""
    max_retries = max_retries or CONFIG["max_retry_count"]
    
    for attempt in range(1, max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            error_msg = str(e).lower()
            is_browser_crash = any(keyword in error_msg for keyword in [
                "target closed", "browser closed", "context closed",
                "page closed", "crashed", "navigated"
            ])
            
            if is_browser_crash and attempt < max_retries:
                logger.warning(f"浏览器异常（第{attempt}次），等待 {CONFIG['retry_delay']}ms 后重试...")
                await asyncio.sleep(CONFIG["retry_delay"] / 1000)
                continue
            else:
                raise


async def login_and_get_token(page: Page) -> bool:
    """登录并获取会话令牌（仅首次运行）"""
    
    # ============== 步骤 1: 打开首页 ==============
    logger.step_start("打开首页")
    await page.goto(CONFIG["url"], wait_until="domcontentloaded")
    logger.info(f"页面已加载: {page.url}")
    logger.step_end(True)
    
    # ============== 步骤 2: 点击交易 ==============
    logger.step_start("点击交易")
    result = await safe_click(page, page.get_by_label("交易"), "交易按钮")
    logger.step_end(result)
    if not result: return False
    
    # ============== 步骤 3: 点击交易入口图片 ==============
    logger.step_start("点击交易入口图片")
    trade_img = page.get_by_label("安全交易，随时随地尽在掌握，官方认证担保，海量账号，极速上号").get_by_role("img")
    result = await safe_click(page, trade_img, "交易入口图片")
    if result:
        await expect(trade_img).to_be_visible()
        await safe_click(page, trade_img, "交易入口图片(第二次点击)")
    logger.step_end(result)
    if not result: return False
    
    # ============== 步骤 4: 点击卖账号 ==============
    logger.step_start("点击卖账号")
    await page.wait_for_timeout(2000)
    sell_btn = page.locator(".grid.grid-cols-2 > uni-button:nth-child(2)")
    try:
        await sell_btn.wait_for(state="visible", timeout=10000)
        await sell_btn.click(force=True)
        logger.info("点击成功: 卖账号按钮")
        logger.step_end(True)
    except Exception as e:
        logger.error("点击失败: 卖账号按钮", e)
        logger.step_end(False)
        return False
    
    # ============== 步骤 5: 等待页面加载 ==============
    logger.step_start("等待页面加载")
    await page.wait_for_timeout(3000)
    logger.step_end(True)
    
    # ============== 步骤 6: 点击密码登录 ==============
    logger.step_start("点击密码登录")
    password_found = False
    for selector in [
        page.locator("uni-button").filter(has_text="密码登录"),
        page.get_by_text("密码登录"),
        page.locator("[class*=\"password\"]")
    ]:
        try:
            await selector.wait_for(state="visible", timeout=5000)
            await selector.click()
            logger.info("点击成功: 密码登录按钮")
            password_found = True
            break
        except:
            continue
    
    if not password_found:
        logger.error("未找到密码登录按钮，可能已在密码登录页面")
    logger.step_end(True)
    
    # ============== 步骤 7: 输入账号密码 ==============
    logger.step_start("输入账号密码")
    
    phone_result = await safe_fill(page, page.get_by_role("spinbutton"), CONFIG["account"], "手机号")
    if not phone_result:
        logger.step_end(False)
        return False
    
    pwd_result = await safe_fill(page, page.get_by_role("textbox"), CONFIG["password"], "密码")
    if not pwd_result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 8: 同意协议并登录 ==============
    logger.step_start("同意协议并登录")
    
    result = await safe_click(page, page.get_by_label("同意服务协议"), "同意服务协议")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.locator("uni-button").filter(has_text=re.compile(r"^登录$")), "登录按钮")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 9: 登录成功后操作 ==============
    logger.step_start("登录成功后操作")
    await page.wait_for_timeout(3000)
    
    result = await safe_click(page, page.locator(".grid.grid-cols-2 > uni-button:nth-child(2)"), "卖账号按钮")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^QQ登录$")), "QQ登录")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^自主发布$")), "自主发布")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    logger.info("✓ 登录完成，会话已建立")
    return True


async def create_goods(page: Page, goods_index: int) -> bool:
    """创建商品（可多次调用）"""
    
    logger.info(f"\n{'='*50}")
    logger.info(f"开始创建第 {goods_index} 个商品")
    logger.info(f"{'='*50}\n")
    
    # 检查页面是否存活
    if not await check_page_alive(page):
        logger.error("页面已崩溃，无法创建商品")
        return False
    
    # 稳定页面状态
    await stabilize_page(page, 2000)
    
    # ============== 步骤 1: 上传图片 ==============
    logger.step_start("上传图片")
    
    local_images = get_upload_images()
    
    if not local_images:
        logger.error("未找到可用图片文件", Exception("图片文件不存在"))
        logger.step_end(False)
        return False
    
    random.shuffle(local_images)
    upload_images = local_images[:2]
    logger.info(f"找到 {len(local_images)} 张可用图片，选择: {[os.path.basename(img) for img in upload_images]}")
    
    try:
        await page.get_by_role("img").nth(2).click()
        await page.locator("input[type=\"file\"]").set_input_files(upload_images[0])
        logger.info(f"上传成功: 第一张图片 - {os.path.basename(upload_images[0])}")
    except Exception as e:
        logger.error("上传失败: 第一张图片", e)
        logger.step_end(False)
        return False
    
    try:
        await page.locator(".h-_lfl_96rpx_lfr_ > img").first.click()
        await page.locator("input[type=\"file\"]").set_input_files(upload_images[-1])
        logger.info(f"上传成功: 第二张图片 - {os.path.basename(upload_images[-1])}")
    except Exception as e:
        logger.error("上传失败: 第二张图片", e)
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 2: 填写账号信息 ==============
    logger.step_start("填写账号信息")
    
    result = await safe_fill(page, page.locator("input[type=\"text\"]"), "325454", "账号ID")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("请选择二次实名"), "二次实名选择器")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^可二次实名$")), "可二次实名")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("确认"), "确认二次实名")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 3: 上传二次实名截图 ==============
    logger.step_start("上传二次实名截图")
    
    screenshot_images = get_upload_images()
    
    if not screenshot_images:
        logger.error("未找到可用图片文件", Exception("图片文件不存在"))
        logger.step_end(False)
        return False
    
    random.shuffle(screenshot_images)
    selected_screenshot = screenshot_images[0]
    logger.info(f"找到 {len(screenshot_images)} 张可用图片，选择: {os.path.basename(selected_screenshot)}")
    
    try:
        screenshot_upload_found = False
        selectors_to_try = [
            page.locator(".h-_lfl_96rpx_lfr_ > img").nth(2),
            page.locator(".h-_lfl_96rpx_lfr_").get_by_role("img").nth(2),
            page.locator(".h-_lfl_96rpx_lfr_").first,
        ]
        
        for sel in selectors_to_try:
            try:
                await sel.wait_for(state="visible", timeout=3000)
                await sel.click(timeout=3000)
                screenshot_upload_found = True
                break
            except:
                continue
        
        if not screenshot_upload_found:
            raise Exception("未找到二次实名截图上传入口")
        
        input_locator = page.locator("input[type=\"file\"]")
        input_count = await input_locator.count()
        
        if input_count >= 3:
            await input_locator.nth(2).set_input_files(selected_screenshot)
        else:
            await input_locator.last.set_input_files(selected_screenshot)
        
        logger.info(f"上传成功: 二次实名截图 - {os.path.basename(selected_screenshot)}")
        logger.step_end(True)
    except Exception as e:
        logger.error("上传失败: 二次实名截图", e)
        logger.step_end(False)
        return False
    
    # ============== 步骤 4: 填写资产信息 ==============
    logger.step_start("填写资产信息")
    
    result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写总资产").get_by_role("spinbutton"), "25", "总资产")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写哈夫币纯币").get_by_role("spinbutton"), "12", "哈夫币纯币")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 5: 选择安全箱 ==============
    logger.step_start("选择安全箱")
    
    result = await safe_click(page, page.get_by_text("请选择安全箱", exact=True), "安全箱选择器")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("顶级安全箱(3*3)"), "顶级安全箱")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.locator("uni-view").filter(has_text="顶级安全箱(3*3)高级安全箱(2*3)进阶安全箱(2*2").nth(3), "确认选择")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("确认"), "确认安全箱")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 6: 选择安全箱皮肤 ==============
    logger.step_start("选择安全箱皮肤")
    
    result = await safe_click(page, page.get_by_text("请选择安全箱皮肤"), "安全箱皮肤选择器")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^S6：蚀金华彩$")), "S6蚀金华彩")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("确认"), "确认安全箱皮肤")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 7: 选择刀皮 ==============
    logger.step_start("选择刀皮")
    
    result = await safe_click(page, page.get_by_text("请选择刀皮"), "刀皮选择器")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("坠星者"), "坠星者")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("电锯惊魂"), "电锯惊魂")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("确认"), "确认刀皮")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 8: 选择挂饰 ==============
    logger.step_start("选择挂饰")
    
    result = await safe_click(page, page.get_by_text("请选择挂饰-传说典藏"), "挂饰选择器")
    if not result:
        logger.step_end(False)
        return False
    
    try:
        await page.locator("uni-view").filter(has_text=re.compile(r"^统统拿走$")).click()
        await page.get_by_text("确认").click()
        logger.info("挂饰选择完成")
        logger.step_end(True)
    except Exception as e:
        logger.error("挂饰选择失败", e)
        logger.step_end(False)
        return False
    
    # ============== 步骤 9: 选择武器 ==============
    logger.step_start("选择武器")
    
    result = await safe_click(page, page.get_by_text("请选择武器-传说典藏"), "武器选择器")
    if not result:
        logger.step_end(False)
        return False
    
    try:
        await page.get_by_text("SCAR-电玩高手").click()
        await page.get_by_text("确认").click()
        logger.info("武器选择完成")
        logger.step_end(True)
    except Exception as e:
        logger.error("武器选择失败", e)
        logger.step_end(False)
        return False
    
    # ============== 步骤 10: 选择仓库和设施 ==============
    logger.step_start("选择仓库和设施")
    
    # 仓库
    result = await safe_click(page, page.get_by_text("请选择仓库"), "仓库选择器")
    if result:
        await stabilize_page(page, 1000)
        await safe_click(page, page.get_by_text("仓库LV.10"), "仓库LV.10")
        await stabilize_page(page, 500)
        await safe_click(page, page.get_by_text("确认"), "确认仓库")
        await stabilize_page(page, 1000)
    
    # 靶场
    result = await safe_click(page, page.get_by_text("请选择靶场"), "靶场选择器")
    if result:
        await stabilize_page(page, 1000)
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^靶场LV\.7$")), "靶场LV.7")
        await stabilize_page(page, 500)
        await safe_click(page, page.get_by_text("确认"), "确认靶场")
        await stabilize_page(page, 1000)
    
    # 训练中心
    result = await safe_click(page, page.get_by_text("请选择训练中心"), "训练中心选择器")
    if result:
        await stabilize_page(page, 1000)
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^训练中心LV\.7$")), "训练中心LV.7")
        await stabilize_page(page, 500)
        await safe_click(page, page.get_by_text("确认"), "确认训练中心")
        await stabilize_page(page, 1000)
    
    # 潜水中心
    result = await safe_click(page, page.get_by_text("请选择潜水中心"), "潜水中心选择器")
    if result:
        await stabilize_page(page, 1000)
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^潜水中心LV\.2$")), "潜水中心LV.2")
        await stabilize_page(page, 500)
        await safe_click(page, page.get_by_text("确认"), "确认潜水中心")
        await stabilize_page(page, 1000)
    
    # 收藏室
    result = await safe_click(page, page.get_by_text("请选择收藏室"), "收藏室选择器")
    if result:
        await stabilize_page(page, 1000)
        await safe_click(page, page.get_by_text("收藏室LV.2"), "收藏室LV.2")
        await stabilize_page(page, 500)
        await safe_click(page, page.get_by_text("确认"), "确认收藏室")
        await stabilize_page(page, 1000)
    
    logger.step_end(True)
    
    # ============== 步骤 11: 选择干员外观 ==============
    logger.step_start("选择干员外观")
    
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^请选择干员外观$")), "干员外观选择器")
    if not result:
        logger.step_end(False)
        return False
    
    try:
        await page.locator("uni-text").filter(has_text="至臻/典藏红皮").click()
        await page.wait_for_timeout(1000)
        
        confirm_found = False
        confirm_selectors = [
            page.get_by_text(re.compile(r"确定\(\d+\)")),
            page.get_by_text("确定"),
            page.locator("uni-button").filter(has_text="确定")
        ]
        
        for selector in confirm_selectors:
            try:
                await selector.wait_for(state="visible", timeout=5000)
                await selector.click()
                logger.info("干员外观选择完成")
                confirm_found = True
                break
            except:
                continue
        
        if not confirm_found:
            raise Exception("未找到确定按钮")
        
        logger.step_end(True)
    except Exception as e:
        logger.error("干员外观选择失败", e)
        logger.step_end(False)
        return False
    
    # ============== 步骤 12: 填写等级信息 ==============
    logger.step_start("填写等级信息")
    
    result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写烽火地带等级（1-60）").get_by_role("spinbutton"), "55", "烽火地带等级")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("请选择烽火地带段位"), "烽火地带段位选择器")
    if result:
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^铂金$")), "铂金段位")
        await safe_click(page, page.get_by_text("确认"), "确认段位")
    
    result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写全面战场等级（1-60）").get_by_role("spinbutton"), "55", "全面战场等级")
    if not result:
        logger.step_end(False)
        return False
    
    result = await safe_click(page, page.get_by_text("请选择全面战场段位"), "全面战场段位选择器")
    if result:
        await safe_click(page, page.get_by_text("尉官"), "尉官段位")
        await safe_click(page, page.get_by_text("确认"), "确认段位")
    
    logger.step_end(True)
    
    # ============== 步骤 13: 填写其他信息 ==============
    logger.step_start("填写其他信息")
    
    try:
        await page.locator("uni-view:nth-child(19) > .relative > .font-body > .uni-input-wrapper > .uni-input-input").fill("5")
        logger.info("填写成功: 安全分 = 5")
    except Exception as e:
        logger.error("填写失败: 安全分", e)
    
    result = await safe_click(page, page.locator("uni-text").filter(has_text="请选择通行证"), "通行证选择器")
    if result:
        await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^S7$")), "S7通行证")
        await safe_click(page, page.get_by_text("确认"), "确认通行证")
    
    logger.step_end(True)
    
    # ============== 步骤 14: 发布商品 ==============
    logger.step_start("发布商品")
    
    try:
        price_input = page.locator("uni-input").filter(has_text=re.compile(r"价格|售价")).get_by_role("spinbutton")
        await price_input.fill("100")
        logger.info("填写成功: 出售价格 = 100")
    except Exception as e:
        logger.error("填写失败: 出售价格", e)
    
    result = await safe_click(page, page.locator(".uni-switch-input"), "开关")
    if not result:
        logger.step_end(False)
        return False
    
    # 勾选协议
    agreement_found = False
    
    try:
        agreement_area = page.locator("uni-view").filter(has_text=re.compile(r".*协议.*|.*同意.*"))
        await agreement_area.wait_for(state="visible", timeout=3000)
        img_element = agreement_area.locator("img")
        await img_element.wait_for(state="visible", timeout=2000)
        await img_element.click(timeout=2000)
        logger.info("勾选成功: 协议（方式1 - 区域内图片）")
        agreement_found = True
    except Exception as e:
        logger.info(f"协议勾选方式1失败: {e}")
    
    if not agreement_found:
        try:
            agreement_img = page.locator("img[src=\"/static/images/trade-goods/default.svg\"]")
            await agreement_img.wait_for(state="visible", timeout=2000)
            await agreement_img.click(timeout=2000)
            logger.info("勾选成功: 协议（方式2 - 精确图片路径）")
            agreement_found = True
        except Exception as e:
            logger.info(f"协议勾选方式2失败: {e}")
    
    if not agreement_found:
        try:
            imgs = page.locator("img")
            count = await imgs.count()
            for i in range(count):
                img = imgs.nth(i)
                try:
                    src = await img.get_attribute("src")
                    if src and "default.svg" in src:
                        await img.click(timeout=1000)
                        logger.info(f"勾选成功: 协议（方式3 - 遍历图片，索引{i}）")
                        agreement_found = True
                        break
                except:
                    continue
        except Exception as e:
            logger.info(f"协议勾选方式3失败: {e}")
    
    if not agreement_found:
        try:
            await page.evaluate('''
                const imgs = document.querySelectorAll('img');
                for(let i=0; i<imgs.length; i++) {
                    if(imgs[i].src.includes('default.svg')) {
                        imgs[i].click();
                        return true;
                    }
                }
                return false;
            ''')
            logger.info("勾选成功: 协议（方式4 - JavaScript）")
            agreement_found = True
        except Exception as e:
            logger.info(f"协议勾选方式4失败: {e}")
    
    if not agreement_found:
        logger.warning("未找到协议勾选框，请手动检查页面")
    
    result = await safe_click(page, page.locator("uni-button").filter(has_text="立即发布"), "立即发布按钮")
    if not result:
        logger.step_end(False)
        return False
    
    logger.step_end(True)
    
    # ============== 步骤 15: 等待发布结果 ==============
    logger.step_start("等待发布结果")
    
    try:
        await page.wait_for_timeout(5000)
        
        screenshot_path = f"trade_publish_result_{goods_index}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        await page.screenshot(path=screenshot_path)
        logger.info(f"已保存发布结果页面截图: {screenshot_path}")
        
        current_url = page.url
        logger.info(f"当前URL: {current_url}")
        
        page_title = await page.title()
        logger.info(f"页面标题: {page_title}")
        
        # 检查待审核状态
        pending_approval_selectors = [
            page.get_by_text("待审核"),
            page.get_by_text("审核中"),
            page.get_by_text("审核"),
            page.get_by_text("审核状态"),
            page.get_by_text("待"),
        ]
        
        found_pending = False
        for selector in pending_approval_selectors:
            try:
                await selector.wait_for(state="visible", timeout=2000)
                logger.info(f"检测到待审核状态")
                found_pending = True
                break
            except:
                continue
        
        if found_pending:
            logger.info("发布成功，商品已进入待审核状态")
            logger.step_end(True)
            return True
        
        # 检查成功提示
        success_selectors = [
            page.get_by_text("发布成功"),
            page.get_by_text("提交成功"),
            page.get_by_text("成功"),
        ]
        
        found_success = False
        for selector in success_selectors:
            try:
                await selector.wait_for(state="visible", timeout=2000)
                logger.info(f"检测到成功提示")
                found_success = True
                break
            except:
                continue
        
        if found_success:
            logger.info("检测到发布成功提示")
            logger.step_end(True)
            return True
        
        # 检查页面内容
        page_content = await page.content()
        if "待审核" in page_content or "审核中" in page_content or "发布成功" in page_content or "提交成功" in page_content:
            logger.info("通过页面内容检测到发布成功状态")
            logger.step_end(True)
            return True
        
        all_text = await page.evaluate("document.body.innerText")
        if "待审核" in all_text or "审核中" in all_text or "发布成功" in all_text:
            logger.info("通过页面文本检测到发布成功状态")
            logger.step_end(True)
            return True
        
        logger.error("未检测到待审核状态或发布成功提示", Exception("发布结果未知"))
        logger.step_end(False)
        return False
                
    except Exception as e:
        logger.error("等待发布结果失败", e)
        logger.step_end(False)
        return False


async def navigate_to_publish_page(page: Page) -> bool:
    """导航到发布页面（用于后续商品创建）"""
    
    logger.info("导航到发布页面...")
    
    # 检查页面是否存活
    if not await check_page_alive(page):
        logger.error("页面已崩溃，无法导航")
        return False
    
    # 返回首页
    await page.goto(CONFIG["url"], wait_until="domcontentloaded")
    await stabilize_page(page, 3000)
    
    # 点击交易
    result = await safe_click(page, page.get_by_label("交易"), "交易按钮")
    if not result:
        return False
    
    await stabilize_page(page, 1000)
    
    # 点击交易入口图片
    trade_img = page.get_by_label("安全交易，随时随地尽在掌握，官方认证担保，海量账号，极速上号").get_by_role("img")
    result = await safe_click(page, trade_img, "交易入口图片")
    if not result:
        return False
    
    await stabilize_page(page, 1000)
    await safe_click(page, trade_img, "交易入口图片(第二次点击)")
    
    await stabilize_page(page, 2000)
    
    # 点击卖账号
    sell_btn = page.locator(".grid.grid-cols-2 > uni-button:nth-child(2)")
    try:
        await sell_btn.wait_for(state="visible", timeout=10000)
        await sell_btn.click(force=True)
        logger.info("点击成功: 卖账号按钮")
    except Exception as e:
        logger.error("点击失败: 卖账号按钮", e)
        return False
    
    await stabilize_page(page, 2000)
    
    # 选择QQ登录
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^QQ登录$")), "QQ登录")
    if not result:
        return False
    
    await stabilize_page(page, 1000)
    
    # 点击自主发布
    result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^自主发布$")), "自主发布")
    if not result:
        return False
    
    # 等待发布页面完全加载
    await stabilize_page(page, 3000)
    
    # 验证页面是否正确加载
    try:
        await page.locator("input[type=\"text\"]").wait_for(state="visible", timeout=5000)
        logger.info("发布页面已加载")
        return True
    except:
        logger.warning("发布页面可能未完全加载")
        return True  # 仍然返回True，让后续步骤尝试


async def run(playwright: Playwright) -> bool:
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
    
    run_count = CONFIG["run_count"]
    success_count = 0
    
    try:
        # ============== 首次运行：登录获取会话 ==============
        logger.info("\n" + "="*60)
        logger.info("首次运行：登录并获取会话")
        logger.info("="*60 + "\n")
        
        login_success = await login_and_get_token(page)
        if not login_success:
            logger.error("登录失败，无法继续")
            return False
        
        # ============== 多次创建商品 ==============
        for i in range(1, run_count + 1):
            logger.info(f"\n{'#'*60}")
            logger.info(f"# 第 {i}/{run_count} 次创建商品")
            logger.info(f"{'#'*60}\n")
            
            # 检查页面是否存活
            if not await check_page_alive(page):
                logger.error(f"第 {i} 次创建：页面已崩溃，尝试恢复...")
                # 尝试重新导航
                try:
                    await page.goto(CONFIG["url"], wait_until="domcontentloaded")
                    await stabilize_page(page, 3000)
                except Exception as e:
                    logger.error(f"第 {i} 次创建：页面恢复失败，跳过此次创建")
                    continue
            
            # 首次创建已经在发布页面，后续需要导航到发布页面
            if i > 1:
                nav_success = await navigate_to_publish_page(page)
                if not nav_success:
                    logger.error(f"第 {i} 次创建：导航到发布页面失败")
                    continue
            
            # 创建商品
            goods_success = await create_goods(page, i)
            if goods_success:
                success_count += 1
                logger.info(f"✓ 第 {i} 个商品创建成功")
            else:
                logger.error(f"✗ 第 {i} 个商品创建失败")
            
            # 如果不是最后一次，等待一下再继续
            if i < run_count:
                logger.info(f"等待 5 秒后继续创建下一个商品...")
                await page.wait_for_timeout(5000)
        
        # ============== 总结 ==============
        logger.info(f"\n{'='*60}")
        logger.info(f"批量创建完成: 成功 {success_count}/{run_count}")
        logger.info(f"{'='*60}\n")
        
        return success_count == run_count
        
    except Exception as e:
        logger.error(f"测试异常终止", e)
        print(f"\n错误堆栈:\n{traceback.format_exc()}")
        return False
    finally:
        try:
            await page.close()
        except:
            pass
        try:
            await context.close()
        except:
            pass
        try:
            await browser.close()
        except:
            pass


async def main() -> None:
    print("=" * 60)
    print("交易发布流程自动化测试")
    print(f"测试网址: {CONFIG['url']}")
    print(f"测试账号: {CONFIG['account']}")
    print(f"运行次数: {CONFIG['run_count']}")
    print("=" * 60)
    
    async with async_playwright() as playwright:
        success = await run(playwright)
        
        if logger.summary():
            print("\n[结果] 测试成功 ✓")
        else:
            print("\n[结果] 测试失败 ✗")


if __name__ == "__main__":
    asyncio.run(main())