from pathlib import Path
from typing import List
import os
import sys

from social_auto_upload.conf import BASE_DIR
from social_auto_upload.utils.log import logger
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
    """设置初始化脚本"""
    try:
        # 获取程序运行目录
        if getattr(sys, 'frozen', False):
            # 如果是打包后的 exe 运行
            base_dir = Path(sys.executable).parent
            stealth_path = base_dir / 'utils' / 'stealth.min.js'
        else:
            # 如果是源码运行，尝试多个可能的路径
            possible_paths = [
                Path(BASE_DIR / "utils/stealth.min.js"),
                Path(BASE_DIR / "social_auto_upload/utils/stealth.min.js"),
            ]
            
            # 尝试所有路径
            stealth_path = None
            for path in possible_paths:
                if path.exists():
                    stealth_path = path
                    break
                    
            if not stealth_path:
                paths_str = '\n'.join(str(p) for p in possible_paths)
                raise FileNotFoundError(f"找不到文件，尝试过的路径:\n{paths_str}")
        
        if not stealth_path.exists():
            raise FileNotFoundError(f"找不到文件: {stealth_path}")
            
        # 读取并添加初始化脚本
        with open(stealth_path, 'r', encoding='utf-8') as f:
            await context.add_init_script(script=f.read())
            
        return context
    except Exception as e:
        logger.info(f"设置初始化脚本失败: {str(e)}")
        raise
