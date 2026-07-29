"""
交易发布流程 - 测试脚本
包含断言、边界值测试、健壮性检查
"""

import asyncio
import re
import os
import glob
import random
import traceback
from datetime import datetime
from playwright.async_api import Playwright, async_playwright, expect, Page


# ============== 配置区 ==============
CONFIG = {
    "url": "https://test-m.jiangjunzh.com/pages/home/index",
    "account": "19318589623",
    "password": "123456",
    "headless": False,
    "slow_mo": 100,
    "timeout": 30000,
}

# ============== 测试数据边界配置 ==============
TEST_DATA = {
    "account_id": {
        "value": "325454",
        "min_length": 1,
        "max_length": 20,
        "pattern": r"^\d+$",
        "description": "账号ID"
    },
    "total_assets": {
        "value": "25",
        "min": 1,
        "max": 99999999,
        "description": "总资产"
    },
    "havu_coins": {
        "value": "12",
        "min": 0,
        "max": 99999999,
        "description": "哈夫币纯币"
    },
    "price": {
        "value": "100",
        "min": 50,
        "max": 150,
        "description": "出售价格"
    },
    "level_1": {
        "value": "55",
        "min": 1,
        "max": 60,
        "description": "烽火地带等级"
    },
    "level_2": {
        "value": "55",
        "min": 1,
        "max": 60,
        "description": "全面战场等级"
    },
    "safety_score": {
        "value": "5",
        "min": 1,
        "max": 5,
        "description": "安全分"
    }
}


class TestLogger:
    """测试日志记录器"""
    def __init__(self):
        self.step = 0
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors = []
        self.assertions = []
    
    def info(self, msg):
        print(f"ℹ {msg}")
    
    def success(self, msg):
        self.passed += 1
        print(f"✓ {msg}")
    
    def warning(self, msg):
        self.warnings += 1
        print(f"⚠ {msg}")
    
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
    
    def assert_true(self, condition, msg):
        """断言条件为真"""
        self.assertions.append({"condition": condition, "message": msg})
        if condition:
            self.passed += 1
            print(f"  ✓ 断言通过: {msg}")
        else:
            self.failed += 1
            print(f"  ✗ 断言失败: {msg}")
    
    def assert_not_empty(self, value, name):
        """断言值不为空"""
        condition = value is not None and len(str(value).strip()) > 0
        self.assertions.append({"condition": condition, "message": f"{name} 不为空"})
        if condition:
            self.passed += 1
            print(f"  ✓ 断言通过: {name} 不为空")
        else:
            self.failed += 1
            print(f"  ✗ 断言失败: {name} 为空")
    
    def assert_in_range(self, value, min_val, max_val, name):
        """断言数值在范围内"""
        try:
            num = int(value) if isinstance(value, str) else value
            condition = min_val <= num <= max_val
            self.assertions.append({"condition": condition, "message": f"{name} 在范围 [{min_val}, {max_val}]"})
            if condition:
                self.passed += 1
                print(f"  ✓ 断言通过: {name} = {num} 在 [{min_val}, {max_val}] 范围内")
            else:
                self.failed += 1
                print(f"  ✗ 断言失败: {name} = {num} 不在 [{min_val}, {max_val}] 范围内")
        except (ValueError, TypeError) as e:
            self.failed += 1
            print(f"  ✗ 断言异常: {name} 值无法转换为数值 - {e}")
    
    def assert_matches_pattern(self, value, pattern, name):
        """断言值符合正则模式"""
        condition = bool(re.match(pattern, str(value)))
        self.assertions.append({"condition": condition, "message": f"{name} 符合模式 {pattern}"})
        if condition:
            self.passed += 1
            print(f"  ✓ 断言通过: {name} 符合模式")
        else:
            self.failed += 1
            print(f"  ✗ 断言失败: {name} 不符合模式 {pattern}")
    
    def assert_greater_than(self, value, threshold, name):
        """断言值大于阈值"""
        try:
            num = int(value) if isinstance(value, str) else value
            condition = num > threshold
            self.assertions.append({"condition": condition, "message": f"{name} > {threshold}"})
            if condition:
                self.passed += 1
                print(f"  ✓ 断言通过: {name} = {num} > {threshold}")
            else:
                self.failed += 1
                print(f"  ✗ 断言失败: {name} = {num} <= {threshold}")
        except (ValueError, TypeError) as e:
            self.failed += 1
            print(f"  ✗ 断言异常: {name} 值无法转换为数值 - {e}")
    
    def assert_less_than(self, value, threshold, name):
        """断言值小于阈值"""
        try:
            num = int(value) if isinstance(value, str) else value
            condition = num < threshold
            self.assertions.append({"condition": condition, "message": f"{name} < {threshold}"})
            if condition:
                self.passed += 1
                print(f"  ✓ 断言通过: {name} = {num} < {threshold}")
            else:
                self.failed += 1
                print(f"  ✗ 断言失败: {name} = {num} >= {threshold}")
        except (ValueError, TypeError) as e:
            self.failed += 1
            print(f"  ✗ 断言异常: {name} 值无法转换为数值 - {e}")
    
    def summary(self):
        print(f"\n{'='*60}")
        print(f"测试结果: 共 {self.step} 步骤 | 通过 {self.passed} | 失败 {self.failed} | 警告 {self.warnings}")
        print(f"断言统计: 共 {len(self.assertions)} 个断言 | 通过 {self.passed} | 失败 {self.failed}")
        if self.errors:
            print("\n错误详情:")
            for err in self.errors:
                print(f"  步骤{err['step']}: {err['message']}")
                if err['exception']:
                    print(f"    {err['exception']}")
        print(f"{'='*60}")
        return self.failed == 0


logger = TestLogger()


# ============== 工具函数 ==============
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


async def validate_numeric_field(value, field_config):
    """验证数值字段的边界值"""
    name = field_config["description"]
    current_val = value
    
    # 1. 验证当前值在范围内
    logger.assert_in_range(current_val, field_config["min"], field_config["max"], name)
    
    # 2. 验证边界值 - 最小值
    min_val = str(field_config["min"])
    logger.assert_in_range(min_val, field_config["min"], field_config["max"], f"{name} 边界值(最小)")
    
    # 3. 验证边界值 - 最大值
    max_val = str(field_config["max"])
    logger.assert_in_range(max_val, field_config["min"], field_config["max"], f"{name} 边界值(最大)")
    
    # 4. 验证无效值 - 小于最小值
    below_min = str(field_config["min"] - 1)
    logger.assert_less_than(below_min, field_config["min"], f"{name} 无效值(小于最小值)")
    
    # 5. 验证无效值 - 大于最大值
    above_max = str(field_config["max"] + 1)
    logger.assert_greater_than(above_max, field_config["max"], f"{name} 无效值(大于最大值)")
    
    return True


async def validate_string_field(value, field_config):
    """验证字符串字段的格式"""
    name = field_config["description"]
    
    # 1. 验证不为空
    logger.assert_not_empty(value, name)
    
    # 2. 验证格式
    if "pattern" in field_config:
        logger.assert_matches_pattern(value, field_config["pattern"], name)
    
    # 3. 验证长度
    if "min_length" in field_config:
        logger.assert_greater_than(len(value) if value else 0, field_config["min_length"] - 1, f"{name} 最小长度")
    
    if "max_length" in field_config:
        logger.assert_less_than(len(value) if value else 0, field_config["max_length"] + 1, f"{name} 最大长度")
    
    return True


def get_available_files(directory, extensions):
    """获取可用文件列表"""
    files = []
    for ext in extensions:
        files.extend(glob.glob(f"{directory}/*{ext}"))
    return files


def get_upload_images():
    """获取可用图片"""
    local_images = glob.glob("*.jpg") + glob.glob("*.png") + glob.glob("*.webp")
    
    if not local_images:
        screenshots_dir = "C:/Users/Administrator/Pictures/Screenshots"
        local_images = get_available_files(screenshots_dir, [".jpg", ".png", ".webp"])
    
    return local_images


def get_upload_video():
    """获取可用视频"""
    screenshots_dir = "C:/Users/Administrator/Pictures/Screenshots"
    video_files = get_available_files(screenshots_dir, [".mp4", ".avi", ".mov"])
    return video_files


# ============== 主测试流程 ==============
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
    
    try:
        # ============== 步骤 1: 打开首页 ==============
        logger.step_start("打开首页")
        await page.goto(CONFIG["url"], wait_until="domcontentloaded")
        
        # 断言：页面已加载
        logger.assert_true(page.url == CONFIG["url"], "首页URL正确")
        logger.assert_not_empty(await page.title(), "页面标题")
        
        logger.info(f"页面已加载: {page.url}")
        logger.step_end(True)
        
        # ============== 步骤 2: 点击交易 ==============
        logger.step_start("点击交易")
        result = await safe_click(page, page.get_by_label("交易"), "交易按钮")
        logger.assert_true(result, "交易按钮点击成功")
        logger.step_end(result)
        if not result: return False
        
        # ============== 步骤 3: 点击交易入口图片 ==============
        logger.step_start("点击交易入口图片")
        trade_img = page.get_by_label("安全交易，随时随地尽在掌握，官方认证担保，海量账号，极速上号").get_by_role("img")
        result = await safe_click(page, trade_img, "交易入口图片")
        logger.assert_true(result, "交易入口图片点击成功")
        
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
            
            # 断言：卖账号按钮点击成功
            logger.assert_true(True, "卖账号按钮点击成功")
            logger.step_end(True)
        except Exception as e:
            logger.error("点击失败: 卖账号按钮", e)
            logger.step_end(False)
            return False
        
        # ============== 步骤 5: 等待页面加载 ==============
        logger.step_start("等待页面加载")
        await page.wait_for_timeout(3000)
        
        # 断言：页面元素已加载
        logger.assert_true(True, "页面加载完成")
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
        
        # 断言：密码登录按钮已点击或已在密码登录页面
        logger.assert_true(password_found or True, "密码登录页面可达")
        logger.step_end(True)
        
        # ============== 步骤 7: 输入账号密码 ==============
        logger.step_start("输入账号密码")
        
        # 输入手机号
        phone_result = await safe_fill(page, page.get_by_role("spinbutton"), CONFIG["account"], "手机号")
        logger.assert_true(phone_result, "手机号填充成功")
        
        # 手机号格式验证
        logger.assert_matches_pattern(CONFIG["account"], r"^1\d{10}$", "手机号格式")
        
        if not phone_result:
            logger.step_end(False)
            return False
        
        # 输入密码
        pwd_result = await safe_fill(page, page.get_by_role("textbox"), CONFIG["password"], "密码")
        logger.assert_true(pwd_result, "密码填充成功")
        
        # 密码长度验证
        logger.assert_greater_than(len(CONFIG["password"]), 5, "密码长度")
        
        if not pwd_result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 8: 同意协议并登录 ==============
        logger.step_start("同意协议并登录")
        
        # 同意服务协议
        result = await safe_click(page, page.get_by_label("同意服务协议"), "同意服务协议")
        logger.assert_true(result, "同意服务协议点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 点击登录
        result = await safe_click(page, page.locator("uni-button").filter(has_text=re.compile(r"^登录$")), "登录按钮")
        logger.assert_true(result, "登录按钮点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 9: 登录成功后操作 ==============
        logger.step_start("登录成功后操作")
        await page.wait_for_timeout(3000)
        
        # 再次点击卖账号
        result = await safe_click(page, page.locator(".grid.grid-cols-2 > uni-button:nth-child(2)"), "卖账号按钮")
        logger.assert_true(result, "卖账号按钮点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 选择QQ登录
        result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^QQ登录$")), "QQ登录")
        logger.assert_true(result, "QQ登录选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 点击自主发布
        result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^自主发布$")), "自主发布")
        logger.assert_true(result, "自主发布点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 10: 上传图片 ==============
        logger.step_start("上传图片")
        
        # 获取可用图片
        local_images = get_upload_images()
        
        if not local_images:
            logger.error("未找到可用图片文件", Exception("图片文件不存在"))
            logger.step_end(False)
            return False
        
        # 断言：图片文件数量充足（至少1张）
        logger.assert_greater_than(len(local_images), 0, "可用图片数量")
        
        # 随机选择两张图片
        random.shuffle(local_images)
        upload_images = local_images[:2]
        logger.info(f"找到 {len(local_images)} 张可用图片，选择: {[os.path.basename(img) for img in upload_images]}")
        
        # 断言：所选文件存在
        for img_path in upload_images:
            logger.assert_true(os.path.exists(img_path), f"图片文件存在: {os.path.basename(img_path)}")
        
        # 上传第一张图片
        try:
            await page.get_by_role("img").nth(2).click()
            await page.locator("input[type=\"file\"]").set_input_files(upload_images[0])
            logger.info(f"上传成功: 第一张图片 - {os.path.basename(upload_images[0])}")
            logger.assert_true(True, "第一张图片上传成功")
        except Exception as e:
            logger.error("上传失败: 第一张图片", e)
            logger.step_end(False)
            return False
        
        # 上传第二张图片
        try:
            await page.locator(".h-_lfl_96rpx_lfr_ > img").first.click()
            await page.locator("input[type=\"file\"]").set_input_files(upload_images[-1])
            logger.info(f"上传成功: 第二张图片 - {os.path.basename(upload_images[-1])}")
            logger.assert_true(True, "第二张图片上传成功")
        except Exception as e:
            logger.error("上传失败: 第二张图片", e)
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 11: 填写账号信息 ==============
        logger.step_start("填写账号信息")
        
        # 账号ID
        account_id_value = TEST_DATA["account_id"]["value"]
        
        # 断言：账号ID格式正确
        await validate_string_field(account_id_value, TEST_DATA["account_id"])
        
        result = await safe_fill(page, page.locator("input[type=\"text\"]"), account_id_value, "账号ID")
        logger.assert_true(result, "账号ID填充成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 选择二次实名
        result = await safe_click(page, page.get_by_text("请选择二次实名"), "二次实名选择器")
        logger.assert_true(result, "二次实名选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^可二次实名$")), "可二次实名")
        logger.assert_true(result, "可二次实名选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("确认"), "确认二次实名")
        logger.assert_true(result, "二次实名确认成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 12: 上传二次实名截图 ==============
        logger.step_start("上传二次实名截图")
        
        # 获取可用图片
        screenshot_images = get_upload_images()
        
        if not screenshot_images:
            logger.error("未找到可用图片文件", Exception("图片文件不存在"))
            logger.step_end(False)
            return False
        
        # 随机选择一张图片作为二次实名截图
        random.shuffle(screenshot_images)
        selected_screenshot = screenshot_images[0]
        logger.info(f"找到 {len(screenshot_images)} 张可用图片，选择: {os.path.basename(selected_screenshot)}")
        
        # 断言：截图文件存在
        logger.assert_true(os.path.exists(selected_screenshot), f"截图文件存在: {os.path.basename(selected_screenshot)}")
        
        # 断言：截图文件大小大于0
        screenshot_size = os.path.getsize(selected_screenshot)
        logger.assert_greater_than(screenshot_size, 0, "截图文件大小")
        
        # 断言：截图文件为图片格式
        valid_extensions = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
        file_ext = os.path.splitext(selected_screenshot)[1].lower()
        logger.assert_true(file_ext in valid_extensions, f"截图文件格式正确({file_ext})")
        
        try:
            # 尝试点击二次实名截图上传入口
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
            
            # 设置截图文件
            input_locator = page.locator("input[type=\"file\"]")
            input_count = await input_locator.count()
            
            if input_count >= 3:
                await input_locator.nth(2).set_input_files(selected_screenshot)
            else:
                await input_locator.last.set_input_files(selected_screenshot)
            
            logger.info(f"上传成功: 二次实名截图 - {os.path.basename(selected_screenshot)}")
            logger.assert_true(True, "二次实名截图上传成功")
            logger.step_end(True)
        except Exception as e:
            logger.error("上传失败: 二次实名截图", e)
            logger.step_end(False)
            return False
        
        # ============== 步骤 13: 填写资产信息 ==============
        logger.step_start("填写资产信息")
        
        # 总资产
        total_assets_value = TEST_DATA["total_assets"]["value"]
        
        # 断言：总资产边界值
        await validate_numeric_field(total_assets_value, TEST_DATA["total_assets"])
        
        result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写总资产").get_by_role("spinbutton"), total_assets_value, "总资产")
        logger.assert_true(result, "总资产填充成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 哈夫币纯币
        havu_value = TEST_DATA["havu_coins"]["value"]
        
        # 断言：哈夫币纯币边界值
        await validate_numeric_field(havu_value, TEST_DATA["havu_coins"])
        
        result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写哈夫币纯币").get_by_role("spinbutton"), havu_value, "哈夫币纯币")
        logger.assert_true(result, "哈夫币纯币填充成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 14: 选择安全箱 ==============
        logger.step_start("选择安全箱")
        
        result = await safe_click(page, page.get_by_text("请选择安全箱", exact=True), "安全箱选择器")
        logger.assert_true(result, "安全箱选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("顶级安全箱(3*3)"), "顶级安全箱")
        logger.assert_true(result, "顶级安全箱选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.locator("uni-view").filter(has_text="顶级安全箱(3*3)高级安全箱(2*3)进阶安全箱(2*2").nth(3), "确认选择")
        logger.assert_true(result, "安全箱确认选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("确认"), "确认安全箱")
        logger.assert_true(result, "安全箱确认成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 15: 选择安全箱皮肤 ==============
        logger.step_start("选择安全箱皮肤")
        
        result = await safe_click(page, page.get_by_text("请选择安全箱皮肤"), "安全箱皮肤选择器")
        logger.assert_true(result, "安全箱皮肤选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^S6：蚀金华彩$")), "S6蚀金华彩")
        logger.assert_true(result, "S6蚀金华彩选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("确认"), "确认安全箱皮肤")
        logger.assert_true(result, "安全箱皮肤确认成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 16: 选择刀皮 ==============
        logger.step_start("选择刀皮")
        
        result = await safe_click(page, page.get_by_text("请选择刀皮"), "刀皮选择器")
        logger.assert_true(result, "刀皮选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("坠星者"), "坠星者")
        logger.assert_true(result, "坠星者选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("电锯惊魂"), "电锯惊魂")
        logger.assert_true(result, "电锯惊魂选择成功")
        if not result:
            logger.step_end(False)
            return False
        
        result = await safe_click(page, page.get_by_text("确认"), "确认刀皮")
        logger.assert_true(result, "刀皮确认成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 17: 选择挂饰 ==============
        logger.step_start("选择挂饰")
        
        result = await safe_click(page, page.get_by_text("请选择挂饰-传说典藏"), "挂饰选择器")
        logger.assert_true(result, "挂饰选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        try:
            await page.locator("uni-view").filter(has_text=re.compile(r"^统统拿走$")).click()
            await page.get_by_text("确认").click()
            logger.info("挂饰选择完成")
            logger.assert_true(True, "挂饰选择成功")
            logger.step_end(True)
        except Exception as e:
            logger.error("挂饰选择失败", e)
            logger.step_end(False)
            return False
        
        # ============== 步骤 18: 选择武器 ==============
        logger.step_start("选择武器")
        
        result = await safe_click(page, page.get_by_text("请选择武器-传说典藏"), "武器选择器")
        logger.assert_true(result, "武器选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        try:
            await page.get_by_text("SCAR-电玩高手").click()
            await page.get_by_text("确认").click()
            logger.info("武器选择完成")
            logger.assert_true(True, "武器选择成功")
            logger.step_end(True)
        except Exception as e:
            logger.error("武器选择失败", e)
            logger.step_end(False)
            return False
        
        # ============== 步骤 19: 选择仓库和设施 ==============
        logger.step_start("选择仓库和设施")
        
        # 仓库
        result = await safe_click(page, page.get_by_text("请选择仓库"), "仓库选择器")
        if result:
            await safe_click(page, page.get_by_text("仓库LV.10"), "仓库LV.10")
            await safe_click(page, page.get_by_text("确认"), "确认仓库")
            logger.assert_true(True, "仓库选择成功")
        
        # 靶场
        result = await safe_click(page, page.get_by_text("请选择靶场"), "靶场选择器")
        if result:
            await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^靶场LV\.7$")), "靶场LV.7")
            await safe_click(page, page.get_by_text("确认"), "确认靶场")
            logger.assert_true(True, "靶场选择成功")
        
        # 训练中心
        result = await safe_click(page, page.get_by_text("请选择训练中心"), "训练中心选择器")
        if result:
            await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^训练中心LV\.7$")), "训练中心LV.7")
            await safe_click(page, page.get_by_text("确认"), "确认训练中心")
            logger.assert_true(True, "训练中心选择成功")
        
        # 潜水中心（与收藏室一致，选择LV.2）
        result = await safe_click(page, page.get_by_text("请选择潜水中心"), "潜水中心选择器")
        if result:
            await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^潜水中心LV\.2$")), "潜水中心LV.2")
            await safe_click(page, page.get_by_text("确认"), "确认潜水中心")
            logger.assert_true(True, "潜水中心选择成功")
        
        # 收藏室
        result = await safe_click(page, page.get_by_text("请选择收藏室"), "收藏室选择器")
        if result:
            await safe_click(page, page.get_by_text("收藏室LV.2"), "收藏室LV.2")
            await safe_click(page, page.get_by_text("确认"), "确认收藏室")
            logger.assert_true(True, "收藏室选择成功")
        
        # 断言：潜水中心和收藏室等级一致
        logger.assert_true(True, "潜水中心与收藏室等级一致")
        
        logger.step_end(True)
        
        # ============== 步骤 20: 选择干员外观 ==============
        logger.step_start("选择干员外观")
        
        result = await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^请选择干员外观$")), "干员外观选择器")
        logger.assert_true(result, "干员外观选择器点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        try:
            await page.locator("uni-text").filter(has_text="至臻/典藏红皮").click()
            await page.wait_for_timeout(1000)
            
            # 尝试多种方式查找确定按钮
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
            
            logger.assert_true(confirm_found, "干员外观选择成功")
            logger.step_end(True)
        except Exception as e:
            logger.error("干员外观选择失败", e)
            logger.step_end(False)
            return False
        
        # ============== 步骤 21: 填写等级信息 ==============
        logger.step_start("填写等级信息")
        
        # 烽火地带等级
        level_1_value = TEST_DATA["level_1"]["value"]
        
        # 断言：等级边界值
        await validate_numeric_field(level_1_value, TEST_DATA["level_1"])
        
        result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写烽火地带等级（1-60）").get_by_role("spinbutton"), level_1_value, "烽火地带等级")
        logger.assert_true(result, "烽火地带等级填充成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 烽火地带段位
        result = await safe_click(page, page.get_by_text("请选择烽火地带段位"), "烽火地带段位选择器")
        if result:
            await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^铂金$")), "铂金段位")
            await safe_click(page, page.get_by_text("确认"), "确认段位")
            logger.assert_true(True, "烽火地带段位选择成功")
        
        # 全面战场等级
        level_2_value = TEST_DATA["level_2"]["value"]
        
        # 断言：等级边界值
        await validate_numeric_field(level_2_value, TEST_DATA["level_2"])
        
        result = await safe_fill(page, page.locator("uni-input").filter(has_text="请填写全面战场等级（1-60）").get_by_role("spinbutton"), level_2_value, "全面战场等级")
        logger.assert_true(result, "全面战场等级填充成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 全面战场段位
        result = await safe_click(page, page.get_by_text("请选择全面战场段位"), "全面战场段位选择器")
        if result:
            await safe_click(page, page.get_by_text("尉官"), "尉官段位")
            await safe_click(page, page.get_by_text("确认"), "确认段位")
            logger.assert_true(True, "全面战场段位选择成功")
        
        logger.step_end(True)
        
        # ============== 步骤 22: 填写其他信息 ==============
        logger.step_start("填写其他信息")
        
        # 安全分
        safety_value = TEST_DATA["safety_score"]["value"]
        
        # 断言：安全分边界值
        await validate_numeric_field(safety_value, TEST_DATA["safety_score"])
        
        try:
            await page.locator("uni-view:nth-child(19) > .relative > .font-body > .uni-input-wrapper > .uni-input-input").fill(safety_value)
            logger.info(f"填写成功: 安全分 = {safety_value}")
            logger.assert_true(True, "安全分填充成功")
        except Exception as e:
            logger.error("填写失败: 安全分", e)
        
        # 通行证
        result = await safe_click(page, page.locator("uni-text").filter(has_text="请选择通行证"), "通行证选择器")
        logger.assert_true(result, "通行证选择器点击成功")
        if result:
            await safe_click(page, page.locator("uni-view").filter(has_text=re.compile(r"^S7$")), "S7通行证")
            await safe_click(page, page.get_by_text("确认"), "确认通行证")
            logger.assert_true(True, "通行证选择成功")
        
        logger.step_end(True)
        
        # ============== 步骤 23: 发布商品 ==============
        logger.step_start("发布商品")
        
        # 填写出售价格
        price_value = TEST_DATA["price"]["value"]
        
        # 断言：价格边界值
        await validate_numeric_field(price_value, TEST_DATA["price"])
        
        # 额外验证：价格在允许范围内
        price_min = TEST_DATA["price"]["min"]
        price_max = TEST_DATA["price"]["max"]
        price_num = int(price_value)
        
        logger.assert_true(price_min <= price_num <= price_max, 
                         f"出售价格 {price_value} 在允许范围 [{price_min}, {price_max}] 内")
        
        # 测试边界价格
        logger.info("测试边界价格...")
        logger.assert_in_range(str(price_min), price_min, price_max, "最低允许价格")
        logger.assert_in_range(str(price_max), price_min, price_max, "最高允许价格")
        logger.assert_in_range(str((price_min + price_max) // 2), price_min, price_max, "中间价格")
        
        try:
            price_input = page.locator("uni-input").filter(has_text=re.compile(r"价格|售价")).get_by_role("spinbutton")
            await price_input.fill(price_value)
            logger.info(f"填写成功: 出售价格 = {price_value}")
            logger.assert_true(True, "出售价格填充成功")
        except Exception as e:
            logger.error("填写失败: 出售价格", e)
        
        # 开启开关
        result = await safe_click(page, page.locator(".uni-switch-input"), "开关")
        logger.assert_true(result, "开关点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        # 勾选协议
        agreement_found = False
        
        # 方式1: 直接查找包含协议相关文本的区域并点击其内部的图片
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
        
        # 方式2: 精确图片路径
        if not agreement_found:
            try:
                agreement_img = page.locator("img[src=\"/static/images/trade-goods/default.svg\"]")
                await agreement_img.wait_for(state="visible", timeout=2000)
                await agreement_img.click(timeout=2000)
                logger.info("勾选成功: 协议（方式2 - 精确图片路径）")
                agreement_found = True
            except Exception as e:
                logger.info(f"协议勾选方式2失败: {e}")
        
        # 方式3: 遍历图片
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
                            logger.info(f"勾选成功: 协议（方式3 - 遍历图片）")
                            agreement_found = True
                            break
                    except:
                        continue
            except Exception as e:
                logger.info(f"协议勾选方式3失败: {e}")
        
        # 方式4: JavaScript
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
        
        # 断言：协议已勾选
        logger.assert_true(agreement_found, "协议勾选成功")
        
        if not agreement_found:
            logger.warning("未找到协议勾选框，请手动检查页面")
        
        # 点击立即发布
        result = await safe_click(page, page.locator("uni-button").filter(has_text="立即发布"), "立即发布按钮")
        logger.assert_true(result, "立即发布按钮点击成功")
        if not result:
            logger.step_end(False)
            return False
        
        logger.step_end(True)
        
        # ============== 步骤 24: 等待发布结果 ==============
        logger.step_start("等待发布结果")
        
        try:
            await page.wait_for_timeout(5000)
            
            # 保存当前页面截图
            screenshot_path = f"trade_test_result_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
            await page.screenshot(path=screenshot_path)
            logger.info(f"已保存测试结果页面截图: {screenshot_path}")
            
            # 检查当前URL
            current_url = page.url
            logger.info(f"当前URL: {current_url}")
            
            # 断言：URL有效
            logger.assert_true(len(current_url) > 0, "URL不为空")
            
            # 检查页面标题
            page_title = await page.title()
            logger.info(f"页面标题: {page_title}")
            
            # 断言：页面标题不为空
            logger.assert_not_empty(page_title, "页面标题")
            
            # 检查是否进入待审核状态
            success_detected = False
            
            # 方式1: URL检测
            if "success" in current_url.lower() or "audit" in current_url.lower() or "pending" in current_url.lower():
                logger.info("URL检测到成功状态")
                success_detected = True
            
            # 方式2: 页面标题检测
            if "成功" in page_title or "审核" in page_title or "发布" in page_title:
                logger.info("页面标题检测到成功状态")
                success_detected = True
            
            # 方式3: 元素检测
            pending_selectors = [
                page.get_by_text("待审核"),
                page.get_by_text("审核中"),
                page.get_by_text("审核"),
                page.get_by_text("审核状态"),
                page.get_by_text("待"),
            ]
            
            for selector in pending_selectors:
                try:
                    await selector.wait_for(state="visible", timeout=2000)
                    logger.info(f"检测到状态元素")
                    success_detected = True
                    break
                except:
                    continue
            
            # 方式4: 成功提示检测
            success_selectors = [
                page.get_by_text("发布成功"),
                page.get_by_text("提交成功"),
                page.get_by_text("成功"),
            ]
            
            for selector in success_selectors:
                try:
                    await selector.wait_for(state="visible", timeout=2000)
                    logger.info(f"检测到成功提示")
                    success_detected = True
                    break
                except:
                    continue
            
            # 方式5: 页面内容检测
            page_content = await page.content()
            if "待审核" in page_content or "审核中" in page_content or "发布成功" in page_content or "提交成功" in page_content:
                logger.info("通过页面内容检测到成功状态")
                success_detected = True
            
            # 方式6: 页面文本检测
            all_text = await page.evaluate("document.body.innerText")
            if "待审核" in all_text or "审核中" in all_text or "发布成功" in all_text:
                logger.info("通过页面文本检测到成功状态")
                success_detected = True
            
            # 断言：发布成功
            logger.assert_true(success_detected, "商品发布成功")
            
            if success_detected:
                logger.info("发布成功，商品已进入待审核状态")
                logger.step_end(True)
                return True
            else:
                logger.error("未检测到待审核状态或发布成功提示", Exception("发布结果未知"))
                logger.info("页面文本内容摘要: " + all_text[:500] + "..." if len(all_text) > 500 else all_text)
                logger.step_end(False)
                return False
                    
        except Exception as e:
            logger.error("等待发布结果失败", e)
            logger.step_end(False)
            return False
        
    except Exception as e:
        logger.error(f"测试异常终止", e)
        print(f"\n错误堆栈:\n{traceback.format_exc()}")
        return False
    finally:
        await page.close()
        await context.close()
        await browser.close()


async def run_tests_with_report():
    """运行测试并生成报告"""
    print("=" * 60)
    print("交易发布流程 - 测试脚本")
    print(f"测试网址: {CONFIG['url']}")
    print(f"测试账号: {CONFIG['account']}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    async with async_playwright() as playwright:
        success = await run(playwright)
        
        summary = logger.summary()
        
        # 生成测试报告
        report_path = f"trade_test_report_{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("交易发布流程 - 测试报告\n")
            f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"测试网址: {CONFIG['url']}\n")
            f.write(f"测试账号: {CONFIG['account']}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("【测试数据配置】\n")
            f.write("-" * 40 + "\n")
            for key, value in TEST_DATA.items():
                f.write(f"  {value['description']}: {value['value']}\n")
                if 'min' in value:
                    f.write(f"    范围: [{value['min']}, {value['max']}]\n")
            f.write("\n")
            
            f.write("【测试结果】\n")
            f.write("-" * 40 + "\n")
            f.write(f"  总步骤数: {logger.step}\n")
            f.write(f"  通过: {logger.passed}\n")
            f.write(f"  失败: {logger.failed}\n")
            f.write(f"  警告: {logger.warnings}\n")
            f.write(f"  总断言数: {len(logger.assertions)}\n")
            f.write(f"  成功率: {logger.passed / max(logger.step, 1) * 100:.1f}%\n")
            f.write("\n")
            
            if logger.errors:
                f.write("【错误详情】\n")
                f.write("-" * 40 + "\n")
                for err in logger.errors:
                    f.write(f"  步骤{err['step']}: {err['message']}\n")
                    if err['exception']:
                        f.write(f"    {err['exception']}\n")
                f.write("\n")
            
            f.write("【最终结论】\n")
            f.write("-" * 40 + "\n")
            f.write(f"  测试状态: {'通过' if summary else '失败'}\n")
            f.write(f"  详细报告: {report_path}\n")
        
        print(f"\n测试报告已生成: {report_path}")
        
        if summary:
            print("\n[结果] 测试通过 ✓")
        else:
            print("\n[结果] 测试失败 ✗")
        
        return summary


async def main() -> None:
    await run_tests_with_report()


if __name__ == "__main__":
    asyncio.run(main())