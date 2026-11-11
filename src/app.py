import os
import secrets
import hashlib
import time
import datetime
from datetime import timedelta
from flask import Flask, request, jsonify, session, redirect
from flask.sessions import SecureCookieSessionInterface
from werkzeug.exceptions import HTTPException
from concurrent.futures import ThreadPoolExecutor


import src.utils.config as config
from src.utils.logger import log_info, log_ok, log_warn, log_alert, log_error
from src.utils.file_io import atomic_write_file
from src.utils.cert import check_ssl
from src.utils.domain import normalize_domain

class DynamicSecureSessionInterface(SecureCookieSessionInterface):
    def get_cookie_secure(self, app):
        val = app.config.get('SESSION_COOKIE_SECURE')
        if val is not None:
            return val
        try:
            # 兼容：如果当前请求是 HTTPS，或者处于反向代理 HTTPS 后面，则使用 Secure Cookie
            return request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
        except Exception:
            return False

import os

cur_dir = os.path.dirname(os.path.abspath(__file__))
dist_path = os.path.abspath(os.path.join(cur_dir, "..", "dist"))
app = Flask(__name__, static_folder=dist_path, static_url_path='')
app.session_interface = DynamicSecureSessionInterface()

# 配置 Session cookie 安全属性
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=None,  # 设为 None，由 DynamicSecureSessionInterface 动态决定
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    MAX_CONTENT_LENGTH=1024 * 1024
)

@app.errorhandler(Exception)
def handle_api_error(error):
    if not request.path.startswith('/api/'):
        if isinstance(error, HTTPException):
            return error
        log_error(f"页面请求处理失败: {request.path}: {error}")
        return "Internal Server Error", 500
    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code
    log_error(f"API 请求处理失败: {request.method} {request.path}: {error}")
    return jsonify({"error": "服务器处理请求失败，请查看服务日志"}), 500

def init_flask_secret():
    secret = None
    if os.path.exists(config.CONFIG_FILE):
        try:
            import json
            with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                secret = cfg.get('flask_secret_key')
        except Exception:
            pass
            
    if not secret:
        secret = secrets.token_hex(32)
        try:
            cfg = {}
            if os.path.exists(config.CONFIG_FILE):
                import json
                with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg['flask_secret_key'] = secret
            atomic_write_file(config.CONFIG_FILE, cfg, is_json=True)
        except Exception:
            pass
    return secret

app.secret_key = init_flask_secret()

# ---------------------------------------------------------
# 登录防暴力破解控制台（内存数据库）
# ---------------------------------------------------------
LOGIN_ATTEMPTS = {}  # 格式: { ip_address: { failed_count: int, lock_until: float } }

# ---------------------------------------------------------
# 用户及域名存储交互
# ---------------------------------------------------------
def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    pwd_hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return pwd_hash_bytes.hex(), salt

def load_users():
    import json
    if os.path.exists(config.USERS_FILE):
        try:
            with open(config.USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_error(f"读取用户文件失败: {e}")
            raise RuntimeError("用户数据文件不可读，请修复后重试") from e
    return {}

def save_users(users):
    if atomic_write_file(config.USERS_FILE, users, is_json=True):
        log_info(f"用户信息已更新保存至 {config.USERS_FILE}")
        return True
    return False

def get_domains():
    if not os.path.exists(config.LIST_FILE):
        return []
    domains = []
    with open(config.LIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.split("#")[0].strip()
            if clean:
                domains.append(clean)
    return domains

def save_domains(domains):
    content = "\n".join(domains) + "\n"
    if atomic_write_file(config.LIST_FILE, content, is_json=False):
        log_info(f"域名列表已同步写入 {config.LIST_FILE}，总域名数: {len(domains)}")
        return True
    return False

def cache_ssl_result(state, domain, ssl_info):
    """更新页面检测缓存，同时保留巡检的已通知等级。"""
    previous = state.get(domain)
    previous = previous if isinstance(previous, dict) else {}
    level = ssl_info.get("level", "正常")
    previous_level = previous.get("level", "正常")
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    retry_at = previous.get("retry_at") if ssl_info.get('success') else (
        datetime.datetime.now() + datetime.timedelta(minutes=30)
    ).isoformat()
    state[domain] = {
        **previous,
        "level": level,
        "alert_level": previous.get("alert_level", previous_level),
        "is_holiday": previous.get("is_holiday", False) if level != "正常" else False,
        "alert_time": now if level != previous_level else previous.get("alert_time") or now,
        "success": ssl_info.get("success", False),
        "days": ssl_info.get("days"),
        "expire": ssl_info.get("expire") if ssl_info.get("success") else ssl_info.get("error"),
        "color": ssl_info.get("color"),
        "ip": ssl_info.get("ip"),
        "issuer": ssl_info.get("issuer"),
        "display_host": ssl_info.get("display_host"),
        "punycode_host": ssl_info.get("punycode_host"),
        "error": ssl_info.get("error") if not ssl_info.get("success") else None
    }
    state[domain]["retry_count"] = previous.get("retry_count", 0) if ssl_info.get('success') else 0
    state[domain]["retry_at"] = retry_at

# ---------------------------------------------------------
# 会话拦截器（越权安全加固修复）
# ---------------------------------------------------------
@app.before_request
def check_authentication():
    # 对 /api/ 请求进行鉴权拦截
    if request.path.startswith('/api/'):
        # 允许任何人调用的认证相关 API (不区分方法)
        public_apis = [
            '/api/auth/status',
            '/api/auth/login',
            '/api/auth/register',
            '/api/monitor/status'
        ]
        
        is_public = False
        if request.path in public_apis:
            is_public = True
        elif request.path == '/api/domains' and request.method == 'GET' and request.args.get('refresh', 'false').lower() != 'true':
            # 只放行获取域名列表的 GET 方法，保护 POST/DELETE 免遭越权
            is_public = True
            
        if not is_public and 'username' not in session:
            log_warn(f"Unauthorized API request: {request.method} {request.path} from IP {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        if request.method in ('POST', 'PUT', 'DELETE') and request.is_json:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify({"error": "请求体必须是 JSON 对象"}), 400
            string_fields = {
                'username', 'password', 'domain', 'old_domain', 'new_domain',
                'domains', 'smtp_host', 'smtp_user', 'smtp_pass', 'email_to',
                'dingtalk_webhook', 'dingtalk_secret', 'dingtalk_keyword'
            }
            if any(key in payload and not isinstance(payload[key], str) for key in string_fields):
                return jsonify({"error": "文本字段格式无效"}), 400
    
    # 2. 已登录用户访问 /login 自动重定向到 /dashboard
    if request.path == '/login' and 'username' in session:
        return redirect('/dashboard')
    
    # 4. 根路径 / 智能分流
    if request.path == '/':
        return redirect('/dashboard')
    
    # 审计记录 API 访问日志
    if request.path.startswith('/api/'):
        log_info(f"API Access: {request.method} {request.path} from IP {request.remote_addr}")

# ---------------------------------------------------------
# HTTP 页面路由映射
# ---------------------------------------------------------
@app.route('/')
@app.route('/login')
@app.route('/dashboard')
@app.route('/dashboard/domains')
@app.route('/dashboard/settings')
def index_page():
    try:
        return app.send_static_file('index.html')
    except Exception:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        fallback_paths = [
            os.path.join(cur_dir, "..", "dist", "index.html"),
            os.path.join(cur_dir, "..", "templates", "index.html")
        ]
        for p in fallback_paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
        log_error("Frontend build file index.html or templates/index.html is missing!")
        return "<h3>SSL Monitor: 前端资源文件缺失，请先编译前端项目。</h3>", 404

# ---------------------------------------------------------
# API 控制端点
# ---------------------------------------------------------

# 1. 获取会话与注册状态
@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    users = load_users()
    logged_in = 'username' in session
    return jsonify({
        "logged_in": logged_in,
        "username": session.get('username') if logged_in else None,
        "has_users": len(users) > 0
    })

# 2. 安全用户注册
@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    users = load_users()
    if len(users) > 0 and 'username' not in session:
        log_warn(f"Blocked unauthorized registration attempt from IP {request.remote_addr}")
        return jsonify({"error": "Unauthorized"}), 401

    if username in users:
        return jsonify({"error": "用户名已存在"}), 400

    pwd_hash, salt = hash_password(password)
    users[username] = {"pwd_hash": pwd_hash, "salt": salt}
    if not save_users(users):
        return jsonify({"error": "保存用户失败"}), 500
    
    log_ok(f"Registered new user '{username}' from IP {request.remote_addr}")
    return jsonify({"success": True})

# 3. 安全用户登录
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    ip = request.remote_addr
    now_ts = time.time()

    attempt = LOGIN_ATTEMPTS.get(ip, {"failed_count": 0, "lock_until": 0.0})
    if attempt["lock_until"] > now_ts:
        remaining_lock = int(attempt["lock_until"] - now_ts)
        log_alert(f"Login request blocked for IP {ip}: locked for {remaining_lock}s due to brute force risk")
        return jsonify({"error": f"由于密码连续错误，您的 IP 已被锁定，请在 {remaining_lock} 秒后重试"}), 429

    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    users = load_users()
    
    def handle_login_failure():
        failed_count = attempt["failed_count"] + 1
        delay = min(failed_count * 1.5, 10.0)
        log_warn(f"Login failed for user '{username}' from IP {ip}. Triggering delay: {delay:.1f}s")
        time.sleep(delay)
        
        lock_until = now_ts + 300.0 if failed_count >= 5 else 0.0
        LOGIN_ATTEMPTS[ip] = {"failed_count": failed_count, "lock_until": lock_until}
        
        if failed_count >= 5:
            log_alert(f"IP {ip} has failed login 5 times. Lock triggered until {datetime.datetime.fromtimestamp(lock_until).strftime('%H:%M:%S')}")
            return jsonify({"error": "密码连续错误多次，该 IP 已被临时锁定 5 分钟，请稍后重试"}), 429
        return jsonify({"error": "用户名或密码错误"}), 400

    if username not in users:
        return handle_login_failure()

    user_info = users[username]
    check_hash, _ = hash_password(password, user_info['salt'])
    
    if check_hash != user_info['pwd_hash']:
        return handle_login_failure()

    LOGIN_ATTEMPTS[ip] = {"failed_count": 0, "lock_until": 0.0}
    session['username'] = username
    session.permanent = True
    
    log_ok(f"User '{username}' logged in successfully from IP {ip}")
    return jsonify({"success": True, "username": username})

# 4. 用户注销
@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    user = session.get('username', 'Unknown')
    session.clear()
    log_ok(f"User '{user}' logged out from IP {request.remote_addr}")
    return jsonify({"success": True})

# 5. 获取域名状态列表
@app.route('/api/monitor/status', methods=['GET'])
def monitor_status():
    from src.monitor import load_state, RUNTIME_ERROR
    state = load_state()
    meta = state.get('__meta__', {})
    if not isinstance(meta, dict):
        meta = {}
    domains = set(get_domains())
    failed_count = sum(
        1 for domain in domains if isinstance(state.get(domain), dict)
        and state[domain].get('success') is False
    )
    return jsonify({
        "last_run_at": meta.get('last_run_at'),
        "last_daily_run": meta.get('last_daily_run'),
        "last_error": RUNTIME_ERROR or meta.get('last_error'),
        "failed_domains": failed_count
    })

# 5. 获取域名状态列表
@app.route('/api/domains', methods=['GET'])
def list_domains():
    domains = get_domains()
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    # 动态热加载当前的检测阈值
    info, warn, crit = config.ALERT_INFO_DAYS, config.ALERT_WARNING_DAYS, config.ALERT_CRITICAL_DAYS
    
    from src.monitor import load_state, save_state
    state = load_state()
    state_changed = False
    
    result = []
    to_check = []
    
    if refresh:
        to_check = domains
    else:
        for d in domains:
            if d in state and isinstance(state[d], dict) and "success" in state[d]:
                cached = state[d]
                from src.utils.cert import parse_domain_and_port, get_domain_variants
                hostname, _ = parse_domain_and_port(d)
                display_h, punycode_h = get_domain_variants(hostname)
                
                ssl_info = {
                    "success": cached.get("success", False),
                    "days": cached.get("days"),
                    "level": cached.get("level", "正常"),
                    "color": cached.get("color", "#32CD32"),
                    "ip": cached.get("ip"),
                    "issuer": cached.get("issuer"),
                    "display_host": cached.get("display_host") or display_h,
                    "punycode_host": cached.get("punycode_host") or punycode_h
                }
                if ssl_info["success"]:
                    ssl_info["expire"] = cached.get("expire")
                else:
                    ssl_info["error"] = cached.get("error")
                result.append({"domain": d, "ssl": ssl_info})
            else:
                to_check.append(d)
                
    if to_check:
        # 并发线程池检测
        def check_single(d):
            return d, check_ssl(d, info, warn, crit)
            
        max_workers = min(len(to_check), 20)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            checked_results = executor.map(check_single, to_check)
            
        for d, ssl_info in checked_results:
            result.append({"domain": d, "ssl": ssl_info})
            if not config.TEST_MODE:
                cache_ssl_result(state, d, ssl_info)
                state_changed = True
                
        if state_changed:
            if not save_state(state):
                return jsonify({"error": "保存检测状态失败"}), 500
            
    # 按 websites_list.txt 中的物理顺序排序返回给前端
    domain_order = {d: i for i, d in enumerate(domains)}
    result.sort(key=lambda x: domain_order.get(x["domain"], 999))
    
    return jsonify(result)

# 6. 单个域名清洗与添加
@app.route('/api/domains', methods=['POST'])
def add_domain():
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "域名不能为空"}), 400

    domain = normalize_domain(domain)

    if not domain:
        return jsonify({"error": "无效的域名格式"}), 400

    domains = get_domains()
    if domain in domains:
        return jsonify({"error": "域名已存在"}), 400

    domains.append(domain)
    if not save_domains(domains):
        return jsonify({"error": "保存域名失败"}), 500
    return jsonify({"success": True, "domain": domain})

# 7. 单个域名删除
@app.route('/api/domains', methods=['DELETE'])
def delete_domain():
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "域名不能为空"}), 400

    domains = get_domains()
    if domain not in domains:
        return jsonify({"error": "域名不存在"}), 404

    domains.remove(domain)
    if not save_domains(domains):
        return jsonify({"error": "保存域名失败"}), 500
    from src.monitor import load_state, save_state
    state = load_state()
    if domain in state:
        del state[domain]
        if not config.TEST_MODE and not save_state(state):
            return jsonify({"error": "域名已删除，但清理检测状态失败"}), 500
    return jsonify({"success": True})

# 7.1 单个域名修改更新
@app.route('/api/domains', methods=['PUT'])
def update_domain():
    data = request.get_json() or {}
    old_domain = data.get('old_domain', '').strip()
    new_domain = data.get('new_domain', '').strip()

    if not old_domain or not new_domain:
        return jsonify({"error": "原域名和新域名不能为空"}), 400

    new_domain = normalize_domain(new_domain)

    if not new_domain:
        return jsonify({"error": "无效的新域名格式"}), 400

    domains = get_domains()
    if old_domain not in domains:
        return jsonify({"error": "原域名不存在"}), 404

    if new_domain != old_domain and new_domain in domains:
        return jsonify({"error": "新域名已存在于列表中"}), 400

    idx = domains.index(old_domain)
    domains[idx] = new_domain
    if not save_domains(domains):
        return jsonify({"error": "保存域名失败"}), 500

    info, warn, crit = config.ALERT_INFO_DAYS, config.ALERT_WARNING_DAYS, config.ALERT_CRITICAL_DAYS
    ssl_info = check_ssl(new_domain, info, warn, crit)

    # 新域名需要重新建立告警状态，不能继承原域名的通知记录。
    from src.monitor import load_state, save_state
    state = load_state()
    if new_domain != old_domain:
        state.pop(old_domain, None)
    cache_ssl_result(state, new_domain, ssl_info)
    if not config.TEST_MODE:
        if not save_state(state):
            return jsonify({"error": "保存检测状态失败"}), 500

    log_ok(f"Domain updated from '{old_domain}' to '{new_domain}' by user '{session.get('username')}'")
    return jsonify({"success": True, "domain": new_domain, "ssl": ssl_info})

# 8. 批量域名导入
@app.route('/api/domains/import', methods=['POST'])
def import_domains():
    data = request.get_json() or {}
    raw_text = data.get('domains', '').strip()
    if not raw_text:
        return jsonify({"error": "导入内容不能为空"}), 400

    lines = raw_text.split('\n')
    domains = get_domains()
    added_count = 0
    duplicate_count = 0
    invalid_count = 0

    for line in lines:
        if not line.split('#', 1)[0].strip():
            continue
        cleaned = normalize_domain(line)
        if not cleaned:
            invalid_count += 1
            continue

        if cleaned not in domains:
            domains.append(cleaned)
            added_count += 1
        elif cleaned in domains:
            duplicate_count += 1

    if added_count > 0:
        if not save_domains(domains):
            return jsonify({"error": "保存域名失败"}), 500

    log_ok(f"Batch domains imported by user '{session.get('username')}': added {added_count}, skipped {duplicate_count}")
    return jsonify({
        "success": True,
        "added_count": added_count,
        "duplicate_count": duplicate_count,
        "invalid_count": invalid_count,
        "total_count": len(domains)
    })

# 9. 单域名局部刷新检测
@app.route('/api/domains/check', methods=['GET'])
def check_single_domain():
    domain = request.args.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "域名不能为空"}), 400
    if domain not in get_domains():
        return jsonify({"error": "域名不存在"}), 404
    info, warn, crit = config.ALERT_INFO_DAYS, config.ALERT_WARNING_DAYS, config.ALERT_CRITICAL_DAYS
    ssl_info = check_ssl(domain, info, warn, crit)
    if not config.TEST_MODE:
        from src.monitor import load_state, save_state
        state = load_state()
        cache_ssl_result(state, domain, ssl_info)
        if not save_state(state):
            return jsonify({"error": "保存检测状态失败"}), 500
    return jsonify({"domain": domain, "ssl": ssl_info})

# 10. 系统参数配置读取
@app.route('/api/settings', methods=['GET'])
def get_settings():
    # 动态载入配置
    config.load_all_configs()
    
    # 构建 json config
    json_config = {}
    if os.path.exists(config.CONFIG_FILE):
        try:
            import json
            with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                json_config = json.load(f)
        except Exception:
            pass

    # 脱敏输出发信口令
    smtp_pass = json_config.get('smtp_pass', '')
    if smtp_pass:
        smtp_pass = '******'

    return jsonify({
        "smtp_host": config.SMTP_HOST,
        "smtp_port": config.SMTP_PORT,
        "smtp_user": config.SMTP_USER,
        "smtp_pass": smtp_pass,
        "email_to": config.EMAIL_TO,
        "dingtalk_webhook": config.DINGTALK_WEBHOOK,
        "dingtalk_secret": config.DINGTALK_SECRET,
        "dingtalk_keyword": config.DINGTALK_KEYWORD,
        "alert_info_days": config.ALERT_INFO_DAYS,
        "alert_warning_days": config.ALERT_WARNING_DAYS,
        "alert_critical_days": config.ALERT_CRITICAL_DAYS,
        "alert_use_emoji": config.ALERT_USE_EMOJI
    })

# 11. 系统参数配置更改
@app.route('/api/settings', methods=['POST'])
def save_settings():
    new_cfg = request.get_json() or {}

    try:
        if 'smtp_port' in new_cfg and not 1 <= int(new_cfg['smtp_port']) <= 65535:
            raise ValueError('SMTP 端口必须在 1 至 65535 之间')
        thresholds = [
            int(new_cfg.get('alert_info_days', config.ALERT_INFO_DAYS)),
            int(new_cfg.get('alert_warning_days', config.ALERT_WARNING_DAYS)),
            int(new_cfg.get('alert_critical_days', config.ALERT_CRITICAL_DAYS)),
        ]
        if not (thresholds[0] >= thresholds[1] >= thresholds[2] >= 0):
            raise ValueError('告警天数须满足提醒 ≥ 警告 ≥ 严重 ≥ 0')
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    old_cfg = {}
    if os.path.exists(config.CONFIG_FILE):
        try:
            import json
            with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_cfg = json.load(f)
        except Exception:
            pass

    merged_cfg = old_cfg.copy()
    fields = [
        'smtp_host', 'smtp_port', 'smtp_user', 'email_to',
        'dingtalk_webhook', 'dingtalk_secret', 'dingtalk_keyword',
        'alert_info_days', 'alert_warning_days', 'alert_critical_days',
        'alert_use_emoji'
    ]
    for field in fields:
        if field in new_cfg:
            merged_cfg[field] = new_cfg[field]

    if 'smtp_pass' in new_cfg:
        smtp_pass = new_cfg['smtp_pass']
        merged_cfg['smtp_pass'] = old_cfg.get('smtp_pass', '') if smtp_pass == '******' else smtp_pass

    # 原子保存
    if atomic_write_file(config.CONFIG_FILE, merged_cfg, is_json=True):
        # 写入成功后触发热重载，同步全局变量
        config.load_all_configs()
        log_ok(f"System settings successfully updated by user '{session.get('username')}'")
        return jsonify({"success": True})
    else:
        return jsonify({"error": "保存配置失败"}), 500

# 12. 测试钉钉机器人连接状态
@app.route('/api/settings/test/dingtalk', methods=['POST'])
def test_settings_dingtalk():
    data = request.get_json() or {}
    webhook = data.get('dingtalk_webhook', '').strip()
    secret = data.get('dingtalk_secret', '')
    keyword = data.get('dingtalk_keyword', '').strip()
    
    if not webhook:
        return jsonify({"error": "Webhook 地址不能为空"}), 400
        
    # 简短 markdown 测试消息（不含 Emoji）
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    text_content = f"测试消息：您的钉钉机器人已成功连通。\n时间: {time_str}"
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "系统测试消息",
            "text": text_content
        }
    }
    
    from src.monitor import post_to_dingtalk
    success, msg = post_to_dingtalk(payload, webhook=webhook, secret=secret, keyword=keyword)
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"error": msg}), 500

# 13. 测试 SMTP 邮箱连通状态
@app.route('/api/settings/test/email', methods=['POST'])
def test_settings_email():
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    data = request.get_json() or {}
    host = data.get('smtp_host', '').strip()
    try:
        port = int(data.get('smtp_port', '465'))
        if not 1 <= port <= 65535:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "SMTP 端口必须在 1 至 65535 之间"}), 400
    user = data.get('smtp_user', '').strip()
    password = data.get('smtp_pass', '')
    email_to = data.get('email_to', '').strip()
    
    if not host or not user or not email_to:
        return jsonify({"error": "SMTP 服务器、发信账号和收件人不能为空"}), 400
        
    # 处理密码掩码
    if password == '******':
        # 从磁盘读取历史密码
        old_cfg = {}
        if os.path.exists(config.CONFIG_FILE):
            try:
                import json
                with open(config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    old_cfg = json.load(f)
            except Exception:
                pass
        password = old_cfg.get('smtp_pass', '')
        
    # 纯文本测试邮件（不含 Emoji）
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    subject = "【测试】通道连通性验证"
    text_body = f"测试消息：您的邮件发信配置已成功连通。\n时间: {time_str}"
    
    msg = MIMEMultipart()
    msg['From'], msg['To'] = user, email_to
    msg['Subject'] = subject
    msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    
    try:
        server = smtplib.SMTP_SSL(host, port, timeout=10) if port in [465, 994] else smtplib.SMTP(host, port, timeout=10)
        if port not in [465, 994]:
            server.starttls()
        server.login(user, password)
        recipients = [email.strip() for email in email_to.split(',') if email.strip()]
        server.sendmail(user, recipients, msg.as_string())
        server.quit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
