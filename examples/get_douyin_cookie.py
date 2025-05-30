import asyncio
from pathlib import Path

from social_auto_upload.conf import BASE_DIR
from social_auto_upload.uploader.douyin_uploader.main import douyin_setup

if __name__ == '__main__':
    account_file = Path(BASE_DIR / "cookies" / "douyin_uploader" / "account.json")
    account_file.parent.mkdir(exist_ok=True)
    cookie_setup = asyncio.run(douyin_setup(str(account_file), handle=True))
