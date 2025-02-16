import asyncio
from pathlib import Path

from social_auto_upload.conf import BASE_DIR
from social_auto_upload.uploader.toutiao.main import toutiao_setup

if __name__ == '__main__':
    account_file = Path(BASE_DIR / "cookies" / "toutiao_uploader" / "account.json")
    cookie_setup = asyncio.run(toutiao_setup(str(account_file), handle=True))
