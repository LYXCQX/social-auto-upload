# -*- coding: utf-8 -*-
import time
from datetime import datetime
from typing import Tuple

import loguru
from playwright.async_api import Playwright, async_playwright
import os
import asyncio

from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_TENCENT
from social_auto_upload.utils.bus_exception import UpdateError
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.files_times import get_absolute_path
from social_auto_upload.utils.log import tencent_logger


def format_str_for_short_title(origin_title: str) -> str:
    # 定义允许的特殊字符
    allowed_special_chars = "《》“”:+?%°"

    # 移除不允许的特殊字符
    filtered_chars = [char if char.isalnum() or char in allowed_special_chars else ' ' if char == ',' else '' for
                      char in origin_title]
    formatted_string = ''.join(filtered_chars)

    # 调整字符串长度
    if len(formatted_string) > 16:
        # 截断字符串
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        # 使用空格来填充字符串
        formatted_string += ' ' * (6 - len(formatted_string))

    return formatted_string


async def cookie_auth(account_file,local_executable_path=None):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, executable_path=local_executable_path)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        try:
            await page.wait_for_selector('div.title-name:has-text("微信小店")', timeout=5000)  # 等待5秒
            tencent_logger.error("[+] 等待5秒 cookie 失效")
            return False
        except:
            tencent_logger.success("[+] cookie 有效")
            return True


async def get_tencent_cookie(account_file, local_executable_path=None):
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
            'executable_path': local_executable_path
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        # await page.pause()
        # # 点击调试器的继续，保存cookie
        # await context.storage_state(path=account_file)
        login_url = page.url
        start_time = time.time()
        while True:
            if login_url == page.url:
                await asyncio.sleep(0.5)
            else:
                break
            elapsed_time = time.time() - start_time
            # 检查是否超过了超时时间
            if elapsed_time > 120:
                raise TimeoutError("操作超时，跳出循环")
        user_id = await get_user_id(page)
        user_name = await page.locator('.finder-nickname').text_content()
        loguru.logger.info(f'{user_id}---{user_name}')
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=get_account_file(user_id, SOCIAL_MEDIA_TENCENT, user_name))
        return user_id,user_name


async def get_user_id(page):
    start_time = time.time()  # 获取开始时间
    while True:
        # 更新选择器以获取视频号ID
        user_id = await page.locator('.finder-uniq-id').text_content()
        user_id = user_id.strip()
        if user_id == '0':
            current_time = time.time()  # 获取当前时间
            elapsed_time = current_time - start_time  # 计算已经过去的时间
            if elapsed_time > 10:  # 如果已经过去的时间超过10秒
                break  # 退出循环
        else:
            break  # 退出循环
    return user_id


async def weixin_setup(account_file, handle=False, local_executable_path=None):
    # account_file = get_absolute_path(account_file, "tencent_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file, local_executable_path=local_executable_path):
        if not handle:
            # Todo alert message
            return False, None, None
        tencent_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        user_id, user_name = await get_tencent_cookie(account_file, local_executable_path=local_executable_path)
    else:
        # 新增：从 account_file 的文件名中提取用户 id 和 name
        base_name = os.path.basename(account_file)
        user_id, user_name = base_name.split('_')[:2]  # 假设文件名格式为 "user_id_user_name_account.json"
    return True, user_id, user_name


class TencentVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, category=None, local_executable_path=None,info=None,collection=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.category = category
        self.local_executable_path =  local_executable_path if local_executable_path else LOCAL_CHROME_PATH
        self.info=info
        self.collection=collection

    async def set_schedule_time_tencent(self, page, publish_date):
        label_element = page.locator("label").filter(has_text="定时").nth(1)
        await label_element.click()

        await page.click('input[placeholder="请选择发表时间"]')

        str_month = str(publish_date.month) if publish_date.month > 9 else "0" + str(publish_date.month)
        current_month = str_month + "月"
        # 获取当前的月份
        page_month = await page.inner_text('span.weui-desktop-picker__panel__label:has-text("月")')

        # 检查当前月份是否与目标月份相同
        if page_month != current_month:
            await page.click('button.weui-desktop-btn__icon__right')

        # 获取页面元素
        elements = await page.query_selector_all('table.weui-desktop-picker__table a')

        # 遍历元素并点击匹配的元素
        for element in elements:
            if 'weui-desktop-picker__disabled' in await element.evaluate('el => el.className'):
                continue
            text = await element.inner_text()
            if text.strip() == str(publish_date.day):
                await element.click()
                break

        # 输入小时部分（假设选择11小时）
        await page.click('input[placeholder="请选择时间"]')
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date.hour))

        # 选择标题栏（令定时时间生效）
        await page.locator("div.input-editor").click()

    async def handle_upload_error(self, page):
        tencent_logger.info("视频出错了，重新上传中")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)

    async def add_activity(self, page):
        if not self.info:
            return

        anchor_info = self.info.get("anchor_info", None)
        if not anchor_info:
            return

        playlet_title = anchor_info.get("title", None)
        if not playlet_title:
            return

        tencent_logger.info(f"开始添加活动: {playlet_title}")

        # 等待包含"活动"标签的form-item出现
        await page.wait_for_selector('.form-item:has(.label:text("活动"))', state="visible", timeout=5000)
        form_item = page.locator('.form-item:has(.label:text("活动"))')

        # 查找并点击"不参与活动"按钮
        no_activity_span = form_item.locator("span:has-text('不参与活动'):visible")
        if await no_activity_span.is_visible():
            await no_activity_span.click()
            tencent_logger.info("已点击不参与活动")

        # 等待活动列表加载
        await page.wait_for_selector('.form-item:has(.label:text("活动")) .common-option-list-wrap', state="visible", timeout=5000)
        search_activity_input = form_item.locator('input[placeholder="搜索活动"]')
        # 填充活动标题
        await search_activity_input.fill(playlet_title)
        # 等待活动列表项出现
        start_time = time.time()
        while True:
            activity_elements = await form_item.locator('.name').all()
            if len(activity_elements) > 1:
                break
            if time.time() - start_time > 5:  # 5秒超时
                raise TimeoutError("等待活动列表加载超时")
            await asyncio.sleep(0.5)
            
        found = False

        for element in activity_elements:
            text = await element.text_content()
            # 去除当前活动标题中的标点符号
            clean_text = ''.join(char for char in text if char.isalnum() or char.isspace())
            tencent_logger.info(f'已找到活动：{clean_text}--需要参加活动：{playlet_title}')
            if clean_text.strip() == playlet_title.strip():
                await element.click()
                tencent_logger.info(f"成功添加活动: {playlet_title}")
                found = True
                break
                
        if not found:
            raise UpdateError(f"没有找到该短剧任务{playlet_title}")

    async def upload(self, playwright: Playwright) -> tuple[bool, str]:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(headless=False, executable_path=self.local_executable_path)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        msg_res = '检测通过，暂未发现异常'
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        tencent_logger.info(f'[+]正在上传-------{self.title}.mp4')
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create")
        # await page.wait_for_selector('input[type="file"]', timeout=10000)
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)
        # 填充标题和话题
        await self.add_title_tags(page)
        # 添加商品
        # await self.add_product(page)
        # 原创选择
        await self.add_original(page)
        # 添加活动
        await self.add_activity(page)
        # 合集功能
        await self.add_collection_with_create(page)
        # 检测上传状态
        await self.detect_upload_status(page)
        if self.publish_date and self.publish_date != 0:
            await self.set_schedule_time_tencent(page, self.publish_date)
        # 添加短标题
        await self.add_short_title(page)

        await self.click_publish(page)

        await context.storage_state(path=f"{self.account_file}")  # 保存cookie
        tencent_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()
        return True, msg_res

    async def add_short_title(self, page):
        short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
            "xpath=following-sibling::div").locator(
            'span input[type="text"]')
        if await short_title_element.count():
            short_title = format_str_for_short_title(self.title)
            await short_title_element.fill(short_title)

    async def click_publish(self, page):
        while True:
            try:
                publish_buttion = page.locator('div.form-btns button:has-text("发表")')
                if await publish_buttion.count():
                    await publish_buttion.click()
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=1500)
                tencent_logger.success("  [-]视频发布成功")
                break
            except Exception as e:
                current_url = page.url
                if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                    tencent_logger.success("  [-]视频发布成功")
                    break
                else:
                    tencent_logger.exception(f"  [-] Exception: {e}")
                    tencent_logger.info("  [-] 视频正在发布中...")
                    await asyncio.sleep(0.5)

    async def detect_upload_status(self, page):
        while True:
            # 匹配删除按钮，代表视频上传完毕，如果不存在，代表视频正在上传，则等待
            try:
                # 匹配删除按钮，代表视频上传完毕
                if "weui-desktop-btn_disabled" not in await page.get_by_role("button", name="发表").get_attribute(
                        'class'):
                    tencent_logger.info("  [-]视频上传完毕")
                    break
                else:
                    tencent_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)
                    # 出错了视频出错
                    if await page.locator('div.status-msg.error').count() and await page.locator(
                            'div.media-status-content div.tag-inner:has-text("删除")').count():
                        tencent_logger.error("  [-] 发现上传出错了...准备重试")
                        await self.handle_upload_error(page)
            except Exception as e:
                if e.message == 'Locator.count: Target page, context or browser has been closed':
                    raise e  # 直接抛出异常
                tencent_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        await page.locator("div.input-editor").click()
        await page.keyboard.type(self.title)
        await page.keyboard.press("Enter")
        for index, tag in enumerate(self.tags, start=1):
            await page.keyboard.type("#" + tag)
            await page.keyboard.press("Space")
        tencent_logger.info(f"成功添加hashtag: {len(self.tags)}")


    async def create_collection(self, page):
        await page.get_by_text("创建新合集").click()
        
        # 等待输入框出现并可见
        await page.wait_for_selector('input[placeholder="有趣的合集标题更容易吸引粉丝"]', state="visible", timeout=5000)
        await page.fill('input[placeholder="有趣的合集标题更容易吸引粉丝"]', self.collection)
        
        # 等待创建按钮可点击
        create_button = page.get_by_role("button", name="创建")
        await create_button.wait_for(state="visible", timeout=5000)
        await create_button.click()
        
        # 等待成功提示对话框出现
        await page.wait_for_selector('.create-dialog-success-wrap', state="visible", timeout=5000)
        try:
            # 等待"我知道了"按钮可点击
            know_button = page.locator('.create-dialog-success-wrap button:has-text("我知道了")')
            await know_button.wait_for(state="enabled", timeout=5000)
            await know_button.click()
        except:
            pass

    async def add_collection_with_create(self, page):
        if not self.collection:
            return
        found = await self.add_collection(page)
        if not found:
            await self.create_collection(page)
            found = await self.add_collection(page)

    async def add_collection(self, page):
        if not self.collection:
            return
            
        await page.click('text=选择合集')
        
        # 等待合集列表容器可见
        await page.wait_for_selector('.option-list-wrap', state="visible", timeout=5000)
        
        # 等待合集列表加载完成
        start_time = time.time()
        while True:
            collection_elements = await page.locator('.option-list-wrap').locator('.name').all()
            if len(collection_elements) > 1:
                break
            if time.time() - start_time > 5:  # 5秒超时
                tencent_logger.warning("等待合集列表加载超时")
                return False
            await asyncio.sleep(0.5)

        found = False
        
        # 查找匹配的合集
        for element in collection_elements:
            text = await element.text_content()
            tencent_logger.info(f'找到合集：{text} 需要选择合集：{self.collection}')
            if text.strip() == self.collection:
                await element.click()
                tencent_logger.info(f"成功选择合集: {self.collection}")
                found = True
                break
        return found

    async def add_original(self, page):
        if await page.get_by_label("视频为原创").count():
            await page.get_by_label("视频为原创").check()
        # 检查 "我已阅读并同意 《视频号原创声明使用条款》" 元素是否存在
        label_locator = await page.locator('label:has-text("我已阅读并同意 《视频号原创声明使用条款》")').is_visible()
        if label_locator:
            await page.get_by_label("我已阅读并同意 《视频号原创声明使用条款》").check()
            await page.get_by_role("button", name="声明原创").click()
        # 2023年11月20日 wechat更新: 可能新账号或者改版账号，出现新的选择页面
        if await page.locator('div.label span:has-text("声明原创")').count() and self.category:
            # 因处罚无法勾选原创，故先判断是否可用
            if not await page.locator('div.declare-original-checkbox input.ant-checkbox-input').is_disabled():
                await page.locator('div.declare-original-checkbox input.ant-checkbox-input').click()
                if not await page.locator(
                        'div.declare-original-dialog label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible').count():
                    await page.locator('div.declare-original-dialog input.ant-checkbox-input:visible').click()
            if await page.locator('div.original-type-form > div.form-label:has-text("原创类型"):visible').count():
                await page.locator('div.form-content:visible').click()  # 下拉菜单
                await page.locator(
                    f'div.form-content:visible ul.weui-desktop-dropdown__list li.weui-desktop-dropdown__list-ele:has-text("{self.category}")').first.click()
                await page.wait_for_timeout(1000)
            if await page.locator('button:has-text("声明原创"):visible').count():
                await page.locator('button:has-text("声明原创"):visible').click()

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
