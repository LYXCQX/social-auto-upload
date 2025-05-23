# -*- coding: utf-8 -*-
import asyncio
import time
from datetime import datetime

from playwright.async_api import async_playwright
from social_auto_upload.utils.log import tencent_logger

from social_auto_upload.utils.base_social_media import set_init_script


async def delete_video(local_executable_path, account_file, minutes_ago, max_views):
    async with async_playwright() as playwright:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(headless=False, executable_path=local_executable_path)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{account_file}")
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com/platform/post/list",timeout=300000)
        await delete_videos_by_conditions(page, minutes_ago=int(minutes_ago), max_views=int(max_views))
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()


async def delete_videos_by_conditions(page, minutes_ago=None, max_views=None):
    """
    根据时间间隔和播放量条件删除视频
    :param page: 页面对象
    :param minutes_ago: 多少分钟之前的视频
    :param max_views: 最大播放量
    :return:
    """
    if not minutes_ago and not max_views:
        tencent_logger.info("[删除流程] 未设置删除条件，跳过删除")
        return

    tencent_logger.info(f"[删除流程] 开始删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views}")
    try:
        start_time = time.time()
        timeout = 300  # 5分钟超时
        page_reload = True
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            tencent_logger.info(f"[删除流程] 当前循环已运行 {elapsed:.2f} 秒")

            if elapsed > timeout:
                tencent_logger.warning(f"[删除流程] 删除操作超过{timeout}秒，自动结束")
                break
            if page_reload:
                # 刷新页面
                tencent_logger.info("[删除流程] 刷新页面")
                await page.reload()
                await asyncio.sleep(1)

            try:
                tencent_logger.info("[删除流程] 等待视频列表加载")
                await page.wait_for_selector('.post-feed-item', timeout=1000000)
            except Exception as e:
                tencent_logger.error(f"[删除流程] 等待视频列表加载超时: {str(e)}")
                return

            # 获取所有视频项
            feed_items = await page.locator('.post-feed-item').all()
            if not feed_items:
                tencent_logger.warning("[删除流程] 未找到任何视频项")
                break

            feed_count = len(feed_items)
            tencent_logger.info(f"[删除流程] 找到 {feed_count} 个视频项")

            deleted_count = 0
            current_index = 0
            while current_index < len(feed_items):
                try:
                    item = feed_items[current_index]
                    # 获取发布时间
                    post_time_element = item.locator('.post-time')
                    if await post_time_element.count() > 0:
                        post_time_str = await post_time_element.text_content()
                        # 解析发布时间
                        post_time = datetime.strptime(post_time_str, '%Y年%m月%d日 %H:%M')
                        current_time = datetime.now()
                        time_diff = (current_time - post_time).total_seconds() / 60  # 转换为分钟

                        # 获取播放量
                        views_element = item.locator('.weui-icon-outlined-eyes-on').locator('..').locator('.count')
                        views_count = await views_element.text_content()
                        views_count = parse_view_count(views_count)
                        
                        # 获取视频标题用于日志
                        title = await item.locator('.post-title').text_content()
                        
                        # 记录详细的比对信息
                        tencent_logger.info(f"[删除流程] 视频信息比对:")
                        tencent_logger.info(f"[删除流程] - 标题: {title}")
                        tencent_logger.info(f"[删除流程] - 发布时间: {post_time_str} ({time_diff:.0f}分钟前)")
                        tencent_logger.info(f"[删除流程] - 播放量: {views_count}")
                        tencent_logger.info(f"[删除流程] - 条件比对: 时间>{minutes_ago}分钟 且 播放量<{max_views}")
                        tencent_logger.info(f"[删除流程] - 实际数据: {time_diff:.0f}>{minutes_ago} 且 {views_count}<{max_views}")

                        # 检查是否满足删除条件
                        should_delete = False
                        if minutes_ago and time_diff > minutes_ago and max_views and views_count < max_views:
                            should_delete = True
                            tencent_logger.info(f"[删除流程] => 符合删除条件")
                        else:
                            tencent_logger.info(f"[删除流程] => 不符合删除条件")

                        if should_delete:
                            # 执行删除
                            delete_button = item.locator('text=删除')
                            if await delete_button.count() > 0:
                                tencent_logger.info(
                                    f"[删除流程] 找到符合条件的视频，准备删除{await item.locator('.post-title').text_content()}")
                                await delete_button.locator('..').locator('.opr-item').evaluate('el => el.click()')
                                await page.click(':text-is("确定")')
                                deleted_count += 1
                                await asyncio.sleep(2)
                                # 删除后重新获取视频列表
                                feed_items = await page.locator('.post-feed-item').all()
                                # 不增加索引，因为当前项已被删除，下一项会变成当前索引位置
                                continue

                    current_index += 1
                except Exception as e:
                    tencent_logger.exception(f"[删除流程] 处理视频项时出错：{str(e)}")
                    current_index += 1
                    continue
            tencent_logger.info(f"[删除流程] 当前页面处理完毕，检验是否有下一页 deleted_count：{deleted_count}")
            if deleted_count == 0:
                # 检查是否有下一页
                try:
                    footer = page.locator('.post-list-footer')
                    tencent_logger.info(f"[删除流程] 当前页面处理完毕，检验是否有下一页 footer.count：{await footer.count()}")
                    if await footer.count() > 0:
                        next_page = footer.locator('a:text("下一页")')
                        tencent_logger.info(f"[删除流程] 当前页面处理完毕，检验是否有下一页 next_page：{await next_page.count()}")
                        if await next_page.count() > 0:
                            tencent_logger.info("[删除流程] 当前页面处理完毕，点击下一页")
                            await next_page.click()
                            await asyncio.sleep(2)  # 等待页面加载
                            page_reload = False
                            continue
                except Exception as e:
                    tencent_logger.exception(f"[删除流程] 检查下一页按钮时出错：{str(e)}")

                tencent_logger.info("[删除流程] 所有页面处理完毕，删除操作完成")
                break

    except Exception as e:
        tencent_logger.exception(f"[删除流程] 删除视频时出错：{str(e)}")

def parse_view_count(view_str):
    """
    解析播放量字符串为整数
    :param view_str: 播放量字符串，如 "1.4万"
    :return: 整数形式的播放量
    """
    try:
        if '万' in view_str:
            num = float(view_str.replace('万', ''))
            return int(num * 10000)
        return int(view_str)
    except Exception as e:
        tencent_logger.error(f"[删除流程] 解析播放量出错：{str(e)}，原始值：{view_str}")
        return 0

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
