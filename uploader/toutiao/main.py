# -*- coding: utf-8 -*-
import logging
import time
from datetime import datetime
from typing import Tuple, Any

import loguru
from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio
from dotenv import load_dotenv
import json

from sympy import true

from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_TOUTIAO
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.log import toutiao_logger

load_dotenv()


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://mp.toutiao.com/profile_v4/xigua/upload-video")
        try:
            await page.wait_for_url("https://mp.toutiao.com/profile_v4/xigua/upload-video", timeout=5000)
            await page.wait_for_selector("text=点击上传或将文件拖入此区域", state="visible", timeout=10000)
        except:
            toutiao_logger.info("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 头条创作者中心
        if await page.get_by_text("点击上传或将文件拖入此区域").is_visible():
            toutiao_logger.info("[+] cookie 有效")
            return True
        else:
            toutiao_logger.info("[+] 等待5秒 cookie 失效")
            return False



async def toutiao_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        toutiao_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await toutiao_cookie_gen(account_file)
    return True


async def get_user_id(page):
    start_time = time.time()
    while True:
        try:
            # 等待页面加载完成
            # 先等待元素出现
            await page.wait_for_selector('text="复制ID"', timeout=2000)

            # 获取用户ID
            user_id_element = page.locator('text="复制ID"').locator('..')
            if await user_id_element.is_visible():
                user_id = await user_id_element.text_content()
                if user_id and user_id != '0':
                    return user_id.replace('复制ID', '')

            current_time = time.time()
            if current_time - start_time > 10:
                toutiao_logger.warning("获取用户ID超时，返回默认值'0'")
                return '0'

            await page.wait_for_timeout(500)

        except Exception as e:
            toutiao_logger.error(f"获取用户ID时发生错误: {str(e)}")
            current_time = time.time()
            if current_time - start_time > 10:
                toutiao_logger.warning("获取用户ID失败，返回默认值'0'")
                return '0'
            await page.wait_for_timeout(500)


async def toutiao_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {
            'headless': False
        }
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()

        # 访问上传页面并等待登录
        await page.goto("https://mp.toutiao.com/auth/page/login")
        login_url = page.url

        start_time = time.time()
        while True:
            current_url = page.url
            if login_url != current_url:
                break

            elapsed_time = time.time() - start_time
            if elapsed_time > 120:
                raise TimeoutError("登录超时，请在2分钟内完成登录")

            await asyncio.sleep(0.5)

        # 等待页面加载完成后再跳转
        await page.goto("https://mp.toutiao.com/profile_v4/personal/info?click_from=header")
        await page.wait_for_url("https://mp.toutiao.com/profile_v4/personal/info?click_from=header")
        user_id = await get_user_id(page)

        try:
            user_name_container = page.locator('text="用户名"').locator('xpath=../div[contains(@class, "content")]')
            user_name = await user_name_container.text_content()
            user_name = user_name.replace('编辑', '')
        except Exception as e:
            toutiao_logger.error(f"获取用户名失败: {str(e)}")
            user_name = "unknown"

        toutiao_logger.info(f'用户ID: {user_id}, 用户名: {user_name}')

        # 保存cookie
        await context.storage_state(path=get_account_file(user_id, SOCIAL_MEDIA_TOUTIAO, user_name))
        await context.close()
        await browser.close()
        return user_id, user_name


class TouTiaoVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None, goods=None,
                 check_video=False, info=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.goods = goods
        self.check_video = check_video
        self.info = info

    async def set_schedule_time_toutiao(self, page, publish_date):
        # 选择包含特定文本内容的 label 元素
        label_element = page.locator("button:text-is('定时发布')")
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
        toutiao_logger.info('视频出错了，重新上传中')
        await page.locator('span:text-is("继续上传")').click()

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
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://mp.toutiao.com/profile_v4/xigua/upload-video")
        toutiao_logger.info(f'[+]正在上传-------{self.title}.mp4')
        # 等待页面跳转到指定的 URL，进入，则自动等待到超时
        toutiao_logger.info(f'[-] 正在打开主页...')
        await page.wait_for_url("https://mp.toutiao.com/profile_v4/xigua/upload-video")

        # 检查提示文字是否存在
        while True:
            text_exists = await page.get_by_text("点击上传或将文件拖入此区域").is_visible()
            if text_exists:
                toutiao_logger.info("检测到上传页面已加载,正在刷新...")
                await page.reload()
                while True:
                    text_exists = await page.get_by_text("点击上传或将文件拖入此区域").is_visible()
                    if text_exists:
                        break
                break

        # 点击 "上传视频" 按钮
        await page.locator("div[class='upload-video-trigger'] input").set_input_files(self.file_path)

        # 等待页面跳转到指定的 URL
        while True:
            # 判断是是否进入视频发布页面，没进入，则自动等待到超时
            try:
                text_exists = await page.get_by_text("添加视频").is_visible()
                if text_exists:
                    break
            except:
                toutiao_logger.info(f'  [-] 正在等待进入视频发布页面...')
                await asyncio.sleep(0.1)
                # try:
                #     await page.wait_for_url(
                #         "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page")
                #     break
                # except:
                #     toutiao_logger.info(f'  [-] 正在等待进入视频发布页面...')
                #     await asyncio.sleep(0.1)

        # 填充标题和话题
        # 检查是否存在包含输入框的元素
        # 这里为了避免页面变化，故使用相对位置定位：作品标题父级右侧第一个元素的input子元素
        await asyncio.sleep(1)
        # 点击"文本 生成图文"元素
        try:
            # 使用精确匹配定位"生成图文"按钮
            sctw = page.locator('span:text-is("生成图文")')
            await sctw.click()
            text_to_image_btn = await page.wait_for_selector('text="添加贴纸"')
            await text_to_image_btn.click()
            await asyncio.sleep(1)

            # 点击包含"关注引导"且有tabindex="-1"属性的元素
            follow_guide = await page.wait_for_selector('[tabindex="-1"]:has-text("关注引导")')
            await follow_guide.click()
            await asyncio.sleep(1)

            # 点击"智能添加"元素
            smart_add_btn = await page.wait_for_selector('text="智能添加"')
            await smart_add_btn.click()
            await asyncio.sleep(1)

            # 点击互动贴纸确定按钮
            confirm_btn = await page.locator("div:has-text('添加互动贴纸')").locator("..").locator("button:has-text('确定')").click()
            await asyncio.sleep(1)
        except Exception as e:
            toutiao_logger.info(f"添加互动贴纸相关操作失败: {e.__class__.__name__} - {str(e)}")
        toutiao_logger.info(f'  [-] 正在填充标题和话题...')
        title_container = page.get_by_text('标题').locator("..").locator("..").locator("input")

        if await title_container.count():
            await title_container.fill(self.title[:30])
        else:
            # titlecontainer = page.locator(".notranslate")
            await title_container.click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.title)
            await page.keyboard.press("Enter")
        tag_input = await page.wait_for_selector('input[placeholder="请输入"]')
        for index, tag in enumerate(self.tags, start=1):
            await tag_input.type("#" + tag)
            await page.wait_for_timeout(500)
            await tag_input.press("Space")
        toutiao_logger.info(f'总共添加{len(self.tags)}个话题')
        # 自行拍摄
        try:
            # 首先尝试直接定位包含"自行拍摄"文本的label元素
            checkbox_label = page.locator('label.byte-checkbox').filter(has_text="自行拍摄")
            await checkbox_label.click()

            # 如果上面的方法失败，尝试备用方案
            if await checkbox_label.count() == 0:
                # 尝试通过span文本定位
                await page.locator('span.byte-checkbox-inner-text:text("自行拍摄")').click()

        except Exception as e:
            toutiao_logger.error(f"点击自行拍摄选项时出错: {str(e)}")
            # 最后一个备用方案
            try:
                await page.evaluate('document.querySelector("label.byte-checkbox:text-is(\'自行拍摄\')").click()')
            except Exception as inner_e:
                toutiao_logger.error(f"所有尝试都失败了: {str(inner_e)}")
                raise inner_e

        while True:
            # 判断重新上传按钮是否存在，如果不存在，代表视频正在上传，则等待
            try:
                #  新版：定位重新上传
                number = await page.locator('span:text-is("上传成功")').count()
                if number > 0:
                    toutiao_logger.success("  [-]视频上传完毕")
                    break
                else:
                    toutiao_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)

                    if await page.locator('span:has-text("上传失败")').count():
                        toutiao_logger.error("  [-] 发现上传出错了... 准备重试")
                        await self.handle_upload_error(page)
            except Exception as e:
                if e.message == 'Locator.count: Target page, context or browser has been closed':
                    raise e  # 直接抛出异常
                toutiao_logger.error(e)
                toutiao_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

        # 上传视频封面
        await self.set_thumbnail(page, self.thumbnail_path)

        # 更换可见元素
        # await self.set_location(page, "杭州市")

        if self.publish_date != 0:
            await self.set_schedule_time_toutiao(page, self.publish_date)
        msg_res = '检测通过，暂未发现异常'
        # 判断视频启用成功
        while True:
            # 判断视频启用成功
            try:
                publish_button = page.locator('button span:text-is("发布")').first
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url("https://mp.toutiao.com/profile_v4/xigua/content-manage-v2**",
                                        timeout=3000)  # 如果自动跳转到作品页面，则代表发布成功
                toutiao_logger.success("  [-]视频发布成功")
                break
            except:
                toutiao_logger.info("  [-] 视频正在发布中...")
                await asyncio.sleep(0.5)

        await context.storage_state(path=self.account_file)  # 保存cookie
        toutiao_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()
        return True, msg_res

    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        # 点击上传封面按钮
        try:
            await page.click('text="上传封面"')
            if thumbnail_path and os.path.exists(thumbnail_path):
                await page.click('text="本地上传"')
                await asyncio.sleep(0.5)
                # 获取"本地上传"按钮的父元素的父元素下的文件输入框
                file_input = page.locator('text="本地上传"').locator('../..').locator('input[type="file"]')
                await file_input.set_input_files(thumbnail_path)

            # 等待上传完成
                await page.wait_for_selector('text="封面编辑"', timeout=10000)
                await page.wait_for_timeout(2000)  # 给图片加载一些时间

                # 点击确定按钮
                await page.locator("div:text-is('封面编辑')").locator("../..").locator("button:text-is('确定')").click()
                await page.wait_for_timeout(1000)

            else:
                await page.wait_for_timeout(2000)
                # 等待并点击可见的"下一步"按钮
                next_step_button = page.locator('text="下一步"')
                await self.click_wait_able(next_step_button, page,'cannot-click')

            # 检查并点击完成裁剪按钮
            try:
                finish_crop_btn = page.locator('div:text-is("完成裁剪")')
                if await finish_crop_btn.count() > 0:
                    await finish_crop_btn.wait_for(state='visible', timeout=5000)
                    await finish_crop_btn.click()
                    await page.wait_for_timeout(500)
            except Exception as e:
                toutiao_logger.warning(f"点击完成裁剪按钮时出错: {str(e)}")
                pass
            
            # 等待并点击确定按钮
            confirm_btn = page.locator('text="确定"')
            await self.click_wait_able(confirm_btn, page)
            # 处理可能出现的确认对话框
            confirm_dialog = page.locator('div:text-is("完成后无法继续编辑，是否确定完成？")')
            if await confirm_dialog.count() > 0:
                await confirm_dialog.locator("..").locator('button:text-is("确定")').click()

            toutiao_logger.info("封面上传成功")
        except Exception as e:
            toutiao_logger.error(f"封面上传失败: {str(e)}")
            # 可以选择是否要抛出异常
            raise e

    async def click_wait_able(self, next_step_button, page, disabled_class='disabled'):
        while True:
            # 直接获取class属性
            class_string = await next_step_button.get_attribute('class', timeout=1000)
            if class_string and disabled_class not in class_string:
                await next_step_button.click()
                await page.wait_for_timeout(500)
                break

    async def set_location(self, page: Page, location: str = "杭州市"):
        # todo supoort location later
        # await page.get_by_text('添加标签').locator("..").locator("..").locator("xpath=following-sibling::div").locator(
        #     "div.semi-select-single").nth(0).click()
        await page.locator('div.semi-select span:text-is("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
