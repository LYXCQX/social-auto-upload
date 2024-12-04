# -*- coding: utf-8 -*-
import time
from datetime import datetime
from typing import Tuple, Any

import loguru
from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio
from dotenv import load_dotenv
import json

from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_DOUYIN
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.log import douyin_logger

# 从环境变量中获取检测失败的内容列表
failure_messages_json = os.getenv('FAILURE_MESSAGES', '[]')
failure_messages = json.loads(failure_messages_json)


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=5000)
        except:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 2024.06.17 抖音创作者中心改版
        if await page.get_by_text('手机号登录').count():
            print("[+] 等待5秒 cookie 失效")
            return False
        else:
            print("[+] cookie 有效")
            return True


async def douyin_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        douyin_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await douyin_cookie_gen(account_file)
    return True


async def get_user_id(page):
    start_time = time.time()  # 获取开始时间
    while True:
        user_id = await page.locator('.eYQd8').text_content()
        user_id = user_id.replace("抖音号：", "").strip()
        if user_id == '0':
            current_time = time.time()  # 获取当前时间
            elapsed_time = current_time - start_time  # 计算已经过去的时间
            if elapsed_time > 10:  # 如果已经过去的时间超过5秒
                break  # 退出循环
        else:
            break  # 退出循环
    return user_id


async def douyin_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {
            'headless': False
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        login_url = page.url
        # await page.pause()
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
        user_name = await page.locator('.rNsML').text_content()
        loguru.logger.info(f'{user_id}---{user_name}')
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=get_account_file(user_id,SOCIAL_MEDIA_DOUYIN))


class DouYinVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path

    async def set_schedule_time_douyin(self, page, publish_date):
        # 选择包含特定文本内容的 label 元素
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        # 在选中的 label 元素下点击 checkbox
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")

        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")

        await asyncio.sleep(1)

    async def handle_upload_error(self, page):
        douyin_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> tuple[bool, Any] | tuple[bool, str]:
        # 使用 Chromium 浏览器启动一个浏览器实例
        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=False,
                executable_path=self.local_executable_path,
                args=['--start-maximized']  # 添加启动参数以最大化窗口
            )
        else:
            browser = await playwright.chromium.launch(
                headless=False,
                args=['--start-maximized']  # 添加启动参数以最大化窗口
            )

        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{self.account_file}", no_viewport=True)
        context = await set_init_script(context)

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        douyin_logger.info(f'[+]正在上传-------{self.title}.mp4')
        # 等待页面跳转到指定的 URL，进入，则自动等待到超时
        douyin_logger.info(f'[-] 正在打开主页...')
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")

        # 检查提示文字是否存在
        while True:
            text_exists = await page.get_by_text("支持常用视频格式，推荐mp4、webm").is_visible()
            if text_exists:
                douyin_logger.info("检测到上传页面已加载,正在刷新...")
                await page.reload()
                while True:
                    text_exists = await page.get_by_text("支持常用视频格式，推荐mp4、webm").is_visible()
                    if text_exists:
                        break
                break

        # 点击 "上传视频" 按钮
        await page.locator("div[class^='container'] input").set_input_files(self.file_path)

        # 等待页面跳转到指定的 URL
        while True:
            # 判断是是否进入视频发布页面，没进入，则自动等待到超时
            try:
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page")
                break
            except:
                douyin_logger.info(f'  [-] 正在等待进入视频发布页面...')
                await asyncio.sleep(0.1)

        # 填充标题和话题
        # 检查是否存在包含输入框的元素
        # 这里为了避免页面变化，故使用相对位置定位：作品标题父级右侧第一个元素的input子元素
        await asyncio.sleep(1)
        douyin_logger.info(f'  [-] 正在填充标题和话题...')
        title_container = page.get_by_text('作品标题').locator("..").locator("xpath=following-sibling::div[1]").locator(
            "input")
        if await title_container.count():
            await title_container.fill(self.title[:30])
        else:
            titlecontainer = page.locator(".notranslate")
            await titlecontainer.click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.title)
            await page.keyboard.press("Enter")
        css_selector = ".zone-container"
        for index, tag in enumerate(self.tags, start=1):
            await page.type(css_selector, "#" + tag)
            await page.press(css_selector, "Space")
        douyin_logger.info(f'总共添加{len(self.tags)}个话题')
        allow_download = page.locator('.download-content-Lci5tL label:has-text("不允许")')
        if await allow_download.count() > 0:
            await allow_download.click()
        while True:
            # 判断重新上传按钮是否存在，如果不存在，代表视频正在上传，则等待
            try:
                #  新版：定位重新上传
                number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                if number > 0:
                    douyin_logger.success("  [-]视频上传完毕")
                    break
                else:
                    douyin_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)

                    if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                        douyin_logger.error("  [-] 发现上传出错了... 准备重试")
                        await self.handle_upload_error(page)
            except Exception as e:
                if e.message == 'Locator.count: Target page, context or browser has been closed':
                    raise e  # 直接抛出异常
                douyin_logger.error(e)
                douyin_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

        # 上传视频封面
        await self.set_thumbnail(page, self.thumbnail_path)

        # 更换可见元素
        await self.set_location(page, "杭州市")

        # 頭條/西瓜
        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        # 定位是否有第三方平台
        if await page.locator(third_part_element).count():
            # 检测是否是已选中状态
            if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
                await page.locator(third_part_element).locator('input.semi-switch-native-control').click()

        if self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)
        msg_res = '检测通过，暂未发现异常'
        # 判断视频是否发布成功
        while True:
            # 判断视频是否发布成功
            try:
                publish_button = page.get_by_role('button', name="发布", exact=True)
                if await publish_button.count():
                    start_time = time.time()
                    while True:
                        try:
                            if await page.locator('p.progressingContent-QEbwRE:has-text("视频检测中")').count() > 0:
                                douyin_logger.info("  [-] 视频检测中...")
                                await asyncio.sleep(2)
                            # 获取视频检测状态
                            elif await page.locator('section.contentWrapper-j5kIqC').count() > 0:
                                msg_res = await page.locator('section.contentWrapper-j5kIqC').text_content()
                                if msg_res in failure_messages:
                                    douyin_logger.error(f"  [-] 视频检测失败: {msg_res}")
                                    return False, msg_res
                                else:
                                    douyin_logger.success("  [-] 视频检测通过")
                                    break

                            # 检查检测时间是否超过5分钟
                            current_time = time.time()
                            elapsed_time = current_time - start_time
                            if elapsed_time > 300:
                                page_content = await page.content()
                                douyin_logger.info(f"页面内容: {page_content}")
                                msg_res = '五分钟也没有检测结果，直接返回'
                                break
                        except:
                            # 检查检测时间是否超过5分钟
                            current_time = time.time()
                            elapsed_time = current_time - start_time
                            if elapsed_time > 300:
                                page_content = await page.content()
                                douyin_logger.info(f"页面内容: {page_content}")
                                msg_res = '五分钟也没有检测结果，直接返回'
                                break
                            douyin_logger.info("  [-] 视频检测中...")
                            await asyncio.sleep(2)
                    await publish_button.click()
                await page.wait_for_url("https://creator.douyin.com/creator-micro/content/manage**",
                                        timeout=3000)  # 如果自动跳转到作品页面，则代表发布成功
                douyin_logger.success("  [-]视频发布成功")
                break
            except:
                douyin_logger.info("  [-] 视频正在发布中...")
                await page.screenshot(full_page=True)
                await asyncio.sleep(0.5)

        await context.storage_state(path=self.account_file)  # 保存cookie
        douyin_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()
        return True, msg_res

    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            await page.click('text="选择封面"')
            await page.wait_for_selector("div.semi-modal-content:visible")
            await page.click('text="设置竖封面"')
            await page.wait_for_timeout(2000)  # 等待2秒
            # 定位到上传区域并点击
            # await (page.locator("div[class^='semi-upload upload'] >> input.semi-upload-hidden-input").set_input_files(thumbnail_path))
            await page.set_input_files('.semi-upload-hidden-input', thumbnail_path)
            await page.wait_for_timeout(2000)  # 等待2秒
            await page.locator("div[class^='extractFooter'] button:visible:has-text('完成')").click()
            # finish_confirm_element = page.locator("div[class^='confirmBtn'] >> div:has-text('完成')")
            # if await finish_confirm_element.count():
            #     await finish_confirm_element.click()
            # await page.locator("div[class^='footer'] button:has-text('完成')").click()

    async def set_location(self, page: Page, location: str = "杭州市"):
        # todo supoort location later
        # await page.get_by_text('添加标签').locator("..").locator("..").locator("xpath=following-sibling::div").locator(
        #     "div.semi-select-single").nth(0).click()
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
