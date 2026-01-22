import os
import requests

from camoufox import DefaultAddons
from social_auto_upload.utils.fingerprint_manager import fingerprint_manager
from social_auto_upload.utils.log import tencent_logger


def test_geoip_with_proxy(proxy_setting, timeout=10):
    """测试通过代理访问 api.ipify.org 是否成功"""
    if not proxy_setting or not proxy_setting.get('server'):
        return True
    
    try:
        proxy_url = proxy_setting.get('server')
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        response = requests.get('https://api.ipify.org', proxies=proxies, timeout=timeout)
        if response.status_code == 200:
            tencent_logger.info(f"通过代理访问 api.ipify.org 成功，IP: {response.text}，将启用 geoip")
            return True
        else:
            tencent_logger.warning(f"通过代理访问 api.ipify.org 返回状态码 {response.status_code}，将禁用 geoip")
            return False
    except Exception as e:
        tencent_logger.warning(f"通过代理访问 api.ipify.org 失败: {str(e)}，将禁用 geoip 以避免启动失败")
        return False


async def _get_camoufox_config(par_):
    addons_path = par_.info.get("addons_path")
    addons = []
    if addons_path:
        addons = [str(item) for item in addons_path.iterdir() if item.is_dir()]
    fingerprint = fingerprint_manager.get_or_create_fingerprint(os.path.basename(par_.account_file))
    
    # 如果代理设置存在，先测试是否能访问 api.ipify.org
    enable_geoip = True
    if par_.proxy_setting and par_.proxy_setting.get('server'):
        enable_geoip = test_geoip_with_proxy(par_.proxy_setting)
    
    return {
        'humanize': 0.75,
        # "showcursor": False,
        'addons': addons,
        'enable_cache': True,
        'geoip': enable_geoip,  # 根据代理测试结果决定是否启用geoip
        'headless':par_.hide_browser,
        'i_know_what_im_doing': True,
        'proxy': par_.proxy_setting,
        'fingerprint': fingerprint,
        'exclude_addons':[DefaultAddons.UBO],
        "firefox_user_prefs": {
            "widget.windows.window_occlusion_tracking.enabled": False,
            "dom.min_background_timeout_value": 0,
            "dom.timeout.background_throttling_maximum": 0,
            "privacy.reduceTimerPrecision": False,
            "browser.startup.minimized": True,

            # 你可以根据需要添加其他首选项，例如：
            # "dom.disable_page_visibility": False,
        },
        'config': {
            'humanize': True,   # 或 2.0
            'showcursor': False,
        },
    }