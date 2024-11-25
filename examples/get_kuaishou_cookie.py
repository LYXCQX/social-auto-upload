import asyncio
from pathlib import Path

from social_auto_upload.conf import BASE_DIR
from social_auto_upload.uploader.ks_uploader.main import ks_setup

if __name__ == '__main__':
    account_file = Path(BASE_DIR / "cookies" / "kuaishou_uploader" / "account.json")
    cookie_setup = asyncio.run(ks_setup(str(account_file), handle=True))
