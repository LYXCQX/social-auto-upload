import asyncio
import os
import re
from typing import Optional, Any, Coroutine

from patchright.async_api import async_playwright, Page, Browser, BrowserContext

from social_auto_upload.conf import BASE_DIR
from social_auto_upload.utils.log import douyin_logger
from social_auto_upload.utils.base_social_media import set_init_script
from social_auto_upload.utils.bus_exception import UpdateError


async def fx_login(account_file=None,local_executable_path: Optional[str] = None) -> bool:
    """
    分销平台登录函数
    打开 https://stardistribute.qinronmedia.com/#/login
    等待页面出现"星图水下业务"文字后保存cookie
    """
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    
    try:
        # 确保分销cookies目录存在
        fx_cookies_dir = os.path.join(BASE_DIR, 'cookies', 'fx')
        if not os.path.exists(fx_cookies_dir):
            os.makedirs(fx_cookies_dir)

        async with async_playwright() as playwright:
            # 启动浏览器（非无头模式）
            browser = await playwright.chromium.launch(headless=False,
                                                       executable_path=local_executable_path)
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context,os.path.basename(account_file) if account_file else None)
            page = await context.new_page()

            # 导航到分销登录页面
            await page.goto("https://stardistribute.qinronmedia.com/#/login")
            
            # 等待页面加载完成，检查是否出现"星图水下业务"文字
            try:
                await page.wait_for_selector('text=星图水下业务', timeout=300000)  # 2分钟超时
                
                # 等待用户信息区域加载完成
                await page.wait_for_selector('.user-info', timeout=30000)
                
                # 提取用户名和账号ID
                user_info = await page.query_selector('.user-info')
                if user_info:
                    # 提取用户名
                    username_element = await user_info.query_selector('div.list:has(label:text("用户名：")) span')
                    username = await username_element.text_content() if username_element else "unknown"
                    
                    # 提取账号ID
                    userid_element = await user_info.query_selector('div.list:has(label:text("账号ID：")) span')
                    userid = await userid_element.text_content() if userid_element else "unknown"
                    
                    # 清理提取的文本
                    username = username.replace("修改密码", "").strip() if username else "unknown"
                    userid = userid.strip() if userid else "unknown"
                    
                    # 保存cookie到文件
                    cookie_file = os.path.join(fx_cookies_dir, f'{username}-{userid}.json')
                    await context.storage_state(path=cookie_file)
                    
                    douyin_logger.info(f"分销登录成功，用户: {username}, ID: {userid}")
                    return True
                else:
                    douyin_logger.error("未找到用户信息区域")
                    return False
                    
            except Exception as e:
                douyin_logger.error(f"等待页面元素超时或失败: {str(e)}")
                return False

    except Exception as e:
        douyin_logger.exception(f"分销登录过程中出错: {str(e)}")
        return False
    finally:
        # 确保浏览器资源被正确关闭
        try:
            if context:
                await context.close()
            if browser:
                await browser.close()
        except Exception as close_error:
            douyin_logger.exception("关闭浏览器资源时出错")

async def fx_publish_material(account_file, material_data, local_executable_path: Optional[str] = None) -> bool | None | \
                                                                                                           list[Any]:
    """
    分销平台发布素材功能
    进入 https://stardistribute.qinronmedia.com/#/StarMapUnderwater/MaterialRelease
    点击添加素材按钮，填充表格并提交
    """
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None

    try:
        async with async_playwright() as playwright:
            print(account_file)
            # 启动浏览器（非无头模式）
            browser = await playwright.chromium.launch(headless=False,
                                                       executable_path=local_executable_path)
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context, os.path.basename(account_file))
            page = await context.new_page()

            return await fx_publish(material_data, page)

    except Exception as e:
        douyin_logger.exception(f"分销素材发布过程中出错: {str(e)}")
        return False
    finally:
        # 确保浏览器资源被正确关闭
        try:
            if context:
                await context.close()
            if browser:
                await browser.close()
        except Exception as close_error:
            douyin_logger.exception("关闭浏览器资源时出错")


async def fx_publish(material_data, page,parent_):
    # 导航到素材发布页面
    await page.goto("https://stardistribute.qinronmedia.com/#/StarMapUnderwater/MaterialRelease")
    # 等待页面加载完成
    await page.wait_for_selector('text=添加素材', timeout=120000)
    # 点击添加素材按钮
    await page.click('text=添加素材')
    # 等待表单加载
    await page.wait_for_selector('.arco-drawer-container', state='attached', timeout=30000)
    up_tk = await page.query_selector('.arco-drawer-container')
    # 填充抖音号
    if 'user_id' in material_data:
        await page.fill('.arco-drawer-container #douyin_id input[type="text"]', material_data['user_id'])
    # 填充抖音昵称
    if 'username' in material_data:
        await page.fill('.arco-drawer-container #douyin_nickname input[type="text"]', material_data['username'])
    # 选择短剧名称（如果有）
    anchor_info = material_data.get("anchor_info", None)
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
    # 暂时使用输入框方式
    drama_input = await page.query_selector('.arco-drawer-container #upstream_video_id input')
    if drama_input:
        await drama_input.fill(search_title)
        # 等待剧名下拉框出现并可见
        await page.wait_for_selector('.arco-trigger-popup-wrapper:not([style*="display: none"])', timeout=30000)
        await asyncio.sleep(2)
        have_video =False
        # 获取所有li元素内容并匹配
        li_elements = await page.query_selector_all('.arco-trigger-popup-wrapper:not([style*="display: none"]) li')
        for li in li_elements:
            text = await li.text_content()
            if not text:
                continue

            # 提取纯文本部分(去掉括号内容)
            pure_text = text.split('(')[0].strip()
            # 完整匹配或部分匹配
            if match_title in text or match_title == pure_text:
                douyin_logger.info(f"fx_publish | 匹配到短剧选项: text={text}，执行选择")
                await li.click()
                have_video = True
                break
        if not have_video:
            raise UpdateError(f"分销上传未找到相关短剧")
    # 上传素材文件
    files = [parent_.file_path]
    if files:
        # 等待文件输入元素
        await up_tk.wait_for_selector('input[type="file"][accept="video/*"]', state='attached', timeout=30000)
        file_input = await up_tk.query_selector('input[type="file"][accept="video/*"]')
        # 设置多个文件路径
        if file_input:
            if material_data.get('videos'):
                files = [video_info['path'] for video_info in material_data.get('videos')[:20] if 'path' in video_info]
            await file_input.set_input_files(files)
    else:
        raise UpdateError(f"分销上传未找到相关短剧")
    # # 填充素材名称
    # if 'material_name' in material_data:
    #     await page.fill('.arco-drawer-container #upstream_video_id input', parent_.title)
    # 设置预计发布时间（如果需要）
    if parent_.publish_date and parent_.publish_date != 0:
        time_input = await up_tk.query_selector('#expect_publish_time input')
        if time_input:
            publish_date_hour = parent_.publish_date.strftime("%Y-%m-%d %H:%M")
            await asyncio.sleep(1)
            await time_input.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.type(str(publish_date_hour))
            await page.keyboard.press("Enter")
    # 点击确定按钮提交表单
    # 在提交前等待进度条消失（确保 [role="progressbar"] 数量为 0）
    try:
        # 优先在当前抽屉范围内等待
        await up_tk.wait_for_selector('[role="progressbar"]', state='detached', timeout=7200000)
    except Exception:
        try:
            await page.wait_for_function(
                '() => document.querySelectorAll("[role=\\"progressbar\\"]").length === 0',
                timeout=7200000
            )
        except Exception:
            douyin_logger.error("fx_publish | 页面级等待进度条失败或超时")
            pass
    submit_button = await up_tk.query_selector('.arco-drawer-footer button:has-text("确定")')
    if submit_button:
        await submit_button.click()
        await asyncio.sleep(2)
    return files


async def main():
    """测试函数"""
    result = await fx_login()
    print(f"登录结果: {result}")

if __name__ == "__main__":
    asyncio.run(main())