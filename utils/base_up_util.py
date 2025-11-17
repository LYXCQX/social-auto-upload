import os

from camoufox import AsyncCamoufox, DefaultAddons
from patchright.async_api import async_playwright

from social_auto_upload.utils.fingerprint_manager import fingerprint_manager

from social_auto_upload.utils.camoufox_util import _get_camoufox_config


async def dispatch_upload(par_):
    if par_.info.get("camoufox", False):
        config = await _get_camoufox_config(par_)
        async with AsyncCamoufox(**config) as browser:
            return await par_.upload(None, browser)
    else:
        async with async_playwright() as playwright:
            return await par_.upload(playwright, None)