import sys
import os
# 自动将 src 目录的父目录（项目根目录）加入 python 搜寻路径以支持绝对导入
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import threading
import time
import schedule

from src.utils.logger import log_system
from src.app import app
from src.monitor import run_task

def monitor_loop():
    log_system("定时巡检后台 Daemon 线程已启动...")
    
    # 启动时立即执行一次巡检自检，生成初版数据
    try:
        run_task()
    except Exception as e:
        log_system(f"启动全量自检异常: {e}")
        
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            log_system(f"定时调度运行发生异常: {e}")
        time.sleep(2)

def main():
    # 1. 启动后台定时检测 Daemon 线程
    t = threading.Thread(target=monitor_loop, name="SSL_Monitor_Daemon", daemon=True)
    t.start()
    
    # 2. 启动前端 Flask 业务端
    port = int(os.getenv("WEB_PORT", "8080"))
    log_system(f"SSL Monitor Web Server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == '__main__':
    main()
