import sys
import atexit
import os
from pathlib import Path
from loguru import logger
from social_auto_upload.conf import BASE_DIR

# 获取程序运行目录
# if getattr(sys, 'frozen', False):
#     # 如果是打包后的 exe 运行
#     base_dir = Path(sys.executable).parent
# else:
#     # 如果是源码运行
#     from social_auto_upload.conf import BASE_DIR
#     base_dir = BASE_DIR

# 创建日志目录
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)

def safe_rotation_function(message, file):
    """
    Custom rotation function that handles Windows file locking gracefully.
    Returns True if rotation should occur, False otherwise.
    
    Args:
        message: The log message being written
        file: The file object being written to
    """
    try:
        file_size = os.path.getsize(file.name)
        # Rotate when file exceeds 10 MB
        return file_size > 10 * 1024 * 1024
    except (OSError, FileNotFoundError, AttributeError):
        # If we can't access the file, don't rotate
        return False


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

    # 基本日志格式
    log_format = f"<fg #70acde>{{time:YYYY-MM-DD HH:mm:ss}}</fg #70acde> | <fg {color}>{{level}}</fg {color}>: <light-white>{{message}}</light-white>\n"

    # 如果有异常信息，添加异常部分
    if record["exception"]:
        log_format += "<red>{exception}</red>\n"

    return log_format


def create_logger(log_name: str, file_path: str):
    """
    Create custom logger for different business modules.
    :param str log_name: name of log
    :param str file_path: Optional path to log file
    :returns: Configured logger
    """
    def filter_record(record):
        return record["extra"].get("business_name") == log_name

    log_file = BASE_DIR / file_path
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        logger.add(str(log_file), filter=filter_record, level="INFO",
                  rotation=safe_rotation_function, retention="3 days",  # 保留3天的日志，自动清理3天前的日志
                  backtrace=True, diagnose=True, delay=True)
    except Exception as e:
        # Fallback: add logger without rotation if custom rotation fails
        logger.add(str(log_file), filter=filter_record, level="INFO",
                  retention="3 days",
                  backtrace=True, diagnose=True, delay=True)
    return logger.bind(business_name=log_name)


# Remove all existing handlers
logger.remove()

# 尝试添加控制台输出，如果失败则跳过
try:
    if sys.stdout is not None:
        logger.add(sys.stdout,
                   colorize=True,
                   format=log_formatter,
                   backtrace=True,
                   diagnose=True)
except:
    # 如果无法添加控制台输出，只记录到文件
    pass

# 添加文件日志
try:
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        rotation=safe_rotation_function,
        retention="3 days",  # 保留3天的日志，自动清理3天前的日志
        encoding="utf-8",
        format=log_formatter,
        level="INFO",
        backtrace=True,
        diagnose=True,
        delay=True
    )
except Exception as e:
    # Fallback: add logger without rotation if custom rotation fails
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        retention="3 days",
        encoding="utf-8",
        format=log_formatter,
        level="INFO",
        backtrace=True,
        diagnose=True,
        delay=True
    )

# 定义所有平台的日志记录器
platform_loggers = {
    'douyin': 'douyin',
    'kuaishou': 'kuaishou',
    'xhs': 'xhs',
    'tiktok': 'tiktok',
    'bilibili': 'bilibili',
    'toutiao': 'toutiao',
    'tencent': 'tencent',
    'baijiahao': 'baijiahao',
    'xiaohongshu': 'xiaohongshu'
}

# 创建所有平台的日志记录器，但只启用当前平台的日志文件
isPackaged: bool = not sys.argv[0].endswith('.py')
for platform_name, log_name in platform_loggers.items():
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
