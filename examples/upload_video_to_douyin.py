import asyncio
import glob
from pathlib import Path

from VidShelfAutomator.check_login import get_user_info_from_filename
from social_auto_upload.conf import BASE_DIR
from social_auto_upload.uploader.douyin_uploader.main import douyin_setup, DouYinVideo
from social_auto_upload.utils.base_social_media import SOCIAL_MEDIA_DOUYIN
from social_auto_upload.utils.files_times import generate_schedule_time_next_day, get_title_and_hashtags
from youdub.do_everything import cookie_path

if __name__ == '__main__':
    cookie_files = glob.glob(f'{cookie_path}/{SOCIAL_MEDIA_DOUYIN}_uploader/*.json')
    for account_file in cookie_files:
        user_id, username = get_user_info_from_filename(account_file)
        if user_id and user_id in ['25760120940']:
            filepath = r'E:\IDEA\workspace\YouDub-webui\data\douyin\videos\zf\final'
            # 获取视频目录
            folder_path = Path(filepath)
            # 获取文件夹中的所有文件
            files = list(folder_path.glob("*.mp4"))
            file_num = len(files)
            publish_datetimes = generate_schedule_time_next_day(file_num, 1, daily_times=[16])
            cookie_setup = asyncio.run(douyin_setup(account_file, handle=False))
            for index, file in enumerate(files):
                title, tags = get_title_and_hashtags(str(file))
                thumbnail_path = file.with_suffix('.png')
                # 打印视频文件名、标题和 hashtag
                print(f"视频文件名：{file}")
                print(f"标题：{title}")
                print(f"Hashtag：{tags}")
                if thumbnail_path.exists():
                    app = DouYinVideo(title, file, tags, publish_datetimes[index], account_file,
                                      thumbnail_path=thumbnail_path)
                else:
                    app = DouYinVideo(title, file, tags, publish_datetimes[index], account_file)
                asyncio.run(app.main(), debug=False)
                break
