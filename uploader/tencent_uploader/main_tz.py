# -*- coding: utf-8 -*-
import asyncio
import os
import time
from datetime import datetime

from playwright.async_api import async_playwright
from social_auto_upload.utils.log import tencent_logger

from social_auto_upload.utils.base_social_media import set_init_script

from social_auto_upload.utils.bus_exception import UpdateError


async def delete_video(local_executable_path, account_file, minutes_ago, max_views):
    async with async_playwright() as playwright:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(headless=False, executable_path=local_executable_path,
                                                   args=[ "--single-process","--no-zygote",'--mute-audio'])
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{account_file}")
        context = await set_init_script(context,os.path.basename(account_file))
        # 创建一个新的页面
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com/platform/post/list",timeout=300000)
        await delete_videos_by_conditions(page, minutes_ago=int(minutes_ago), max_views=int(max_views))
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()


async def delete_videos_by_conditions(page, minutes_ago=None, max_views=None,page_index=0,video_title=None):
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
    await page.goto('https://channels.weixin.qq.com/platform/post/list')
    tencent_logger.info(f"[删除流程] 开始删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views} 且 标题为{video_title} 且 页码为{page_index}")
    try:
        start_time = time.time()
        timeout = 300  # 5分钟超时
        page_reload = True
        current_page = 0
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
            tencent_logger.info(f"[删除流程] 找到 {feed_count} 个视频项 current_page ={current_page}")
            if 0 < page_index <= current_page:
                return
            deleted_count = 0
            current_index = 0
            while current_index < len(feed_items):
                try:
                    item = feed_items[current_index]
                    # 获取发布时间
                    post_time_element = item.locator('.post-time')
                    should_delete = False
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
                        try:
                            if await item.locator('.post-title').count()>0:
                                title = await item.locator('.post-title').text_content()
                            else:
                                title = ''
                        except Exception as e:
                            tencent_logger.error(f"[删除流程] 获取视频标题时出错: {str(e)}")
                            title = ''
                        
                        # 记录详细的比对信息
                        tencent_logger.info(f"[删除流程] 视频信息比对:")
                        tencent_logger.info(f"[删除流程] - 标题: {title}")
                        tencent_logger.info(f"[删除流程] - 发布时间: {post_time_str} ({time_diff:.0f}分钟前)")
                        tencent_logger.info(f"[删除流程] - 播放量: {views_count}")
                        tencent_logger.info(f"[删除流程] - 条件比对: 时间>{minutes_ago}分钟 且 播放量<{max_views}")
                        tencent_logger.info(f"[删除流程] - 实际数据: {time_diff:.0f}>{minutes_ago} 且 {views_count}<{max_views}")
                        # 检查是否满足删除条件
                        if video_title:
                            if title.startswith(video_title) and  minutes_ago is not None and time_diff >= minutes_ago and max_views is not None and views_count < max_views:
                                should_delete = True
                                tencent_logger.info(f"[删除流程] => 符合删除条件")
                        else :
                            if  minutes_ago is not None and time_diff >= minutes_ago and max_views is not None and views_count < max_views:
                                should_delete = True
                                tencent_logger.info(f"[删除流程] => 符合删除条件")
                            else:
                                tencent_logger.info(f"[删除流程] => 不符合删除条件")
                        item_title = item.locator('.post-title')
                        if await item_title.count() > 0:
                            title_text = await item_title.text_content()
                            if title_text.startswith('waitdel-'):
                                should_delete = True
                                tencent_logger.info(f"[删除流程] => waitdel-视频符合删除条件")
                    else:
                        fail_video = await item.locator('.post-processed-fail').count()
                        if fail_video > 0:
                            should_delete = True
                            tencent_logger.info(f"[删除流程] => 错误视频符合删除条件")
                    if should_delete:
                        # 执行删除
                        delete_button = item.locator('text=删除')
                        if await delete_button.count() > 0:
                            tencent_logger.info(f"[删除流程] 找到符合条件的视频，准备删除")
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
                            current_page += 1
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


async def add_original(parent_, page):
    if not parent_.declare_original:
        tencent_logger.info('未启用声明原创功能')
        return
    if await page.get_by_label("视频为原创").count():
        await page.get_by_label("视频为原创").check()
    # 检查 "我已阅读并同意 《视频号原创声明使用条款》" 元素是否存在
    label_locator = await page.locator('label:has-text("我已阅读并同意 《视频号原创声明使用条款》")').is_visible()
    if label_locator:
        await page.get_by_label("我已阅读并同意 《视频号原创声明使用条款》").check()
        await page.get_by_role("button", name="声明原创").click()
    # 2023年11月20日 wechat更新: 可能新账号或者改版账号，出现新的选择页面
    if await page.locator('div.label span:has-text("声明原创")').count() and parent_.category:
        # 因处罚无法勾选原创，故先判断是否可用
        if not await page.locator('div.declare-original-checkbox input.ant-checkbox-input').is_disabled():
            await page.locator('div.declare-original-checkbox input.ant-checkbox-input').click()
            if not await page.locator(
                    'div.declare-original-dialog label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible').count():
                await page.locator('div.declare-original-dialog input.ant-checkbox-input:visible').click()
        if await page.locator('div.original-type-form > div.form-label:has-text("原创类型"):visible').count():
            await page.locator('div.form-content:visible').click()  # 下拉菜单
            await page.locator(
                f'div.form-content:visible ul.weui-desktop-dropdown__list li.weui-desktop-dropdown__list-ele:has-text("{parent_.category}")').first.click()
            await page.wait_for_timeout(1000)
        if await page.locator('button:has-text("声明原创"):visible').count():
            await page.locator('button:has-text("声明原创"):visible').click()

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


async def add_short_play_by_juji(self, page,pub_config):
    # 等待并点击"选择链接"按钮
    baobai_lj = pub_config.get('baobai_lj')
    juji_jjxl = pub_config.get('juji_jjxl')
    juji_xzjj = pub_config.get('juji_xzjj')
    juji_jjss = pub_config.get('juji_jjss')
    await page.wait_for_selector(baobai_lj, state='visible', timeout=5000)
    await page.click(baobai_lj)
    # 等待并点击"短剧"选项，使用精确匹配
    await page.wait_for_selector(juji_jjxl, state='visible', timeout=5000)
    await page.click(juji_jjxl)
    # 等待并点击"选择需要添加的短剧"按钮
    await page.wait_for_selector(juji_xzjj, state='visible', timeout=5000)
    await page.click(juji_xzjj)
    # 等待输入框出现
    await page.wait_for_selector(juji_jjss, state='visible', timeout=5000)
    await page.click(juji_jjss)
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
    search_activity_input = page.locator(juji_jjss)
    await search_activity_input.fill(search_title)
    while time.time() - start_time < timeout:
        try:
            if page_index == 1:
                # await search_activity_input.clear()
                await search_activity_input.fill(search_title)
                await asyncio.sleep(2)
            # await page.wait_for_selector('.drama-title', timeout=5000)

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

async def add_comment(page, comment=None):
    try:
        try:
            tencent_logger.info("[评论流程] 等待视频列表加载")
            await page.wait_for_selector('.post-feed-item', timeout=1000000)
        except Exception as e:
            tencent_logger.error(f"[评论流程] 等待视频列表加载超时: {str(e)}")
            return

        # 获取所有视频项
        feed_items = await page.locator('.post-feed-item').filter(has_text='评论管理').all()
        if not feed_items:
            tencent_logger.warning("[评论流程] 未找到任何视频项")
            return
        comment_item = feed_items[0]
        comment_button = comment_item.locator('text="评论管理"')
        if await comment_button.count() > 0:
            await comment_button.locator('..').locator('.opr-item').evaluate('el => el.click()')
            # await page.click(':text-is("写评论 ")')
            await page.locator(':text-is("写评论 ")').evaluate('el => el.click()')
            search_activity_input = page.locator('textarea[placeholder="发表评论"]')
            await search_activity_input.fill(comment)

            comment_element = page.locator(".create-ft >> text=评论")
            await comment_element.wait_for(state="visible", timeout=10000)
            await comment_element.evaluate('el => el.click()')
            await page.wait_for_selector('text="置顶"', state='attached', timeout=5000)
            zd_element = page.locator('text="置顶"')
            await zd_element.evaluate('el => el.click()')
            tencent_logger.info(f"[评论流程] 评论发布完毕")
    except Exception as e:
        tencent_logger.exception(f"[评论流程] 评论视频时出错：{str(e)}")