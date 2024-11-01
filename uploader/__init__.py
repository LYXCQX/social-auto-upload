from pathlib import Path

from social_auto_upload.conf import BASE_DIR
import social_auto_upload.conf as conf

Path(BASE_DIR / "cookies").mkdir(exist_ok=True)
