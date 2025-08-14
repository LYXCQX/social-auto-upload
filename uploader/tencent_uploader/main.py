# -*- coding: utf-8 -*-
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
import re

import loguru
from config import PLATFORM
from config_manager import ConfigManager
from playwright.async_api import Playwright, async_playwright
from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.uploader.tencent_uploader.main_tz import delete_videos_by_conditions
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_TENCENT
from social_auto_upload.utils.bus_exception import UpdateError
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.log import tencent_logger

from social_auto_upload.uploader.tencent_uploader.main_tz import add_original

config = ConfigManager()
pub_config = json.loads(config.get(f'{PLATFORM}_pub_config', "{}")).get('tencent', {})


def format_str_for_short_title(origin_title: str) -> str:
    # 定义允许的特殊字符
    allowed_special_chars = "《》""+?%°"

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


async def cookie_auth(account_file, local_executable_path=None, un_close=False):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False if un_close else True,
                                                   executable_path=local_executable_path)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        try:
            await page.wait_for_selector('span:has-text("内容管理")', timeout=5000)  # 等待5秒
            tencent_logger.success("[+] cookie 有效")
            if un_close:
                # 如果不关闭浏览器，则进入循环等待页面关闭
                try:
                    # 等待页面关闭
                    await page.wait_for_event('close', timeout=0)  # 无限等待直到页面关闭
                except:
                    # 如果出现异常，可能是用户手动关闭了页面
                    pass
                finally:
                    try:
                        await context.close()
                        await browser.close()
                    except:
                        pass
            else:
                await context.close()
                await browser.close()
            return True
        except:
            tencent_logger.error("[+] 等待5秒 cookie 失效")
            return False


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
        try:
            # 设置页面标题为 local_executable_path 的文件名
            if account_file:
                file_name = os.path.basename(account_file)
                await page.evaluate(f'document.title = "{file_name}"')
        except:
            pass

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
        return user_id, user_name


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
    if not os.path.exists(account_file) or not await cookie_auth(account_file,
                                                                 local_executable_path=local_executable_path):
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
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, category=None,
                 local_executable_path=None, info=None, collection=None, declare_original=None, proxy_setting=None):
        self.title = title[:999]  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.category = category
        self.local_executable_path = local_executable_path if local_executable_path else LOCAL_CHROME_PATH
        self.info = info
        self.collection = collection
        self.declare_original = declare_original
        self.proxy_setting = proxy_setting

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
        await page.keyboard.type(f'{publish_date.hour}:{publish_date.minute}')

        # 选择标题栏（令定时时间生效）
        await page.locator("div.input-editor").click()

    async def handle_upload_error(self, page):
        tencent_logger.info("视频出错了，重新上传中")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator(pub_config.get('up_file'))
        await file_input.set_input_files(self.file_path)

    async def add_activity(self, page):
        if not self.info:
            return

        anchor_info = self.info.get("anchor_info", None)
        if not anchor_info:
            return

        # 获取展示剧名和搜索剧名
        display_name = anchor_info.get("display_name", None)
        search_name = anchor_info.get("search_name", None)

        # 如果没有设置专门的搜索剧名和展示剧名，则使用旧逻辑的剧名
        playlet_title = anchor_info.get("title", None)
        if not playlet_title:
            return

        # 优先使用搜索剧名进行搜索
        search_title = search_name if search_name else playlet_title
        # 优先使用展示剧名进行匹配
        match_title = display_name if display_name else playlet_title

        match_drama_name = anchor_info.get("match_drama_name", None)
        playlet_title_tag = anchor_info.get("playlet_title_tag", None)
        tencent_logger.info(f"开始添加活动: 搜索剧名[{search_title}] 展示剧名[{match_title}]")
        active_hd = pub_config.get('active_hd')
        # 等待包含"活动"标签的form-item出现
        await page.wait_for_selector(active_hd, state="visible", timeout=5000)
        form_item = page.locator(active_hd)

        # 查找并点击"不参与活动"按钮
        no_activity_span = form_item.locator("span:has-text('不参与活动'):visible")
        if await no_activity_span.is_visible():
            await no_activity_span.click()
            tencent_logger.info("已点击不参与活动")

        # 等待活动列表加载
        await page.wait_for_selector(f"{active_hd} .common-option-list-wrap", state="visible", timeout=5000)
        search_activity_input = form_item.locator('input[placeholder="搜索活动"]')
        # 使用搜索剧名填充活动搜索框
        await search_activity_input.fill(search_title)
        # 等待活动列表项出现
        start_time = time.time()
        while True:
            await search_activity_input.fill(search_title)
            activity_elements = await form_item.locator('.activity-item-info').all()
            if len(activity_elements) > 1:
                break
            if time.time() - start_time > 5:  # 5秒超时
                raise UpdateError(f"没有找到该短剧任务{search_title}")
            await asyncio.sleep(0.5)

        found = False

        for element in activity_elements:
            name = await element.locator('.name').text_content()
            if name == '不参与活动':
                continue
            creator_name = await element.locator('.creator-name').text_content()
            # 去除当前活动标题中的标点符号
            tencent_logger.info(f'已找到活动：{name}--需要匹配活动：{match_title}')

            # 提取书名号中的内容和推广前的内容
            book_title = re.search(r'《(.*?)》', name)
            promotion_title = re.search(r'》(.*?)推广', name)

            if book_title:
                book_content = book_title.group(1)
                promotion_content = promotion_title.group(1).strip()
                tencent_logger.info(f'提取的活动名称：书名号内容={book_content}, 推广前内容={promotion_content}')

                if match_drama_name:
                    have_platlet = match_title.strip() == book_content.strip()
                else:
                    have_platlet = match_title.strip() in book_content.strip()
            # else:
            # have_platlet = False
            if have_platlet:
                if playlet_title_tag:
                    if playlet_title_tag not in creator_name:
                        continue
                await element.click()
                tencent_logger.info(f"成功添加活动: {match_title}")
                found = True
                break

        if not found:
            raise UpdateError(f"没有找到 {playlet_title_tag}：剧场的短剧任务：{match_title}")

    async def upload(self, playwright: Playwright) -> tuple[bool, str]:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(
            headless=False,
            executable_path=self.local_executable_path,
            proxy=self.proxy_setting,
            args=['--mute-audio']  # 设置浏览器静音
        )
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(
            storage_state=f"{self.account_file}",
            viewport={'width': 1280, 'height': 720},
            no_viewport=False,
            bypass_csp=True
        )
        context = await set_init_script(context)
        msg_res = '检测通过，暂未发现异常'
        # 创建一个新的页面
        page = await context.new_page()
        # 动态获取屏幕尺寸
        screen_size = await page.evaluate("""() => ({
            width: window.screen.availWidth,
            height: window.screen.availHeight
        })""")

        await page.set_viewport_size(screen_size)
        old_title = self.title
        upload_count = 1
        if self.info and "video_upload_count" in self.info:
            upload_count = max(1, int(self.info.get("video_upload_count", 1)))  # 确保至少上传1次
            tencent_logger.info(f'[+]计划上传 {upload_count} 次 -------{self.title}.mp4')
        for i in range(upload_count):
            tencent_logger.info(f'[+]正在进行第 {i + 1}/{upload_count} 次上传 -------{self.title}.mp4')
            # 访问指定的 URL
            await page.goto("https://channels.weixin.qq.com/platform/post/create")
            tencent_logger.info(f'[+]正在上传-------{self.title}.mp4')
            # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
            await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create")
            # await page.wait_for_selector('input[type="file"]', timeout=10000)
            file_input = page.locator(pub_config.get('up_file'))
            await file_input.set_input_files(self.file_path)
            # 添加商品
            # await self.add_product(page)
            if self.info.get("enable_drama", False):
                # 添加活动
                if self.info.get("enable_baobai", False):
                    await self.add_short_play_by_baobai(page)
                else:
                    if 1 < upload_count != i + 1:
                        tencent_logger.info('，，，')
                    else:
                        await self.add_activity(page)
            else:
                tencent_logger.info('未选择挂短剧')
            try:
                await add_original(self, page)
            except:
                tencent_logger.exception('添加原创失败，不影响执行')
            should_delete = self.info and self.info.get("delete_platform_video", False) and (
                        upload_count == 1 or i < upload_count - 1)
            if should_delete:
                random_uuid = str(uuid.uuid4())[:5]
                self.title = f"waitdel-{random_uuid} {self.title}"
            else:
                self.title = old_title
            # 填充标题和话题
            await self.add_title_tags(page)
            await self.close_location(page)
            # 检测上传状态
            await self.detect_upload_status(page)
            if self.publish_date and self.publish_date != 0 and not should_delete:
                await self.set_schedule_time_tencent(page, self.publish_date)
            # 添加短标题
            # await self.add_short_title(page)
            try:
                # 合集功能
                await self.add_collection_with_create(page)
            except:
                tencent_logger.exception('添加合集失败，不影响执行')
            await self.click_publish(page)

            await context.storage_state(path=f"{self.account_file}")  # 保存cookie
            tencent_logger.success('  [-]cookie更新完毕！')
            if should_delete:
                await self.delete_video(page)
        if self.info and self.info.get("delete_after_play", False):
            await delete_videos_by_conditions(page, minutes_ago=self.info.get("delete_time_threshold", 1440), max_views=self.info.get("delete_play_threshold", 100),page_index=5)
            # await delete_videos_by_conditions(page, minutes_ago=180, max_views=100)
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()
        return True, msg_res

    async def close_location(self, page):
        if self.info and not self.info.get('location_enabled', False):
            # 循环尝试10秒
            start_time = time.time()
            success = False
            while time.time() - start_time < 10 and not success:
                try:
                    await page.wait_for_selector('.position-display', timeout=1000)
                    await page.click('.position-display-wrap')
                    await asyncio.sleep(0.5)
                    await page.click(':text-is("不显示位置")')
                    success = True
                    tencent_logger.info('成功关闭位置显示')
                    break
                except:
                    await asyncio.sleep(0.5)
                    continue
            if not success:
                tencent_logger.warning('关闭位置显示失败，继续执行')

    async def delete_video(self, page):
        # 检查是否需要删除视频
        if self.info and self.info.get("delete_platform_video", False):
            delete_delay = self.info.get("delete_delay")
            tencent_logger.info(f"[删除流程] 准备开始删除视频，等待 {delete_delay} 秒")
            await asyncio.sleep(delete_delay)

            try:
                is_first_time = False  # 标记是否使用第一个视频的时间
                start_time = time.time()  # 记录开始时间
                timeout = 20  # 20秒超时

                while True:  # 外层循环，直到找不到匹配的post_time为止
                    current_time = time.time()
                    elapsed = current_time - start_time
                    tencent_logger.info(f"[删除流程] 当前循环已运行 {elapsed:.2f} 秒")

                    # 检查是否超时
                    if elapsed > timeout:
                        tencent_logger.warning(f"[删除流程] 删除操作超过{timeout}秒，自动结束")
                        break

                    # 刷新页面
                    tencent_logger.info("[删除流程] 刷新页面")
                    await page.reload()
                    await asyncio.sleep(1)  # 等待页面加载
                    video_list = pub_config.get('video_list')
                    try:
                        tencent_logger.info("[删除流程] 等待视频列表加载")
                        await page.wait_for_selector(video_list, timeout=10000)
                    except Exception as e:
                        tencent_logger.error(f"[删除流程] 等待视频列表加载超时，未找到 post-feed-item 元素: {str(e)}")
                        return

                    found_video = False
                    # 获取所有视频项
                    feed_items = await page.locator(video_list).all()
                    if not feed_items:
                        tencent_logger.warning("[删除流程] 未找到任何视频项")
                        break

                    feed_count = len(feed_items)
                    tencent_logger.info(f"[删除流程] 找到 {feed_count} 个视频项")

                    # 检查所有项是否都包含effective-time
                    all_have_effective_time = True
                    # 遍历所有视频项
                    for index, item in enumerate(feed_items):
                        try:
                            effective_time = await item.locator('.effective-time').count()
                            tencent_logger.info(f"[删除流程] 检查有效时间: {effective_time}")
                            if effective_time == 0:
                                all_have_effective_time = False
                            item_title = item.locator('.post-title')
                            if await item_title.count() > 0:
                                title_text = await item_title.text_content()
                                if title_text.startswith('waitdel-'):
                                    # 执行删除
                                    delete_button = item.locator('text=删除')
                                    if await delete_button.count() > 0:
                                        tencent_logger.info(f"[删除流程] 找到删除按钮，准备删除视频")
                                        await delete_button.locator('..').locator('.opr-item').evaluate(
                                            'el => el.click()')
                                        await page.click(':text-is("确定")')
                                        found_video = True
                                        is_first_time = True
                                        await asyncio.sleep(2)
                                        # break
                        except Exception as e:
                            tencent_logger.exception(f"[删除流程] 处理视频项时出错：{str(e)}")
                            continue
                    if all_have_effective_time:
                        tencent_logger.info("[删除流程] 所有视频项都包含effective-time，调用批量删除方法")
                        await delete_videos_by_conditions(page, 0, 10, page_index=5, video_title='waitdel-')
                    # 如果没有找到匹配的视频，说明删除完成
                    if not found_video:
                        if is_first_time:
                            tencent_logger.info(f"[删除流程] 未找到title为 {self.title} 的视频，删除操作完成")
                        else:
                            tencent_logger.warning(f"[删除流程] 未找到要删除的视频")
                        break

            except Exception as e:
                tencent_logger.exception(f"[删除流程] 删除视频时出错：{str(e)}")

    async def add_short_play_by_baobai(self, page):
        # 等待并点击"选择链接"按钮
        baobai_lj = pub_config.get('baobai_lj')
        await page.wait_for_selector(baobai_lj, state='visible', timeout=5000)
        await page.click(baobai_lj)
        # 等待并点击"短剧"选项，使用精确匹配
        await page.wait_for_selector(':text-is("短剧"), :text-is("小程序短剧")', state='visible', timeout=5000)
        await page.click(':text-is("短剧"), :text-is("小程序短剧")')
        # 等待并点击"选择需要添加的短剧"按钮
        await page.wait_for_selector(':text-is("选择需要添加的短剧")', state='visible', timeout=5000)
        await page.click(':text-is("选择需要添加的短剧")')
        # 等待输入框出现
        await page.wait_for_selector('input[placeholder="请输入短剧名称"]', state='visible', timeout=5000)
        await page.click('input[placeholder="请输入短剧名称"]')
        anchor_info = self.info.get("anchor_info", None)
        if not anchor_info:
            raise UpdateError(f"未找到挂短剧参数：{anchor_info}")

        # 获取展示剧名和搜索剧名
        display_name = anchor_info.get("display_name", None)
        search_name = anchor_info.get("search_name", None)

        # 如果没有设置专门的搜索剧名和展示剧名，则使用旧逻辑的剧名
        playlet_title = anchor_info.get("title", None)
        if not playlet_title:
            raise UpdateError(f"未找到挂短剧参数：{playlet_title}")

        # 优先使用搜索剧名进行搜索
        search_title = search_name if search_name else playlet_title
        # 优先使用展示剧名进行匹配
        match_title = display_name if display_name else playlet_title
        jishu = anchor_info.get("jishu", None)
        tencent_logger.info(f"开始添加短剧: 搜索剧名[{search_title}] 展示剧名[{match_title}]")

        # 填充短剧名称
        # 设置开始时间和超时时间
        start_time = time.time()
        timeout = 20  # 20秒超时
        found = False
        retry_count = 0
        page_index = 1
        match_drama_name = anchor_info.get("match_drama_name", None)
        search_activity_input = page.locator('input[placeholder="请输入短剧名称"]')
        await search_activity_input.fill(search_title)
        while time.time() - start_time < timeout:
            try:
                if page_index == 1:
                    # await search_activity_input.clear()
                    await search_activity_input.fill(search_title)
                    await asyncio.sleep(2)
                await page.wait_for_selector('.drama-title', timeout=5000)

                # 直接获取所有非禁用短剧项中的标题元素
                drama_text_elements = await page.locator('.drama-item:not(.drama-item--disabled) .drama-text').all()

                # 遍历所有短剧标题元素
                for text_element in drama_text_elements:
                    title_element = text_element.locator('.drama-title')
                    extinfo = await text_element.locator('.extinfo').text_content()
                    # 获取标题文本
                    text_content = await title_element.text_content()
                    tencent_logger.info(f'找到短剧标题：{text_content}')

                    # 检查标题是否匹配
                    if not jishu or (jishu and str(jishu) in extinfo):
                        if match_drama_name:
                            have_platlet = match_title == text_content
                        else:
                            have_platlet = match_title in text_content
                    else:
                        have_platlet = False
                    if have_platlet:
                        await title_element.evaluate('el => el.click()')
                        tencent_logger.info(f'点击了匹配【{match_title}】的{jishu}短剧')
                        found = True
                        break

                if found:
                    break

                retry_count += 1

                # 如果循环3次还没找到，尝试翻页
                if retry_count >= 3:
                    # 查找下一页按钮
                    next_page = page.locator('a:has-text("下一页")')
                    if await next_page.count() > 0 and await next_page.is_visible():
                        tencent_logger.info('当前页未找到，点击下一页继续查找')
                        await next_page.click()
                        # 重置重试计数
                        retry_count = 0
                        page_index += 1
                        # 等待页面加载
                        await asyncio.sleep(1)

                tencent_logger.info('未找到匹配元素，等待0.5秒后重试...')
                await asyncio.sleep(0.5)

            except Exception as e:
                tencent_logger.exception(f'查找高亮元素时发生错误')
                await asyncio.sleep(0.5)
                continue

        if not found:
            tencent_logger.error(f'超时{timeout}秒，未找到匹配【{match_title}】的短剧')
            raise UpdateError(f"未找到匹配的短剧：{match_title}")

    # async def add_short_title(self, page):
    #     short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
    #         "xpath=following-sibling::div").locator(
    #         'span input[type="text"]')
    #     if await short_title_element.count():
    #         short_title = format_str_for_short_title(self.title)
    #         await short_title_element.fill(short_title)

    async def click_publish(self, page):
        start_time = time.time()
        timeout = 120  # 两分钟超时
        while True:
            try:
                # 检查是否超时
                if time.time() - start_time > timeout:
                    tencent_logger.warning("  [-] 发布操作超过两分钟，强制结束")
                    raise UpdateError(f"发布操作超过两分钟，强制结束{self.file_path}")

                await asyncio.sleep(10)
                tencent_logger.info("  [-] 开始检查编辑保留提示框...")

                # 检查是否出现"将此次编辑保留?"文本
                has_edit_retain = await page.locator('div:has-text("将此次编辑保留?")').count() > 0
                tencent_logger.info(f"  [-] 是否找到编辑保留提示框: {has_edit_retain}")

                if has_edit_retain:
                    # 查找并点击"不保存"按钮，直接校验可见性
                    no_save_button = page.locator('button:has-text("不保存"):visible')
                    has_no_save_button = await no_save_button.count() > 0
                    tencent_logger.info(f"  [-] 是否找到可见的不保存按钮: {has_no_save_button}")

                    if has_no_save_button:
                        await no_save_button.click()
                        await page.goto('https://channels.weixin.qq.com/platform/post/list')
                        tencent_logger.info("  [-] 已点击不保存按钮")
                        break
                    else:
                        tencent_logger.warning("  [-] 未找到可见的不保存按钮")

                tencent_logger.info("  [-] 尝试点击发布按钮...")
                up_button = pub_config.get('up_button')
                publish_buttion = page.locator(up_button)
                if await publish_buttion.count():
                    await publish_buttion.click()
                    tencent_logger.info("  [-] 已点击发布按钮")
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=1500)
                tencent_logger.success("  [-]视频发布成功")
                break
            except UpdateError as e:
                raise e
            except Exception as e:
                if 'Target page, context or browser has been closed' in e.message:
                    raise e  # 直接抛出异常
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
                tencent_logger.exception('上传中...')
                if 'Target page, context or browser has been closed' in e.message:
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
        try:
            await page.wait_for_selector('.create-dialog-success-wrap button:has-text("我知道了")', state="visible",
                                         timeout=5000)
            # 等待"我知道了"按钮可点击
            await page.locator('.create-dialog-success-wrap button:has-text("我知道了")').click()
        except:
            try:
                tencent_logger.exception('我知道了，没找到')
                ycz = page.locator('div:text("此标题与现有合集重复，请修改标题后再试")')
                if await ycz.count() > 0:
                    qx = page.locator('button:text("取消")')
                    if await qx.count() > 0:
                        await qx.click()
            except:
                pass
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

        await page.click(':text-is("选择合集")')

        # 等待合集列表容器可见
        try:
            await page.wait_for_selector('.option-list-wrap', state="visible", timeout=5000)
        except:
            pass

        # 等待合集列表加载完成
        start_time = time.time()
        while True:
            collection_elements = await page.locator('.option-list-wrap').locator(
                '.option-item .item:not(:has-text("创建新合集"))').all()
            if len(collection_elements) > 0:
                break
            if time.time() - start_time > 5:  # 5秒超时
                tencent_logger.warning("等待合集列表加载超时")
                return False
            await asyncio.sleep(0.5)

        found = False
        last_count = 0

        while not found:
            # 获取当前所有合集元素
            collection_elements = await page.locator('.option-list-wrap').locator(
                '.option-item .item:not(:has-text("创建新合集"))').all()
            current_count = len(collection_elements)
            tencent_logger.info(f'当前找到 {current_count} 个合集')

            # 如果数量没有增加,说明已经到底了
            if current_count == last_count:
                tencent_logger.info('合集数量未增加，可能已到底部')
                break

            # 查找匹配的合集
            for element in collection_elements:
                text = await element.locator('.name').text_content()
                tencent_logger.info(f'找到合集：{text} 需要选择合集：{self.collection}')
                if text.strip() == self.collection:
                    # 使用JavaScript来执行点击操作
                    await element.evaluate('el => el.click()')
                    tencent_logger.info(f"成功选择合集: {self.collection}")
                    found = True
                    break

            if found:
                break

            # 记录当前数量
            last_count = current_count

            try:
                # 使用Playwright定位器找到滚动容器
                scroll_container = page.locator('div.common-option-list-wrap.option-list-wrap')
                if await scroll_container.count() > 0:
                    # 获取滚动容器的位置和尺寸
                    box = await scroll_container.bounding_box()
                    if box:
                        tencent_logger.info(f'找到滚动容器，位置: {box}')
                        # 先滚动到底部
                        await page.evaluate('''(container) => {
                            if (container) {
                                const prevHeight = container.scrollHeight;
                                container.scrollTop = prevHeight;
                                return { success: true, prevHeight: prevHeight };
                            }
                            return { success: false };
                        }''', await scroll_container.element_handle())
                        tencent_logger.info('已执行滚动到底部操作')

                        # 等待一下让内容加载
                        await asyncio.sleep(0.5)

                        # 先向上滚动一段距离
                        await page.evaluate('''(container) => {
                            if (container) {
                                const currentScrollTop = container.scrollTop;
                                // 向上滚动约1/3的容器高度
                                container.scrollTop = Math.max(0, currentScrollTop - container.clientHeight / 3);
                                return { success: true, scrolledTo: container.scrollTop };
                            }
                            return { success: false };
                        }''', await scroll_container.element_handle())
                        tencent_logger.info('已执行向上滚动操作')

                        # 再次等待
                        await asyncio.sleep(0.3)

                        # 再次滚动到底部以触发更新
                        await page.evaluate('''(container) => {
                            if (container) {
                                const prevHeight = container.scrollHeight;
                                container.scrollTop = prevHeight;
                                return {
                                    success: true,
                                    prevHeight: prevHeight,
                                    newScrollTop: container.scrollTop,
                                    clientHeight: container.clientHeight,
                                    scrollHeight: container.scrollHeight
                                };
                            }
                            return { success: false };
                        }''', await scroll_container.element_handle())
                        tencent_logger.info('已再次执行滚动到底部操作')
                    else:
                        tencent_logger.warning('找到滚动容器但无法获取位置信息')
                else:
                    tencent_logger.warning('未找到滚动容器')
            except Exception as e:
                tencent_logger.exception(f'滚动操作出错: {str(e)}')

            # 等待新内容加载
            await asyncio.sleep(1)

        return found


    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)

# def normalize_post_time(post_time: str) -> str:
#     """标准化发布时间格式，便于比较"""
#     tencent_logger.debug(f"开始标准化时间: {post_time}")
#     # 移除可能存在的空格
#     post_time = post_time.strip()
#     # 统一年月日时间格式
#     post_time = post_time.replace('年', '-').replace('月', '-').replace('日', '')
#     # 如果时间包含空格（日期和时间之间），保留空格
#     tencent_logger.debug(f"标准化后的时间: {post_time}")
#     return post_time
