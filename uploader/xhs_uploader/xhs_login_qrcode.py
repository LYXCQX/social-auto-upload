import datetime
import json
from pathlib import Path
from time import sleep

import qrcode
from playwright.sync_api import sync_playwright
from PIL import Image

from social_auto_upload.utils.file_util import get_account_file
from xhs import XhsClient

from social_auto_upload.conf import BASE_DIR


def sign(uri, data=None, a1="", web_session=""):
    for _ in range(10):
        try:
            with sync_playwright() as playwright:
                stealth_js_path = Path(BASE_DIR / "utils/stealth.min.js")
                chromium = playwright.chromium

                # 如果一直失败可尝试设置成 False 让其打开浏览器，适当添加 sleep 可查看浏览器状态
                browser = chromium.launch(headless=True)

                browser_context = browser.new_context()
                browser_context.add_init_script(path=stealth_js_path)
                context_page = browser_context.new_page()
                context_page.goto("https://www.xiaohongshu.com")
                browser_context.add_cookies([
                    {'name': 'a1', 'value': a1, 'domain': ".xiaohongshu.com", 'path': "/"}]
                )
                context_page.reload()
                # 这个地方设置完浏览器 cookie 之后，如果这儿不 sleep 一下签名获取就失败了，如果经常失败请设置长一点试试
                sleep(1)
                encrypt_params = context_page.evaluate("([url, data]) => window._webmsxyw(url, data)", [uri, data])
                return {
                    "x-s": encrypt_params["X-s"],
                    "x-t": str(encrypt_params["X-t"])
                }
        except Exception:
            # 这儿有时会出现 window._webmsxyw is not a function 或未知跳转错误，因此加一个失败重试趴
            pass
    raise Exception("重试了这么多次还是无法签名成功，寄寄寄")


# pip install qrcode
if __name__ == '__main__':
    xhs_client = XhsClient(sign=sign)
    print(datetime.datetime.now())
    qr_res = xhs_client.get_qrcode()
    qr_id = qr_res["qr_id"]
    qr_code = qr_res["code"]

    qr = qrcode.QRCode(version=1, error_correction=qrcode.ERROR_CORRECT_L,
                       box_size=50,
                       border=1)
    qr.add_data(qr_res["url"])
    qr.make()
    
    # 生成二维码图像并显示
    img = qr.make_image(fill='black', back_color='white')
    img.show()

    while True:
        check_qrcode = xhs_client.check_qrcode(qr_id, qr_code)
        print(check_qrcode)
        sleep(1)
        if check_qrcode["code_status"] == 2:
            print(json.dumps(check_qrcode["login_info"], indent=4))
            print("当前 cookie：" + xhs_client.cookie)
            # 提取 red_id
            user_info = xhs_client.get_self_info()
            user_id = user_info["basic_info"]["red_id"]
            nickname = user_info["basic_info"]['nickname']
            account_file = Path(BASE_DIR / "cookies" / "xhs_uploader" / f'{user_id}_accounts.ini')
            with open(account_file, 'w') as file:
                file.write("[account1]\n")
                file.write(f"cookies ={xhs_client.cookie}")
            break

    print(json.dumps(xhs_client.get_self_info(), indent=4))