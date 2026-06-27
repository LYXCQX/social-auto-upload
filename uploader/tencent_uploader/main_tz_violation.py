# -*- coding: utf-8 -*-
"""
违规视频处理模块
"""
import asyncio
import time
from datetime import datetime

from aiohttp import ThreadedResolver, TCPConnector

from social_auto_upload.utils.log import tencent_logger


def extract_video_info_from_notification(content, ref_url, title=''):
    """从通知内容和refUrl中提取视频信息
    
    支持多种通知格式：
    1. 作品优化建议：作品标题：xxx  发布时间：xxx
    2. 限制传播：你于xxxx-xx-xx xx:xx:xx发表的短剧视频" #xxx..."中
    """
    import re
    from urllib.parse import unquote
    
    video_title = ''
    publish_timestamp = 0
    object_id = ''
    
    # ========== 提取标题 ==========
    # 格式1：作品标题：《xxx》
    title_match = re.search(r'作品标题：\s*(.+)', content)
    if title_match:
        video_title = title_match.group(1).strip()
    # 格式2：短剧视频" #xxx..."中
    else:
        title_match2 = re.search(r'短剧视频["\s]*[#《]*([^"\.]+)', content)
        if title_match2:
            video_title = title_match2.group(1).strip()
            # 清理可能的后缀
            video_title = video_title.rstrip('...')
    
    # ========== 提取发布时间 ==========
    # 格式1：发布时间：2026-06-26 07:10:01
    time_match = re.search(r'发布时间：(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', content)
    if time_match:
        publish_time_str = time_match.group(1)
    # 格式2：你于2026-06-26 07:10:01发表的
    else:
        time_match2 = re.search(r'你于(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})发表的', content)
        if time_match2:
            publish_time_str = time_match2.group(1)
        else:
            publish_time_str = ''
    
    # 转换为时间戳
    if publish_time_str:
        try:
            dt = datetime.strptime(publish_time_str, '%Y-%m-%d %H:%M:%S')
            publish_timestamp = int(dt.timestamp())
        except:
            pass
    
    # ========== 提取ObjectID ==========
    # 格式1：unique_id=mmfindermachineauditdelivery14943811069001337356
    if ref_url:
        unique_id_match = re.search(r'unique_id=mmfindermachineauditdelivery(\d+)', ref_url)
        if unique_id_match:
            object_id = unique_id_match.group(1)
        # 格式2：rand_id=FDxxxxxxxxx (这种通常无法提取objectId)
        # 后续只能依赖时间戳匹配
    
    return video_title, publish_timestamp, object_id


def collect_violation_videos(notification_list):
    """收集所有违规视频的信息（notification_list已经过滤过时间）
    
    支持的违规类型：
    1. 作品优化建议
    2. 视频被暂时限制传播
    3. 其他违规通知
    """
    violation_videos = []
    
    # 定义需要处理的违规通知类型
    violation_titles = [
        '作品优化建议',
        '你有1条视频号视频被暂时限制传播',
        '视频号视频被暂时限制传播',
        '你的视频号视频被暂时限制传播',
    ]
    
    for notification in notification_list:
        title = notification.get('title', '')
        timestamp = notification.get('timestamp', 0)
        is_special_jump = notification.get('isSpecialJumpType', 1)
        content = notification.get('content', '')
        ref_url = notification.get('refUrl', '')
        
        # 检查是否是违规通知（支持多种类型）
        is_violation = False
        violation_type = ''
        
        for vt in violation_titles:
            if vt in title:
                is_violation = True
                violation_type = vt
                break
        
        if is_violation and is_special_jump == 0 and content:
            # 从content和refUrl中提取视频信息
            video_title, publish_timestamp, object_id = extract_video_info_from_notification(content, ref_url, title)
            
            # 只有当至少有objectId或时间戳时才添加
            if object_id or publish_timestamp:
                violation_videos.append({
                    'video_title': video_title,
                    'publish_timestamp': publish_timestamp,
                    'object_id': object_id,
                    'notification_timestamp': timestamp,
                    'content': content,
                    'violation_type': violation_type,  # 记录违规类型
                    'match_method': 'object_id' if object_id else 'timestamp'
                })
            else:
                tencent_logger.warning(f"[违规处理] 无法从通知中提取有效信息: {title} - {content[:50]}...")
    
    return violation_videos


async def get_post_list_by_date_with_early_stop_async(session, headers, cookies, start_time, end_time, violation_videos, page_size=50):
    """根据日期范围查询视频列表（支持翻页，找到所有违规视频后提前停止） - 异步版本"""
    url = 'https://channels.weixin.qq.com/micro/statistic/cgi-bin/mmfinderassistant-bin/statistic/post_list'
    
    all_videos = []
    current_page = 1
    
    # 构建需要匹配的objectId和时间戳集合
    target_object_ids = set()
    target_timestamps = set()
    
    for violation in violation_videos:
        object_id = violation.get('object_id', '')
        timestamp = violation.get('publish_timestamp', 0)
        if object_id:
            target_object_ids.add(object_id)
        if timestamp:
            target_timestamps.add(timestamp)
    
    matched_count = 0
    
    tencent_logger.info(f"[违规处理] 开始分页查询视频列表（需要匹配 {len(violation_videos)} 个违规视频）")
    
    while True:
        data = {
            'pageSize': page_size,
            'currentPage': current_page,
            'sort': 0,
            'order': 0,
            'startTime': start_time,
            'endTime': end_time,
            'timestamp': str(int(time.time() * 1000)),
            '_log_finder_uin': '',
            '_log_finder_id': '',
            'rawKeyBuff': None,
            'pluginSessionId': None,
            'scene': 7,
            'reqScene': 7
        }
        
        try:
            async with session.post(url, headers=headers, cookies=cookies, json=data) as response:
                if response.status not in [200, 201]:
                    tencent_logger.error(f"[违规处理] 查询视频列表失败（第{current_page}页），状态码：{response.status}")
                    break
                
                result = await response.json()
                
                if result.get('errCode') != 0:
                    tencent_logger.error(f"[违规处理] 视频列表API返回错误：{result.get('errMsg')}")
                    break
                
                data_obj = result.get('data', {})
                video_list = data_obj.get('list', [])
                total_count = data_obj.get('totalCount', 0)
                
                if not video_list:
                    tencent_logger.info(f"[违规处理] 第{current_page}页无数据，查询完成")
                    break
                
                all_videos.extend(video_list)
                
                # 检查当前页是否匹配到了目标视频
                page_matched = 0
                for video in video_list:
                    object_id = video.get('objectId', '')
                    create_time = video.get('createTime', 0)
                    
                    if object_id in target_object_ids or create_time in target_timestamps:
                        page_matched += 1
                
                matched_count += page_matched
                
                tencent_logger.info(f"[违规处理] 第{current_page}页: 获取 {len(video_list)} 个视频，本页匹配 {page_matched} 个 (累计匹配: {matched_count}/{len(violation_videos)}，总获取: {len(all_videos)}/{total_count})")
                
                # 如果已经找到所有违规视频，提前结束
                if matched_count >= len(violation_videos):
                    tencent_logger.info(f"[违规处理] ✅ 已找到所有 {len(violation_videos)} 个违规视频，提前结束查询！")
                    break
                
                # 如果已获取所有数据，结束循环
                if len(all_videos) >= total_count:
                    tencent_logger.info(f"[违规处理] 已获取所有视频数据")
                    break
                
                current_page += 1
                await asyncio.sleep(0.5)  # 避免请求过快
                
        except Exception as e:
            tencent_logger.error(f"[违规处理] 查询视频列表出错（第{current_page}页）：{str(e)}")
            break
    
    return all_videos


async def find_videos_by_object_id_and_time_async(session, headers, cookies, violation_videos):
    """根据所有违规视频的时间范围，一次性查询所有视频并匹配 - 异步版本"""
    from datetime import timedelta
    
    if not violation_videos:
        tencent_logger.warning("[违规处理] 没有违规视频需要查询")
        return {}
    
    # 找出最小和最大发布时间戳
    timestamps = [v['publish_timestamp'] for v in violation_videos if v['publish_timestamp']]
    if not timestamps:
        tencent_logger.warning("[违规处理] 没有有效的时间戳")
        return {}
    
    min_timestamp = min(timestamps)
    max_timestamp = max(timestamps)
    
    # 计算查询时间范围（开始用最早当天00:00:00，结束用最晚当天23:59:59）
    min_date = datetime.fromtimestamp(min_timestamp)
    max_date = datetime.fromtimestamp(max_timestamp)
    
    # 最早发布时间当天的 00:00:00
    start_date = min_date.replace(hour=0, minute=0, second=0, microsecond=0)
    # 最晚发布时间当天的 23:59:59（包含整天）
    end_date = max_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_time = int(start_date.timestamp())
    end_time = int(end_date.timestamp())
    
    tencent_logger.info(f"[违规处理] 统一查询时间范围:")
    tencent_logger.info(f"[违规处理]    最早发布时间: {min_date.strftime('%Y-%m-%d %H:%M:%S')}")
    tencent_logger.info(f"[违规处理]    最晚发布时间: {max_date.strftime('%Y-%m-%d %H:%M:%S')}")
    tencent_logger.info(f"[违规处理]    查询范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    tencent_logger.info(f"[违规处理]    时间戳范围: {start_time} ~ {end_time}")
    
    # 查询所有视频（自动翻页，找到所有违规视频后提前停止）
    all_videos = await get_post_list_by_date_with_early_stop_async(session, headers, cookies, start_time, end_time, violation_videos)
    
    if not all_videos:
        tencent_logger.warning(f"[违规处理] 未查询到任何视频")
        return {}
    
    tencent_logger.info(f"[违规处理] 共查询到 {len(all_videos)} 个视频")
    
    # 构建两种索引：objectId索引（最靠谱）和时间戳索引（降级）
    object_id_to_video = {}
    time_to_video = {}
    
    for video in all_videos:
        object_id = video.get('objectId', '')
        create_time = video.get('createTime', 0)
        
        if object_id:
            object_id_to_video[object_id] = video
        if create_time:
            time_to_video[create_time] = video
    
    tencent_logger.info(f"[违规处理] 构建了 {len(object_id_to_video)} 个objectId索引，{len(time_to_video)} 个时间索引")
    
    # 匹配违规视频（优先使用objectId，降级到时间戳）
    matched_videos = {}
    matched_by_object_id = 0
    matched_by_timestamp = 0
    
    for violation in violation_videos:
        video_title = violation['video_title']
        object_id = violation.get('object_id', '')
        publish_timestamp = violation.get('publish_timestamp', 0)
        
        matched = False
        match_key = None
        
        # 优先使用objectId匹配（最靠谱）
        if object_id and object_id in object_id_to_video:
            match_key = f"objectId_{object_id}"
            matched_videos[match_key] = {
                'video': object_id_to_video[object_id],
                'violation': violation,
                'match_method': 'object_id'
            }
            matched_by_object_id += 1
            matched = True
        # 降级到时间戳匹配
        elif publish_timestamp and publish_timestamp in time_to_video:
            match_key = f"timestamp_{publish_timestamp}"
            matched_videos[match_key] = {
                'video': time_to_video[publish_timestamp],
                'violation': violation,
                'match_method': 'timestamp'
            }
            matched_by_timestamp += 1
            matched = True
        
        if not matched:
            tencent_logger.warning(f"[违规处理] 未匹配: {video_title[:30]}... (ObjectID: {object_id or '无'}, 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(publish_timestamp)) if publish_timestamp else '无'})")
    
    tencent_logger.info(f"[违规处理] 匹配到 {len(matched_videos)}/{len(violation_videos)} 个违规视频")
    tencent_logger.info(f"[违规处理]    - 通过ObjectID匹配: {matched_by_object_id} 个")
    tencent_logger.info(f"[违规处理]    - 通过时间戳匹配: {matched_by_timestamp} 个")
    
    return matched_videos
async def delete_violation_video(object_id, account_file=None, sessionid=None, wxuin=None):
    """删除指定的违规视频 - 使用异步HTTP请求"""
    import json
    import aiohttp
    
    try:
        tencent_logger.info("=" * 80)
        tencent_logger.info(f"[违规处理-删除] 开始删除视频: {object_id}")
        tencent_logger.info("=" * 80)
        
        # 如果没有提供cookie，从session文件读取
        if not sessionid or not wxuin:
            if not account_file:
                tencent_logger.error("[违规处理-删除] 未提供cookie或session文件")
                return False
            
            tencent_logger.info(f"[违规处理-删除] 从session文件读取cookie: {account_file}")
            # ✅ 使用异步文件读取
            import aiofiles
            async with aiofiles.open(account_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                session_data = json.loads(content)
            
            cookies_list = session_data.get('cookies', [])
            for cookie in cookies_list:
                if cookie['name'] == 'sessionid':
                    sessionid = cookie['value']
                elif cookie['name'] == 'wxuin':
                    wxuin = cookie['value']
        
        if not sessionid or not wxuin:
            tencent_logger.error('[违规处理-删除] 无法获取sessionid或wxuin')
            return False
        
        # 调用删除接口
        url = 'https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_delete'
        
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-WECHAT-UIN': wxuin,
            'Referer': 'https://channels.weixin.qq.com/micro/content/post/list'
        }
        
        cookies = {
            'sessionid': sessionid,
            'wxuin': wxuin
        }
        
        data = {
            'objectId': object_id,
            'timestamp': str(int(time.time() * 1000)),
            '_log_finder_uin': '',
            '_log_finder_id': '',
            'rawKeyBuff': None,
            'pluginSessionId': None,
            'scene': 7,
            'reqScene': 7
        }
        
        # 打印请求参数
        tencent_logger.info(f"[违规处理-删除] 请求URL: {url}")
        tencent_logger.info(f"[违规处理-删除] 请求Headers: {json.dumps(headers, ensure_ascii=False, indent=2)}")
        tencent_logger.info(f"[违规处理-删除] 请求Cookies: sessionid={sessionid[:20]}..., wxuin={wxuin}")
        tencent_logger.info(f"[违规处理-删除] 请求Body: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        tencent_logger.info(f"[违规处理-删除] 正在发送删除请求...")
        # ✅ 使用 aiohttp 进行异步HTTP请求
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        resolver = ThreadedResolver()  # 使用线程池进行DNS解析，避免Windows异步DNS问题
        connector = TCPConnector(resolver=resolver, ssl=False)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(url, headers=headers, cookies=cookies, json=data) as response:
                # 打印响应参数
                tencent_logger.info(f"[违规处理-删除] 响应状态码: {response.status}")
                tencent_logger.info(f"[违规处理-删除] 响应Headers: {json.dumps(dict(response.headers), ensure_ascii=False, indent=2)}")
                
                try:
                    response_json = await response.json()
                    tencent_logger.info(f"[违规处理-删除] 响应Body: {json.dumps(response_json, ensure_ascii=False, indent=2)}")
                except:
                    response_text = await response.text()
                    tencent_logger.warning(f"[违规处理-删除] 响应Body (非JSON): {response_text[:500]}")
                
                if response.status in [200, 201]:
                    result = await response.json()
                    if result.get('errCode') == 0:
                        tencent_logger.info(f"[违规处理-删除] ✅ 视频删除成功: {object_id}")
                        tencent_logger.info("=" * 80)
                        return True
                    else:
                        tencent_logger.error(f"[违规处理-删除] ❌ 删除失败 - errCode: {result.get('errCode')}, errMsg: {result.get('errMsg')}")
                        tencent_logger.info("=" * 80)
                        return False
                else:
                    tencent_logger.error(f"[违规处理-删除] ❌ 删除请求失败，状态码: {response.status}")
                    tencent_logger.info("=" * 80)
                    return False
            
    except Exception as e:
        tencent_logger.exception(f"[违规处理-删除] 删除视频异常: {str(e)}")
        tencent_logger.info("=" * 80)
        return False


async def hide_violation_video(object_id, account_file=None, sessionid=None, wxuin=None):
    """隐藏指定的违规视频（设置为仅自己可见） - 使用异步HTTP请求"""
    import json
    import aiohttp
    
    try:
        tencent_logger.info("=" * 80)
        tencent_logger.info(f"[违规处理-隐藏] 开始隐藏视频: {object_id}")
        tencent_logger.info("=" * 80)
        
        # 如果没有提供cookie，从session文件读取
        if not sessionid or not wxuin:
            if not account_file:
                tencent_logger.error("[违规处理-隐藏] 未提供cookie或session文件")
                return False
            
            tencent_logger.info(f"[违规处理-隐藏] 从session文件读取cookie: {account_file}")
            # ✅ 使用异步文件读取
            import aiofiles
            async with aiofiles.open(account_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                session_data = json.loads(content)
            
            cookies_list = session_data.get('cookies', [])
            for cookie in cookies_list:
                if cookie['name'] == 'sessionid':
                    sessionid = cookie['value']
                elif cookie['name'] == 'wxuin':
                    wxuin = cookie['value']
        
        if not sessionid or not wxuin:
            tencent_logger.error('[违规处理-隐藏] 无法获取sessionid或wxuin')
            return False
        
        # 调用隐藏接口（设置为仅自己可见）
        url = 'https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_update_visible'
        
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-WECHAT-UIN': wxuin,
            'Referer': 'https://channels.weixin.qq.com/micro/content/post/list'
        }
        
        cookies = {
            'sessionid': sessionid,
            'wxuin': wxuin
        }
        
        data = {
            'objectId': object_id,
            'visibleType': 3,  # 3 = 仅自己可见
            'timestamp': str(int(time.time() * 1000)),
            '_log_finder_uin': '',
            '_log_finder_id': '',
            'rawKeyBuff': None,
            'pluginSessionId': None,
            'scene': 7,
            'reqScene': 7
        }
        
        # 打印请求参数
        tencent_logger.info(f"[违规处理-隐藏] 请求URL: {url}")
        tencent_logger.info(f"[违规处理-隐藏] 请求Headers: {json.dumps(headers, ensure_ascii=False, indent=2)}")
        tencent_logger.info(f"[违规处理-隐藏] 请求Cookies: sessionid={sessionid[:20]}..., wxuin={wxuin}")
        tencent_logger.info(f"[违规处理-隐藏] 请求Body: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        tencent_logger.info(f"[违规处理-隐藏] 正在发送隐藏请求...")
        # ✅ 使用 aiohttp 进行异步HTTP请求
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        resolver = ThreadedResolver()  # 使用线程池进行DNS解析，避免Windows异步DNS问题
        connector = TCPConnector(resolver=resolver, ssl=False)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(url, headers=headers, cookies=cookies, json=data) as response:
                # 打印响应参数
                tencent_logger.info(f"[违规处理-隐藏] 响应状态码: {response.status}")
                tencent_logger.info(f"[违规处理-隐藏] 响应Headers: {json.dumps(dict(response.headers), ensure_ascii=False, indent=2)}")
                
                try:
                    response_json = await response.json()
                    tencent_logger.info(f"[违规处理-隐藏] 响应Body: {json.dumps(response_json, ensure_ascii=False, indent=2)}")
                except:
                    response_text = await response.text()
                    tencent_logger.warning(f"[违规处理-隐藏] 响应Body (非JSON): {response_text[:500]}")
                
                if response.status in [200, 201]:
                    result = await response.json()
                    if result.get('errCode') == 0:
                        tencent_logger.info(f"[违规处理-隐藏] ✅ 视频隐藏成功: {object_id}")
                        tencent_logger.info("=" * 80)
                        return True
                    else:
                        tencent_logger.error(f"[违规处理-隐藏] ❌ 隐藏失败 - errCode: {result.get('errCode')}, errMsg: {result.get('errMsg')}")
                        tencent_logger.info("=" * 80)
                        return False
                else:
                    tencent_logger.error(f"[违规处理-隐藏] ❌ 隐藏请求失败，状态码: {response.status}")
                    tencent_logger.info("=" * 80)
                    return False
            
    except Exception as e:
        tencent_logger.exception(f"[违规处理-隐藏] 隐藏视频异常: {str(e)}")
        tencent_logger.info("=" * 80)
        return False


async def check_and_handle_violation(account_file, violation_delete_days, violation_delete_views,
                                     violation_hide_views):
    """检查并处理违规视频"""
    import json
    import aiohttp
    
    tencent_logger.info("=" * 60)
    tencent_logger.info("[违规处理] 开始检查违规视频")
    tencent_logger.info("=" * 60)
    tencent_logger.info(f"[违规处理] 检查范围: 最近{violation_delete_days}天")
    tencent_logger.info(f"[违规处理] 删除条件: 播放量 < {violation_delete_views}")
    tencent_logger.info(f"[违规处理] 隐藏条件: 播放量 >= {violation_hide_views}")
    tencent_logger.info("=" * 60)
    
    try:
        # 从session文件读取cookie
        tencent_logger.info(f"[违规处理] 从session文件读取cookie: {account_file}")
        
        # ✅ 使用异步文件读取
        import aiofiles
        async with aiofiles.open(account_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            session_data = json.loads(content)
        
        # 提取cookies
        cookies_list = session_data.get('cookies', [])
        
        # 获取sessionid和wxuin
        sessionid = None
        wxuin = None
        for cookie in cookies_list:
            if cookie['name'] == 'sessionid':
                sessionid = cookie['value']
            elif cookie['name'] == 'wxuin':
                wxuin = cookie['value']
        
        if not sessionid or not wxuin:
            tencent_logger.error('[违规处理] 未找到sessionid或wxuin')
            return
        
        tencent_logger.info(f'[违规处理] 成功读取cookie (sessionid长度: {len(sessionid)}, wxuin: {wxuin})')
        tencent_logger.info('[违规处理] 正在请求通知列表...')
        
        # 构造请求
        url = 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/notification/notification_list'
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-WECHAT-UIN': wxuin
        }
        cookies = {'sessionid': sessionid, 'wxuin': wxuin}
        
        # 请求第一页
        data = {
            'pageSize': 20,
            'currentPage': 1,
            'reqType': 1,
            'timestamp': str(int(time.time() * 1000)),
            '_log_finder_uin': '',
            '_log_finder_id': '',
            'scene': 7,
            'reqScene': 7
        }
        
        # 计算时间范围（用于判断是否继续翻页）
        current_timestamp = int(time.time())
        time_range_seconds = violation_delete_days * 24 * 60 * 60
        oldest_allowed_timestamp = current_timestamp - time_range_seconds
        
        tencent_logger.info(f"[违规处理] 时间过滤：只处理 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(oldest_allowed_timestamp))} 之后的通知")
        
        resolver = ThreadedResolver()  # 使用线程池进行DNS解析，避免Windows异步DNS问题
        connector = aiohttp.TCPConnector(resolver=resolver, ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(url, headers=headers, cookies=cookies, json=data) as response:
                if response.status not in [200, 201]:
                    tencent_logger.error(f'[违规处理] 请求失败，状态码：{response.status}')
                    return
                
                result = await response.json()
                
                if result.get('errCode') != 0:
                    tencent_logger.error(f'[违规处理] API返回错误：{result.get("errMsg")}')
                    return
                
                # 获取数据
                data_obj = result.get('data', {})
                total_count = data_obj.get('totalCount', 0)
                page_list = data_obj.get('list', [])
                
                notification_list = []
                current_page = 1
                
                tencent_logger.info(f"[违规处理] 总通知数：{total_count}")
                tencent_logger.info(f"[违规处理] 第{current_page}页获取：{len(page_list)} 条")
                
                # 检查第一页是否有符合时间范围的通知
                page_has_valid_notifications = False
                for notification in page_list:
                    notification_timestamp = notification.get('timestamp', 0)
                    if notification_timestamp >= oldest_allowed_timestamp:
                        notification_list.append(notification)
                        page_has_valid_notifications = True
                
                tencent_logger.info(f"[违规处理] 第{current_page}页符合时间范围：{len(notification_list)} 条")
                
                # 如果第一页最后一条通知还在时间范围内，继续翻页
                if page_list:
                    last_notification_timestamp = page_list[-1].get('timestamp', 0)
                    should_continue = last_notification_timestamp >= oldest_allowed_timestamp
                else:
                    should_continue = False
                
                # 继续翻页直到：1) 某页所有通知都超出时间范围 2) 没有更多数据 3) 达到最大页数
                max_pages = 100  # 最多检查100页
                
                while should_continue and current_page < max_pages and len(notification_list) < total_count:
                    current_page += 1
                    data['currentPage'] = current_page
                    data['timestamp'] = str(int(time.time() * 1000))
                    
                    try:
                        async with session.post(url, headers=headers, cookies=cookies, json=data) as response:
                            if response.status not in [200, 201]:
                                tencent_logger.warning(f'[违规处理] 第{current_page}页请求失败，状态码：{response.status}')
                                break
                            
                            result = await response.json()
                            
                            if result.get('errCode') != 0:
                                tencent_logger.warning(f'[违规处理] 第{current_page}页API返回错误：{result.get("errMsg")}')
                                break
                            
                            page_list = result.get('data', {}).get('list', [])
                            
                            if not page_list:
                                tencent_logger.info(f'[违规处理] 第{current_page}页无数据，停止翻页')
                                break
                            
                            # 统计本页符合时间范围的通知
                            page_valid_count = 0
                            page_oldest_timestamp = float('inf')
                            
                            for notification in page_list:
                                notification_timestamp = notification.get('timestamp', 0)
                                page_oldest_timestamp = min(page_oldest_timestamp, notification_timestamp)
                                
                                if notification_timestamp >= oldest_allowed_timestamp:
                                    notification_list.append(notification)
                                    page_valid_count += 1
                            
                            tencent_logger.info(f"[违规处理] 第{current_page}页获取：{len(page_list)} 条，符合时间范围：{page_valid_count} 条（最旧：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(page_oldest_timestamp))}）")
                            
                            # 判断是否需要继续翻页：如果本页最后一条通知还在时间范围内，继续
                            last_notification_timestamp = page_list[-1].get('timestamp', 0)
                            if last_notification_timestamp < oldest_allowed_timestamp:
                                tencent_logger.info(f'[违规处理] ✅ 本页最后一条通知已超出时间范围 ({time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_notification_timestamp))} < {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(oldest_allowed_timestamp))})，提前停止翻页')
                                should_continue = False
                            else:
                                should_continue = True
                            
                            await asyncio.sleep(0.5)  # 避免请求过快
                            
                    except Exception as e:
                        tencent_logger.error(f'[违规处理] 第{current_page}页请求异常：{str(e)}')
                        break
                
                tencent_logger.info(f"[违规处理] 通知列表获取完成：共获取 {current_page} 页，筛选出 {len(notification_list)} 条符合时间范围的通知（总数：{total_count}）")
                
                # 第一步：收集所有优化建议视频
                tencent_logger.info("=" * 60)
                tencent_logger.info("[违规处理] 第一步：收集所有优化建议视频")
                tencent_logger.info("=" * 60)
                
                violation_videos = collect_violation_videos(notification_list)
                
                tencent_logger.info(f"[违规处理] 收集结果：发现 {len(violation_videos)} 个违规视频")
                
                if not violation_videos:
                    tencent_logger.info("[违规处理] 未找到任何违规视频，无需继续处理")
                    return
                
                # 显示收集到的视频列表
                for idx, v in enumerate(violation_videos, 1):
                    ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(v['publish_timestamp'])) if v['publish_timestamp'] else '无'
                    title_short = v['video_title'][:40] if v['video_title'] else '未知标题'
                    object_id = v.get('object_id', '')
                    violation_type = v.get('violation_type', '未知类型')
                    tencent_logger.info(f"[违规处理] [{idx}] {title_short} (类型: {violation_type}, 发布: {ts_str}, ObjectID: {object_id or '无'})")
                
                # 第二步：按时间区间查询所有视频
                tencent_logger.info("=" * 60)
                tencent_logger.info("[违规处理] 第二步：按时间区间查询所有视频（自动翻页）")
                tencent_logger.info("=" * 60)
                
                # ✅ 调用异步版本的查询函数
                matched_videos = await find_videos_by_object_id_and_time_async(session, headers, cookies, violation_videos)
        
        # 第三步：对比数据并执行逻辑
        tencent_logger.info("=" * 60)
        tencent_logger.info("[违规处理] 第三步：对比数据并执行判断逻辑")
        tencent_logger.info("=" * 60)
        
        delete_count = 0
        hide_count = 0
        skip_count = 0
        not_found_count = 0
        already_hidden_count = 0
        
        for idx, violation in enumerate(violation_videos, 1):
            video_title = violation['video_title']
            object_id = violation.get('object_id', '')
            publish_timestamp = violation['publish_timestamp']
            
            tencent_logger.info(f"[违规处理] [{idx}/{len(violation_videos)}] 处理违规视频: {video_title[:50]}")
            
            # 查找匹配的视频
            match_key = None
            if object_id:
                match_key = f"objectId_{object_id}"
            elif publish_timestamp:
                match_key = f"timestamp_{publish_timestamp}"
            
            match_data = matched_videos.get(match_key) if match_key else None
            
            if match_data:
                video = match_data['video']
                used_match_method = match_data.get('match_method', 'unknown')
                read_count = video.get('readCount', 0)
                video_object_id = video.get('objectId', '')  # 纯数字ID
                export_id = video.get('exportId', '')  # export/ 格式的ID
                visible_type = video.get('visibleType', 1)  # 1=公开, 3=仅自己可见
                
                tencent_logger.info(f"[违规处理] 找到匹配视频 (匹配方式: {used_match_method})")
                tencent_logger.info(f"[违规处理] Object ID: {video_object_id}")
                tencent_logger.info(f"[违规处理] Export ID: {export_id}")
                tencent_logger.info(f"[违规处理] 真实播放量: {read_count}")
                tencent_logger.info(f"[违规处理] 可见性: {visible_type} (1=公开, 3=仅自己可见)")
                
                # 根据真实播放量判断并执行操作
                if read_count < violation_delete_views:
                    tencent_logger.warning(f"[违规处理] ❌ 满足删除条件（{read_count} < {violation_delete_views}）")
                    # 执行删除（使用 exportId）
                    success = await delete_violation_video(export_id, account_file, sessionid, wxuin)
                    if success:
                        delete_count += 1
                        tencent_logger.info(f"[违规处理] 删除成功")
                    else:
                        tencent_logger.error(f"[违规处理] 删除失败")
                        
                elif read_count >= violation_hide_views:
                    # 检查是否已经隐藏
                    if visible_type == 3:
                        tencent_logger.info(f"[违规处理] ⏭️  视频已经是隐藏状态（仅自己可见），跳过")
                        already_hidden_count += 1
                    else:
                        tencent_logger.warning(f"[违规处理] 🔒 满足隐藏条件（{read_count} >= {violation_hide_views}）")
                        # 执行隐藏（使用 exportId）
                        success = await hide_violation_video(export_id, account_file, sessionid, wxuin)
                        if success:
                            hide_count += 1
                            tencent_logger.info(f"[违规处理] 隐藏成功")
                        else:
                            tencent_logger.error(f"[违规处理] 隐藏失败")
                        
                else:
                    tencent_logger.info(f"[违规处理] ⏸️  不满足条件（{violation_delete_views} <= {read_count} < {violation_hide_views}）")
                    skip_count += 1
            else:
                tencent_logger.warning(f"[违规处理] 未找到匹配的视频（可能已删除或时间范围外）")
                not_found_count += 1
        
        # 汇总结果
        tencent_logger.info("=" * 60)
        tencent_logger.info("[违规处理] 最终结果汇总")
        tencent_logger.info("=" * 60)
        tencent_logger.info(f"[违规处理] 发现优化建议视频: {len(violation_videos)} 个")
        tencent_logger.info(f"[违规处理] 成功匹配视频: {len(matched_videos)} 个")
        tencent_logger.info(f"[违规处理] 未找到视频: {not_found_count} 个")
        tencent_logger.info(f"[违规处理] ")
        tencent_logger.info(f"[违规处理] 已删除: {delete_count} 个（播放量 < {violation_delete_views}）")
        tencent_logger.info(f"[违规处理] 已隐藏: {hide_count} 个（播放量 >= {violation_hide_views}）")
        tencent_logger.info(f"[违规处理] 已是隐藏状态: {already_hidden_count} 个（跳过）")
        tencent_logger.info(f"[违规处理] 暂不处理: {skip_count} 个")
        tencent_logger.info("=" * 60)
        
    except Exception as e:
        tencent_logger.exception(f"[违规处理] 处理过程出错: {str(e)}")
