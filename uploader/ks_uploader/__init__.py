from pathlib import Path

from social_auto_upload.conf import BASE_DIR

Path(BASE_DIR / "cookies" / "kuaishou_uploader").mkdir(exist_ok=True)