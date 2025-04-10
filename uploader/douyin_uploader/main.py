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

from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_DOUYIN
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.log import douyin_logger

from social_auto_upload.uploader.douyin_uploader.juliang_util import xt_have_task

from social_auto_upload.utils.bus_exception import UpdateError,BusError


load_dotenv()
# 从环境变量中获取检测失败的内容列表
failure_messages_json = os.getenv('FAILURE_MESSAGES', '[]')
failure_messages = json.loads(failure_messages_json)


async def cookie_auth(account_file, local_executable_path=None,un_close=False):
    if not local_executable_path or not os.path.exists(local_executable_path):
        douyin_logger.warning(f"浏览器路径无效: {local_executable_path}")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False if un_close else True,
                                                   executable_path=local_executable_path)
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


async def douyin_setup(account_file, handle=False, local_executable_path=None):
    if not os.path.exists(account_file) or not await cookie_auth(account_file,local_executable_path):
        if not handle:
            # Todo alert message
            return False, None, None, None
        douyin_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        user_id, user_name, response_data = await douyin_cookie_gen(account_file,local_executable_path)
    else:
        # 新增：从 account_file 的文件名中提取用户 id 和 name
        base_name = os.path.basename(account_file)
        user_id, user_name = base_name.split('_')[:2]  # 假设文件名格式为 "user_id_user_name_account.json"

    return True, user_id, user_name, None


async def get_user_id(page):
    start_time = time.time()  # 获取开始时间
    while True:
        user_id = await page.locator('[class^="unique_id-"]:has-text("抖音号：")').text_content()
        user_id = user_id.replace("抖音号：", "").strip()
        if user_id == '0':
            current_time = time.time()  # 获取当前时间
            elapsed_time = current_time - start_time  # 计算已经过去的时间
            if elapsed_time > 10:  # 如果已经过去的时间超过5秒
                break  # 退出循环
        else:
            break  # 退出循环
    return user_id


async def douyin_cookie_gen(account_file,local_executable_path=None):
    async with async_playwright() as playwright:
        # Make sure to run headed.
        browser = await playwright.chromium.launch(headless=False,
                                                   executable_path=local_executable_path)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        try:
            # 设置页面标题为 local_executable_path 的文件名
            if account_file:
                file_name = os.path.basename(account_file)
                await page.evaluate(f'document.title = "{file_name}"')
        except:
            pass
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
        user_name = await page.locator('[class^="header-"] [class^="name-"]').text_content()
        loguru.logger.info(f'{user_id}---{user_name}')
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=get_account_file(user_id, SOCIAL_MEDIA_DOUYIN, user_name))
        response_data = None

        async def handle_route(route):
            nonlocal response_data
            url = route.request.url
            if "web/general/search/single" in url:  # 更精确的URL匹配
                # 获取请求头中的cookie
                headers = route.request.headers
                response_data = headers.get('cookie', '')
                loguru.logger.info(f"获取到cookie: {response_data}")  # 添加日志
            await route.continue_()
        await context.close()
        await browser.close()
        return user_id, user_name, response_data



class DouYinVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None, goods=None,
                 check_video=False, info=None, collection=None,local_executable_path =None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = local_executable_path if local_executable_path else LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.goods = goods
        self.check_video = check_video
        self.info = info
        self.collection = collection

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
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        if self.info and self.info.get("anchor_info", None) and self.info.get("enable_drama", False):
            anchor_info = self.info.get("anchor_info", None)
            playlet_title = anchor_info.get("title", None)
            playlet_title_tag = anchor_info.get("title_tag", None)
            auto_order = self.info.get("auto_order", None)
            if self.info.get('use_xt'):
                try:
                    # 创建一个浏览器上下文，使用指定的 cookie 文件
                    have_task, page = await xt_have_task(page, playlet_title)
                    if not have_task:
                        if auto_order:
                            douyin_logger.info('[+] 检测到不在上传页面，需要新建任务')
                            have_task, page, n_url = await self.new_xt_task(page, playlet_title)
                        else:
                            douyin_logger.info('[+] 没有找到任务，也没有开启自动接单，直接返回')
                            raise UpdateError(f"没有找到任务标签:{playlet_title}，也没有开启自动接单，请先接取任务")
                    else:
                        douyin_logger.info('[+] 已经存在任务，继续处理')
                    have_task, page, n_url = await self.click_go_to_upload(have_task, page)
                finally:
                    await context.storage_state(path=self.account_file)  # 保存cookie
                    douyin_logger.success('  星图cookie更新完毕！')
            else:
                if playlet_title:
                    have_task, page, n_url = await self.check_have_task(page, playlet_title, playlet_title_tag)
                    if not have_task:
                        if auto_order:
                            douyin_logger.info('[+] 检测到不在上传页面，需要新建任务')
                            page = await self.new_task(page, playlet_title, playlet_title_tag)
                        else:
                            douyin_logger.info('[+] 没有找到任务，也没有开启自动接单，直接返回')
                            raise UpdateError(f"没有找到任务标签:{playlet_title}，也没有开启自动接单，请先接取任务")
                    else:
                        douyin_logger.info('[+] 已经存在任务，继续处理')
        else:
            # 访问指定的 URL
            await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        douyin_logger.info(f'[+]正在上传-------{self.title}.mp4')
        # 等待页面跳转到指定的 URL，进入，则自动等待到超时
        douyin_logger.info(f'[-] 正在打开主页...')
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload*")
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

        # 等待页面跳转到指定的 URL 2025.01.08修改在原有基础上兼容两种页面
        while True:
            try:
                # 尝试等待第一个 URL
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish*", timeout=3)
                douyin_logger.info("[+] 成功进入version_1发布页面!")
                break  # 成功进入页面后跳出循环
            except Exception:
                try:
                    # 如果第一个 URL 超时，再尝试等待第二个 URL
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/post/video*",
                        timeout=3)
                    douyin_logger.info("[+] 成功进入version_2发布页面!")

                    break  # 成功进入页面后跳出循环
                except:
                    print("  [-] 超时未进入视频发布页面，重新尝试...")
                    await asyncio.sleep(0.5)  # 等待 0.5 秒后重新尝试
        # 填充标题和话题
        await self.fill_title_and_tags(page)
        allow_download = page.locator('.download-content-Lci5tL label:has-text("不允许")')
        if await allow_download.count() > 0:
            await allow_download.click()
        # 添加商品
        await self.add_goods(page)
        await self.set_collection(page)
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
        # await self.set_thumbnail(page, self.thumbnail_path)

        # 更换可见元素
        # await self.set_location(page, "杭州市")

        # 頭條/西瓜
        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        # 定位是否有第三方平台
        if await page.locator(third_part_element).count():
            # 检测是否是已选中状态
            if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
                await page.locator(third_part_element).locator('input.semi-switch-native-control').click()

        if self.publish_date and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)
        msg_res = '检测通过，暂未发现异常'
        # 判断视频启用成功
        while True:
            # 判断视频启用成功
            try:
                publish_button = page.get_by_role('button', name="发布", exact=True)
                if await publish_button.count():
                    start_time = time.time()
                    if self.check_video:
                        while True:
                            try:
                                if await page.locator('p.progressingContent-QEbwRE:has-text("视频检测中")').count() > 0:
                                    douyin_logger.info("  [-] 视频检测中...")
                                    await asyncio.sleep(2)
                                # 获取视频检测状态
                                if (await page.locator('div:has-text("作品未见异常")').count() > 0 or
                                        await page.locator('div:has-text("仅支持检测5分钟以内的视频")').count() > 0):
                                    break
                                elif await page.locator(
                                        'section.contentWrapper-j5kIqC').count() > 0 or await page.locator(
                                    'div.detectItemTitle-X5pTL9').count() > 0:
                                    j5kIqC = await page.query_selector('section.contentWrapper-j5kIqC')
                                    if j5kIqC:
                                        msg_res = await page.locator('section.contentWrapper-j5kIqC').text_content()
                                    X5pTL9 = await page.query_selector('div.detectItemTitle-X5pTL9')
                                    if X5pTL9:
                                        msg_res = await page.locator('div.detectItemTitle-X5pTL9').text_content()
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

    async def new_xt_task(self, page, playlet_title):
        await page.goto("https://www.xingtu.cn/sup/creator/market?type=submission")
        await page.wait_for_url("https://www.xingtu.cn/sup/creator/market*")
        await self.xt_click_plate(page, playlet_title)
        page = await self.click_tougao(page)
        return await self.click_go_to_upload(True, page)


    async def xt_click_plate(self, page, playlet_title):
        # 等待并点击行业标签
        await page.wait_for_selector('span:text("行业：")', timeout=10000)
        await page.locator('span:text("行业：")').click()
        
        # 选择短剧选项
        await page.wait_for_selector('.xt-cascader-panel input', state='visible')
        await page.locator('.xt-cascader-panel input').fill('短剧')
        await page.wait_for_selector('.xt-cascader-panel .xt-option__content')
        await page.locator('.xt-cascader-panel .xt-option__content').first.click()
        
        search_input = page.locator('input[placeholder="请输入任务名称/ID"]')
        await search_input.fill(playlet_title)
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(2000)  # 等待搜索结果加载
        
        # 查找所有百分比元素
        percent_elements = page.locator('.content .task-list .author-market-task-card')
        # 打印每个元素的HTML内容
        for i in range(await percent_elements.count()):
            element_html = await percent_elements.nth(i).evaluate('element => element.outerHTML')
            douyin_logger.info(f"任务卡片 {i + 1} HTML: {element_html}")
        percent_count = await percent_elements.count()
        if percent_count > 0:
            max_card = None
            max_amount = 0
            # 遍历所有任务卡片
            for i in range(percent_count):
                card = percent_elements.nth(i)
                douyin_logger.info(f"任务卡片 HTML: {await card.evaluate('element => element.outerHTML')}")
                try:
                    # 方式一：累加所有 .rate 的值
                    rates = card.locator('.rate')
                    douyin_logger.info(f"任务卡片 HTML: {await rates.evaluate('element => element.outerHTML')}")
                    total_rate = 0
                    rate_count = await rates.count()
                    for j in range(rate_count):
                        rate_text = await rates.nth(j).text_content()
                        rate_value = float(rate_text.strip('%'))
                        total_rate += rate_value
                        
                    if total_rate > max_amount:
                        max_amount = total_rate
                        max_card = card
                except:
                    try:
                        # 方式二：查找总奖金金额
                        price_element = card.locator('.price-number')
                        if await price_element.count() > 0:
                            price_text = await price_element.text_content()
                            price_value = float(price_text)
                            if price_value > max_amount:
                                max_amount = price_value
                                max_card = card
                    except:
                        continue
            print(f'最大佣金为{max_amount}')
            print(max_amount > 0)
            if max_card:
                print(f'最大佣金为{max_amount}')
                # 点击最大金额对应的任务卡片
                douyin_logger.info(f"任务卡片 HTML: {await max_card.evaluate('element => element.outerHTML')}")
                await max_card.locator('button:has-text("我要投稿"):visible').click()
                douyin_logger.info(f'[+] 选择了最高金额的任务: {max_amount}')
                return
                
        # 如果上面的方式都没找到，尝试直接查找"我要投稿"按钮
        # submit_button = page.locator('span:text("我要投稿")')
        # if await submit_button.count() > 0:
        #     await submit_button.click()
        #     douyin_logger.info('[+] 直接点击了"我要投稿"按钮')
        #     return
            
        raise UpdateError(f"没有找到任务标签:{playlet_title}，可能还没接取该任务，请先接取任务")

    async def click_button_with_timeout(self, page, selector, button_name, parent_dom=None, timeout=30, force_click=False):
        """带超时的按钮点击
        Args:
            page: playwright page对象
            selector: 按钮选择器
            button_name: 按钮名称(用于日志)
            timeout: 超时时间(秒)
        Returns:
            bool: 是否点击成功
            :param force_click:
            :param timeout:
            :param button_name:
            :param page:
            :param selector:
            :param parent_dom:
        """
        start_time = time.time()
        while True:
            try:
                if parent_dom:
                    button = parent_dom.locator(selector)
                else:
                    button = page.locator(selector)
                if await button.count() > 0:
                    if force_click:
                        await button.evaluate('el => el.click()')
                    else:
                        await button.click()
                    douyin_logger.info(f'[+] 点击了{button_name}按钮')
                    return True

                if time.time() - start_time > timeout:
                    douyin_logger.error(f'[!] 等待{button_name}按钮超时')
                    return False

                await asyncio.sleep(1)

            except Exception as e:
                douyin_logger.error(f'[!] 点击{button_name}按钮失败: {str(e)}')
                return False

    async def wait_for_clickable(self, page, selector, timeout=30):
        """等待元素可点击
        Args:
            page: playwright page对象
            selector: 元素选择器
            timeout: 超时时间(秒)
        Returns:
            element: 可点击的元素，如果超时返回None
        """
        start_time = time.time()
        while True:
            try:
                element = page.locator(selector)
                if await element.count() > 0:
                    # 检查元素是否可见且可点击
                    is_visible = await element.is_visible()

                    if is_visible:
                        return element

                if time.time() - start_time > timeout:
                    douyin_logger.error(f'[!] 等待元素可点击超时: {selector}')
                    return None

                await asyncio.sleep(0.5)

            except Exception as e:
                douyin_logger.error(f'[!] 等待元素可点击出错: {str(e)}')
                return None

    async def new_task(self, page, playlet_title, playlet_title_tag):
        await page.goto("https://creator.douyin.com/creator-micro/revenue/market")
        await page.wait_for_selector('.wrapper-hAV6HZ, .wrapper-DizYsD', state='visible', timeout=10000)  # 等待最多 10 秒
        # 找到搜索框并输入任务名称
        search_input = page.locator('input[placeholder="请输入任务名称/任务ID"]')
        await search_input.fill(playlet_title)
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(2000)  # 等待搜索结果加载
        await self.click_playlet_video(page, playlet_title_tag, new_task=True)
        return await self.click_tougao(page)

    # 点击投稿
    async def click_tougao(self, page):
        page = await page.wait_for_event('popup')
        await page.wait_for_selector('span:text("我要投稿")', state='visible', timeout=10000)  # 等待按钮可见
        await self.get_title_tag(page)
        print('开始投稿了')
        # 点击"我要投稿"按钮
        start_time = time.time()
        while True:
            submit_button = page.locator('span:text("我要投稿")')
            if await submit_button.count() > 0:
                await submit_button.click()
                await page.wait_for_timeout(1000)
                confirm_box = page.locator('.el-message-box__btns')
                if await confirm_box.count() > 0:
                    break
            if time.time() - start_time > 10:
                douyin_logger.error(f'[!] 等待元素可点击超时:我要投稿')
                raise BusError(f"未找到投稿按钮，下次再试")
            # 等待并处理确认弹窗
        if await confirm_box.count() > 0:
            await self.click_button_with_timeout(page, 'span:text("确定")', "确定", confirm_box)
            douyin_logger.info('[+] 点击了确认弹窗的确定按钮')

            async with page.expect_popup() as popup_info:
                await self.click_button_with_timeout(page, selector='span:has-text("上传视频")', button_name="上传视频",force_click=True)
            douyin_logger.info('[+] 点击了上传视频按钮')
            page = await popup_info.value
            return page
        else:
            # 检查是否存在 el-dialog__body 元素
            dialog_body = page.locator('.el-dialog__body')
            # 等待 el-dialog__body 元素出现
            if await dialog_body.count() > 0:  # 检查元素是否存在
                # 获取并打印内容
                dialog_content = await dialog_body.evaluate('el => el.textContent')
                raise UpdateError(f"暂不满足参与条件：{dialog_content}")

    async def check_have_task(self, page, playlet_title, playlet_title_tag):
        await page.goto("https://creator.douyin.com/creator-micro/revenue/tasks")
        # 点击"进行中"标签
        await page.wait_for_selector('a:has-text("进行中")', timeout=10000)  # 等待最多 10 秒
        await page.locator('a:has-text("进行中")').click()
        douyin_logger.info('[+] 点击了进行中标签')
        await page.wait_for_timeout(1000)  # 等待页面加载
        # 点击"客户"标签
        customer_labels = await page.locator('span:text("客户")').element_handles()  # 获取所有客户标签的元素句柄
        for label in customer_labels:
            await label.click()  # 点击每个客户标签
            douyin_logger.info(f'[+] 点击了客户标签: {await label.text_content()}')  # 打印被点击的客户标签文本
            await page.wait_for_timeout(1000)
        # 点击"任务名称"标签
        task_name_tab = page.locator('div:text("任务名称")')
        await task_name_tab.click()
        douyin_logger.info('[+] 点击了任务名称标签')
        await page.wait_for_timeout(1000)  # 等待页面加载
        # 在进行中页面输入任务名称
        task_search = page.locator('input[placeholder="请输入任务名称"]')
        await task_search.fill(playlet_title)
        await page.keyboard.press('Enter')
        douyin_logger.info(f'[+] 在进行中页面搜索任务: {playlet_title}')
        await page.wait_for_timeout(2000)  # 等待搜索结果加载
        have_task = await self.click_playlet_video(page, playlet_title_tag, new_task=False)
        return await self.click_go_to_upload(have_task, page)

    async def click_go_to_upload(self, have_task, page):
        if have_task:
            # 点击"查看任务详情"按钮
            detail_button = page.locator('span:has-text("查看任务详情")')
            await detail_button.click()
            douyin_logger.info('[+] 点击了查看任务详情按钮')
            await page.wait_for_timeout(2000)  # 等待详情页面加载
            await self.get_title_tag(page)
            # 点击"上传视频"按钮
            upload_button = page.locator('span:has-text("上传视频")')
            if await upload_button.count() > 0:
                # await upload_button.click(force=True)
                async with page.expect_popup() as popup_info:
                    await upload_button.evaluate('el => el.click()')  # 使用 JavaScript 强制点击
                douyin_logger.info('[+] 点击了上传视频按钮')
                page = await popup_info.value
            else:
                if await page.get_by_text('达人已取消任务').count() > 0:
                    return False, page, page.url
        return have_task, page, page.url

    async def get_title_tag(self, page):
        # 等待硬性要求标签出现
        await page.wait_for_timeout(1000)
        hard_req_element = page.locator('text="硬性要求"')
        if await hard_req_element.count() > 0:
            # 获取硬性要求的内容
            hard_req_content = await hard_req_element.locator("..").text_content()
            # 找到第一个#的位置
            hash_index = hard_req_content.find('#')
            if hash_index != -1:
                # 获取从第一个#到最后的内容作为标题
                self.title = f"{hard_req_content[hash_index:]} {self.title}"
                douyin_logger.info(f'[+] 从硬性要求中获取到标题: {self.title}')
            else:
                douyin_logger.info("没有找到硬性要求标签")
        else:
            douyin_logger.info("-没有找到硬性要求标签")

    async def click_playlet_video(self, page, playlet_title_tag, new_task=False):
        # 如果有标签,点击对应标签
        if playlet_title_tag:
            tag_element = page.locator(f'text="{playlet_title_tag}"')
            if await tag_element.count() > 0:
                await tag_element.click()
        else:
            # 查找所有百分比元素
            percent_elements = page.locator('.percent-bdUwB0')
            percent_count = await percent_elements.count()

            if percent_count > 0:
                max_percent = 0
                max_index = 0

                # 遍历所有百分比元素找出最大值
                for i in range(percent_count):
                    percent_text = await percent_elements.nth(i).text_content()
                    percent_value = float(percent_text.strip('%'))
                    if percent_value > max_percent:
                        max_percent = percent_value
                        max_index = i

                # 点击最大百分比对应的标签
                await percent_elements.nth(max_index).click()
                douyin_logger.info(f'[+] 选择了最高百分比的标签: {max_percent}%')
            else:
                if new_task:
                    raise UpdateError(f"没有找到任务标签:{playlet_title_tag}，可能还没接取该任务，请先接取任务")
                else:
                    return False
        return True

    async def add_goods(self, page):
        if self.goods:
            await page.click('text="位置"')
            await page.click('text="购物车"')
            await page.locator('input[placeholder="粘贴商品链接"]').fill(self.goods.itemLinkUrl)
            await page.click('text="添加链接"')
            await page.locator('input[placeholder="请输入商品短标题"]').fill(self.goods.itemTitle)
            await page.click('text="完成编辑"')

    # async def set_thumbnail(self, page: Page, thumbnail_path: str):
    #     if thumbnail_path:
    #         await page.click('text="选择封面"')
    #         await page.wait_for_selector("div.semi-modal-content:visible")
    #         await page.click('text="设置竖封面"')
    #         await page.wait_for_timeout(2000)  # 等待2秒
    #         # 定位到上传区域并点击
    #         # await (page.locator("div[class^='semi-upload upload'] >> input.semi-upload-hidden-input").set_input_files(thumbnail_path))
    #         await page.set_input_files('.semi-upload-hidden-input', thumbnail_path)
    #         await page.wait_for_timeout(2000)  # 等待2秒
    #         await page.locator("div[class^='extractFooter'] button:visible:has-text('完成')").click()
    # async def set_location(self, page: Page, location: str = "杭州市"):
    #     # todo supoort location later
    #     # await page.get_by_text('添加标签').locator("..").locator("..").locator("xpath=following-sibling::div").locator(
    #     #     "div.semi-select-single").nth(0).click()
    #     await page.locator('div.semi-select span:has-text("输入地理位置")').click()
    #     await page.keyboard.press("Backspace")
    #     await page.wait_for_timeout(2000)
    #     await page.keyboard.type(location)
    #     await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
    #     await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def set_collection(self, page):
        """设置视频合集"""
        try:
            if not self.collection:
                return

            douyin_logger.info(f'[+] 开始设置合集: {self.collection}')

            # 点击合集选择按钮
            await page.click('div:text("请选择合集")')
            # 尝试选择合集

            if await self.click_button_with_timeout(page, f'div[role="option"]:has-text("{self.collection}")',
                                                    "self.collection"):
                douyin_logger.info(f'[+] 成功选择合集：{self.collection}')
                return True
            else:
                douyin_logger.warning(f'[!] 未找到合集: {self.collection}')

        except Exception as e:
            douyin_logger.error(f'[!] 设置合集失败: {str(e)}')

    async def check_upload_status(self, page):
        """检查视频上传状态"""
        try:
            # 检查重新上传按钮
            reupload_btn = page.locator('[class^="long-card"] div:has-text("重新上传")')
            if await reupload_btn.count() > 0:
                douyin_logger.success("[+] 视频上传完毕")
                return True

            # 检查上传失败状态
            fail_status = page.locator('div.progress-div > div:has-text("上传失败")')
            if await fail_status.count() > 0:
                douyin_logger.error("[!] 发现上传出错，准备重试")
                await self.handle_upload_error(page)
                return False

            douyin_logger.info("[-] 正在上传视频中...")
            return False

        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                raise e
            douyin_logger.error(f"[!] 检查上传状态出错: {str(e)}")
            return False

    async def wait_upload_complete(self, page):
        """等待视频上传完成"""
        while True:
            try:
                if await self.check_upload_status(page):
                    break
                await asyncio.sleep(2)
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e):
                    raise e
                douyin_logger.error(e)
                await asyncio.sleep(2)

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)

    async def fill_title_and_tags(self, page):
        """填充标题和话题"""
        try:
            douyin_logger.info('[-] 正在填充标题和话题...')

            # 填充标题
            title_input = page.get_by_text('作品标题').locator("..").locator("xpath=following-sibling::div[1]").locator(
                "input")
            if await title_input.count():
                await title_input.fill(self.title[:30])
            else:
                # 备用方案
                title_input = page.locator(".notranslate")
                await title_input.click()
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Delete")
                await title_input.type(self.title)
                await page.keyboard.press("Enter")

            # 填充话题
            if self.tags:
                css_selector = ".zone-container"
                for tag in self.tags:
                    # 去除前后空格并检查标签是否已经包含#
                    tag = tag.strip()
                    if not tag:  # 跳过空标签
                        continue
                        
                    tag_text = tag if tag.startswith('#') else f'#{tag}'
                    await page.type(css_selector, tag_text)
                    await page.press(css_selector, "Space")
                douyin_logger.info(f'[+] 已添加 {len(self.tags)} 个话题')

        except Exception as e:
            douyin_logger.error(f'[!] 填充标题和话题失败: {str(e)}')
