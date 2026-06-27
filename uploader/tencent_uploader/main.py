# -*- coding: utf-8 -*-
import asyncio
import hashlib
import json
import os
import random
import time
import uuid
from datetime import datetime
import re
from types import SimpleNamespace

from camoufox import AsyncCamoufox
from config import PLATFORM
from config_manager import ConfigManager
from patchright.async_api import Playwright, async_playwright
from social_auto_upload.conf import LOCAL_CHROME_PATH
from social_auto_upload.uploader.tencent_uploader.main_tz import delete_videos_by_conditions
from social_auto_upload.uploader.tencent_uploader.main_tz_violation import check_and_handle_violation
from social_auto_upload.utils.base_social_media import set_init_script, SOCIAL_MEDIA_TENCENT
from social_auto_upload.utils.bus_exception import UpdateError
from social_auto_upload.utils.file_util import get_account_file
from social_auto_upload.utils.log import tencent_logger

from log import logger
from social_auto_upload.uploader.tencent_uploader.main_tz import add_original

from social_auto_upload.uploader.tencent_uploader.main_tz import add_short_play_by_juji, add_comment

from social_auto_upload.utils.base_up_util import dispatch_upload

from social_auto_upload.utils.camoufox_util import _get_camoufox_config

config = ConfigManager()
pub_config = json.loads(config.get(f'{PLATFORM}_pub_config', "{}")).get('tencent', {})


def remove_punctuation(text: str) -> str:
    """移除字符串中的所有标点符号和空格"""
    # 使用正则表达式移除所有非字母数字字符（包括中英文标点和空格）
    return re.sub(r'[^\w]', '', text, flags=re.UNICODE)


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


async def cookie_auth(account_file, local_executable_path=None, un_close=False,proxy_setting=None,camoufox=False,addons_path=None,load_addons=False):
    hide_browser = False if un_close else True
    if camoufox:
        camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path if load_addons else None},account_file=account_file,hide_browser=hide_browser,proxy_setting=proxy_setting))
        async with AsyncCamoufox(**camoufox_config) as browser:
            return await cookie_auth_br(account_file, browser, un_close)
    else:
        async with async_playwright() as playwright:
            # 只有在 load_addons=True 且有插件目录时才加载插件
            if load_addons and addons_path and addons_path.exists() and addons_path.is_dir():
                addons = [str(item) for item in addons_path.iterdir() if item.is_dir()]
                if addons:
                    tencent_logger.info(f"普通浏览器模式：已加载 {len(addons)} 个插件")
                    # 使用 persistent context 加载插件
                    args = [
                        '--disable-blink-features=AutomationControlled',
                        '--lang=zh-CN',
                        '--disable-infobars',
                        '--start-fullscreen',
                        '--no-sandbox',
                        '--disable-web-security'
                    ]
                    # 添加插件路径
                    for addon in addons:
                        args.append(f'--load-extension={addon}')
                    # 禁用扩展自动更新
                    args.append('--disable-extensions-except=' + ','.join(addons))
                    
                    # 创建临时用户数据目录
                    import tempfile
                    user_data_dir = tempfile.mkdtemp(prefix='playwright_profile_')
                    
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir,
                        headless=False,  # 加载插件时必须使用非无头模式
                        executable_path=local_executable_path,
                        proxy=proxy_setting,
                        args=args
                    )
                    # 加载 cookie - 从 storage_state 格式中提取 cookies 数组
                    storage_state = json.load(open(account_file))
                    if isinstance(storage_state, dict) and 'cookies' in storage_state:
                        await context.add_cookies(storage_state['cookies'])
                    else:
                        # 如果是直接的 cookies 数组
                        await context.add_cookies(storage_state)
                    return await cookie_auth_persistent(context, un_close)
            
            # 没有插件或不加载插件时使用普通模式
            options = {
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                    '--disable-infobars',
                    '--start-fullscreen',
                    '--no-sandbox',
                    '--disable-web-security'
                ],
                'headless': hide_browser,
                'executable_path': local_executable_path,
                'proxy': proxy_setting
            }
            browser = await playwright.chromium.launch(**options)
            return await cookie_auth_br(account_file, browser, un_close)


async def cookie_auth_br(account_file, browser, un_close):
    context = await browser.new_context(storage_state=account_file)
    context = await set_init_script(context, os.path.basename(account_file))
    # 创建一个新的页面
    page = await context.new_page()
    # 访问指定的 URL
    await page.goto("https://channels.weixin.qq.com/platform/post/create")
    try:
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
            await page.wait_for_selector('span:has-text("内容管理")', timeout=5000)  # 等待5秒
            tencent_logger.success("  [视频号上传] cookie 有效")
            await context.close()
            await browser.close()
        return True
    except:
        tencent_logger.error(" [视频号上传]等待5秒 cookie 失效")
        return False


async def cookie_auth_persistent(context, un_close):
    """使用 persistent context 进行 cookie 认证（用于加载插件）"""
    await set_init_script(context, "persistent_context")
    # 创建一个新的页面
    page = await context.new_page()
    # 访问指定的 URL
    await page.goto("https://channels.weixin.qq.com/platform/post/create")
    try:
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
                except:
                    pass
        else:
            await page.wait_for_selector('span:has-text("内容管理")', timeout=5000)  # 等待5秒
            tencent_logger.success("  [视频号上传] cookie 有效")
            await context.close()
        return True
    except:
        tencent_logger.error(" [视频号上传]等待5秒 cookie 失效")
        return False


async def get_tencent_cookie(account_file, local_executable_path=None,proxy_setting=None,camoufox=False,addons_path=None):
    if camoufox:
        camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path},account_file=account_file,hide_browser=False,proxy_setting=proxy_setting))
        async with AsyncCamoufox(**camoufox_config) as browser:
            return await get_tencent_cookie_br(account_file, browser)
    else:
        async with async_playwright() as playwright:
            options = {
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                    '--disable-infobars',
                    '--start-fullscreen',
                    '--no-sandbox',
                    '--disable-web-security'
                ],
                'headless': False,  # Set headless option here
                'executable_path': local_executable_path,
                'proxy':proxy_setting
            }
            # Make sure to run headed.
            browser = await playwright.chromium.launch(**options)
            return await get_tencent_cookie_br(account_file, browser)


async def get_tencent_cookie_br(account_file, browser):
    # Setup context however you like.
    context = await browser.new_context()  # Pass any options
    # Pause the page, and start recording manually.
    context = await set_init_script(context, os.path.basename(account_file))
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
        if elapsed_time > 1200:
            raise TimeoutError("操作超时，跳出循环")
    user_id = await get_user_id(page)
    user_name = await page.locator('.finder-nickname').text_content()
    
    # 获取头像和粉丝数
    avatar_url = None
    fans_count = 0
    video_count = 0
    
    try:
        # 获取头像：finder-info-container 下的 img 标签的 src
        avatar_element = page.locator('.finder-info-container img').first
        if avatar_element:
            avatar_url = await avatar_element.get_attribute('src')
            tencent_logger.info(f'[视频号登录] 获取到头像URL: {avatar_url}')
    except Exception as e:
        tencent_logger.warning(f'[视频号登录] 获取头像失败: {e}')
    
    try:
        # 获取视频数和粉丝数：finder-content-info 下的 finder-info-num
        info_nums = await page.locator('.finder-content-info .finder-info-num').all_text_contents()
        if len(info_nums) >= 2:
            video_count_str = info_nums[0].strip()
            fans_count_str = info_nums[1].strip()
            
            # 转换为数字（可能包含万、亿等单位）
            video_count = parse_count_string(video_count_str)
            fans_count = parse_count_string(fans_count_str)
            
            tencent_logger.info(f'[视频号登录] 视频数: {video_count}, 粉丝数: {fans_count}')
    except Exception as e:
        tencent_logger.warning(f'[视频号登录] 获取粉丝数失败: {e}')
    
    logger.info(f'{user_id}---{user_name}')
    # 点击调试器的继续，保存cookie
    await context.storage_state(path=get_account_file(user_id, SOCIAL_MEDIA_TENCENT, user_name))
    
    return user_id, user_name, avatar_url, fans_count, video_count


def parse_count_string(count_str):
    """解析数量字符串，支持万、亿等单位"""
    try:
        count_str = count_str.strip()
        if '亿' in count_str:
            return int(float(count_str.replace('亿', '')) * 100000000)
        elif '万' in count_str:
            return int(float(count_str.replace('万', '')) * 10000)
        else:
            return int(count_str)
    except:
        return 0


async def get_user_id(page):
    start_time = time.time()  # 获取开始时间
    while True:
        try:
            # 更新选择器以获取视频号ID
            user_id = await page.locator('.finder-uniq-id').text_content()
            user_id = user_id.strip()
            if user_id == '0':
                current_time = time.time()  # 获取当前时间
                elapsed_time = current_time - start_time  # 计算已经过去的时间
                if elapsed_time > 10:  # 如果已经过去的时间超过10秒
                    break  # 退出循环
                # 添加延迟避免过于频繁的查询
                await asyncio.sleep(0.5)
            else:
                break  # 退出循环
        except Exception as e:
            # 如果元素不存在或出现其他错误，等待后重试
            current_time = time.time()
            elapsed_time = current_time - start_time
            if elapsed_time > 10:
                break
            await asyncio.sleep(0.5)
    return user_id


async def weixin_setup(account_file, handle=False, local_executable_path=None,proxy_setting=None,camoufox=False,addons_path=None):
    # account_file = get_absolute_path(account_file, "tencent_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file,
                                                                 local_executable_path=local_executable_path,proxy_setting=proxy_setting,camoufox=camoufox,addons_path=addons_path):
        if not handle:
            # Todo alert message
            return False, None, None, None, 0, 0
        tencent_logger.info(f'[视频号登录] {account_file} cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        user_id, user_name, avatar_url, fans_count, video_count = await get_tencent_cookie(account_file, local_executable_path=local_executable_path,proxy_setting=proxy_setting,camoufox=camoufox,addons_path=addons_path)
        return True, user_id, user_name, avatar_url, fans_count, video_count
    else:
        # 新增：从 account_file 的文件名中提取用户 id 和 name
        base_name = os.path.basename(account_file)
        user_id, user_name = base_name.split('_')[:2]  # 假设文件名格式为 "user_id_user_name_account.json"
        return True, user_id, user_name, None, 0, 0


async def weidaren_cookie_auth(account_file, local_executable_path=None, un_close=False, proxy_setting=None, camoufox=False, addons_path=None, load_addons=False):
    """微达人cookie验证"""
    hide_browser = False if un_close else True
    if camoufox:
        camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path if load_addons else None},account_file=account_file,hide_browser=hide_browser,proxy_setting=proxy_setting))
        async with AsyncCamoufox(**camoufox_config) as browser:
            return await weidaren_cookie_auth_br(account_file, browser, un_close)
    else:
        async with async_playwright() as playwright:
            # 只有在 load_addons=True 且有插件目录时才加载插件
            if load_addons and addons_path and addons_path.exists() and addons_path.is_dir():
                addons = [str(item) for item in addons_path.iterdir() if item.is_dir()]
                if addons:
                    tencent_logger.info(f"微达人普通浏览器模式：已加载 {len(addons)} 个插件")
                    # 使用 persistent context 加载插件
                    args = [
                        '--disable-blink-features=AutomationControlled',
                        '--lang=zh-CN',
                        '--disable-infobars',
                        '--start-fullscreen',
                        '--no-sandbox',
                        '--disable-web-security'
                    ]
                    # 添加插件路径
                    for addon in addons:
                        args.append(f'--load-extension={addon}')
                    # 禁用扩展自动更新
                    args.append('--disable-extensions-except=' + ','.join(addons))
                    
                    # 创建临时用户数据目录
                    import tempfile
                    user_data_dir = tempfile.mkdtemp(prefix='playwright_profile_')
                    
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir,
                        headless=False,  # 加载插件时必须使用非无头模式
                        executable_path=local_executable_path,
                        proxy=proxy_setting,
                        args=args
                    )
                    # 加载 cookie - 从 storage_state 格式中提取 cookies 数组
                    storage_state = json.load(open(account_file))
                    if isinstance(storage_state, dict) and 'cookies' in storage_state:
                        await context.add_cookies(storage_state['cookies'])
                    else:
                        # 如果是直接的 cookies 数组
                        await context.add_cookies(storage_state)
                    return await weidaren_cookie_auth_persistent(context, un_close)
            
            # 没有插件或不加载插件时使用普通模式
            options = {
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                    '--disable-infobars',
                    '--start-fullscreen',
                    '--no-sandbox',
                    '--disable-web-security'
                ],
                'headless': hide_browser,
                'executable_path': local_executable_path,
                'proxy': proxy_setting
            }
            browser = await playwright.chromium.launch(**options)
            return await weidaren_cookie_auth_br(account_file, browser, un_close)


async def weidaren_cookie_auth_br(account_file, browser, un_close):
    """微达人cookie验证 - 浏览器模式"""
    context = await browser.new_context(storage_state=account_file)
    context = await set_init_script(context, os.path.basename(account_file))
    # 创建一个新的页面
    page = await context.new_page()
    # 访问微达人页面
    await page.goto("https://store.weixin.qq.com/talent/?redirect_url=%2Fchannel%2Ffinder")
    try:
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
            # 检查页面是否有"邀约"字样，表示登录成功
            await page.wait_for_selector('text=邀约', timeout=5000)  # 等待5秒
            tencent_logger.success("  [微达人] cookie 有效")
            await context.close()
            await browser.close()
        return True
    except:
        tencent_logger.error(" [微达人] 等待5秒 cookie 失效")
        return False


async def weidaren_cookie_auth_persistent(context, un_close):
    """微达人cookie验证 - persistent context模式（用于加载插件）"""
    await set_init_script(context, "persistent_context")
    # 创建一个新的页面
    page = await context.new_page()
    # 访问微达人页面
    await page.goto("https://store.weixin.qq.com/talent/channel/finder")
    try:
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
                except:
                    pass
        else:
            # 检查页面是否有"邀约"字样，表示登录成功
            await page.wait_for_selector('text=邀约', timeout=5000)  # 等待5秒
            tencent_logger.success("  [微达人] cookie 有效")
            await context.close()
        return True
    except:
        tencent_logger.error(" [微达人] 等待5秒 cookie 失效")
        return False


async def get_weidaren_cookie(account_file, local_executable_path=None, proxy_setting=None, camoufox=False, addons_path=None):
    """获取微达人cookie"""
    if camoufox:
        camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path},account_file=account_file,hide_browser=False,proxy_setting=proxy_setting))
        async with AsyncCamoufox(**camoufox_config) as browser:
            return await get_weidaren_cookie_br(account_file, browser)
    else:
        async with async_playwright() as playwright:
            options = {
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                    '--disable-infobars',
                    '--start-fullscreen',
                    '--no-sandbox',
                    '--disable-web-security'
                ],
                'headless': False,  # Set headless option here
                'executable_path': local_executable_path,
                'proxy':proxy_setting
            }
            # Make sure to run headed.
            browser = await playwright.chromium.launch(**options)
            return await get_weidaren_cookie_br(account_file, browser)


async def weidaren_click_publish_and_save(page, context, account_file):
    """微达人点击发视频按钮，跳转到发布页面并保存cookie
    
    这个函数被以下场景复用：
    1. 首次登录后保存cookie
    2. 重登时store在线但channels离线，需要刷新cookie
    """
    # 等待页面加载，确认有"邀约"字样
    await page.wait_for_selector('text=邀约', timeout=10000)
    tencent_logger.info("[微达人] 已进入微达人页面")
    
    # 点击"发视频"按钮
    await page.click('text=发视频')
    tencent_logger.info("[微达人] 已点击发视频按钮，等待跳转...")
    
    # 等待新标签页打开并跳转到发布页面
    async with page.expect_popup() as popup_info:
        pass
    new_page = await popup_info.value
    
    # 等待跳转到发布页面
    await new_page.wait_for_url("https://channels.weixin.qq.com/platform/post/create*", timeout=30000)
    tencent_logger.info("[微达人] 已跳转到发布页面")

    await new_page.wait_for_selector('span:has-text("内容管理")', timeout=10000)  # 等待5秒
    # 再跳转到平台首页
    await new_page.goto("https://channels.weixin.qq.com/platform")
    tencent_logger.info("[微达人] 已跳转到平台首页")
    
    # 获取用户信息
    user_id = await get_user_id(new_page)
    user_name = await new_page.locator('.finder-nickname').text_content()
    logger.info(f'{user_id}---{user_name}')
    
    # 保存cookie
    await context.storage_state(path=get_account_file(user_id, SOCIAL_MEDIA_TENCENT, user_name))
    tencent_logger.success("[微达人] cookie已保存")
    
    # 关闭新标签页
    await new_page.close()
    
    return user_id, user_name


async def get_weidaren_cookie_br(account_file, browser):
    """获取微达人cookie - 浏览器模式"""
    # Setup context however you like.
    context = await browser.new_context()  # Pass any options
    # Pause the page, and start recording manually.
    context = await set_init_script(context, os.path.basename(account_file))
    page = await context.new_page()
    await page.goto("https://store.weixin.qq.com/talent/?redirect_url=%2Fchannel%2Ffinder")
    try:
        # 设置页面标题为 local_executable_path 的文件名
        if account_file:
            file_name = os.path.basename(account_file)
            await page.evaluate(f'document.title = "{file_name}"')
    except:
        pass
    
    # 等待登录成功，检查是否有"邀约"字样
    start_time = time.time()
    while True:
        try:
            await page.wait_for_selector('text=邀约', timeout=1000)
            # 出现邀约，登录成功
            break
        except:
            # 检查是否超时
            elapsed_time = time.time() - start_time
            if elapsed_time > 1200:
                raise TimeoutError("等待登录超时，跳出循环")
            await asyncio.sleep(0.5)
    
    tencent_logger.info("[微达人] 登录成功，检测到邀约字样")
    
    # 复用点击发视频和保存cookie的逻辑
    user_id, user_name = await weidaren_click_publish_and_save(page, context, account_file)
    
    return user_id, user_name


async def weidaren_setup(account_file, handle=False, local_executable_path=None, proxy_setting=None, camoufox=False, addons_path=None):
    """微达人登录设置"""
    # 第一步：检查 channels.weixin.qq.com 是否在线
    if os.path.exists(account_file):
        tencent_logger.info(f'[微达人登录] 检查 channels.weixin.qq.com 是否在线...')
        is_channels_online = await cookie_auth(account_file,
                                               local_executable_path=local_executable_path,
                                               proxy_setting=proxy_setting,
                                               camoufox=camoufox,
                                               addons_path=addons_path)
        if is_channels_online:
            tencent_logger.success(f'[微达人登录] channels.weixin.qq.com 在线，登录成功')
            # 从文件名中提取用户信息
            base_name = os.path.basename(account_file)
            user_id, user_name = base_name.split('_')[:2]
            return True, user_id, user_name
        
        # 第二步：检查 store.weixin.qq.com 是否在线
        tencent_logger.info(f'[微达人登录] channels.weixin.qq.com 离线，检查 store.weixin.qq.com 是否在线...')
        is_store_online = await weidaren_cookie_auth(account_file,
                                                     local_executable_path=local_executable_path,
                                                     proxy_setting=proxy_setting,
                                                     camoufox=camoufox,
                                                     addons_path=addons_path)
        if is_store_online:
            tencent_logger.success(f'[微达人登录] store.weixin.qq.com 在线，执行登录后逻辑...')
            # 执行登录后的逻辑：点击发视频，跳转到发布页面，保存cookie（隐藏窗口）
            if camoufox:
                camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path},account_file=account_file,hide_browser=True,proxy_setting=proxy_setting))
                async with AsyncCamoufox(**camoufox_config) as browser:
                    return await weidaren_post_login(account_file, browser)
            else:
                async with async_playwright() as playwright:
                    options = {
                        'args': [
                            '--disable-blink-features=AutomationControlled',
                            '--lang=zh-CN',
                            '--disable-infobars',
                            '--start-fullscreen',
                            '--no-sandbox',
                            '--disable-web-security'
                        ],
                        'headless': True,  # 隐藏窗口
                        'executable_path': local_executable_path,
                        'proxy':proxy_setting
                    }
                    browser = await playwright.chromium.launch(**options)
                    return await weidaren_post_login(account_file, browser)
    
    # 第三步：完全离线，需要重新登录
    if not handle:
        return False, None, None
    
    tencent_logger.info(f'[微达人登录] {account_file} cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
    user_id, user_name = await get_weidaren_cookie(account_file, local_executable_path=local_executable_path,proxy_setting=proxy_setting,camoufox=camoufox,addons_path=addons_path)
    return True, user_id, user_name


async def weidaren_post_login(account_file, browser):
    """微达人登录后的逻辑：点击发视频，跳转到发布页面，保存cookie"""
    context = await browser.new_context(storage_state=account_file)
    context = await set_init_script(context, os.path.basename(account_file))
    page = await context.new_page()
    
    try:
        # 访问微达人页面
        await page.goto("https://store.weixin.qq.com/talent/channel/finder")
        
        # 复用点击发视频和保存cookie的逻辑
        user_id, user_name = await weidaren_click_publish_and_save(page, context, account_file)
        
        # 关闭页面和浏览器
        await page.close()
        await context.close()
        await browser.close()
        
        return True, user_id, user_name
        
    except Exception as e:
        tencent_logger.error(f"[微达人] 登录后逻辑执行失败: {str(e)}")
        try:
            await context.close()
            await browser.close()
        except:
            pass
        raise


async def weidaren_refresh_backend(account_file, local_executable_path=None, proxy_setting=None, camoufox=False, addons_path=None):
    """刷新微达人后台并保存cookie
    
    用于后台校验时，如果微达人账号在线，则打开新tab刷新后台并保存cookie
    """
    hide_browser = True
    if camoufox:
        camoufox_config = await _get_camoufox_config(
            SimpleNamespace(
                info={'addons_path': None},
                account_file=account_file,
                hide_browser=hide_browser,
                proxy_setting=proxy_setting
            )
        )
        async with AsyncCamoufox(**camoufox_config) as browser:
            await weidaren_refresh_backend_br(account_file, browser)
    else:
        async with async_playwright() as playwright:
            options = {
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                    '--disable-infobars',
                    '--start-fullscreen',
                    '--no-sandbox',
                    '--disable-web-security'
                ],
                'headless': hide_browser,
                'executable_path': local_executable_path,
                'proxy': proxy_setting
            }
            browser = await playwright.chromium.launch(**options)
            await weidaren_refresh_backend_br(account_file, browser)
            await browser.close()


async def weidaren_refresh_backend_br(account_file, browser):
    """刷新微达人后台 - 浏览器模式"""
    context = await browser.new_context(storage_state=account_file)
    context = await set_init_script(context, os.path.basename(account_file))
    
    try:
        # 创建一个新的页面
        page = await context.new_page()
        
        # 访问微达人后台
        tencent_logger.info("[微达人] 正在访问微达人后台...")
        await page.goto("https://store.weixin.qq.com/talent/channel/finder", timeout=30000)
        
        # 等待页面加载完成
        await page.wait_for_load_state('networkidle', timeout=10000)
        tencent_logger.info("[微达人] 后台页面加载完成")
        
        # 关闭页面
        await page.close()
        
        # 保存更新后的cookie
        tencent_logger.info(f"[微达人] 正在保存更新后的cookie到: {account_file}")
        await context.storage_state(path=account_file)
        tencent_logger.success("[微达人] cookie已更新并保存")
        
    finally:
        await context.close()


class TencentVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, category=None,
                 local_executable_path=None, info=None, collection=None, declare_original=None, proxy_setting=None, hide_browser=False, thumbnail_path=None):
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
        self.hide_browser = hide_browser
        self.upload_retry_attempts = 0
        self.max_upload_retries = 3
        self.thumbnail_path = thumbnail_path

    async def _check_is_weidaren_login(self) -> bool:
        """检查是否为微达人登录方式
        通过检查cookie文件中是否包含store.weixin.qq.com域名的cookie来判断
        """
        try:
            if not os.path.exists(self.account_file):
                return False
            
            # ✅ 使用异步文件读取
            import aiofiles
            async with aiofiles.open(self.account_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                cookie_data = json.loads(content)
            
            # 检查cookies数组
            cookies = cookie_data.get('cookies', [])
            for cookie in cookies:
                if 'store.weixin.qq.com' in cookie.get('domain', ''):
                    return True
            
            return False
        except Exception as e:
            tencent_logger.error(f"判断微达人登录方式失败: {e}")
            return False

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
        if self.upload_retry_attempts >= self.max_upload_retries:
            msg = f"  [视频号上传] {self.file_path} 上传失败，已达到最大重试次数 {self.max_upload_retries} 次"
            tencent_logger.error(msg)
            raise UpdateError(msg)

        self.upload_retry_attempts += 1
        tencent_logger.info(
            f"  [视频号上传] {self.file_path} 视频出错了，重新上传中（第 {self.upload_retry_attempts}/{self.max_upload_retries} 次）")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator(pub_config.get('up_file'))
        await file_input.set_input_files(self.file_path)

    async def add_activity(self, page,type=1):
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
        theater = anchor_info.get("theater", None)
        if theater:
            playlet_title_tag = theater
        else:
            playlet_title_tag = anchor_info.get("playlet_title_tag", None)
        tencent_logger.info(f"  [视频号上传] {self.file_path} 开始添加活动: 搜索剧名[{search_title}] 展示剧名[{match_title}]")
        active_hd = pub_config.get('active_hd')
        # 等待包含"活动"标签的form-item出现
        await page.wait_for_selector(active_hd, state="visible", timeout=5000)
        form_item = page.locator(active_hd)

        # 查找并点击"不参与活动"按钮
        no_activity_span = form_item.locator("span:has-text('不参与活动'):visible")
        if await no_activity_span.is_visible():
            await no_activity_span.click()
            tencent_logger.info(f"  [视频号上传] {self.file_path} 已点击不参与活动")

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
            tencent_logger.info(f'  [视频号上传] {self.file_path} 已找到活动：{name}--需要匹配活动：{match_title}')

            # 提取书名号中的内容和推广前的内容
            book_title = re.search(r'《(.*?)》', name)
            promotion_title = re.search(r'》(.*?)推广', name)

            if book_title:
                book_content = book_title.group(1)
                promotion_content = promotion_title.group(1).strip()
                tencent_logger.info(f'  [视频号上传] {self.file_path} 提取的活动名称：书名号内容={book_content}, 推广前内容={promotion_content}')

                # 获取忽略标点设置
                ignore_punctuation = anchor_info.get("ignore_punctuation", False)
                
                # 根据设置决定是否移除标点符号
                if ignore_punctuation:
                    compare_match_title = remove_punctuation(match_title.strip())
                    compare_book_content = remove_punctuation(book_content.strip())
                    tencent_logger.info(f'  [视频号上传] {self.file_path} 忽略标点对比：[{compare_match_title}] vs [{compare_book_content}]')
                else:
                    compare_match_title = match_title.strip()
                    compare_book_content = book_content.strip()

                if match_drama_name:
                    have_platlet = compare_match_title == compare_book_content
                else:
                    have_platlet = compare_match_title in compare_book_content
            # else:
            # have_platlet = False
            if have_platlet:
                if playlet_title_tag:
                    if playlet_title_tag not in creator_name:
                        continue
                await element.click()
                tencent_logger.info(f"  [视频号上传] {self.file_path} 成功添加活动: {match_title}")
                found = True
                break

        if not found:
            if type == 1:
                raise UpdateError(f"  [视频号上传] {self.file_path} 没有找到 {playlet_title_tag}：剧场的短剧任务：{match_title}")
            else:
                random_element = random.choice(activity_elements)
                if random_element:
                    random_element.click()

    async def upload(self, playwright: Playwright,browser) -> tuple[bool, str]:
        if playwright:
            # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误

            options = {
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                    '--disable-infobars',
                    '--start-fullscreen',
                    '--no-sandbox',
                    '--disable-web-security'
                ],
                'headless': self.hide_browser,  # 保持与原代码一致的逻辑
                'executable_path': self.local_executable_path,  # 注意使用 self. 前缀
                'proxy': self.proxy_setting  # 注意使用 self. 前缀
            }
            browser = await playwright.chromium.launch(**options)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(
            storage_state=f"{self.account_file}",
        )
        context = await set_init_script(context,os.path.basename(self.account_file))
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
        for i in range(upload_count):
            tencent_logger.info(f'  [视频号上传] {self.file_path} 正在进行第 {i + 1}/{upload_count} 次上传 -------{self.title}.mp4')
            # 访问指定的 URL
            await page.goto("https://channels.weixin.qq.com/platform/post/create")
            tencent_logger.info(f' [视频号上传] {self.file_path} 正在上传-------{self.title}.mp4')
            
            # 检查是否需要重新登录（微达人方式）
            try:
                # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create", timeout=10000)
            except:
                # 如果跳转失败，可能是掉线了，检查是否为微达人登录方式
                is_weidaren = await self._check_is_weidaren_login()
                if is_weidaren:
                    tencent_logger.info(f'  [视频号上传] {self.file_path} 检测到微达人登录已掉线，尝试重新登录...')
                    # 跳转到微达人页面
                    await page.goto("https://store.weixin.qq.com/talent/channel/finder")
                    # 等待页面加载
                    await page.wait_for_selector('text=邀约', timeout=10000)
                    # 点击"发视频"按钮
                    await page.click('text=发视频')
                    tencent_logger.info(f'  [视频号上传] {self.file_path} 已点击发视频按钮，等待跳转...')
                    # 等待新标签页打开
                    async with page.expect_popup() as popup_info:
                        pass
                    new_page = await popup_info.value
                    # 等待跳转到发布页面
                    await new_page.wait_for_url("https://channels.weixin.qq.com/platform/post/create*", timeout=30000)
                    tencent_logger.info(f'  [视频号上传] {self.file_path} 已重新进入发布页面')
                    # 关闭旧页面，使用新页面
                    await page.close()
                    page = new_page
                else:
                    # 不是微达人登录方式，抛出异常
                    raise
            
            # await page.wait_for_selector('input[type="file"]', timeout=10000)
            file_input = page.locator(pub_config.get('up_file'))
            await file_input.set_input_files(self.file_path)
            # 添加商品
            # await self.add_product(page)
            if self.info.get("enable_drama", False):
                if self.info.get("enable_cps", False):
                    if 1 < upload_count != i + 1 and self.info.get("delete_platform_video", False):
                        tencent_logger.info('，，，')
                    else:
                        await self.add_activity(page)
                # 添加活动
                if self.info.get("enable_baobai", False):
                    await self.add_short_play_by_baobai(page)
                elif self.info.get("enable_juji", False):
                    # if 1 < upload_count != i + 1:
                    #     tencent_logger.info('，，，')
                    # else:
                    if 1 < upload_count != i + 1 and self.info.get("delete_platform_video", False):
                        tencent_logger.info('，，，')
                    else:
                        await add_short_play_by_juji(self,page,pub_config)
            else:
                tencent_logger.info(f'  [视频号上传] {self.file_path} 未选择挂短剧')
            try:
                await add_original(self, page)
            except:
                tencent_logger.exception(f'  [视频号上传] {self.file_path} 添加原创失败，不影响执行')
            should_delete = self.info and self.info.get("delete_platform_video", False) and (i < upload_count - 1)
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
                # 检查是否开启了定时功能
                # 如果定时时间小于当前时间（已过期），使用当前时间+间隔
                use_schedule = self.info and self.info.get('use_current_time_schedule', False)
                if use_schedule:
                    from datetime import datetime
                    current_time = datetime.now()
                    # 只有当定时时间比当前时间小时才调整（说明是过期的定时时间）
                    if self.publish_date < current_time:
                        # 获取定时间隔（分钟）
                        schedule_interval = self.info.get('schedule_interval', '5')
                        try:
                            from config_util import parse_schedule_interval
                            interval_minutes = parse_schedule_interval(schedule_interval)
                        except:
                            tencent_logger.warning(f"解析定时间隔失败，使用默认值5分钟")
                            interval_minutes = 5
                        
                        # 计算新的定时时间：当前时间 + 定时间隔
                        from datetime import timedelta
                        self.publish_date = current_time + timedelta(minutes=interval_minutes)
                        tencent_logger.info(f"  [视频号上传] {self.file_path} 定时时间已过期，使用当前时间加上定时间隔 {interval_minutes} 分钟，新定时时间为 {self.publish_date}")
                
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
            
            # 检查页面是否有错误视频，如果有则删除
            try:
                fail_video_count = await page.locator('.post-processed-fail').count()
                if fail_video_count > 0:
                    tencent_logger.warning(f'[错误视频处理] 发现 {fail_video_count} 个错误视频，准备删除')
                    await delete_videos_by_conditions(page, only_delete_fail=True)
                    tencent_logger.success('[错误视频处理] 错误视频删除完毕')
                else:
                    tencent_logger.info('[错误视频处理] 未发现错误视频')
            except Exception as e:
                tencent_logger.exception(f'[错误视频处理] 检查或删除错误视频时出错: {str(e)}')
            
            if should_delete:
                await self.delete_video(page)
        if not (self.publish_date and self.publish_date != 0):
            if self.info and self.info.get("auto_comment_enabled", False) and self.info.get("auto_comment_text", None) :
                await add_comment(page,self.info.get("auto_comment_text", None))
        if self.info and self.info.get("delete_after_play", False):
            # 检查是否使用API删除
            delete_use_api = self.info.get("delete_use_api", False)
            tencent_logger.info(f"[删除流程] delete_use_api配置值: {delete_use_api} (类型: {type(delete_use_api)})")
            tencent_logger.info(f"[删除流程] self.info完整内容: {self.info}")

            if delete_use_api:
                tencent_logger.info("[删除流程] 使用API接口删除视频（异步执行，不阻塞主流程）")
                # 获取用户信息用于更新时间戳
                user_id = self.info.get("user_id")
                last_delete_timestamp = self.info.get("last_delete_video_timestamp")
                # 创建独立的异步任务，不等待完成
                asyncio.create_task(self.delete_videos_by_api(
                    minutes_ago=self.info.get("delete_time_threshold", 1440), 
                    max_views=self.info.get("delete_play_threshold", 100),
                    user_id=user_id,
                    last_delete_timestamp=last_delete_timestamp))
                tencent_logger.info("[删除流程] API删除任务已在后台启动")
            else:
                tencent_logger.info("[删除流程] 使用页面操作删除视频")
                await delete_videos_by_conditions(page, 
                    minutes_ago=self.info.get("delete_time_threshold", 1440), 
                    max_views=self.info.get("delete_play_threshold", 100),
                    page_index=50)
        
        # 检查并处理违规视频（异步执行，不阻塞主流程）
        if self.info and self.info.get("delete_violation", False):
            try:
                violation_delete_days = self.info.get("violation_delete_days", 7)
                violation_delete_views = self.info.get("violation_delete_views", 100)
                violation_hide_views = self.info.get("violation_hide_views", 1000)
                user_id = self.info.get("user_id")  # 获取用户ID
                last_check_timestamp = self.info.get("last_violation_check_timestamp")  # 获取最后检查时间戳
                
                tencent_logger.info("[违规处理] 开始后台检查违规视频（不阻塞主流程）")
                # 创建独立的异步任务，不等待完成
                asyncio.create_task(check_and_handle_violation(
                    self.account_file,  # 传递session文件路径
                    violation_delete_days,
                    violation_delete_views,
                    violation_hide_views,
                    user_id,  # 传递用户ID用于更新数据库
                    last_check_timestamp  # 传递最后检查时间戳，避免重复查询
                ))
                tencent_logger.info("[违规处理] 违规检查任务已在后台启动")
            except Exception as e:
                tencent_logger.exception(f"启动违规检查任务时出错: {str(e)}")



        # 关闭浏览器上下文和浏览器实例
        try:
            if context:
                await context.close()
            if browser:
                await browser.close()
        except Exception as e:
            tencent_logger.exception(f"关闭浏览器资源时出错: {str(e)}")
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
                    tencent_logger.info(f'  [视频号上传] {self.file_path} 成功关闭位置显示')
                    break
                except:
                    await asyncio.sleep(0.5)
                    continue
            if not success:
                tencent_logger.warning(f'  [视频号上传] {self.file_path} 关闭位置显示失败，继续执行')

    async def delete_video(self, page):
        # 检查是否需要删除视频
        if self.info and self.info.get("delete_platform_video", False):
            delete_delay = self.info.get("delete_delay")
            tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 准备开始删除视频，等待 {delete_delay} 秒")
            await asyncio.sleep(delete_delay)

            try:
                is_first_time = False  # 标记是否使用第一个视频的时间
                start_time = time.time()  # 记录开始时间
                timeout = 300  # 5分钟超时
                running_cover_item = None
                found_video = False
                while True:  # 外层循环，直到找不到匹配的post_time为止
                    current_time = time.time()
                    elapsed = current_time - start_time
                    tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 当前循环已运行 {elapsed:.2f} 秒")

                    # 检查是否超时
                    if elapsed > timeout:
                        if running_cover_item:
                            # 执行删除
                            delete_button = running_cover_item.locator('text=删除')
                            if await delete_button.count() > 0:
                                tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 超时找到删除按钮，准备删除视频")
                                await delete_button.locator('..').locator('.opr-item').evaluate(
                                    'el => el.click()')
                                await page.click(':text-is("确定"):visible')
                                await asyncio.sleep(2)
                        tencent_logger.warning(f"  [视频号上传] {self.file_path} [删除流程] 删除操作超过{timeout}秒，自动结束")
                        break

                    # 刷新页面
                    tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 刷新页面")
                    if not found_video:
                        await page.reload()
                        await asyncio.sleep(1)  # 等待页面加载
                    video_list = pub_config.get('video_list')
                    try:
                        tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 等待视频列表加载")
                        await page.wait_for_selector(video_list, timeout=30000)
                    except Exception as e:
                        tencent_logger.error(f"  [视频号上传] {self.file_path} [删除流程] 等待视频列表加载超时，未找到 post-feed-item 元素: {str(e)}")
                        return

                    found_video = False
                    # 获取所有视频项
                    feed_items = await page.locator(video_list).all()
                    if not feed_items:
                        tencent_logger.warning(f"  [视频号上传] {self.file_path} [删除流程] 未找到任何视频项")
                        break

                    feed_count = len(feed_items)
                    tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 找到 {feed_count} 个视频项")

                    # 检查所有项是否都包含effective-time
                    all_have_effective_time = True
                    # 遍历所有视频项
                    for index, item in enumerate(feed_items):
                        try:
                            effective_time = await item.locator('.effective-time').count()
                            tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 检查有效时间: {effective_time}")
                            if effective_time == 0:
                                all_have_effective_time = False
                            item_title = item.locator('.post-title')
                            if await item_title.count() > 0:
                                title_text = await item_title.text_content()
                                if title_text.startswith('waitdel-'):
                                    found_video = True  # 找到了符合条件的视频
                                    # 检查是否存在running-cover标签
                                    running_cover = await item.locator('.running-cover').count()
                                    if running_cover > 0:
                                        # 检查是否启用了完毕后删除设置
                                        if self.info and self.info.get("delete_after_complete", False):
                                            running_cover_item = item
                                            tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 发现转圈视频，先继续查找其他可删除的视频")
                                            # 不再break，继续查找下一个视频
                                            continue
                                        else:
                                            tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 视频正在处理中，但未启用完毕后删除设置，跳过处理")
                                            continue
                                    # 执行删除（没有转圈的视频）
                                    delete_button = item.locator('text=删除')
                                    if await delete_button.count() > 0:
                                        tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 找到删除按钮，准备删除视频")
                                        await delete_button.locator('..').locator('.opr-item').evaluate(
                                            'el => el.click()')
                                        await page.click(':text-is("确定"):visible')
                                        is_first_time = True
                                        await asyncio.sleep(2)
                                        break
                        except Exception as e:
                            tencent_logger.exception(f"  [视频号上传] {self.file_path} [删除流程] 处理视频项时出错：{str(e)}")
                            continue
                    if all_have_effective_time:
                        tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 所有视频项都包含effective-time，调用批量删除方法")
                        await delete_videos_by_conditions(page, 0, 10, page_index=5, video_title='waitdel-')
                    # 如果没有找到匹配的视频，说明删除完成
                    if not found_video:
                        if is_first_time:
                            tencent_logger.info(f"  [视频号上传] {self.file_path} [删除流程] 未找到title为 {self.title} 的视频，删除操作完成")
                        else:
                            tencent_logger.warning(f"  [视频号上传] {self.file_path} [删除流程] 未找到要删除的视频")
                        break

            except Exception as e:
                tencent_logger.exception(f"  [视频号上传] {self.file_path} [删除流程] 删除视频时出错：{str(e)}")

    async def delete_videos_by_api(self, minutes_ago=None, max_views=None, user_id=None, last_delete_timestamp=None):
        """
        使用API接口根据时间间隔和播放量条件删除视频
        :param minutes_ago: 多少分钟之前的视频
        :param max_views: 最大播放量
        :param user_id: 用户ID，用于更新最后删除时间戳
        :param last_delete_timestamp: 最后删除时的视频发布时间戳，避免重复处理
        """
        import requests
        import json
        from datetime import datetime, timedelta
        
        if not minutes_ago and not max_views:
            tencent_logger.info("[删除流程-API] 未设置删除条件，跳过删除")
            return
        
        tencent_logger.info(f"[删除流程-API] 开始使用API删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views}")
        
        if last_delete_timestamp:
            tencent_logger.info(f"[删除流程-API] 上次删除时的视频时间戳: {last_delete_timestamp} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_delete_timestamp))})")
        
        try:
            # 从session文件读取cookie
            # ✅ 使用异步文件读取
            import aiofiles
            async with aiofiles.open(self.account_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                session_data = json.loads(content)
            
            cookies_list = session_data.get('cookies', [])
            sessionid = None
            wxuin = None
            for cookie in cookies_list:
                if cookie['name'] == 'sessionid':
                    sessionid = cookie['value']
                elif cookie['name'] == 'wxuin':
                    wxuin = cookie['value']
            
            if not sessionid or not wxuin:
                tencent_logger.error('[删除流程-API] 无法获取sessionid或wxuin')
                return
            
            # 导入删除函数
            from social_auto_upload.uploader.tencent_uploader.main_tz_violation import delete_violation_video
            
            # 计算时间范围（与页面操作逻辑一致：获取 minutes_ago 分钟前的时间点）
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(days=3)
            cutoff_timestamp = int(cutoff_time.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

            tencent_logger.info(f"[删除流程-API] 当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            tencent_logger.info(f"[删除流程-API] 截止时间: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} (时间戳: {cutoff_timestamp})")
            tencent_logger.info(f"[删除流程-API] 删除条件: 发布时间 <= {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 且 播放量 < {max_views}")
            
            # 查询视频列表
            url = 'https://channels.weixin.qq.com/micro/statistic/cgi-bin/mmfinderassistant-bin/statistic/post_list'

            headers = {
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Connection': 'keep-alive',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
                'X-WECHAT-UIN': wxuin,
                'Referer': 'https://channels.weixin.qq.com/micro/statistic/post',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'finger-print-device-id': hashlib.md5(sessionid.encode()).hexdigest(),
                'sec-ch-ua': '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
            
            cookies = {'sessionid': sessionid, 'wxuin': wxuin}
            # 禁用SSL警告
            import warnings
            from urllib3.exceptions import InsecureRequestWarning
            warnings.filterwarnings('ignore', category=InsecureRequestWarning)

            session = requests.Session()

            # 分页查询视频
            page_size = 20
            current_page = 1
            delete_success_count = 0
            delete_fail_count = 0
            
            while True:
                data = {
                    'pageSize': page_size,
                    'currentPage': current_page,
                    'sort': 0,  # 使用当前排序字段
                    'order': 0,  # 使用当前排序方向
                    'startTime': cutoff_timestamp,
                    'endTime': int(current_time.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()),
                    'timestamp': str(int(time.time() * 1000)),
                    '_log_finder_uin': '',
                    '_log_finder_id': '',
                    'rawKeyBuff': '',
                    'pluginSessionId': None,
                    'scene': 7,
                    'reqScene': 7
                }
                print(data)
                # ✅ 使用 asyncio.to_thread 将同步请求转移到线程池
                response = await asyncio.to_thread(
                    session.post, url, headers=headers, cookies=cookies, json=data, timeout=30, verify=False
                )
                
                if response.status_code not in [200, 201]:
                    tencent_logger.error(f"[删除流程-API] 查询视频列表失败（第{current_page}页），状态码：{response.status_code}")
                    break
                
                result = response.json()
                
                if result.get('errCode') != 0:
                    tencent_logger.error(f"[删除流程-API] 视频列表API返回错误：{result.get('errMsg')}")
                    break
                
                data_obj = result.get('data', {})
                video_list = data_obj.get('list', [])
                total_count = data_obj.get('totalCount', 0)
                
                if not video_list:
                    tencent_logger.info(f"[删除流程-API] 第{current_page}页无数据，查询完成")
                    break
                
                tencent_logger.info(f"[删除流程-API] 第{current_page}页: 获取 {len(video_list)} 个视频")
                
                # 记录本页第一条视频的发布时间（用于更新时间戳）
                first_video_timestamp = None
                if current_page == 1 and video_list:
                    first_video_timestamp = video_list[0].get('createTime', 0)
                
                # 检查符合条件的视频并立即删除
                should_continue = False
                stop_pagination = False
                
                for video in video_list:
                    create_time = video.get('createTime', 0)
                    read_count = video.get('readCount', 0)
                    export_id = video.get('exportId', '')
                    object_id = video.get('objectId', '')
                    
                    # 如果有上次删除时间戳，遇到更早或相等的视频就停止
                    if last_delete_timestamp and create_time <= last_delete_timestamp:
                        tencent_logger.info(f"[删除流程-API] 遇到已处理的视频（发布时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(create_time))}），停止检查")
                        stop_pagination = True
                        break
                    
                    # 计算时间差（分钟）
                    video_time = datetime.fromtimestamp(create_time)
                    time_diff = (current_time - video_time).total_seconds() / 60
                    
                    # 记录详细的比对信息
                    tencent_logger.info(f"[删除流程-API] 视频信息比对:")
                    tencent_logger.info(f"[删除流程-API] - ObjectID: {object_id}")
                    tencent_logger.info(f"[删除流程-API] - 发布时间: {video_time.strftime('%Y年%m月%d日 %H:%M')} ({time_diff:.0f}分钟前)")
                    tencent_logger.info(f"[删除流程-API] - 播放量: {read_count}")
                    tencent_logger.info(f"[删除流程-API] - 条件比对: 时间>={minutes_ago}分钟 且 播放量<{max_views}")
                    tencent_logger.info(f"[删除流程-API] - 实际数据: {time_diff:.0f}>={minutes_ago} 且 {read_count}<{max_views}")
                    
                    # 检查是否符合删除条件（与页面操作逻辑一致）
                    if minutes_ago is not None and time_diff >= minutes_ago and max_views is not None and read_count < max_views:
                        tencent_logger.info(f"[删除流程-API] => 符合删除条件，立即删除")
                        
                        # 立即执行删除
                        success = await delete_violation_video(export_id, self.account_file, sessionid, wxuin)
                        if success:
                            delete_success_count += 1
                            tencent_logger.info(f"[删除流程-API] ✅ 删除成功 (已删除: {delete_success_count})")
                        else:
                            delete_fail_count += 1
                            tencent_logger.error(f"[删除流程-API] ❌ 删除失败 (失败: {delete_fail_count})")
                        
                        # ✅ 使用 asyncio.sleep 替代 time.sleep
                        await asyncio.sleep(1)  # 避免请求过快
                        should_continue = True
                    else:
                        tencent_logger.info(f"[删除流程-API] => 不符合删除条件")
                
                # 如果遇到了已处理的视频，停止翻页
                if stop_pagination:
                    tencent_logger.info(f"[删除流程-API] 已到达上次处理的时间节点，停止翻页")
                    break
                
                # 如果没有找到符合条件的视频且已检查完本页，检查是否需要翻页
                if not should_continue and len(video_list) >= page_size:
                    # 继续翻页查找
                    pass
                elif len(video_list) < page_size:
                    # 已到最后一页
                    tencent_logger.info(f"[删除流程-API] 已到最后一页，处理完成")
                    break
                
                current_page += 1
                # ✅ 使用 asyncio.sleep 替代 time.sleep
                await asyncio.sleep(0.5)
            
            tencent_logger.info(f"[删除流程-API] 删除完成：成功 {delete_success_count} 个，失败 {delete_fail_count} 个")
            
            # 更新用户的最后删除视频时间戳（使用第一页第一条视频的发布时间）
            if user_id and first_video_timestamp:
                try:
                    from db_manager import get_db_manager
                    
                    db_manager = get_db_manager()
                    
                    # 更新最后删除时的视频时间戳
                    db_manager.update_user(user_id, {'last_delete_video_timestamp': first_video_timestamp})
                    tencent_logger.info(f"[删除流程-API] ✅ 已更新最后删除视频时间戳: {first_video_timestamp} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(first_video_timestamp))})")
                except Exception as e:
                    tencent_logger.warning(f"[删除流程-API] 更新最后删除时间戳失败: {str(e)}")
            
        except Exception as e:
            tencent_logger.exception(f"[删除流程-API] 删除视频时出错：{str(e)}")

    async def add_short_play_by_baobai(self, page,idx=1,need_click =True):
        # 等待并点击"选择链接"按钮
        baobai_lj = pub_config.get('baobai_lj')
        baobai_duanju_selector = pub_config.get('baobai_duanju_selector')
        baobai_xzjj_selector = pub_config.get('baobai_xzjj_selector')
        baobai_input_selector = pub_config.get('baobai_input_selector')
        # 短剧选择器配置
        drama_item_selector = pub_config.get('drama_item_selector')
        drama_title_selector = pub_config.get('drama_title_selector')
        drama_extinfo_selector = pub_config.get('drama_extinfo_selector')
        drama_theater_selector = pub_config.get('drama_theater_selector')
        
        if idx==1:
            await page.wait_for_selector(baobai_lj, state='visible', timeout=5000)
            await page.click(baobai_lj)
            # 等待并点击"短剧"选项，使用精确匹配
            await page.wait_for_selector(baobai_duanju_selector, state='visible', timeout=5000)
            await page.click(baobai_duanju_selector)
            # 等待并点击"选择需要添加的短剧"按钮
            await page.wait_for_selector(baobai_xzjj_selector, state='visible', timeout=5000)
            await page.click(baobai_xzjj_selector)
            # 等待输入框出现
            await page.wait_for_selector(baobai_input_selector, state='visible', timeout=5000)
            await page.click(baobai_input_selector)
        anchor_info = self.info.get("anchor_info", None)
        if not anchor_info:
            raise UpdateError(f"未找到挂短剧参数：{anchor_info}")

        # 获取展示剧名和搜索剧名
        display_name = anchor_info.get("display_name", None)
        search_name = anchor_info.get("search_name", None)
        theater = anchor_info.get("theater", None)

        # 如果没有设置专门的搜索剧名和展示剧名，则使用旧逻辑的剧名
        playlet_title = anchor_info.get("title", None)
        if not playlet_title:
            raise UpdateError(f"未找到挂短剧参数：{playlet_title}")

        # 优先使用搜索剧名进行搜索
        search_title = search_name if search_name else playlet_title
        # 优先使用展示剧名进行匹配
        match_title = display_name if display_name else playlet_title
        jishu = anchor_info.get("jishu", None)
        tencent_logger.info(f"  [视频号上传] {self.file_path} 开始添加短剧: 搜索剧名[{search_title}] 展示剧名[{match_title}]")

        # 填充短剧名称
        # 设置开始时间和超时时间
        start_time = time.time()
        timeout = 120  # 20秒超时
        found = False
        retry_count = 0
        page_index = 1
        match_drama_name = anchor_info.get("match_drama_name", None)
        search_activity_input = page.locator(baobai_input_selector)
        await search_activity_input.fill(search_title)
        while time.time() - start_time < timeout:
            try:
                if page_index == 1:
                    # await search_activity_input.clear()
                    await search_activity_input.fill(search_title)
                    await asyncio.sleep(2)
                await page.wait_for_selector(drama_title_selector, timeout=5000)

                # 直接获取所有非禁用短剧项中的标题元素
                drama_text_elements = await page.locator(drama_item_selector).all()

                # 遍历所有短剧标题元素
                for text_element in drama_text_elements:
                    title_element = text_element.locator(drama_title_selector)
                    extinfo = await text_element.locator(drama_extinfo_selector).text_content()
                    theater_gf = await text_element.locator(drama_theater_selector).text_content()

                    # 获取标题文本
                    text_content = await title_element.text_content()
                    tencent_logger.info(f'  [视频号上传] {self.file_path} 找到短剧标题：{text_content}   jishu:{jishu} match_title:{match_title}  theater_gf {theater_gf}')

                    # 检查标题是否匹配
                    if not jishu or (jishu and str(jishu) in extinfo):
                        # 获取忽略标点设置
                        ignore_punctuation = anchor_info.get("ignore_punctuation", False)
                        
                        # 根据设置决定是否移除标点符号
                        if ignore_punctuation:
                            compare_match_title = remove_punctuation(match_title)
                            compare_text_content = remove_punctuation(text_content)
                            tencent_logger.info(f'  [视频号上传] {self.file_path} 忽略标点对比：[{compare_match_title}] vs [{compare_text_content}]')
                        else:
                            compare_match_title = match_title
                            compare_text_content = text_content
                        
                        if match_drama_name:
                            have_platlet = compare_match_title == compare_text_content
                        else:
                            have_platlet = compare_match_title in compare_text_content
                    else:
                        have_platlet = False
                    if have_platlet:
                        if not theater or theater == theater_gf:
                            if need_click:
                                await title_element.evaluate('el => el.click()')
                                tencent_logger.info(f'  [视频号上传] {self.file_path} 点击了剧场为{theater}  {theater_gf} 匹配【{match_title}】的{jishu}短剧')
                            found = True
                            break
                        else:
                            tencent_logger.info(f'  [视频号上传] {self.file_path} 配置的剧场为{theater}与当前剧场{theater_gf}不匹配')

                if found:
                    break

                retry_count += 1

                # 如果循环3次还没找到，尝试翻页
                if retry_count >= 2:
                    # 查找下一页按钮
                    next_page = page.locator('a:has-text("下一页"):visible')
                    if await next_page.count() > 0 and await next_page.is_visible():
                        tencent_logger.info(f'  [视频号上传] {self.file_path} 当前页未找到，点击下一页继续查找')
                        await next_page.click()
                        # 重置重试计数
                        retry_count = 0
                        page_index += 1
                        # 等待页面加载
                        await asyncio.sleep(1)
                    else:
                        break

                tencent_logger.info(f'  [视频号上传] {self.file_path} 未找到匹配元素，等待0.5秒后重试...')
                await asyncio.sleep(0.5)

            except Exception as e:
                tencent_logger.exception(f'  [视频号上传] {self.file_path} 查找高亮元素时发生错误')
                await asyncio.sleep(0.5)
                continue

        if not found:
            tencent_logger.error(f'  [视频号上传] {self.file_path} 超时{timeout}秒，未找到匹配【{match_title}】的短剧')
            raise UpdateError(f"  [视频号上传] {self.file_path} 未找到匹配的短剧：{match_title}")

    # async def add_short_title(self, page):
    #     short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
    #         "xpath=following-sibling::div").locator(
    #         'span input[type="text"]')
    #     if await short_title_element.count():
    #         short_title = format_str_for_short_title(self.title)
    #         await short_title_element.fill(short_title)

    async def click_publish(self, page):
        # 在点击发布按钮之前，先处理封面编辑
        if self.thumbnail_path:
            await self.edit_thumbnail(page)
        
        start_time = time.time()
        timeout = 120  # 两分钟超时
        while True:
            try:
                # 检查是否超时
                if time.time() - start_time > timeout:
                    raise UpdateError(f"  [视频号上传] {self.file_path} 发布操作超过两分钟，强制结束{self.file_path}")

                await asyncio.sleep(2)
                # 检查是否出现"将此次编辑保留?"文本
                has_edit_retain = await page.locator('div:has-text("将此次编辑保留?")').count() > 0
                tencent_logger.info(f"  [视频号上传] {self.file_path} 是否找到编辑保留提示框: {has_edit_retain}")

                if has_edit_retain:
                    # 查找并点击"不保存"按钮，直接校验可见性
                    no_save_button = page.locator('button:has-text("不保存"):visible')
                    has_no_save_button = await no_save_button.count() > 0
                    if has_no_save_button:
                        await no_save_button.click()
                        await page.goto('https://channels.weixin.qq.com/platform/post/list')
                        tencent_logger.info(f"  [视频号上传] {self.file_path} 已点击不保存按钮")
                        break
                    else:
                        tencent_logger.warning(f"  [视频号上传] {self.file_path} 未找到可见的不保存按钮")

                up_button = pub_config.get('up_button')
                publish_buttion = page.locator(up_button)
                if await publish_buttion.count():
                    await publish_buttion.click()
                    tencent_logger.info(f"  [视频号上传] {self.file_path} 已点击发布按钮")
                await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=1500)
                tencent_logger.success(f"  [视频号上传] {self.file_path} 视频发布成功")
                # 等待2秒再跳转
                await asyncio.sleep(2)
                break
            except UpdateError as e:
                raise e
            except Exception as e:
                if 'Target page, context or browser has been closed' in e.message:
                    raise e  # 直接抛出异常
                current_url = page.url
                if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                    tencent_logger.success(f"  [视频号上传] {self.file_path} 视频发布成功")
                    # 等待2秒再跳转
                    await asyncio.sleep(2)
                    break
                else:
                    tencent_logger.exception(f"  [视频号上传] {self.file_path} Exception: {e}")
                    tencent_logger.info(f"  [视频号上传] {self.file_path} 视频正在发布中...")
                    await asyncio.sleep(0.5)

    async def detect_upload_status(self, page):
        upload_tip_count = 0  # 记录upload-tip标签出现的次数
        last_progress_text = None  # 上次进度文本
        progress_unchanged_start = None  # 进度未变化的起始时间
        PROGRESS_TIMEOUT = 300  # 5分钟超时（秒）
        
        while True:
            # 匹配删除按钮，代表视频上传完毕，如果不存在，代表视频正在上传，则等待
            try:
                try:
                    # 检测是否出现了class为upload-tip的标签（仅当页面可见时计数）
                    visible_upload_tips = await page.locator('.upload-tip:visible').count()
                    if visible_upload_tips > 0:
                        upload_tip_count += 1
                        tencent_logger.warning(f"  [视频号上传] {self.file_path} 检测到upload-tip标签（第{upload_tip_count}次）")

                        # 如果出现三次，抛出异常
                        if upload_tip_count >= 3:
                            msg = f"  [视频号上传] {self.file_path} 上传视频解析失败，请检查视频"
                            tencent_logger.error(msg)
                            raise UpdateError(msg)

                    # 检测 ant-progress-text 进度是否停滞
                    progress_locator = page.locator('.ant-progress-text')
                    if await progress_locator.count() > 0:
                        current_progress_text = await progress_locator.first.inner_text()
                        current_time = time.time()

                        # 检查是否包含 check-circle 图标（上传完成但卡住）
                        check_circle_locator = page.locator('i[aria-label="图标: check-circle"]')
                        has_check_circle = await check_circle_locator.count() > 0

                        if last_progress_text is None:
                            last_progress_text = current_progress_text
                            progress_unchanged_start = current_time
                        elif current_progress_text == last_progress_text or has_check_circle:
                            # 进度未变化或已完成但卡住，检查是否超过5分钟
                            elapsed = current_time - progress_unchanged_start
                            if elapsed >= PROGRESS_TIMEOUT:
                                if has_check_circle:
                                    msg = f"  [视频号上传] {self.file_path} 上传已完成但5分钟无响应，可能异常"
                                else:
                                    msg = f"  [视频号上传] {self.file_path} 上传进度已经5分钟没有变动（{current_progress_text}），可能异常"
                                tencent_logger.error(msg)
                                raise UpdateError(msg)
                            else:
                                tencent_logger.info(f"  [视频号上传] {self.file_path} 进度未变化: {current_progress_text}，已等待 {int(elapsed)} 秒")
                        else:
                            # 进度有变化，重置计时
                            last_progress_text = current_progress_text
                            progress_unchanged_start = current_time
                except UpdateError as e:
                    raise e
                except:
                    tencent_logger.info(f"  [视频号上传] {self.file_path} 校验视频进度异常，可能给class已经变更...")

                # 匹配删除按钮，代表视频上传完毕
                if "weui-desktop-btn_disabled" not in await page.get_by_role("button", name="发表").get_attribute(
                        'class'):
                    tencent_logger.info(f"  [视频号上传] {self.file_path} 视频上传完毕")
                    break
                else:
                    await asyncio.sleep(2)
                    # 出错了视频出错
                    if await page.locator('div.status-msg.error').count() and await page.locator(
                            'div.media-status-content div.tag-inner:has-text("删除")').count():
                        tencent_logger.error(f"  [视频号上传] {self.file_path} 发现上传出错了...准备重试")
                        await self.handle_upload_error(page)

            except UpdateError as e:
                raise e
            except Exception as e:
                tencent_logger.exception(f'  [视频号上传] {self.file_path} 上传中...')
                if 'Target page, context or browser has been closed' in e.message:
                    raise e  # 直接抛出异常
                tencent_logger.info(f"  [视频号上传] {self.file_path} 正在上传视频中...")
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        await page.locator("div.input-editor").click()
        await page.keyboard.type(self.title)
        await page.keyboard.press("Enter")
        for index, tag in enumerate(self.tags, start=1):
            await page.keyboard.type("#" + tag)
            await page.keyboard.press("Space")
        tencent_logger.info(f"  [视频号上传] {self.file_path} 成功添加hashtag: {len(self.tags)}")

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
                tencent_logger.exception(f'  [视频号上传] {self.file_path} 我知道了，没找到')
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

    async def edit_thumbnail(self, page):
        """编辑视频封面"""
        try:
            tencent_logger.info(f"  [视频号上传] {self.file_path} 开始处理封面编辑")
            
            # 等待 vertical-img-wrap 出现
            await page.wait_for_selector('.vertical-img-wrap', state='visible', timeout=10000)
            
            # 等待"文件上传中，请等待完成后再编辑"提示消失
            start_time = time.time()
            timeout = 60  # 最多等待60秒
            while time.time() - start_time < timeout:
                # 在 .vertical-img-wrap 下检查是否存在上传提示文本
                upload_tip = page.locator('.vertical-img-wrap :has-text("文件上传中，请等待完成后再编辑")')
                if await upload_tip.count() == 0:
                    tencent_logger.info(f"  [视频号上传] {self.file_path} 文件上传完成，可以编辑封面")
                    break
                tencent_logger.info(f"  [视频号上传] {self.file_path} 文件上传中，等待完成...")
                await asyncio.sleep(1)
            
            # 再次检查提示是否消失
            upload_tip = page.locator('.vertical-img-wrap :has-text("文件上传中，请等待完成后再编辑")')
            if await upload_tip.count() > 0:
                tencent_logger.warning(f"  [视频号上传] {self.file_path} 等待文件上传完成超时，跳过封面编辑")
                return
            
            # 检查"编辑"按钮是否存在
            edit_button = page.locator('.vertical-img-wrap:has-text("编辑")')
            
            if await edit_button.count() > 0:
                # 使用 JavaScript 点击，避免被其他元素遮挡
                await edit_button.evaluate('el => el.click()')
                tencent_logger.info(f"  [视频号上传] {self.file_path} 已点击编辑按钮")
                
                # 等待文件选择器出现
                file_input = page.locator('input[type="file"][accept*="image"]')
                await file_input.wait_for(state='attached', timeout=5000)
                
                # 上传封面图片
                await file_input.set_input_files(self.thumbnail_path)
                tencent_logger.info(f"  [视频号上传] {self.file_path} 已上传封面: {self.thumbnail_path}")
                
                # 等待并点击确认按钮（注意是"确认"不是"确定"）
                confirm_button = page.locator('button:has-text("确认"):visible')
                await confirm_button.wait_for(state='visible', timeout=5000)
                await confirm_button.click()
                tencent_logger.success(f"  [视频号上传] {self.file_path} 封面编辑完成")
                
                # 等待一下确保操作完成
                await asyncio.sleep(1)
            else:
                tencent_logger.info(f"  [视频号上传] {self.file_path} 未找到编辑按钮")
                
        except Exception as e:
            tencent_logger.exception(f"  [视频号上传] {self.file_path} 编辑封面时出错: {str(e)}")
            # 封面编辑失败不影响发布流程，继续执行

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
                tencent_logger.warning(f"  [视频号上传] {self.file_path} 等待合集列表加载超时")
                return False
            await asyncio.sleep(0.5)

        found = False
        last_count = 0

        while not found:
            # 获取当前所有合集元素
            collection_elements = await page.locator('.option-list-wrap').locator(
                '.option-item .item:not(:has-text("创建新合集"))').all()
            current_count = len(collection_elements)
            tencent_logger.info(f'  [视频号上传] {self.file_path} 当前找到 {current_count} 个合集')

            # 如果数量没有增加,说明已经到底了
            if current_count == last_count:
                tencent_logger.info(f'  [视频号上传] {self.file_path} 合集数量未增加，可能已到底部')
                break

            # 查找匹配的合集
            for element in collection_elements:
                text = await element.locator('.name').text_content()
                tencent_logger.info(f'  [视频号上传] {self.file_path} 找到合集：{text} 需要选择合集：{self.collection}')
                if text.strip() == self.collection:
                    # 使用JavaScript来执行点击操作
                    await element.evaluate('el => el.click()')
                    tencent_logger.info(f"  [视频号上传] {self.file_path} 成功选择合集: {self.collection}")
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
                        tencent_logger.info(f'  [视频号上传] {self.file_path} 找到滚动容器，位置: {box}')
                        # 先滚动到底部
                        await page.evaluate('''(container) => {
                            if (container) {
                                const prevHeight = container.scrollHeight;
                                container.scrollTop = prevHeight;
                                return { success: true, prevHeight: prevHeight };
                            }
                            return { success: false };
                        }''', await scroll_container.element_handle())
                        tencent_logger.info('  [视频号上传] {self.file_path} 已执行滚动到底部操作')

                        # 等待一下让内容加载
                        await asyncio.sleep(0.5)

                        # 先向上滚动一段距离
                        await page.evaluate('''(container) => {
                            if (container) {
                                const currentScrollTop = container.scrollTop;
                                container.scrollTop = Math.max(0, currentScrollTop - container.clientHeight / 3);
                                return { success: true, scrolledTo: container.scrollTop };
                            }
                            return { success: false };
                        }''', await scroll_container.element_handle())
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
                    else:
                        tencent_logger.warning(f'  [视频号上传] {self.file_path} 找到滚动容器但无法获取位置信息')
                else:
                    tencent_logger.warning(f'  [视频号上传] {self.file_path} 未找到滚动容器')
            except Exception as e:
                tencent_logger.exception(f'  [视频号上传] {self.file_path} 滚动操作出错: {str(e)}')

            # 等待新内容加载
            await asyncio.sleep(1)

        return found


    async def main(self):
        return await dispatch_upload(self)

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
