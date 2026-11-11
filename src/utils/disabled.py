import json
import os

from src.utils import config
from src.utils.file_io import atomic_write_file


def load_disabled_domains():
    if not os.path.exists(config.DISABLED_FILE):
        return set()
    with open(config.DISABLED_FILE, encoding='utf-8') as file:
        data = json.load(file)
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError('停用域名文件格式无效')
    return set(data)


def save_disabled_domains(domains):
    return atomic_write_file(config.DISABLED_FILE, sorted(domains), is_json=True)
