# -*- coding: utf-8 -*-
import asyncio
import os
import time
import json
import hashlib
from datetime import datetime

from patchright.async_api import async_playwright
from social_auto_upload.utils.log import tencent_logger

from social_auto_upload.utils.base_social_media import set_init_script

from social_auto_upload.utils.bus_exception import UpdateError


def remove_punctuation(text: str) -> str:
    """移除字符串中的所有标点符号和空格"""
    import re
    # 使用正则表达式移除所有非字母数字字符（包括中英文标点和空格）
    return re.sub(r'[^\w]', '', text, flags=re.UNICODE)


async def delete_video(local_executable_path, account_file, minutes_ago, max_views, video_title=None):
    async with async_playwright() as playwright:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(headless=False, executable_path=local_executable_path)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(storage_state=f"{account_file}")
        context = await set_init_script(context,os.path.basename(account_file))
        # 创建一个新的页面
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com/platform/post/list",timeout=300000)
        await delete_videos_by_conditions(page, minutes_ago=int(minutes_ago), max_views=int(max_views), video_title=video_title)
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()


async def delete_videos_by_conditions(page, minutes_ago=None, max_views=None,page_index=0,video_title=None,only_delete_fail=False):
    """
    根据时间间隔和播放量条件删除视频
    :param page: 页面对象
    :param minutes_ago: 多少分钟之前的视频
    :param max_views: 最大播放量
    :param page_index: 处理到第几页停止（0表示全部处理）
    :param video_title: 视频标题前缀匹配
    :param only_delete_fail: 仅删除错误视频（.post-processed-fail）
    :return:
    """
    if not only_delete_fail and not minutes_ago and not max_views:
        tencent_logger.info("[删除流程] 未设置删除条件，跳过删除")
        return
    await page.goto('https://channels.weixin.qq.com/platform/post/list')
    if only_delete_fail:
        tencent_logger.info(f"[删除流程] 开始删除错误视频（仅删除 .post-processed-fail）")
    else:
        if video_title:
            tencent_logger.info(f"[删除流程] 开始删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views} 且 剧名为'{video_title}' 且 页码为{page_index}")
        else:
            tencent_logger.info(f"[删除流程] 开始删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views} 且 页码为{page_index}")
    try:
        start_time = time.time()
        timeout = 864000  # 5分钟超时
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
                await page.goto(page.url)
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
                    should_delete = False
                    
                    # 如果只删除错误视频，直接检查是否有 .post-processed-fail 元素
                    if only_delete_fail:
                        fail_video = await item.locator('.post-processed-fail').count()
                        if fail_video > 0:
                            should_delete = True
                            tencent_logger.info(f"[删除流程] => 找到错误视频，符合删除条件")
                    else:
                        # 原有的删除逻辑
                        # 获取发布时间
                        post_time_element = item.locator('.post-time')
                        if await post_time_element.count() > 0:
                            post_time_str = await post_time_element.text_content()
                            # 解析发布时间
                            post_time = datetime.strptime(post_time_str.replace('仅自己可见', ''), '%Y年%m月%d日 %H:%M')
                            current_time = datetime.now()
                            time_diff = (current_time - post_time).total_seconds() / 60  # 转换为分钟

                            # 获取播放量
                            views_element = item.locator('.weui-icon-outlined-eyes-on').locator('..').locator('.count')
                            views_count = await views_element.text_content()
                            views_count = parse_view_count(views_count)
                            
                            # 获取视频标题用于日志和比对
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
                            
                            # 检查剧名是否匹配（如果设置了剧名）
                            drama_name_match = True
                            if video_title:
                                drama_name_match = (video_title in title) if title else False
                                tencent_logger.info(f"[删除流程] - 剧名匹配: {drama_name_match} (标题包含'{video_title}')")
                            
                            tencent_logger.info(f"[删除流程] - 条件比对: 时间>={minutes_ago}分钟 且 播放量<{max_views}")
                            tencent_logger.info(f"[删除流程] - 实际数据: {time_diff:.0f}>={minutes_ago} 且 {views_count}<{max_views}")
                            
                            # 检查是否满足删除条件
                            if drama_name_match and minutes_ago is not None and time_diff >= minutes_ago and max_views is not None and views_count < max_views:
                                should_delete = True
                                tencent_logger.info(f"[删除流程] => 符合删除条件")
                            else:
                                tencent_logger.info(f"[删除流程] => 不符合删除条件")
                            
                            # 特殊处理：以 waitdel- 开头的视频直接删除
                            if title and title.startswith('waitdel-'):
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
                            await page.click(':text-is("确定"):visible')
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


async def add_short_play_by_juji(parent_, page,pub_config,idx=1,need_click =True):
    # 等待并点击"选择链接"按钮
    baobai_lj = pub_config.get('baobai_lj')
    juji_jjxl = pub_config.get('juji_jjxl')
    juji_xzjj = pub_config.get('juji_xzjj')
    juji_jjss = pub_config.get('juji_jjss')
    # 短剧选择器配置
    drama_item_selector = pub_config.get('drama_item_selector')
    drama_title_selector = pub_config.get('drama_title_selector')
    drama_extinfo_selector = pub_config.get('drama_extinfo_selector')
    if idx==1:
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
    anchor_info = parent_.info.get("anchor_info", None)
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
            drama_text_elements = await page.locator(drama_item_selector).all()

            # 遍历所有短剧标题元素
            for text_element in drama_text_elements:
                title_element = text_element.locator(drama_title_selector)
                extinfo = await text_element.locator(drama_extinfo_selector).text_content()
                # 获取标题文本
                text_content = await title_element.text_content()
                tencent_logger.info(f'找到短剧标题：{text_content}   jishu:{jishu} match_title:{match_title}')

                # 检查标题是否匹配
                if not jishu or (jishu and str(jishu) in extinfo):
                    # 获取忽略标点设置
                    ignore_punctuation = anchor_info.get("ignore_punctuation", False)
                    
                    # 根据设置决定是否移除标点符号
                    if ignore_punctuation:
                        compare_match_title = remove_punctuation(match_title)
                        compare_text_content = remove_punctuation(text_content)
                        tencent_logger.info(f'忽略标点对比：[{compare_match_title}] vs [{compare_text_content}]')
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
                    if need_click:
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

async def add_declaration(parent_, page):
    """添加视频号自主声明"""
    try:
        # 检查info中是否有declaration且不为"不声明"和"无需标注"
        if not parent_.info:
            tencent_logger.info('[视频号声明] 没有info信息，跳过声明添加')
            return

        declaration = parent_.info.get('declaration', '')
        if not declaration or declaration == '不声明' or declaration == '无需标注':
            tencent_logger.info('[视频号声明] 没有声明内容或选择不声明，跳过声明添加')
            return

        tencent_logger.info(f'[视频号声明] 开始添加声明: {declaration}')

        # 检查页面上是否有"选择视频标注"的span
        video_annotation_span = page.locator('span:has-text("选择视频标注")')
        if await video_annotation_span.count() > 0:
            tencent_logger.info('[视频号声明] 找到"选择视频标注"按钮')
            # 点击"选择视频标注"
            await video_annotation_span.click()
            tencent_logger.info('[视频号声明] 已点击"选择视频标注"按钮')

            # 等待声明选项容器出现
            await page.wait_for_selector('.mark-tag-options', timeout=5000)
            tencent_logger.info('[视频号声明] 声明选项容器已出现')

            # 查找包含目标文本的选项
            # 使用更精确的选择器：在 .mark-tag-options 容器内查找包含目标文本的 .option-main
            declaration_option = page.locator(f'.mark-tag-options .mark-tag-option:has(.option-main:text-is("{declaration}"))')
            
            # 检查声明选项是否存在
            if await declaration_option.count() > 0:
                tencent_logger.info(f'[视频号声明] 找到声明选项: {declaration}，准备点击')
                await declaration_option.click()
                tencent_logger.info(f'[视频号声明] 已点击声明选项: {declaration}')
                
                # 等待选择生效
                await asyncio.sleep(1)
                tencent_logger.info('[视频号声明] 声明添加完成')
            else:
                tencent_logger.warning(f'[视频号声明] 声明选项 {declaration} 未找到')
                # 尝试打印所有可用的选项用于调试
                try:
                    all_options = await page.locator('.mark-tag-options .option-main').all_text_contents()
                    tencent_logger.info(f'[视频号声明] 页面上可用的声明选项: {all_options}')
                except:
                    pass
        else:
            tencent_logger.info('[视频号声明] 页面上未找到"选择视频标注"按钮，可能当前账号不支持此功能')

    except Exception as e:
        tencent_logger.error(f'[视频号声明] 添加声明失败: {str(e)}')
        tencent_logger.exception(f'[视频号声明] 详细错误信息')


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



async def delete_videos_by_search_api(account_file, minutes_ago, max_views, video_title=None, process_interval=0):
    """
    使用新的搜索API删除视频（手动删除专用）
    :param account_file: cookie文件路径
    :param minutes_ago: 多少分钟之前的视频
    :param max_views: 最大播放量
    :param video_title: 视频标题匹配（剧名），如果为None则不按剧名过滤
    :param process_interval: 处理间隔（秒）
    """
    import requests
    import aiofiles
    
    if not minutes_ago and not max_views:
        tencent_logger.info("[手动删除-API] 未设置删除条件，跳过删除")
        return
    
    if video_title:
        tencent_logger.info(f"[手动删除-API] 开始使用搜索API删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views} 且 剧名包含'{video_title}'")
    else:
        tencent_logger.info(f"[手动删除-API] 开始使用搜索API删除视频，条件：{minutes_ago}分钟前 且 播放量少于{max_views}")
    
    tencent_logger.info(f"[手动删除-API] 处理间隔: {process_interval}秒")
    
    try:
        # 从session文件读取cookie
        async with aiofiles.open(account_file, 'r', encoding='utf-8') as f:
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
            tencent_logger.error('[手动删除-API] 无法获取sessionid或wxuin')
            return
        
        # 导入删除函数
        from social_auto_upload.uploader.tencent_uploader.main_tz_violation import delete_violation_video
        
        # 计算时间范围
        current_time = datetime.now()
        
        # 构建请求
        url = 'https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_search_user_page'
        
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
            'X-WECHAT-UIN': wxuin,
            'Referer': 'https://channels.weixin.qq.com/micro/content/post/list',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'finger-print-device-id': hashlib.md5(sessionid.encode()).hexdigest(),
            'sec-ch-ua': '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
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
        last_buffer = ""
        continue_flag = True
        delete_success_count = 0
        delete_fail_count = 0
        page_count = 0
        
        while continue_flag:
            page_count += 1
            
            # 构建请求数据
            data = {
                'wording': video_title if video_title else "",  # 搜索关键词（剧名）
                'lastBuffer': last_buffer,
                'continueFlag': False if not last_buffer else True,
                'timestamp': str(int(time.time() * 1000)),
                '_log_finder_uin': '',
                '_log_finder_id': '',
                'rawKeyBuff': '',
                'pluginSessionId': None,
                'scene': 7,
                'reqScene': 7
            }
            
            tencent_logger.info(f"[手动删除-API] 第{page_count}页: 请求数据 wording='{data['wording']}', lastBuffer={'有' if last_buffer else '无'}")
            
            # 使用 asyncio.to_thread 将同步请求转移到线程池
            response = await asyncio.to_thread(
                session.post, url, headers=headers, cookies=cookies, json=data, timeout=30, verify=False
            )
            
            if response.status_code not in [200, 201]:
                tencent_logger.error(f"[手动删除-API] 查询视频列表失败（第{page_count}页），状态码：{response.status_code}")
                break
            
            result = response.json()
            
            if result.get('errCode') != 0:
                tencent_logger.error(f"[手动删除-API] 视频列表API返回错误：{result.get('errMsg')}")
                break
            
            data_obj = result.get('data', {})
            video_list = data_obj.get('list', [])
            last_buffer = data_obj.get('lastBuffer', '')
            continue_flag = data_obj.get('continueFlag', False)
            
            if not video_list:
                tencent_logger.info(f"[手动删除-API] 第{page_count}页无数据，查询完成")
                break
            
            tencent_logger.info(f"[手动删除-API] 第{page_count}页: 获取 {len(video_list)} 个视频，continueFlag={continue_flag}")
            
            # 检查符合条件的视频并立即删除
            for video in video_list:
                create_time = video.get('createTime', 0)
                read_count = video.get('readCount', 0)
                export_id = video.get('exportId', '')
                object_id = video.get('objectId', '')
                
                # 获取视频标题 - 优先从desc.component.title提取，再从desc.description提取
                desc_obj = video.get('desc', {})
                title = ''
                
                if isinstance(desc_obj, dict):
                    # 优先从component.title提取
                    component_obj = desc_obj.get('component', {})
                    if isinstance(component_obj, dict):
                        title = component_obj.get('title', '')
                    
                    # 如果component.title为空，从description提取
                    if not title:
                        title = desc_obj.get('description', '')
                elif isinstance(desc_obj, str):
                    # 兼容desc直接是字符串的情况
                    title = desc_obj
                
                # 计算时间差（分钟）
                video_time = datetime.fromtimestamp(create_time)
                time_diff = (current_time - video_time).total_seconds() / 60
                
                # 记录详细的比对信息
                tencent_logger.info(f"[手动删除-API] 视频信息比对:")
                tencent_logger.info(f"[手动删除-API] - ObjectID: {object_id}")
                tencent_logger.info(f"[手动删除-API] - 标题: {title}")
                tencent_logger.info(f"[手动删除-API] - 发布时间: {video_time.strftime('%Y年%m月%d日 %H:%M')} ({time_diff:.0f}分钟前)")
                tencent_logger.info(f"[手动删除-API] - 播放量: {read_count}")
                
                # 检查剧名是否匹配（如果设置了剧名）
                drama_name_match = True
                if video_title:
                    drama_name_match = (video_title in title) if title else False
                    tencent_logger.info(f"[手动删除-API] - 剧名匹配: {drama_name_match} (标题包含'{video_title}')")
                
                tencent_logger.info(f"[手动删除-API] - 条件比对: 时间>={minutes_ago}分钟 且 播放量<{max_views}")
                tencent_logger.info(f"[手动删除-API] - 实际数据: {time_diff:.0f}>={minutes_ago} 且 {read_count}<{max_views}")
                
                # 检查是否符合删除条件
                if drama_name_match and minutes_ago is not None and time_diff >= minutes_ago and max_views is not None and read_count < max_views:
                    tencent_logger.info(f"[手动删除-API] => 符合删除条件，立即删除")
                    
                    # 立即执行删除
                    success, errmsg = await delete_violation_video(export_id, account_file, sessionid, wxuin)
                    
                    # 使用配置的处理间隔
                    if process_interval > 0:
                        tencent_logger.info(f"[手动删除-API] 等待处理间隔 {process_interval} 秒...")
                        await asyncio.sleep(process_interval)
                    else:
                        await asyncio.sleep(1)  # 默认间隔
                    
                    if success:
                        delete_success_count += 1
                        tencent_logger.info(f"[手动删除-API] ✅ 删除成功 (已删除: {delete_success_count})")
                    else:
                        # 检查是否是删除频率限制
                        if errmsg == '暂无法删除，你今日删除太频繁，如需继续操作可登录管理员账号重试':
                            tencent_logger.error(f"[手动删除-API] ⚠️ 遇到删除频率限制，停止后续处理")
                            tencent_logger.info(f"[手动删除-API] 删除完成：成功 {delete_success_count} 个，失败 {delete_fail_count} 个（遇到频率限制）")
                            return  # 立即结束函数
                        
                        delete_fail_count += 1
                        tencent_logger.error(f"[手动删除-API] ❌ 删除失败 (失败: {delete_fail_count}): {errmsg}")
                else:
                    tencent_logger.info(f"[手动删除-API] => 不符合删除条件")
            
            # 如果没有下一页，停止循环
            if not continue_flag:
                tencent_logger.info(f"[手动删除-API] 已到最后一页，处理完成")
                break
            
            # 翻页间隔
            await asyncio.sleep(0.5)
        
        tencent_logger.info(f"[手动删除-API] 删除完成：成功 {delete_success_count} 个，失败 {delete_fail_count} 个")
        
    except Exception as e:
        tencent_logger.exception(f"[手动删除-API] 删除视频时出错：{str(e)}")
