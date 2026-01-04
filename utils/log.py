"""
统一日志模块 - 从根目录 log.py 导入
所有日志都输出到 logs/app_{YYYY-MM-DD}.log
"""
import sys
import os

# 确保根目录在 Python 路径中
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from log import logger

# 为了兼容性，保留平台特定的日志记录器别名
# 它们都指向同一个 logger 实例
douyin_logger = logger
kuaishou_logger = logger
xhs_logger = logger
tiktok_logger = logger
bilibili_logger = logger
toutiao_logger = logger
tencent_logger = logger
baijiahao_logger = logger
xiaohongshu_logger = logger

__all__ = [
    'logger',
    'douyin_logger',
    'kuaishou_logger', 
    'xhs_logger',
    'tiktok_logger',
    'bilibili_logger',
    'toutiao_logger',
    'tencent_logger',
    'baijiahao_logger',
    'xiaohongshu_logger'
]
