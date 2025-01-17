# -*- coding: utf-8 -*-
import base64
import time
from datetime import datetime
from typing import Tuple

import loguru
from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio

from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_KUAISHOU
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.files_times import get_absolute_path
from social_auto_upload.utils.log import kuaishou_logger


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://cp.kuaishou.com/article/publish/video")
        try:
            await page.wait_for_selector("div.names div.container div.name:text('机构服务')", timeout=5000)  # 等待5秒

            kuaishou_logger.info("[+] 等待5秒 cookie 失效")
            return False
        except:
            kuaishou_logger.success("[+] cookie 有效")
            return True

async def get_user_id(page):
    start_time = time.time()  # 获取开始时间
    while True:
        user_id = await page.locator('.info-top-number').text_content()
        user_id = user_id.replace("快手号：", "").strip()
        if user_id == '0':
            current_time = time.time()  # 获取当前时间
            elapsed_time = current_time - start_time  # 计算已经过去的时间
            if elapsed_time > 10:  # 如果已经过去的时间超过5秒
                break  # 退出循环
        else:
            break  # 退出循环
    return user_id
async def ks_setup(account_file, handle=False):
    account_file = get_absolute_path(account_file, "kuaishou_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        kuaishou_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await get_ks_cookie(account_file)
    return True


async def get_ks_cookie(account_file):
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': False,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com")
        await page.locator('.login').click()
        await page.locator('.platform-switch').click()
        login_url = page.url
        img_url = await page.locator('.qrcode img').get_attribute('src')
        # 解码 base64 图片
        # img_data = base64.b64decode(img_url.replace('data:image/png;base64,', ''))
        # img = Image.open(BytesIO(img_data))
        # img.save(get_upload_login_path('kuaishou'))
        start_time = time.time()
        while True:
            if login_url == page.url:
                await asyncio.sleep(0.5)
            else:
                break
            elapsed_time = time.time() - start_time
            # 检查是否超过了超时时间
            if elapsed_time > 60:
                raise TimeoutError("操作超时，跳出循环")
        await page.goto('https://cp.kuaishou.com/profile')
        await asyncio.sleep(0.5)
        user_id = await get_user_id(page)
        user_name = await page.locator('.info-top-name').text_content()
        loguru.logger.info(f'{user_id}---{user_name}')
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=get_account_file(user_id, SOCIAL_MEDIA_KUAISHOU, user_name))
        # try:
        #     os.remove(get_upload_login_path('kuaishou'))
        # except:
        #     loguru.logger.info(f"删除图片失败")
        return user_id, user_name


class KSVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, goods=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.goods = goods
        self.account_file = account_file
        self.date_format = '%Y-%m-%d %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH

    async def handle_upload_error(self, page):
        kuaishou_logger.error("视频出错了，重新上传中")
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> tuple[bool, str]:
        # 使用 Chromium 浏览器启动一个浏览器实例
        print(self.local_executable_path)
        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=False,
                executable_path=self.local_executable_path,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=False
            )  # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        context.on("close", lambda: context.storage_state(path=self.account_file))
        msg_res = '检测通过，暂未发现异常'
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://cp.kuaishou.com/article/publish/video")
        kuaishou_logger.info(f'正在上传-------{self.title}.mp4{self.file_path}')
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        kuaishou_logger.info('正在打开主页...')
        await page.wait_for_url("https://cp.kuaishou.com/article/publish/video")
        # 点击 "上传视频" 按钮
        upload_button = page.locator("button[class^='_upload-btn']")
        await upload_button.wait_for(state='visible')  # 确保按钮可见

        async with page.expect_file_chooser() as fc_info:
            await upload_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

        await asyncio.sleep(2)

        # if not await page.get_by_text("封面编辑").count():
        #     raise Exception("似乎没有跳转到到编辑页面")

        await asyncio.sleep(1)

        # 等待按钮可交互
        new_feature_button = page.locator('button[type="button"] span:text("我知道了")')
        if await new_feature_button.count() > 0:
            await new_feature_button.click()

        kuaishou_logger.info("正在填充标题和话题...")
        await page.get_by_text("描述").locator("xpath=following-sibling::div").click()
        kuaishou_logger.info("clear existing title")
        await page.keyboard.press("Backspace")
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        kuaishou_logger.info("filling new  title")
        await page.keyboard.type(self.title)
        await page.keyboard.press("Enter")

        # 快手只能添加3个话题
        for index, tag in enumerate(self.tags[:3], start=1):
            kuaishou_logger.info("正在添加第%s个话题" % index)
            await page.keyboard.type(f"#{tag} ")
            await asyncio.sleep(2)
        # 点击不允许下载
        allow_download = page.locator('label:has-text("允许下载此作品")')
        if await allow_download.count() > 0:
            await allow_download.click()
        # 关联商品
        if self.goods and self.goods.relItemId:
            await self.set_author_service(page,'关联商品')
        max_retries = 600  # 设置最大重试次数,最大等待时间为 2 分钟
        retry_count = 0

        while retry_count < max_retries:
            try:
                # 获取包含 '上传中' 文本的元素数量
                number = await page.locator("text=上传中").count()

                if number == 0:
                    kuaishou_logger.success("视频上传完毕")
                    break
                else:
                    if retry_count % 5 == 0:
                        kuaishou_logger.info("正在上传视频中...")
                    await asyncio.sleep(2)
            except Exception as e:
                if e.message == 'Locator.count: Target page, context or browser has been closed':
                    raise e  # 直接抛出异常
                kuaishou_logger.error(f"检查上传状态时发生错误: {e}")
                await asyncio.sleep(2)  # 等待 2 秒后重试
            retry_count += 1

        if retry_count == max_retries:
            kuaishou_logger.warning("超过最大重试次数，视频上传可能未完成。")

        # 定时任务
        if self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        # 判断视频是否发布成功
        while True:
            try:
                publish_button = page.get_by_text("发布", exact=True)
                if await publish_button.count() > 0:
                    await publish_button.click()

                await asyncio.sleep(1)
                confirm_button = page.get_by_text("确认发布")
                if await confirm_button.count() > 0:
                    await confirm_button.click()

                # 等待页面跳转，确认发布成功
                await page.wait_for_url(
                    "https://cp.kuaishou.com/article/manage/video?status=2&from=publish",
                    timeout=5000,
                )
                kuaishou_logger.success("视频发布成功")
                break
            except Exception as e:
                kuaishou_logger.info(f"视频正在发布中... 错误: {e}")
                await page.screenshot(full_page=True)
                await asyncio.sleep(1)

        await context.storage_state(path=self.account_file)  # 保存cookie
        kuaishou_logger.info('cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()
        return True, msg_res

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)

    async def set_schedule_time(self, page, publish_date):
        kuaishou_logger.info("click schedule")
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M:%S")
        await page.locator("label:text('发布时间')").locator('xpath=following-sibling::div').locator(
            '.ant-radio-input').nth(1).click()
        await asyncio.sleep(1)

        await page.locator('div.ant-picker-input input[placeholder="选择日期时间"]').click()
        await asyncio.sleep(1)

        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)
    # 作者服务
    async def set_author_service(self, page: Page, location: str = "关联商品"):
        await page.locator('div.ant-select-selector span:has-text("选择服务类型")').locator("..").click()
        await page.wait_for_selector('#microSupport .ant-select-item-option', timeout=5000)
        await page.locator(f'#microSupport .ant-select-item-option:has-text("{location}")').click()
        product_selector = 'div.ant-select-selector span:has-text("关联商品获得更多收入")'
        search_input = page.locator(product_selector).locator("..").locator('.ant-select-selection-search-input')
        await search_input.type(str(self.goods.relItemId))
        await page.wait_for_selector('.rc-virtual-list', state='visible', timeout=5000)
        
        # 获取所有商品标题元素
        goods_titles = await page.locator('.rc-virtual-list [class^="_goods-title"]').all()
        
        # 遍历所有标题，找到匹配的商品并点击
        for title_element in goods_titles:
            title_text = await title_element.text_content()
            if title_text.strip() == str(self.goods.itemTitle).strip():
                await title_element.click()
                return
        await asyncio.sleep(2)
        for title_element in goods_titles:
            title_text = await title_element.text_content()
            if title_text.strip() == str(self.goods.itemTitle).strip():
                await title_element.click()
                return  
        # 如果没有找到匹配的商品，按回车选择第一个
        await page.keyboard.press("Enter")
        
