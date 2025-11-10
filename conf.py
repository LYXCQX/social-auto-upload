import os
import sys
from pathlib import Path

import sys
import os

isPackaged: bool = not sys.argv[0].endswith('.py')

if isPackaged:
    BASE_DIR = Path(sys.argv[0]).parent
else:
    BASE_DIR = Path(os.path.abspath(sys.argv[0])).parent
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
LOCAL_CHROME_PATH = ""   # change me necessary！ for example C:/Program Files/Google/Chrome/Application/chrome.exe
