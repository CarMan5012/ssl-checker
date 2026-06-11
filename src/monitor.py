import os
import datetime
import smtplib
import requests
import schedule
import time
import random
import hmac
import hashlib
import base64
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import src.utils.config as config
from src.utils.logger import Colors, log_system, log_info, log_ok, log_warn, log_alert, log_error
from src.utils.file_io import atomic_write_file
from src.utils.cert import check_ssl

# 告警等级权重（用于判断是否“升级”）
LEVEL_WEIGHT = {
    "正常": 0,
    "提醒": 1,
    "警告": 2,
    "严重": 3
}

# ---------------------------------------------------------
# 状态管理
# ---------------------------------------------------------
def load_state():
    """从本地 JSON 加载已发送的告警状态"""
    import json
    if os.path.exists(config.STATE_FILE):
        try:
            with open(config.STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    """保存告警状态到本地 JSON (测试模式下不调用此函数)"""
    if config.TEST_MODE: 
        return
    atomic_write_file(config.STATE_FILE, state, is_json=True)

# ---------------------------------------------------------
# 通知模块
# ---------------------------------------------------------
def send_email_alert(alerts):
    if not config.SMTP_HOST or not config.SMTP_USER or not config.EMAIL_TO: 
        return

    subject_prefix = "[TEST] " if config.TEST_MODE else ""
    msg = MIMEMultipart()
    msg['From'], msg['To'] = config.SMTP_USER, config.EMAIL_TO
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
            <h3>🚨 SSL 证书到期巡检报告 {"(测试模式)" if config.TEST_MODE else ""}</h3>
            <p>阶梯提醒策略: {config.ALERT_INFO_DAYS}天(提醒) / {config.ALERT_WARNING_DAYS}天(警告) / {config.ALERT_CRITICAL_DAYS}天(严重)</p>
          </div>
          <table>
            <tr><th>等级</th><th>域名</th><th>剩余天数</th><th>到期时间 / 错误详情</th></tr>
    """
    for a in alerts:
        html += f"""
            <tr>
              <td style="color: {a['color']}; font-weight: bold;">{a['level']}</td>
              <td>{a['domain']}</td>
              <td style="color: {a['color']}; font-weight: bold;">{a['days'] if a['days'] is not None else '失败'}</td>
              <td>{a['detail']}</td>
            </tr>
        """
    html += "</table></div></body></html>"
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT) if config.SMTP_PORT in [465, 994] else smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT)
        if config.SMTP_PORT not in [465, 994]: 
            server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASS)
        recipients = [email.strip() for email in config.EMAIL_TO.split(',') if email.strip()]
        server.sendmail(config.SMTP_USER, recipients, msg.as_string())
        server.quit()
        log_info("邮件告警发送成功")
    except Exception as e:
        log_error(f"邮件发送失败: {e}")

def post_to_dingtalk(data):
    if not config.DINGTALK_WEBHOOK: 
        return
    
    # 自动注入自定义关键词（如果未在内容中出现）
    if config.DINGTALK_KEYWORD:
        if data.get("msgtype") == "markdown" and "markdown" in data:
            text = data["markdown"].get("text", "")
            if config.DINGTALK_KEYWORD not in text:
                data["markdown"]["text"] = f"{text}\n\n📌 匹配关键词：{config.DINGTALK_KEYWORD}"
        elif data.get("msgtype") == "text" and "text" in data:
            content = data["text"].get("content", "")
            if config.DINGTALK_KEYWORD not in content:
                data["text"]["content"] = f"{content}\n📌 匹配关键词：{config.DINGTALK_KEYWORD}"

    # 签名计算 (加签)
    url = config.DINGTALK_WEBHOOK
    if config.DINGTALK_SECRET:
        timestamp = str(round(time.time() * 1000))
        secret_enc = config.DINGTALK_SECRET.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, config.DINGTALK_SECRET)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        connector = "&" if "?" in url else "?"
        url = f"{url}{connector}timestamp={timestamp}&sign={sign}"

    # 发送请求与结果判断
    try:
        if config.TEST_MODE:
            import json
            log_info(f"发送钉钉消息 [测试模式] - URL: {url}, Payload: {json.dumps(data, ensure_ascii=False)}")
        res = requests.post(url, json=data, timeout=10)
        
        # 尝试解析钉钉返回的 JSON
        res_json = {}
        try:
            res_json = res.json()
        except Exception:
            pass

        errcode = res_json.get("errcode", 0)
        errmsg = res_json.get("errmsg", "")

        if res.status_code != 200 or errcode != 0:
            log_error(f"钉钉发送失败: HTTP {res.status_code}, errcode: {errcode}, errmsg: {errmsg}, Response Body: {res.text}")
        else:
            log_info(f"钉钉消息发送成功: {res.status_code}")
    except Exception as e:
        log_error(f"钉钉发送请求发生异常: {e}")

def send_dingtalk_alert(alerts):
    if not config.DINGTALK_WEBHOOK: 
        return
    
    title_prefix = "[TEST] " if config.TEST_MODE else ""
    text = f"### {title_prefix}🛡️ SSL 证书到期监控告警\n\n"
    text += f"> 策略: {config.ALERT_INFO_DAYS}天提醒 / {config.ALERT_WARNING_DAYS}天警告 / {config.ALERT_CRITICAL_DAYS}天严重\n\n"
    text += f"---\n\n"
    
    for i, a in enumerate(alerts):
        if i > 0:
            text += f"---\n\n"
        days_str = f"{a['days']} 天" if a['days'] is not None else "读取失败"
        text += f"🌐 **域名:** {a['domain']}\n\n"
        text += f"📊 **告警等级:** <font color='{a['color']}'>{a['level']}</font>\n\n"
        text += f"⏳ **剩余天数:** <font color='{a['color']}'>**{days_str}**</font>\n\n"
        if a['days'] is not None:
            text += f"📅 **到期时间:** {a['detail']}\n\n"
        else:
            text += f"🔴 **错误详情:** {a['detail']}\n\n"

    data = {"msgtype": "markdown", "markdown": {"title": "SSL证书巡检报告", "text": text}}
    post_to_dingtalk(data)

def send_system_error_alert(error_msg, file_path=None):
    """当发生严重系统配置错误时（如找不到域名列表），发送紧急通知"""
    if not config.DINGTALK_WEBHOOK: 
        return
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    text = f"### 🔴 SSL 监控系统运行错误\n\n"
    text += f"> 警告: 严重系统配置错误\n\n"
    text += f"---\n\n"
    text += f"⚠️ **错误原因:** {error_msg}\n\n"
    if file_path:
        text += f"📂 **容器路径:** {file_path}\n\n"
    text += f"📅 **当前时间:** {time_str}\n\n"
    text += f"💡 **排查建议:** 请检查容器挂载路径或配置文件内容！"
    
    data = {"msgtype": "markdown", "markdown": {"title": "SSL监控系统错误", "text": text}}
    post_to_dingtalk(data)

def check_is_workday():
    """通过第三方 API 判断今天是否为工作日 (支持调休和法定节假日)"""
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
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
    # 每次运行任务时重新从磁盘重载全局配置参数
    config.load_all_configs()
    
    abs_path = os.path.abspath(config.LIST_FILE)
    log_system(f"开始执行 SSL 证书巡检任务 (路径: {abs_path})")
    
    if not os.path.exists(config.LIST_FILE):
        err = "找不到配置文件"
        log_error(f"{err}: {abs_path}")
        send_system_error_alert(err, abs_path)
        return

    domains = []
    with open(config.LIST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            clean_line = line.split('#')[0].strip()
            if clean_line:
                domains.append(clean_line)

    if not domains:
        err = "配置文件内容为空，未发现有效域名"
        log_error(f"{err}: {abs_path}")
        send_system_error_alert(err, abs_path)
        return

    log_system(f"成功加载 {len(domains)} 个待检测域名: {', '.join(domains)}")

    alerts = []
    state = load_state()
    state_changed = False

    # 获取今日工作属性
    is_today_workday = check_is_workday()

    for domain in domains:
        # 调用统一的 SSL 检测工具，传入当前热加载的阈值
        ssl_info = check_ssl(
            domain, 
            config.ALERT_INFO_DAYS, 
            config.ALERT_WARNING_DAYS, 
            config.ALERT_CRITICAL_DAYS
        )
        
        level = ssl_info.get("level", "正常")
        color = ssl_info.get("color", "#32CD32")
        days = ssl_info.get("days")
        expire_time = ssl_info.get("expire") if ssl_info.get("success") else ssl_info.get("error", "未知错误")

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
        
        if config.TEST_MODE:
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
                'domain': domain, 'days': days, 'detail': expire_time,
                'level': level, 'color': color
            })
            log_alert(f"{domain} 触发通知: {level} (今日工作日: {is_today_workday})")
            
            if not config.TEST_MODE:
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

    # 只要状态有变化（包括恢复正常），或者文件根本不存在，就执行保存
    if state_changed or not os.path.exists(config.STATE_FILE):
        save_state(state)
        log_system(f"同步状态记录至文件: {config.STATE_FILE}")

    # 生产模式下，任务结束后重新计算明天的随机运行时间并排程
    if not config.TEST_MODE:
        schedule_next_run()

def schedule_next_run(silent=False):
    """
    精确计算下一次在明天的 09:00 - 09:59 之间的随机时间，
    并通过单次秒级延迟调度进行排程，彻底避免 at() 方案对同一天排程时引发的重复触发与失效 Bug。
    """
    # 清除旧的 daily_job 排程
    schedule.clear('daily_job')
    
    now = datetime.datetime.now()
    # 锁定日期为明天
    target_date = now.date() + datetime.timedelta(days=1)
    
    # 随机生成明天 09:00 - 09:59 的某个时分秒
    random_minute = random.randint(0, 59)
    random_second = random.randint(0, 59)
    target_time = datetime.datetime.combine(
        target_date,
        datetime.time(9, random_minute, random_second)
    )
    
    delay_seconds = (target_time - now).total_seconds()
    if delay_seconds < 0:
        # 安全防御，若极特殊情况下为负，直接推迟一天
        delay_seconds += 86400
        
    # 注册单次延迟定时器任务
    schedule.every(delay_seconds).seconds.do(run_task).tag('daily_job')
    
    if not silent:
        target_time_str = target_time.strftime('%Y-%m-%d %H:%M:%S')
        log_system(f"计划任务已排定：下一次巡检将于 {Colors.YELLOW}{target_time_str}{Colors.RESET} 执行 (延迟 {delay_seconds:.0f} 秒)")
