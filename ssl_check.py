import os
import ssl
import socket
import datetime
import smtplib
import requests
import schedule
import time
import sys
import json
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cryptography import x509
from cryptography.hazmat.backends import default_backend

# ---------------------------------------------------------
# 环境变量与全局配置
# ---------------------------------------------------------
# 默认路径逻辑：优先使用 /app/conf 目录（便于 Docker 挂载）
BASE_DIR = "/app/conf" if os.path.exists("/app/conf") else "."

def resolve_path(env_var, default_name):
    path = os.getenv(env_var, default_name)
    # 如果用户提供的是绝对路径，直接返回；否则拼接 BASE_DIR
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)

# 域名列表文件与状态文件（支持自定义名称）
LIST_FILE = resolve_path('LIST_FILE', 'websites_list.txt')
STATE_FILE = resolve_path('STATE_FILE', 'ssl_alert_state.json')

# 其他配置
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
EMAIL_TO = os.getenv('EMAIL_TO', '')
DINGTALK_WEBHOOK = os.getenv('DINGTALK_WEBHOOK', '')

# 测试模式判断
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true' or '--test' in sys.argv

# 告警等级权重（用于判断是否“升级”）
LEVEL_WEIGHT = {
    "正常": 0,
    "提醒": 1,
    "警告": 2,
    "严重": 3
}

# ---------------------------------------------------------
# 全局运行状态
# ---------------------------------------------------------
LAST_RUN_DATE = None  # 记录上一次成功运行的日期 (YYYY-MM-DD)
# 日志美化模块
# ---------------------------------------------------------
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'

def get_time():
    return f"{Colors.BLUE}[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{Colors.RESET}"

def log_system(msg): print(f"{get_time()} {Colors.CYAN}[SYSTEM]{Colors.RESET} ⚙️  {msg}")
def log_info(msg):   print(f"{get_time()} {Colors.GREEN}[INFO  ]{Colors.RESET} ℹ️  {msg}")
def log_ok(msg):     print(f"{get_time()} {Colors.GREEN}[OK    ]{Colors.RESET} ✅ {msg}")
def log_warn(msg):   print(f"{get_time()} {Colors.YELLOW}[WARN  ]{Colors.RESET} ⚠️  {msg}")
def log_alert(msg):  print(f"{get_time()} {Colors.MAGENTA}[ALERT ]{Colors.RESET} 🚨 {Colors.MAGENTA}{msg}{Colors.RESET}")
def log_error(msg):  print(f"{get_time()} {Colors.RED}[ERROR ]{Colors.RESET} ❌ {Colors.RED}{msg}{Colors.RESET}")

# ---------------------------------------------------------
# 状态管理
# ---------------------------------------------------------
def load_state():
    """从本地 JSON 加载已发送的告警状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    """保存告警状态到本地 JSON (测试模式下不调用此函数)"""
    if TEST_MODE: return
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log_error(f"保存状态文件失败: {e}")

# ---------------------------------------------------------
# 核心业务逻辑
# ---------------------------------------------------------
def get_alert_level(days_remaining):
    """
    三级硬编码策略:
    - <= 3: 严重
    - <= 7: 警告
    - <= 14: 提醒
    - 其余: 正常
    """
    if days_remaining is None:
        return "严重", "#FF0000", "证书读取或网络连接失败，请排查！"
    elif days_remaining <= 3:
        return "严重", "#FF0000", "证书即将过期，请立即续签替换！"
    elif days_remaining <= 7:
        return "警告", "#FF8C00", "过期风险极高，请尽快安排续签！"
    elif days_remaining <= 14:
        return "提醒", "#1E90FF", "进入监控阈值范围，请关注"
    return "正常", "#32CD32", "无需操作"

def check_ssl_expiry(domain_with_port):
    """获取 SSL 证书剩余天数"""
    if ':' in domain_with_port:
        hostname, port = domain_with_port.split(':')
        port = int(port)
    else:
        hostname, port = domain_with_port, 443

    try:
        encoded_hostname = hostname.encode('idna').decode('ascii')
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((encoded_hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=encoded_hostname) as ssock:
                cert_bin = ssock.getpeercert(binary_form=True)

        cert = x509.load_der_x509_certificate(cert_bin, default_backend())
        expire_date = cert.not_valid_after
        remaining = expire_date - datetime.datetime.utcnow()
        return remaining.days, expire_date.strftime('%Y-%m-%d %H:%M:%S')

    except Exception as e:
        error_msg = str(e).split('] ')[-1]
        log_error(f"获取 {hostname}:{port} 证书失败: {error_msg}")
        return None, error_msg

# ---------------------------------------------------------
# 通知模块
# ---------------------------------------------------------
def send_email_alert(alerts):
    if not SMTP_HOST or not SMTP_USER or not EMAIL_TO: return

    subject_prefix = "[TEST] " if TEST_MODE else ""
    msg = MIMEMultipart()
    msg['From'], msg['To'] = SMTP_USER, EMAIL_TO
    msg['Subject'] = f"{subject_prefix}【SSL告警】有 {len(alerts)} 个域名需要关注"

    html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: Arial, sans-serif; background-color: #f4f7f6; padding: 20px; }}
          .container {{ max-width: 900px; margin: 0 auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); overflow: hidden; }}
          .header {{ background-color: #f8f9fa; padding: 20px; border-bottom: 1px solid #eee; }}
          table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
          th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
          th {{ background-color: #f8f9fa; color: #666; }}
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h3>🚨 SSL 证书到期巡检报告 {"(测试模式)" if TEST_MODE else ""}</h3>
            <p>阶梯提醒策略: 14天(提醒) / 7天(警告) / 3天(严重)</p>
          </div>
          <table>
            <tr><th>等级</th><th>域名</th><th>剩余天数</th><th>到期时间</th><th>处理建议</th></tr>
    """
    for a in alerts:
        html += f"""
            <tr>
              <td style="color: {a['color']}; font-weight: bold;">{a['level']}</td>
              <td>{a['domain']}</td>
              <td style="color: {a['color']}; font-weight: bold;">{a['days'] if a['days'] is not None else '失败'}</td>
              <td>{a['expire_time']}</td>
              <td>{a['suggestion']}</td>
            </tr>
        """
    html += "</table></div></body></html>"
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) if SMTP_PORT in [465, 994] else smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        if SMTP_PORT not in [465, 994]: server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, EMAIL_TO.split(','), msg.as_string())
        server.quit()
        log_info("邮件告警发送成功")
    except Exception as e:
        log_error(f"邮件发送失败: {e}")

def send_dingtalk_alert(alerts):
    if not DINGTALK_WEBHOOK: return
    
    title_prefix = "[TEST] " if TEST_MODE else ""
    text = f"## {title_prefix}🛡️ SSL 证书到期监控告警\n\n"
    text += f"> 策略: 14天提醒 / 7天警告 / 3天严重\n\n---\n\n"
    
    for a in alerts:
        days_str = f"{a['days']} 天" if a['days'] is not None else "读取失败"
        text += f"🌐 **域名:** {a['domain']}\n\n"
        text += f"📊 **告警等级:** <font color='{a['color']}'>{a['level']}</font>\n\n"
        text += f"⏳ **剩余天数:** <font color='{a['color']}'>**{days_str}**</font>\n\n"
        text += f"📅 **到期时间:** `{a['expire_time']}`\n\n"
        text += f"🔍 **建议:** {a['suggestion']}\n\n---\n\n"

    data = {"msgtype": "markdown", "markdown": {"title": "SSL证书巡检报告", "text": text}}
    try:
        res = requests.post(DINGTALK_WEBHOOK, json=data, timeout=10)
        log_info(f"钉钉告警发送成功: {res.status_code}")
    except Exception as e:
        log_error(f"钉钉发送失败: {e}")

def send_system_error_alert(error_msg):
    """当发生严重系统配置错误时（如找不到域名列表），发送紧急通知"""
    if not DINGTALK_WEBHOOK: return
    text = f"### ❌ SSL 监控系统运行错误\n\n"
    text += f"> **错误原因:** {error_msg}\n\n"
    text += f"> **当前时间:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    text += f"请检查容器挂载路径或配置文件内容！"
    
    data = {"msgtype": "markdown", "markdown": {"title": "SSL监控系统错误", "text": text}}
    try:
        requests.post(DINGTALK_WEBHOOK, json=data, timeout=10)
    except:
        pass

def check_is_workday():
    """通过第三方 API 判断今天是否为工作日 (支持调休和法定节假日)"""
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    # 使用 timor.tech 开源 API (或可替换为其他可靠 API)
    url = f"https://timor.tech/api/holiday/info/{date_str}"
    headers = {"User-Agent": "Mozilla/5.0 (SSL-Monitor-Bot)"}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get('code') == 0:
                # type.type: 0 是工作日, 1 是周末, 2 是节日, 3 是调休(工作日)
                t = data['type']['type']
                is_work = (t in [0, 3])
                status_name = data['type']['name']
                log_info(f"今日属性查询成功: {status_name} ({'工作日' if is_work else '非工作日'})")
                return is_work
    except Exception as e:
        log_warn(f"节假日 API 请求失败 ({e})，正在回退至基础周末判断逻辑...")
    
    # 回退逻辑：周一至周五视为工作日
    return datetime.datetime.now().weekday() < 5

# ---------------------------------------------------------
# 任务执行逻辑
# ---------------------------------------------------------
def run_task():
    global LAST_RUN_DATE
    today_str = datetime.date.today().isoformat()
    
    # 生产模式下，如果今天已经运行过，则跳过重复触发
    if not TEST_MODE and LAST_RUN_DATE == today_str:
        return

    abs_path = os.path.abspath(LIST_FILE)
    log_system(f"开始执行 SSL 证书巡检任务 (路径: {abs_path})")
    
    if not os.path.exists(LIST_FILE):
        err = f"找不到配置文件: {abs_path}"
        log_error(err)
        send_system_error_alert(err)
        return

    with open(LIST_FILE, 'r', encoding='utf-8') as f:
        domains = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not domains:
        err = f"配置文件内容为空，未发现有效域名: {abs_path}"
        log_error(err)
        send_system_error_alert(err)
        return

    log_system(f"成功加载 {len(domains)} 个待检测域名: {', '.join(domains)}")

    alerts = []
    state = load_state()
    state_changed = False

    # 获取今日工作属性
    is_today_workday = check_is_workday()

    for domain in domains:
        days, expire_time = check_ssl_expiry(domain)
        level, color, suggestion = get_alert_level(days)
        
        # 获取上次告警状态
        last_state = state.get(domain, "正常")
        if isinstance(last_state, dict):
            last_level = last_state.get('level', '正常')
            last_was_holiday = last_state.get('is_holiday', False)
        else:
            last_level = last_state
            last_was_holiday = False
        
        # 判断是否需要发送告警
        should_alert = False
        
        if TEST_MODE:
            should_alert = True
        elif level != "正常":
            # 逻辑 A: 等级升级了
            if LEVEL_WEIGHT[level] > LEVEL_WEIGHT[last_level]:
                should_alert = True
            # 逻辑 B: 工作日“补发”非工作日的未处理告警
            elif is_today_workday and last_was_holiday:
                should_alert = True
                log_info(f"{domain} 为节假日遗留告警，今日工作日执行补发提醒")

        if should_alert:
            alerts.append({
                'domain': domain, 'days': days, 'expire_time': expire_time,
                'level': level, 'color': color, 'suggestion': suggestion
            })
            log_alert(f"{domain} 触发通知: {level} (今日工作日: {is_today_workday})")
            
            if not TEST_MODE:
                state[domain] = {
                    "level": level,
                    "is_holiday": not is_today_workday,
                    "alert_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                state_changed = True
        else:
            # 如果证书恢复正常，重置状态
            if level == "正常" and last_level != "正常":
                state[domain] = {
                    "level": "正常",
                    "is_holiday": False,
                    "alert_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                state_changed = True
            log_ok(f"{domain} 状态良好 (剩余 {days} 天)")

    if alerts:
        log_system(f"巡检完毕，检测到 {len(alerts)} 个域名的告警状态有更新，正在下发通知...")
        send_email_alert(alerts)
        send_dingtalk_alert(alerts)
    else:
        log_info("巡检完毕，所有域名状态稳定，无风险等级变化")

    # 标记今天已运行
    LAST_RUN_DATE = today_str
    
    # 只要状态有变化（包括恢复正常），或者文件根本不存在，就执行保存
    if state_changed or not os.path.exists(STATE_FILE):
        save_state(state)
        log_system(f"同步状态记录至文件: {STATE_FILE}")

    # 生产模式下，任务结束后重新计算明天的随机运行时间
    if not TEST_MODE:
        schedule_next_run()

def schedule_next_run(silent=False):
    """计算下一次在 09:00 - 09:59 之间的随机时间"""
    schedule.clear('daily_job')
    random_minute = random.randint(0, 59)
    run_time_str = f"09:{random_minute:02d}"
    
    schedule.every().day.at(run_time_str).do(run_task).tag('daily_job')
    if not silent:
        log_system(f"计划任务已排定：下次巡检将于 {Colors.YELLOW}{run_time_str}{Colors.RESET} 执行 (09:00-10:00 随机时间)")

# ---------------------------------------------------------
# 程序入口
# ---------------------------------------------------------
if __name__ == '__main__':
    if TEST_MODE:
        log_system(f"{Colors.MAGENTA}>>> 测试模式启动 <<< (单次执行后将退出){Colors.RESET}")
        run_task()
        sys.exit(0)

    # 生产模式
    log_system(f"{Colors.GREEN}>>> 生产模式启动 <<< {Colors.RESET}")
    log_system(f"当前系统时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_system(f"状态文件路径: {STATE_FILE}")
    
    # 1. 立即执行一次巡检（内部会自动执行下一次排程并打印日志）
    run_task()
    
    while True:
        schedule.run_pending()
        time.sleep(10)
