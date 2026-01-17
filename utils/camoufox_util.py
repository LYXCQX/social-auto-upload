import os

from camoufox import DefaultAddons
from social_auto_upload.utils.fingerprint_manager import fingerprint_manager


async def _get_camoufox_config(par_):
    addons_path = par_.info.get("addons_path")
    addons = []
    if addons_path:
        addons = [str(item) for item in addons_path.iterdir() if item.is_dir()]
    fingerprint = fingerprint_manager.get_or_create_fingerprint(os.path.basename(par_.account_file))
    return {
        'humanize': 0.75,
        # "showcursor": False,
        'addons': addons,
        'enable_cache': True,
        'geoip': True,
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