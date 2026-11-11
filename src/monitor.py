import os
import datetime
import smtplib
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import src.utils.config as config
from src.utils.logger import log_system, log_info, log_ok, log_warn, log_alert, log_error
from src.utils.file_io import atomic_write_file
from src.utils.cert import check_ssl

# 告警等级权重（用于判断是否“升级”）
LEVEL_WEIGHT = {
    "正常": 0,
    "提醒": 1,
    "警告": 2,
    "严重": 3,
    "失败": 4
}
RUNTIME_ERROR = None

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
        return False
    return atomic_write_file(config.STATE_FILE, state, is_json=True)

def record_monitor_error(message):
    global RUNTIME_ERROR
    RUNTIME_ERROR = message
    if config.TEST_MODE:
        return
    state = load_state()
    meta = state.get('__meta__')
    if not isinstance(meta, dict):
        meta = state['__meta__'] = {}
    meta['last_error'] = message
    meta['last_run_at'] = datetime.datetime.now().isoformat(timespec='seconds')
    if not save_state(state):
        log_error("无法保存巡检异常状态")

# ---------------------------------------------------------
# 通知模块
# ---------------------------------------------------------
def send_email_alert(alerts):
    if not config.SMTP_HOST or not config.SMTP_USER or not config.EMAIL_TO: 
        return None

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
            <h3>{"🚨 " if config.ALERT_USE_EMOJI else ""}SSL 证书到期巡检报告 {"(测试模式)" if config.TEST_MODE else ""}</h3>
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
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10) if config.SMTP_PORT in [465, 994] else smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        if config.SMTP_PORT not in [465, 994]: 
            server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASS)
        recipients = [email.strip() for email in config.EMAIL_TO.split(',') if email.strip()]
        server.sendmail(config.SMTP_USER, recipients, msg.as_string())
        server.quit()
        log_info("邮件告警发送成功")
        return True
    except Exception as e:
        log_error(f"邮件发送失败: {e}")
        return False

def post_to_dingtalk(data, webhook=None, secret=None, keyword=None):
    wh = webhook if webhook is not None else config.DINGTALK_WEBHOOK
    sec = secret if secret is not None else config.DINGTALK_SECRET
    kw = keyword if keyword is not None else config.DINGTALK_KEYWORD
    
    if not wh: 
        return False, "钉钉 Webhook 地址未配置"
    
    # 自动在 Webhook 只有 token 的情况下补全 URL
    if wh and not wh.startswith('http'):
        wh = f"https://oapi.dingtalk.com/robot/send?access_token={wh}"
    
    # 自动注入自定义关键词（如果未在内容中出现）
    if kw:
        if data.get("msgtype") == "markdown" and "markdown" in data:
            text = data["markdown"].get("text", "")
            if kw not in text:
                data["markdown"]["text"] = f"{text}\n\n匹配关键词：{kw}"
        elif data.get("msgtype") == "text" and "text" in data:
            content = data["text"].get("content", "")
            if kw not in content:
                data["text"]["content"] = f"{content}\n匹配关键词：{kw}"
    # 签名计算 (加签)
    url = wh
    if sec:
        timestamp = str(round(time.time() * 1000))
        secret_enc = sec.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, sec)
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
        try:
            res_json = res.json()
        except Exception:
            res_json = None

        errcode = res_json.get("errcode") if isinstance(res_json, dict) else None
        errmsg = res_json.get("errmsg", "") if isinstance(res_json, dict) else ""

        if res.status_code != 200 or errcode != 0:
            err_msg = f"HTTP {res.status_code}, errcode: {errcode}, errmsg: {errmsg}, Response: {res.text}"
            log_error(f"钉钉发送失败: {err_msg}")
            return False, err_msg
        else:
            log_info(f"钉钉消息发送成功: {res.status_code}")
            return True, "Success"
    except Exception as e:
        err_msg = str(e)
        log_error(f"钉钉发送请求发生异常: {err_msg}")
        return False, err_msg

def send_dingtalk_alert(alerts):
    if not config.DINGTALK_WEBHOOK: 
        return None
    
    title_prefix = "[TEST] " if config.TEST_MODE else ""
    
    emoji_shield = "🛡️ " if config.ALERT_USE_EMOJI else ""
    emoji_globe = "🌐 " if config.ALERT_USE_EMOJI else ""
    emoji_chart = "📊 " if config.ALERT_USE_EMOJI else ""
    emoji_hourglass = "⏳ " if config.ALERT_USE_EMOJI else ""
    
    text = f"### {title_prefix}{emoji_shield}SSL 证书到期监控告警\n\n"
    text += f"> 策略: {config.ALERT_INFO_DAYS}天提醒 / {config.ALERT_WARNING_DAYS}天警告 / {config.ALERT_CRITICAL_DAYS}天严重\n\n"
    text += f"---\n\n"
    
    for i, a in enumerate(alerts):
        if i > 0:
            text += f"---\n\n"
        days_str = f"{a['days']} 天" if a['days'] is not None else "读取失败"
        emoji_detail = ("📅 " if a['days'] is not None else "🔴 ") if config.ALERT_USE_EMOJI else ""
        detail_label = "到期时间" if a['days'] is not None else "错误详情"
        
        text += f"{emoji_globe}**域名:** {a['domain']}\n\n"
        text += f"{emoji_chart}**告警等级:** <font color='{a['color']}'>{a['level']}</font>\n\n"
        text += f"{emoji_hourglass}**剩余天数:** <font color='{a['color']}'>**{days_str}**</font>\n\n"
        text += f"{emoji_detail}**{detail_label}:** {a['detail']}\n\n"

    data = {"msgtype": "markdown", "markdown": {"title": "SSL证书巡检报告", "text": text}}
    success, _ = post_to_dingtalk(data)
    return success

def send_system_error_alert(error_msg, file_path=None):
    """当发生严重系统配置错误时（如找不到域名列表），发送紧急通知"""
    if not config.DINGTALK_WEBHOOK: 
        return
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    emoji_red = "🔴 " if config.ALERT_USE_EMOJI else ""
    emoji_warn = "⚠️ " if config.ALERT_USE_EMOJI else ""
    emoji_folder = "📂 " if config.ALERT_USE_EMOJI else ""
    emoji_calendar = "📅 " if config.ALERT_USE_EMOJI else ""
    emoji_bulb = "💡 " if config.ALERT_USE_EMOJI else ""
    
    text = f"### {emoji_red}SSL 监控系统运行错误\n\n"
    text += f"> 警告: 严重系统配置错误\n\n"
    text += f"---\n\n"
    text += f"{emoji_warn}**错误原因:** {error_msg}\n\n"
    if file_path:
        text += f"{emoji_folder}**容器路径:** {file_path}\n\n"
    text += f"{emoji_calendar}**当前时间:** {time_str}\n\n"
    text += f"{emoji_bulb}**排查建议:** 请检查容器挂载路径或配置文件内容！"
    
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
def run_task(retry_only=False):
    # 每次运行任务时重新从磁盘重载全局配置参数
    config.load_all_configs()
    
    abs_path = os.path.abspath(config.LIST_FILE)
    log_system(f"开始执行 SSL 证书巡检任务 (路径: {abs_path})")
    
    if not os.path.exists(config.LIST_FILE):
        err = "找不到配置文件"
        log_error(f"{err}: {abs_path}")
        send_system_error_alert(err, abs_path)
        record_monitor_error("域名列表文件不存在")
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
        record_monitor_error("域名列表为空")
        return

    email_alerts = []
    dingtalk_alerts = []
    state = load_state()
    state_changed = False
    now = datetime.datetime.now()
    if retry_only:
        domains = [domain for domain in domains if isinstance(state.get(domain), dict)
                   and state[domain].get('retry_at')
                   and datetime.datetime.fromisoformat(state[domain]['retry_at']) <= now]
        if not domains:
            return
    log_system(f"开始检测 {len(domains)} 个域名: {', '.join(domains)}")

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

        last_state = state.get(domain, {})
        if not isinstance(last_state, dict):
            last_state = {'level': last_state}
        last_level = last_state.get('level', '正常')
        legacy_alert_level = last_state.get('alert_level', last_level)
        last_was_holiday = last_state.get('is_holiday', False)
        alert = {'domain': domain, 'days': days, 'detail': expire_time,
                 'level': level, 'color': color}
        channel_alerts = (
            ('email', bool(config.SMTP_HOST and config.SMTP_USER and config.EMAIL_TO), email_alerts),
            ('dingtalk', bool(config.DINGTALK_WEBHOOK), dingtalk_alerts),
        )
        for channel, enabled, pending in channel_alerts:
            previous_level = last_state.get(f'{channel}_alert_level', legacy_alert_level)
            if enabled and (config.TEST_MODE or (level != '正常' and (
                LEVEL_WEIGHT.get(level, 0) > LEVEL_WEIGHT.get(previous_level, 0)
                or (is_today_workday and last_was_holiday)
            ))):
                pending.append(alert)

        if alert in email_alerts or alert in dingtalk_alerts:
            log_alert(f"{domain} 触发通知: {level} (今日工作日: {is_today_workday})")
            
        if not config.TEST_MODE:
            count = (last_state.get('retry_count', 0) + 1) if retry_only else 0
            retry_at = (now + datetime.timedelta(minutes=30)).isoformat() if not ssl_info.get('success') and count < 3 else None
            state[domain] = {
                **last_state,
                'level': level,
                'alert_level': legacy_alert_level,
                'email_alert_level': last_state.get('email_alert_level', legacy_alert_level),
                'dingtalk_alert_level': last_state.get('dingtalk_alert_level', legacy_alert_level),
                'is_holiday': not is_today_workday if level != '正常' else False,
                'alert_time': now.strftime('%Y-%m-%d %H:%M:%S') if level != last_level else last_state.get('alert_time') or now.strftime('%Y-%m-%d %H:%M:%S'),
                'success': ssl_info.get('success', False),
                'days': days,
                'expire': expire_time,
                'color': color,
                'ip': ssl_info.get('ip'),
                'issuer': ssl_info.get('issuer'),
                'display_host': ssl_info.get('display_host'),
                'punycode_host': ssl_info.get('punycode_host'),
                'error': ssl_info.get('error') if not ssl_info.get('success') else None,
                'retry_count': count,
                'retry_at': retry_at,
            }
            if level == '正常':
                state[domain]['alert_level'] = '正常'
                state[domain]['email_alert_level'] = '正常'
                state[domain]['dingtalk_alert_level'] = '正常'
            state_changed = True
        if level == '正常':
            log_ok(f"{domain} 状态良好 (剩余 {days} 天)")
        elif alert not in email_alerts and alert not in dingtalk_alerts:
            log_info(f"{domain} 告警等级未提升: {level}")

    delivery_errors = []
    for channel, pending, sender in (
        ('email', email_alerts, send_email_alert),
        ('dingtalk', dingtalk_alerts, send_dingtalk_alert),
    ):
        if not pending:
            continue
        delivered = sender(pending)
        if not config.TEST_MODE:
            if delivered:
                for alert in pending:
                    state[alert['domain']][f'{channel}_alert_level'] = alert['level']
            else:
                log_warn(f"{channel} 告警未送达，将重试该通道")
                delivery_errors.append('邮件' if channel == 'email' else '钉钉')
                for alert in pending:
                    entry = state[alert['domain']]
                    if entry['retry_count'] < 3:
                        entry['retry_at'] = (now + datetime.timedelta(minutes=30)).isoformat()

    if not config.TEST_MODE:
        meta = state.setdefault('__meta__', {})
        meta['last_run_at'] = now.isoformat(timespec='seconds')
        meta['last_error'] = f"{'、'.join(delivery_errors)}告警发送失败，等待重试" if delivery_errors else None
        if not retry_only:
            meta['last_daily_run'] = now.date().isoformat()
        state_changed = True

    # 只要状态有变化（包括恢复正常），或者文件根本不存在，就执行保存
    if state_changed or not os.path.exists(config.STATE_FILE):
        if not save_state(state):
            raise IOError(f"保存巡检状态失败: {config.STATE_FILE}")
        log_system(f"同步状态记录至文件: {config.STATE_FILE}")
    global RUNTIME_ERROR
    RUNTIME_ERROR = None

def daily_due(now=None):
    now = now or datetime.datetime.now()
    if now.time() < datetime.time(9, 15):
        return False
    return load_state().get('__meta__', {}).get('last_daily_run') != now.date().isoformat()

def retry_due(now=None):
    now = now or datetime.datetime.now()
    if not os.path.exists(config.LIST_FILE):
        return False
    with open(config.LIST_FILE, encoding='utf-8') as file:
        active_domains = {line.split('#')[0].strip() for line in file}
    state = load_state()
    for domain in active_domains:
        entry = state.get(domain)
        if isinstance(entry, dict) and entry.get('retry_at'):
            try:
                if datetime.datetime.fromisoformat(entry['retry_at']) <= now:
                    return True
            except ValueError:
                pass
    return False
