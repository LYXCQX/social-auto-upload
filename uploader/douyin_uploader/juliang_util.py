# -*- coding: utf-8 -*-
import asyncio
import json
import os
import time
from types import SimpleNamespace
from urllib.parse import unquote_plus

from camoufox import AsyncCamoufox
from config import PLATFORM
from config_manager import ConfigManager
from dotenv import load_dotenv
from patchright.async_api import async_playwright
from social_auto_upload.utils.base_social_media import set_init_script
from social_auto_upload.utils.log import douyin_logger

from social_auto_upload.utils.bus_exception import UpdateError
from task_crawler import TaskCrawler, PlatformType, TaskType

from social_auto_upload.utils.camoufox_util import _get_camoufox_config

load_dotenv()


config = ConfigManager()
pub_config = json.loads(config.get(f'{PLATFORM}_pub_config',"{}")).get('douyin',{})
async def cookie_auth(account_file, local_executable_path=None,proxy_setting=None,camoufox=False,addons_path=None):
    if not local_executable_path or not os.path.exists(local_executable_path):
        douyin_logger.warning(f"浏览器路径无效: {local_executable_path}")
    if camoufox:
        camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path},account_file=account_file,hide_browser=True,proxy_setting=proxy_setting))
        async with AsyncCamoufox(**camoufox_config) as browser:
            return await cookie_auth_br(account_file, browser)
    else:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True,
                                                       executable_path=local_executable_path, proxy=proxy_setting)
            return await cookie_auth_br(account_file, browser)


async def cookie_auth_br(account_file, browser):

    context = await browser.new_context(storage_state=account_file)
    context = await set_init_script(context, os.path.basename(account_file))
    # 创建一个新的页面
    page = await context.new_page()
    # 访问指定的 URL
    await page.goto("https://www.xingtu.cn/sup/creator/user/overview")
    try:
        await page.wait_for_url(
            "https://www.xingtu.cn/sup/creator/user/overview", timeout=5000)
    except:
        douyin_logger.info("[+] 等待5秒 cookie 失效")
        try:
            if context:
                await context.close()
            if browser:
                await browser.close()
        except Exception as e:
            douyin_logger.exception(f"关闭浏览器资源时出错: {str(e)}")
        return False
    await asyncio.sleep(2)
    # 2024.06.17 抖音创作者中心改版
    if await page.get_by_text('星图资讯').count():
        douyin_logger.info("[+] 等待5秒 cookie 失效")
        return False
    else:
        douyin_logger.info("[+] cookie 有效")
        return True


async def juliang_setup(account_file, handle=False, local_executable_path=None, proxy_setting=None,camoufox=False,addons_path=None):
    if (account_file and not os.path.exists(account_file)) or not await cookie_auth(account_file, local_executable_path,proxy_setting,camoufox=camoufox,addons_path=addons_path):
        if not handle:
            # Todo alert message
            return False, None, None, None
        douyin_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        user_id, user_name, douyin_id = await juliang_cookie_gen(account_file, local_executable_path,proxy_setting,camoufox=camoufox,addons_path=addons_path)
    else:
        # 新增：从 account_file 的文件名中提取用户 id 和 name
        base_name = os.path.basename(account_file)
        print(base_name)
        douyin_id, douyin_user_name = base_name.split('_')[:2]  # 假设文件名格式为 "user_id_user_name_account.json"
        user_id = None
        user_name = None

    return True, user_id, user_name, douyin_id


async def get_user_id(page):
    global user_id, douyin_id
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
            
            douyin_id_element = basic_info.locator('text=抖音号:').first
            douyin_id_text = await douyin_id_element.text_content()
            douyin_parts = douyin_id_text.split("抖音号:")
            if len(douyin_parts) > 1:
                douyin_id = douyin_parts[1].split("<")[0].strip()
            else:
                douyin_id = ""
            douyin_logger.info(f"提取的抖音ID: {douyin_id}")
            if user_id == '0' or not user_id:
                douyin_logger.info(f"获取用户ID时失败")
            else:
                douyin_logger.info(f"成功获取ID，退出循环，返回user_id={user_id}, douyin_id={douyin_id}")
                break  # 退出循环
        except Exception as e:
            douyin_logger.exception(f"获取用户ID时发生错误：{str(e)}")
            await asyncio.sleep(0.5)
        current_time = time.time()  # 获取当前时间
        elapsed_time = current_time - start_time  # 计算已经过去的时间
        if elapsed_time > 30:  # 如果已经过去的时间超过30秒
            douyin_logger.info(f"超时30秒，退出循环，返回user_id={user_id}, douyin_id={douyin_id}")
            break  # 退出循环
    return user_id, douyin_id


async def juliang_cookie_gen(account_file, local_executable_path=None, proxy_setting=None,camoufox=False,addons_path=None):
    if camoufox:
        camoufox_config = await _get_camoufox_config(SimpleNamespace(info={'addons_path':addons_path},account_file=account_file,hide_browser=False,proxy_setting=proxy_setting))
        async with AsyncCamoufox(**camoufox_config) as browser:
            return await juliang_cookie_gen_br(account_file, browser)
    else:
        async with async_playwright() as playwright:
            # Make sure to run headed.
            browser = await playwright.chromium.launch(headless=False,
                                                       executable_path=local_executable_path,proxy=proxy_setting)
            return await juliang_cookie_gen_br(account_file, browser)


async def juliang_cookie_gen_br(account_file, browser):
    # Setup context however you like.
    context = await browser.new_context(storage_state=account_file)
    context = await set_init_script(context, os.path.basename(account_file))
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
    douyin_logger.info(f'---------{account_file}')
    # 点击调试器的继续，保存cookie
    await context.storage_state(path=account_file)
    try:
        if context:
            await context.close()
        if browser:
            await browser.close()
    except Exception as e:
        douyin_logger.exception(f"关闭浏览器资源时出错: {str(e)}")
    # return user_id, user_name, douyin_id


async def xt_have_task(page, playlet_title,pub_config):
    await page.goto("https://www.xingtu.cn/sup/creator/user/task")
    await page.wait_for_url("https://www.xingtu.cn/sup/creator/user/task*")

    # 检查"知道了"按钮是否存在，如果存在则点击
    try:
        know_button = page.locator('button:text("知道了")')
        if await know_button.count() > 0:
            await know_button.click()
    except:
        pass

    await page.click('text="进行中"')
    xt_search_rw = pub_config.get('xt_search_rw')
    search_input = page.locator(xt_search_rw)
    await search_input.fill(playlet_title)
    await page.keyboard.press('Enter')
    await page.wait_for_timeout(2000)  # 等待搜索结果加载

    # 获取所有可见的"去上传"按钮
    upload_buttons = page.locator('button:has-text("查看详情"):visible')
    upload_count = await upload_buttons.count()
    douyin_logger.info(f'[+] 找到 {upload_count} 个可见的去上传按钮')

    have_task = False
    # 如果找到按钮,点击第一个
    if upload_count > 0:
        try:
            first_button = upload_buttons.first
            if await first_button.is_visible():
                async with page.expect_popup() as popup_info:
                    await first_button.click()
                page = await popup_info.value
                douyin_logger.info('[+] 点击了去上传按钮')
                await page.wait_for_timeout(2000)
                have_task = True
            else:
                douyin_logger.warning('[!] 找到的去上传按钮不可见')
        except Exception as e:
            douyin_logger.error(f'[!] 点击去上传按钮失败: {str(e)}')

    return have_task, page



async def xt_check_login(parent_, auto_order, context, page, playlet_title):
    try:
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        have_task, page = await xt_have_task(page, playlet_title, pub_config)
        if not have_task:
            if auto_order:
                douyin_logger.info('[+] 检测到不在上传页面，需要新建任务')
                if parent_.info.get('douyin_publish_type') == '王牌智媒':
                    task_type = parent_.info.get('task_type_filter',TaskType.ALL)
                    commission_type=parent_.info.get('commission_type_filter')
                    publish_status=parent_.info.get('publish_status_filter')
                    star_ad_support=parent_.info.get('star_ad_support_filter')
                    reward_support=parent_.info.get('reward_support_filter')
                    crawler = TaskCrawler([playlet_title], PlatformType.DOUYIN, local_executable_path=parent_.local_executable_path, task_type=task_type,account_file=parent_.info.get('wp_account'),commission_type=commission_type,publish_status=publish_status,star_ad_support=star_ad_support,reward_support=reward_support)
                    task_url = await crawler.get_task_url()
                    if task_url:
                        await page.goto(unquote_plus(task_url))
                        new_feature_button = page.locator('button[type="button"] span:text("我知道了")')
                        if await new_feature_button.count() > 0:
                            await new_feature_button.click()
                        # task_detail_button = page.locator('button:has-text("任务详情"):visible')
                        xt_sj_xq = pub_config.get('xt_sj_xq')
                        rwxqc = await check_element_exists(page, xt_sj_xq)
                        if not rwxqc:
                            sj_cytg = pub_config.get('sj_cytg')
                            tougao_b = page.locator(sj_cytg)
                            await tougao_b.evaluate('el => el.click()')
                            douyin_logger.info('[+] 智能点击了存在的按钮')

                            # 等待页面出现 aria-labelledby="确认是否参与任务" 的元素
                            sj_sfcyrw = pub_config.get('sj_sfcyrw')
                            await page.wait_for_selector(sj_sfcyrw, state='visible', timeout=10000)
                            qrcyrw = page.locator(sj_sfcyrw)
                            # 检查是否有"已阅读并同意"文字，如果有则点击
                            agree_checkbox = qrcyrw.locator('text="已阅读并同意"')
                            if await agree_checkbox.count() > 0:
                                await agree_checkbox.click()
                                douyin_logger.info('[+] 点击了"已阅读并同意"复选框')

                            # 点击"参与投稿"按钮
                            # await qrcyrw.locator('text="参与投稿", text="立即预约"').click()
                            sj_djtg = pub_config.get('sj_djtg')
                            tougao = qrcyrw.locator(sj_djtg)
                            douyin_logger.info(f'[+] 找到了投稿按钮 {await tougao.count()}')
                            await tougao.evaluate('el => el.click()')
                            # await asyncio.sleep(2)
                            try:
                                await page.wait_for_selector(xt_sj_xq, state='visible', timeout=10000)
                            except:
                                douyin_logger.exception('[+] 等待任务详情失败')
                        page = await xt_check_login(parent_, auto_order, context, page, playlet_title)
                    else:
                        raise UpdateError(f"王牌接单失败:{playlet_title}")
                else:
                    have_task, page, n_url = await parent_.new_xt_task(page, playlet_title)
            else:
                douyin_logger.info('[+] 没有找到任务，也没有开启自动接单，直接返回')
                raise UpdateError(f"没有找到任务标签:{playlet_title}，也没有开启自动接单，请先接取任务")
        else:
            await asyncio.sleep(3)
            douyin_logger.info('[+] 已经存在任务，继续处理')
            have_task, page, n_url = await parent_.click_go_to_upload(have_task, page)
        return page
    finally:
        await context.storage_state(path=parent_.account_file)  # 保存cookie
        douyin_logger.success('  星图cookie更新完毕！')


async def check_element_exists(page, selector, timeout=3000):
    """
    检查元素是否存在且可见
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except:
        return False