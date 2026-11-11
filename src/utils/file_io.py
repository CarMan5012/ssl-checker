import os
import json
import tempfile
import threading
from src.utils.logger import log_error

_replace_lock = threading.Lock()

def atomic_write_file(file_path, content, is_json=False):
    """
    使用临时文件写入并原子替换目标文件，防止写入期间发生中断或损坏。
    """
    dir_name = os.path.dirname(file_path)
    if not dir_name:
        dir_name = "."
    
    # 确保父目录存在
    if dir_name and not os.path.exists(dir_name):
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception as e:
            log_error(f"创建目录 {dir_name} 失败: {e}")
            return False

    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=dir_name,
                                         prefix=os.path.basename(file_path) + '.',
                                         suffix='.tmp', delete=False) as f:
            temp_file = f.name
            if is_json:
                json.dump(content, f, indent=4, ensure_ascii=False)
            else:
                f.write(content)
        
        # 原子替换
        with _replace_lock:
            os.replace(temp_file, file_path)
        return True
    except Exception as e:
        log_error(f"原子写入文件失败 {file_path}: {e}")
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass
        return False
