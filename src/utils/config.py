import os
import sys
import json

# 默认路径逻辑：优先使用 /app/conf 目录，其次使用当前目录下的 conf，最后使用 "."
if os.path.exists("/app/conf"):
    BASE_DIR = "/app/conf"
elif os.path.exists("./conf"):
    BASE_DIR = "./conf"
else:
    BASE_DIR = "."

def resolve_path(env_var, default_name):
    path = os.getenv(env_var, default_name)
    # 如果用户提供的是绝对路径，直接返回；否则拼接 BASE_DIR
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)

# 域名列表文件与状态文件（支持自定义名称）
LIST_FILE = resolve_path('LIST_FILE', 'websites_list.txt')
STATE_FILE = resolve_path('STATE_FILE', 'ssl_alert_state.json')
CONFIG_FILE = resolve_path('CONFIG_FILE', 'config.json')
USERS_FILE = resolve_path('USERS_FILE', 'users.json')

# 全局配置变量，读取时请始终以 `config.VARIABLE` 形式引用以实现热重载同步
SMTP_HOST = ''
SMTP_PORT = 465
SMTP_USER = ''
SMTP_PASS = ''
EMAIL_TO = ''
DINGTALK_WEBHOOK = ''
DINGTALK_TOKEN = ''
DINGTALK_SECRET = ''
DINGTALK_KEYWORD = ''
ALERT_INFO_DAYS = 14
ALERT_WARNING_DAYS = 7
ALERT_CRITICAL_DAYS = 3

# 测试模式判断
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true' or '--test' in sys.argv

def load_all_configs():
    global SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
    global DINGTALK_WEBHOOK, DINGTALK_TOKEN, DINGTALK_SECRET, DINGTALK_KEYWORD
    global ALERT_INFO_DAYS, ALERT_WARNING_DAYS, ALERT_CRITICAL_DAYS

    # 1. 尝试从 config.json 读取配置
    json_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                json_config = json.load(f)
        except Exception:
            pass

    # 2. 读取优先级：优先 JSON -> 其次环境变量 -> 最后默认值
    def get_cfg(key, env_var, default_val=''):
        val = json_config.get(key)
        if val is None or val == '':
            return os.getenv(env_var, default_val)
        return val

    SMTP_HOST = get_cfg('smtp_host', 'SMTP_HOST')
    SMTP_PORT = int(get_cfg('smtp_port', 'SMTP_PORT', '465'))
    SMTP_USER = get_cfg('smtp_user', 'SMTP_USER')
    SMTP_PASS = get_cfg('smtp_pass', 'SMTP_PASS')
    EMAIL_TO = get_cfg('email_to', 'EMAIL_TO')
    
    DINGTALK_WEBHOOK = get_cfg('dingtalk_webhook', 'DINGTALK_WEBHOOK')
    DINGTALK_TOKEN = get_cfg('dingtalk_token', 'DINGTALK_TOKEN')
    DINGTALK_SECRET = get_cfg('dingtalk_secret', 'DINGTALK_SECRET')
    DINGTALK_KEYWORD = get_cfg('dingtalk_keyword', 'DINGTALK_KEYWORD')

    ALERT_INFO_DAYS = int(get_cfg('alert_info_days', 'ALERT_INFO_DAYS', '14'))
    ALERT_WARNING_DAYS = int(get_cfg('alert_warning_days', 'ALERT_WARNING_DAYS', '7'))
    ALERT_CRITICAL_DAYS = int(get_cfg('alert_critical_days', 'ALERT_CRITICAL_DAYS', '3'))

    # 钉钉 Token / Webhook 自动拼接规整
    if DINGTALK_TOKEN:
        DINGTALK_WEBHOOK = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}"
    elif DINGTALK_WEBHOOK and not DINGTALK_WEBHOOK.startswith('http'):
        DINGTALK_WEBHOOK = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_WEBHOOK}"

# 首次初始化加载
load_all_configs()
