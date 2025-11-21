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
        'addons': addons,
        'enable_cache': True,
        'geoip': True,
        'headless':par_.hide_browser,
        'i_know_what_im_doing': True,
        'proxy': par_.proxy_setting,
        'fingerprint': fingerprint,
        'exclude_addons':[DefaultAddons.UBO],
    }