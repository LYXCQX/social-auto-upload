import sys
import hashlib
import os
import random
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import loguru
import requests

from social_auto_upload.conf import BASE_DIR


def download_video(url, output_filename):
    loguru.logger.info(f'视频下载链接：{url}')
    try:
        # 发送HTTP GET请求来获取视频数据

        # 发送HTTP HEAD请求来获取视频文件大小
        response = requests.get(url, stream=True, timeout=(10, 300))
        response.raise_for_status()
        max_size_mb = 300
        # 从响应头中获取内容长度（文件大小）
        file_size = int(response.headers.get('Content-Length', 0))
        max_size_bytes = max_size_mb * 1024 * 1024

        # 检查文件大小是否超过最大限制
        if file_size > max_size_bytes:
            loguru.logger.error(f"文件太大，大小为 {file_size / (1024 * 1024):.2f} MB，超过最大限制 {max_size_mb} MB。")
            return

        # tmp_file = base_video_url + 'tmp.mp4'
        # 打开一个本地文件用于保存视频数据
        with open(output_filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    file.write(chunk)

        # 使用ffmpeg将视频文件转换为所需格式（可选）
        # ffmpeg.input(tmp_file).output(output_filename).run(overwrite_output=True)

        loguru.logger.info(f"视频已成功下载到 {output_filename}")
    except Exception as e:
        loguru.logger.error(f"下载视频时发生错误: {e}")


def get_mp4_files(folder_path):
    mp4_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".mp4"):
                path = os.path.join(root, file)
                mp4_files.append({"path": path, "file_name": file})
    return mp4_files


def get_json_files(folder_path):
    json_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".json"):
                path = os.path.join(root, file)
                json_files.append({"path": path, "file_name": file})
    return json_files


def get_img_files(folder_path):
    audio_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if (file.endswith(".jpg") or file.endswith(".jpeg")
                    or file.endswith(".png") or file.endswith(".gif")
                    or file.endswith(".raw") or file.endswith(".webp")
                    or file.endswith(".tiff") or file.endswith(".svg")
                    or file.endswith(".bmp")):
                audio_files.append(os.path.join(root, file))
    return audio_files


def get_font_files(folder_path):
    font_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if (file.endswith(tuple(".ttf")) or
                    file.endswith(tuple(".woff")) or
                    file.endswith(tuple(".woff2")) or
                    file.endswith(tuple(".otf"))):
                font_files.append(os.path.join(root, file))
    return font_files


def get_audio_files(folder_path):
    audio_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if (file.endswith(tuple(".mp3")) or file.endswith(tuple(".wav"))
                    or file.endswith(tuple(".flac")) or file.endswith(tuple(".aac"))
                    or file.endswith(tuple(".ogg"))):
                audio_files.append(os.path.join(root, file))
    return audio_files

def delete_files(file_paths):
    for file_path in file_paths:
        try:
            if 'video\\temp' in file_path:
                os.remove(file_path)
                print(f"删除成功: {file_path}")
        except FileNotFoundError:
            print(f"文件未找到: {file_path}")
        except Exception as e:
            print(f"删除失败 {file_path}: {e}")
def get_mp4_files_path(folder_path):
    mp4_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(tuple(".mp4")) or file.endswith(tuple(".MOV")) or file.endswith(tuple(".MP4")) or file.endswith(tuple(".mov")):
                path = os.path.join(root, file)
                mp4_files.append(path)
    return mp4_files

# 获取视频，这个会看文件及名称是否包含goods_name

def find_folders(base_path, goods_name):
    result = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if goods_name in dir_name:
                if not is_add_goods_name(root,result):
                    result.append(os.path.join(root, dir_name))
        # 只处理一级子文件夹
    return result

# 便利是否已经添加过上级目录
def is_add_goods_name(root, result):
    for ins_goods_name in result:
        if root.startswith(ins_goods_name):
            return True
    return False

def get_mp4_by_goods_name(base_path,goods_name):
    goods_name_patch_ = find_folders(base_path,goods_name)
    if len(goods_name_patch_) ==0:
        return get_mp4_files_path(base_path)
    else:
        video_path =[]
        for goods_name_patch in goods_name_patch_:
            video_path.extend(get_mp4_files_path(goods_name_patch))
        return video_path

def get_file_names(folder_path):
    mp4_files = []
    for path in folder_path:
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith(".mp4"):
                    mp4_files.append(file.split('-')[0])
    return mp4_files


def get_temp_path(suffix):
    # temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    # temp_file_path = temp_file.name
    #
    # # 关闭临时文件，ffmpeg 输出流会自动写入到该临时文件中
    # temp_file.close()
    return f'video/temp/{uuid.uuid4()}{suffix}'


def calculate_video_md5(file_path):
    # 打开视频文件
    with open(file_path, 'rb') as file:
        # 创建一个 MD5 对象
        md5 = hashlib.md5()

        # 读取文件内容并更新 MD5 值
        for chunk in iter(lambda: file.read(4096), b''):
            md5.update(chunk)

    # 获取计算得到的 MD5 值并返回
    return md5.hexdigest()


def get_account_file(user_id, platform, user_name=None):
    """获取账号文件路径"""
    # 获取程序运行目录
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe 运行
        base_dir = Path(sys.executable).parent
    else:
        # 如果是源码运行
        base_dir = BASE_DIR
    
    if user_name:
        user_ck_path = "{}_{}_account.json".format(user_id, user_name)
    else:
        # 获取cookies/platform_uploader目录下所有以user_id开头的json文件
        cookie_dir = Path(base_dir / "cookies" / f"{platform}_uploader")
        json_files = list(cookie_dir.glob(f"{user_id}_*_account.json"))
        
        if not json_files:
            loguru.logger.error(f"未找到用户ID为 {user_id} 的账号文件")
            return None
            
        # 使用找到的第一个匹配文件
        user_ck_path = json_files[0].name

    account_file = Path(base_dir / "cookies" / f"{platform}_uploader" / user_ck_path)
    return account_file

def create_missing_dirs(folder_path):
    """创建缺失的目录"""
    # 获取程序运行目录
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe 运行
        base_dir = Path(sys.executable).parent
    else:
        # 如果是源码运行
        base_dir = BASE_DIR
        
    # 确保目录存在
    for dir_name in ['cookies', 'logs', 'utils']:
        dir_path = base_dir / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True)
            loguru.logger.info(f"文件夹 {dir_path} 创建成功")
            
    # 创建特定的目录
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        loguru.logger.info(f"文件夹 {folder_path} 创建成功")


@contextmanager
def acquire_lock(lock, timeout=0):
    result = lock.acquire(timeout=timeout)
    try:
        yield result
    finally:
        if result:
            lock.release()



def generate_temp_filename(original_filepath, new_ext="", new_directory=None):
    # 获取文件的目录、文件名和扩展名
    directory, filename_with_ext = os.path.split(original_filepath)
    filename, ext = os.path.splitext(filename_with_ext)

    # 在文件名后添加.temp，但不改变扩展名
    if new_ext:
        new_filename = filename + '.temp' + new_ext
    else:
        new_filename = filename + '.temp' + ext

    # 如果你需要完整的路径，可以使用os.path.join
    if new_directory:
        new_filepath = os.path.join(new_directory, new_filename)
    else:
        new_filepath = os.path.join(directory, new_filename)

    return new_filepath.replace('\\', '/')

def random_with_system_time():
    system_time = int(time.time() * 1000)
    random_seed = (system_time + random.randint(0, 10000))
    return random_seed