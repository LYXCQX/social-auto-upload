# -*- coding: utf-8 -*-
import asyncio
import json
import os
import time

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from social_auto_upload.utils.log import douyin_logger
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.base_social_media import set_init_script

load_dotenv()


async def cookie_auth(account_file, thumbnail_path=None):
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        douyin_logger.warning(f"浏览器路径无效: {thumbnail_path}")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True,
                                                   executable_path=thumbnail_path)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://www.xingtu.cn/sup/creator/user/overview")
        try:
            await page.wait_for_url(
                "https://www.xingtu.cn/sup/creator/user/overview", timeout=5000)
        except:
            douyin_logger.info("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 2024.06.17 抖音创作者中心改版
        if await page.get_by_text('星图资讯').count():
            douyin_logger.info("[+] 等待5秒 cookie 失效")
            return False
        else:
            douyin_logger.info("[+] cookie 有效")
            return True


async def juliang_setup(account_file, handle=False, thumbnail_path=None):
    if (account_file and not os.path.exists(account_file)) or not await cookie_auth(account_file, thumbnail_path):
        if not handle:
            # Todo alert message
            return False, None, None, None
        douyin_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        user_id, user_name, douyin_id = await juliang_cookie_gen(account_file, thumbnail_path)
    else:
        # 新增：从 account_file 的文件名中提取用户 id 和 name
        base_name = os.path.basename(account_file)
        user_id, user_name, douyin_id = base_name.split('_')[:3]  # 假设文件名格式为 "user_id_user_name_account.json"

    return True, user_id, user_name, douyin_id


async def get_user_id(page):
    start_time = time.time()  # 获取开始时间
    while True:
        try:
            basic_info = page.locator('[class="basic-info"]')
            id_text = await basic_info.locator('span:has-text("ID:")').text_content()
            id_parts = id_text.split("ID:")
            if len(id_parts) > 1:
                user_id = id_parts[1].split("<")[0].strip()
            else:
                user_id = "0"
            douyin_logger.info(f"提取的用户ID: {user_id}")
            
            douyin_id_element = basic_info.locator('text=抖音号:')
            douyin_id_text = await douyin_id_element.text_content()
            douyin_parts = douyin_id_text.split("抖音号:")
            if len(douyin_parts) > 1:
                douyin_id = douyin_parts[1].split("<")[0].strip()
            else:
                douyin_id = ""
            douyin_logger.info(f"提取的抖音ID: {douyin_id}")
            if user_id == '0' or not user_id:
                current_time = time.time()  # 获取当前时间
                elapsed_time = current_time - start_time  # 计算已经过去的时间
                if elapsed_time > 30:  # 如果已经过去的时间超过30秒
                    douyin_logger.info(f"超时30秒，退出循环，返回user_id={user_id}, douyin_id={douyin_id}")
                    break  # 退出循环
            else:
                douyin_logger.info(f"成功获取ID，退出循环，返回user_id={user_id}, douyin_id={douyin_id}")
                break  # 退出循环
        except Exception as e:
            await asyncio.sleep(0.5)
            
    return user_id, douyin_id


async def juliang_cookie_gen(account_file, thumbnail_path=None):
    async with async_playwright() as playwright:
        # Make sure to run headed.
        browser = await playwright.chromium.launch(headless=False,
                                                   executable_path=thumbnail_path)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://www.xingtu.cn/?redirect_uri=https://www.xingtu.cn/sup/creator/user/overview")
        start_time = time.time()
        while True:
            if page.url.startswith('https://www.xingtu.cn/sup/creator/user/overview'):
                break
            else:
                await asyncio.sleep(0.5)
            elapsed_time = time.time() - start_time
            # 检查是否超过了超时时间
            if elapsed_time > 240:
                raise TimeoutError("操作超时，跳出循环")
        user_id, douyin_id = await get_user_id(page)
        # 修复：添加await关键字获取text_content()的结果
        name_element = page.locator('[class="basic-info"] [class="name"]')
        user_name = await name_element.text_content()
        user_name = user_name.strip()
        douyin_logger.info(f"获取到用户名: {user_name}")
        
        douyin_logger.info(f'{user_id}---{douyin_id}---{user_name}')
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=get_account_file(user_id, 'juliang', user_name, douyin_id))
        await context.close()
        await browser.close()
        return user_id, user_name, douyin_id
