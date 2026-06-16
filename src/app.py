import os
import secrets
import hashlib
import time
import datetime
from datetime import timedelta
from flask import Flask, request, jsonify, session, redirect
from flask.sessions import SecureCookieSessionInterface
from concurrent.futures import ThreadPoolExecutor


import src.utils.config as config
from src.utils.logger import log_info, log_ok, log_warn, log_alert, log_error
from src.utils.file_io import atomic_write_file
from src.utils.cert import check_ssl

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

app = Flask(__name__)
app.session_interface = DynamicSecureSessionInterface()

# 配置 Session cookie 安全属性
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=None,  # 设为 None，由 DynamicSecureSessionInterface 动态决定
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)
)

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
            return {}
    return {}

def save_users(users):
    if atomic_write_file(config.USERS_FILE, users, is_json=True):
        log_info(f"用户信息已更新保存至 {config.USERS_FILE}")

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
            '/api/auth/register'
        ]
        
        is_public = False
        if request.path in public_apis:
            is_public = True
        elif request.path == '/api/domains' and request.method == 'GET':
            # 只放行获取域名列表的 GET 方法，保护 POST/DELETE 免遭越权
            is_public = True
            
        if not is_public and 'username' not in session:
            log_warn(f"Unauthorized API request: {request.method} {request.path} from IP {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
    
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
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(cur_dir, "..", "templates", "index.html"),
        os.path.join(cur_dir, "templates", "index.html"),
        os.path.join("templates", "index.html")
    ]
    
    template_path = None
    for p in candidates:
        if os.path.exists(p):
            template_path = p
            break
            
    if template_path:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        log_error("Frontend templates/index.html file is missing!")
        return "<h3>SSL Monitor: 前端资源文件 templates/index.html 缺失，请检查配置。</h3>", 404

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
    save_users(users)
    
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
                # 从状态缓存读取
                cached = state[d]
                ssl_info = {
                    "success": cached.get("success", False),
                    "days": cached.get("days"),
                    "level": cached.get("level", "正常"),
                    "color": cached.get("color", "#32CD32"),
                    "ip": cached.get("ip")
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
                existing_alert_time = ""
                existing_is_holiday = False
                last_level = "正常"
                if d in state and isinstance(state[d], dict):
                    existing_alert_time = state[d].get("alert_time", "")
                    existing_is_holiday = state[d].get("is_holiday", False)
                    last_level = state[d].get("level", "正常")
                
                level = ssl_info.get("level", "正常")
                if level != last_level:
                    current_alert_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    current_alert_time = existing_alert_time or datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                state[d] = {
                    "level": level,
                    "is_holiday": existing_is_holiday if level != "正常" else False,
                    "alert_time": current_alert_time,
                    "success": ssl_info.get("success", False),
                    "days": ssl_info.get("days"),
                    "expire": ssl_info.get("expire") if ssl_info.get("success") else ssl_info.get("error"),
                    "color": ssl_info.get("color"),
                    "ip": ssl_info.get("ip"),
                    "error": ssl_info.get("error") if not ssl_info.get("success") else None
                }
                state_changed = True
                
        if state_changed:
            save_state(state)
            
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

    # 清洗逻辑与之前完全对齐
    domain = domain.split("#")[0].strip()
    if domain.startswith("http://"):
        domain = domain[7:]
    elif domain.startswith("https://"):
        domain = domain[8:]
    if "/" in domain:
        domain = domain.split("/")[0]
    domain = domain.strip()

    if not domain:
        return jsonify({"error": "无效的域名格式"}), 400

    domains = get_domains()
    if domain in domains:
        return jsonify({"error": "域名已存在"}), 400

    domains.append(domain)
    save_domains(domains)
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
    save_domains(domains)
    return jsonify({"success": True})

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

    for line in lines:
        cleaned = line.split("#")[0].strip()
        if not cleaned:
            continue
        if cleaned.startswith("http://"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("https://"):
            cleaned = cleaned[8:]
        if "/" in cleaned:
            cleaned = cleaned.split("/")[0]
        cleaned = cleaned.strip()

        if cleaned and cleaned not in domains:
            domains.append(cleaned)
            added_count += 1
        elif cleaned in domains:
            duplicate_count += 1

    if added_count > 0:
        save_domains(domains)

    log_ok(f"Batch domains imported by user '{session.get('username')}': added {added_count}, skipped {duplicate_count}")
    return jsonify({
        "success": True,
        "added_count": added_count,
        "duplicate_count": duplicate_count,
        "total_count": len(domains)
    })

# 9. 单域名局部刷新检测
@app.route('/api/domains/check', methods=['GET'])
def check_single_domain():
    domain = request.args.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "域名不能为空"}), 400
    info, warn, crit = config.ALERT_INFO_DAYS, config.ALERT_WARNING_DAYS, config.ALERT_CRITICAL_DAYS
    ssl_info = check_ssl(domain, info, warn, crit)
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

    smtp_pass = new_cfg.get('smtp_pass', '')
    if smtp_pass == '******':
        merged_cfg['smtp_pass'] = old_cfg.get('smtp_pass', '')
    else:
        merged_cfg['smtp_pass'] = smtp_pass

    # 原子保存
    if atomic_write_file(config.CONFIG_FILE, merged_cfg, is_json=True):
        # 写入成功后触发热重载，同步全局变量
        config.load_all_configs()
        log_ok(f"System settings successfully updated by user '{session.get('username')}'")
        return jsonify({"success": True})
    else:
        return jsonify({"error": "保存配置失败"}), 500
