import os
import sys
from pathlib import Path

# 获取程序运行目录
if getattr(sys, 'frozen', False):
    # 如果是打包后的 exe 运行，使用 exe 所在目录
    BASE_DIR = Path(sys.executable).parent
else:
    # 如果是源码运行，使用当前目录
    BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 创建必要的目录
for dir_name in ['cookies', 'logs']:
    dir_path = BASE_DIR / dir_name
    if not dir_path.exists():
        dir_path.mkdir(parents=True)

# 创建平台特定的 cookies 目录
for platform in ['douyin', 'kuaishou', 'xiaohongshu']:
    cookie_dir = BASE_DIR / 'cookies' / f'{platform}_uploader'
    if not cookie_dir.exists():
        cookie_dir.mkdir(parents=True)

XHS_SERVER = "http://127.0.0.1:5005"
LOCAL_CHROME_PATH = "D:\Chrome\Application\chrome.exe"   # change me necessary！ for example C:/Program Files/Google/Chrome/Application/chrome.exe
