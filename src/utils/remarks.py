import json
import os

from src.utils import config
from src.utils.file_io import atomic_write_file


MAX_REMARK_LENGTH = 200


def load_domain_remarks():
    if not os.path.exists(config.REMARKS_FILE):
        return {}
    with open(config.REMARKS_FILE, encoding='utf-8') as file:
        data = json.load(file)
    if not isinstance(data, dict) or not all(
        isinstance(domain, str) and isinstance(remark, str)
        for domain, remark in data.items()
    ):
        raise ValueError('域名备注文件格式无效')
    return data


def save_domain_remarks(remarks):
    return atomic_write_file(config.REMARKS_FILE, remarks, is_json=True)


def normalize_remark(value):
    if not isinstance(value, str) or len(value) > MAX_REMARK_LENGTH:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return value.strip()
