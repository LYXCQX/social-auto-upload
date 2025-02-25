import os
import sys
import atexit
from pathlib import Path
from loguru import logger
from config import PLATFORM_UPLOAD

# 获取程序运行目录
if getattr(sys, 'frozen', False):
    # 如果是打包后的 exe 运行
    base_dir = Path(sys.executable).parent
else:
    # 如果是源码运行
    from social_auto_upload.conf import BASE_DIR
    base_dir = BASE_DIR

# 创建日志目录
log_dir = base_dir / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)

def log_formatter(record: dict) -> str:
    """
    Formatter for log records.
    :param dict record: Log object containing log metadata & message.
    :returns: str
    """
    colors = {
        "TRACE": "#cfe2f3",
        "INFO": "#9cbfdd",
        "DEBUG": "#8598ea",
        "WARNING": "#dcad5a",
        "SUCCESS": "#3dd08d",
        "ERROR": "#ae2c2c"
    }
    color = colors.get(record["level"].name, "#b3cfe7")
    return f"<fg #70acde>{{time:YYYY-MM-DD HH:mm:ss}}</fg #70acde> | <fg {color}>{{level}}</fg {color}>: <light-white>{{message}}</light-white>\n"


def create_logger(log_name: str, file_path: str):
    """
    Create custom logger for different business modules.
    :param str log_name: name of log
    :param str file_path: Optional path to log file
    :returns: Configured logger
    """
    def filter_record(record):
        return record["extra"].get("business_name") == log_name

    log_file = base_dir / file_path
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_file), filter=filter_record, level="INFO", 
              rotation="10 MB", retention="10 days", 
              backtrace=True, diagnose=True)
    return logger.bind(business_name=log_name)


# Remove all existing handlers
logger.remove()

# 尝试添加控制台输出，如果失败则跳过
try:
    if sys.stdout is not None:
        logger.add(sys.stdout, colorize=True, format=log_formatter)
except:
    # 如果无法添加控制台输出，只记录到文件
    pass

# 添加文件日志
logger.add(
    log_dir / "app_{time:YYYY-MM-DD}.log",
    rotation="500 MB",
    encoding="utf-8",
    format=log_formatter,
    level="INFO"
)

# 定义所有平台的日志记录器
platform_loggers = {
    'douyin': 'douyin',
    'kuaishou': 'kuaishou',
    'xhs': 'xhs',
    'tiktok': 'tiktok',
    'bilibili': 'bilibili',
    'toutiao': 'toutiao',
    'tencent': 'tencent'
}

# 创建所有平台的日志记录器，但只启用当前平台的日志文件
for platform_name, log_name in platform_loggers.items():
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe 运行
        if platform_name == PLATFORM_UPLOAD:
            # 当前平台创建文件日志
            globals()[f"{platform_name}_logger"] = create_logger(log_name, f'logs/{platform_name}.log')
        else:
            # 其他平台只创建内存日志
            globals()[f"{platform_name}_logger"] = logger.bind(business_name=log_name)
    else:
        # 源码运行时创建所有平台的文件日志
        globals()[f"{platform_name}_logger"] = create_logger(log_name, f'logs/{platform_name}.log')

# 添加清理函数
def cleanup_loggers():
    """清理所有日志记录器"""
    logger.remove()  # 移除所有处理器
    # 确保所有日志文件被正确关闭
    for handler_id in logger._core.handlers:
        try:
            logger.remove(handler_id)
        except:
            pass

# 注册清理函数
atexit.register(cleanup_loggers)
