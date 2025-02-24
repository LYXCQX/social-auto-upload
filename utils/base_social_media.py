from pathlib import Path
from typing import List

from social_auto_upload.conf import BASE_DIR

SOCIAL_MEDIA_DOUYIN = "douyin"
SOCIAL_MEDIA_TENCENT = "tencent"
SOCIAL_MEDIA_TIKTOK = "tiktok"
SOCIAL_MEDIA_BILIBILI = "bilibili"
SOCIAL_MEDIA_KUAISHOU = "kuaishou"
SOCIAL_MEDIA_XHS = "xhs"
SOCIAL_MEDIA_JD = "jd"
SOCIAL_MEDIA_TOUTIAO = "toutiao"

def get_supported_social_media() -> List[str]:
    return [SOCIAL_MEDIA_DOUYIN, SOCIAL_MEDIA_TENCENT, SOCIAL_MEDIA_TIKTOK, SOCIAL_MEDIA_KUAISHOU,SOCIAL_MEDIA_TOUTIAO]


def get_platforms() -> List[str]:
    return [SOCIAL_MEDIA_DOUYIN, SOCIAL_MEDIA_TENCENT, SOCIAL_MEDIA_TIKTOK, SOCIAL_MEDIA_BILIBILI,
            SOCIAL_MEDIA_KUAISHOU, SOCIAL_MEDIA_XHS, SOCIAL_MEDIA_JD,SOCIAL_MEDIA_TOUTIAO]


def get_cli_action() -> List[str]:
    return ["upload", "login", "watch"]


async def set_init_script(context):
    stealth_js_path = Path(BASE_DIR / "utils/stealth.min.js")
    await context.add_init_script(path=stealth_js_path)
    return context
