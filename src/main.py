import sys
import os
# 自动将 src 目录的父目录（项目根目录）加入 python 搜寻路径以支持绝对导入
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import threading
import time
import datetime

from src.utils.logger import log_system
import src.utils.config as config
from src.app import app
from src.monitor import run_task, daily_due, retry_due, record_monitor_error

def monitor_loop():
    log_system("定时巡检后台 Daemon 线程已启动...")
    next_attempt = datetime.datetime.min
    while True:
        now = datetime.datetime.now()
        if now >= next_attempt:
            try:
                if daily_due(now):
                    run_task()
                    next_attempt = now + datetime.timedelta(minutes=30)
                elif retry_due(now):
                    run_task(retry_only=True)
                    next_attempt = now + datetime.timedelta(minutes=1)
            except Exception as e:
                log_system(f"巡检调度运行发生异常: {e}")
                record_monitor_error("巡检任务异常，请查看服务日志")
                next_attempt = now + datetime.timedelta(minutes=5)
        time.sleep(2)

def main():
    if config.TEST_MODE:
        run_task()
        return
    # 1. 启动后台定时检测 Daemon 线程
    t = threading.Thread(target=monitor_loop, name="SSL_Monitor_Daemon", daemon=True)
    t.start()
    
    # 2. 启动前端 Flask 业务端
    port = int(os.getenv("WEB_PORT", "8080"))
    log_system(f"SSL Monitor Web Server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == '__main__':
    main()
