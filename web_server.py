#!/usr/bin/env python3
"""
SSL 证书监控管理 Web 服务
使用 Flask 框架重构，提供强密码哈希、登录防爆破、History 物理路由支持与全局彩色日志打印。
"""
import os
import ssl
import socket
import datetime
import json
import secrets
import hashlib
import time
from datetime import timedelta
from flask import Flask, request, jsonify, session

# ---------------------------------------------------------
# 日志美化模块（与巡检脚本日志完全对齐）
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

def log_system(msg): print(f"{get_time()} {Colors.CYAN}[SYSTEM]{Colors.RESET} ⚙️  {msg}", flush=True)
def log_info(msg):   print(f"{get_time()} {Colors.GREEN}[INFO  ]{Colors.RESET} ℹ️  {msg}", flush=True)
def log_ok(msg):     print(f"{get_time()} {Colors.GREEN}[OK    ]{Colors.RESET} ✅ {msg}", flush=True)
def log_warn(msg):   print(f"{get_time()} {Colors.YELLOW}[WARN  ]{Colors.RESET} ⚠️  {msg}", flush=True)
def log_alert(msg):  print(f"{get_time()} {Colors.MAGENTA}[ALERT ]{Colors.RESET} 🚨 {Colors.MAGENTA}{msg}{Colors.RESET}", flush=True)
def log_error(msg):  print(f"{get_time()} {Colors.RED}[ERROR ]{Colors.RESET} ❌ {Colors.RED}{msg}{Colors.RESET}", flush=True)

# ---------------------------------------------------------
# 基础配置与路径声明
# ---------------------------------------------------------
BASE_DIR = "/app/conf" if os.path.exists("/app/conf") else "."
LIST_FILE = os.path.join(BASE_DIR, "websites_list.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")

# ---------------------------------------------------------
# Flask 初始化与安全属性加固
# ---------------------------------------------------------
app = Flask(__name__)

# 配置 Session cookie 安全选项，防范 XSS 与 CSRF
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)
)

# 从配置文件中获取已有的 Flask secret key，如果没有则生成并写入
def init_flask_secret():
    secret = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                secret = cfg.get('flask_secret_key')
        except Exception:
            pass
            
    if not secret:
        secret = secrets.token_hex(32)
        try:
            cfg = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg['flask_secret_key'] = secret
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
    return secret

app.secret_key = init_flask_secret()

# ---------------------------------------------------------
# 登录防暴力破解控制台（内存数据库）
# ---------------------------------------------------------
LOGIN_ATTEMPTS = {}  # 格式: { ip_address: { failed_count: int, lock_until: float } }

# ---------------------------------------------------------
# 配置读写与动态阈值
# ---------------------------------------------------------
def get_alert_thresholds():
    info, warn, crit = 14, 7, 3
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                info = int(cfg.get('alert_info_days', 14))
                warn = int(cfg.get('alert_warning_days', 7))
                crit = int(cfg.get('alert_critical_days', 3))
        except Exception:
            pass
    return info, warn, crit

def get_alert_level(days):
    info, warn, crit = get_alert_thresholds()
    if days is None or days <= crit:
        return "严重", "#FF0000"
    elif days <= warn:
        return "警告", "#FF8C00"
    elif days <= info:
        return "提醒", "#1E90FF"
    return "正常", "#32CD32"

# ---------------------------------------------------------
# 加固版用户密码安全机制 (PBKDF2-HMAC-SHA256 迭代 100,000 次)
# ---------------------------------------------------------
def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    # 使用 PBKDF2-HMAC-SHA256 算法，迭代 100,000 次进行安全派生
    pwd_hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return pwd_hash_bytes.hex(), salt

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_error(f"读取用户文件失败: {e}")
            return {}
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
        log_info(f"用户信息已更新保存至 {USERS_FILE}")
    except Exception as e:
        log_error(f"写入用户文件失败: {e}")

# ---------------------------------------------------------
# 业务工具函数
# ---------------------------------------------------------
def get_domains():
    if not os.path.exists(LIST_FILE):
        return []
    domains = []
    with open(LIST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.split("#")[0].strip()
            if clean:
                domains.append(clean)
    return domains

def save_domains(domains):
    try:
        with open(LIST_FILE, "w", encoding="utf-8") as f:
            for d in domains:
                f.write(d + "\n")
        log_info(f"域名列表已同步写入 {LIST_FILE}，总域名数: {len(domains)}")
    except Exception as e:
        log_error(f"写入域名列表文件失败: {e}")

def check_ssl(domain_with_port):
    """检测 SSL 证书状态"""
    clean = domain_with_port.strip()
    if clean.startswith("http://"):
        clean = clean[7:]
    elif clean.startswith("https://"):
        clean = clean[8:]
    if "/" in clean:
        clean = clean.split("/")[0]

    if ":" in clean:
        parts = clean.split(":")
        hostname = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            port = 443
    else:
        hostname, port = clean, 443

    try:
        encoded = hostname.encode("idna").decode("ascii")
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((encoded, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=encoded) as ssock:
                cert_bin = ssock.getpeercert(binary_form=True)
                if not cert_bin:
                    return {
                        "success": False, "error": "无法获取证书二进制数据",
                        "level": "失败", "color": "#999999"
                    }

                # 优先使用 cryptography 解析二进制证书，未安装则进行 CERT_REQUIRED 握手降级
                try:
                    from cryptography import x509
                    from cryptography.hazmat.backends import default_backend
                    has_crypto = True
                except ImportError:
                    has_crypto = False

                if has_crypto:
                    cert = x509.load_der_x509_certificate(cert_bin, default_backend())
                    try:
                        expire_date = cert.not_valid_after_utc
                        expire_ts = expire_date.timestamp()
                    except AttributeError:
                        expire_date = cert.not_valid_after
                        expire_ts = expire_date.replace(tzinfo=datetime.timezone.utc).timestamp()
                else:
                    # 降级方案：使用内置 ssl 重新建立验证连接
                    context_req = ssl.create_default_context()
                    with socket.create_connection((encoded, port), timeout=10) as sock_req:
                        with context_req.wrap_socket(sock_req, server_hostname=encoded) as ssock_req:
                            cert_dict = ssock_req.getpeercert()
                            if not cert_dict:
                                return {
                                    "success": False, "error": "无法解析对端证书字典",
                                    "level": "失败", "color": "#999999"
                                }
                            not_after = cert_dict.get("notAfter")
                            if not not_after:
                                return {
                                    "success": False, "error": "证书缺少到期时间",
                                    "level": "失败", "color": "#999999"
                                }
                            expire_ts = ssl.cert_time_to_seconds(not_after)

                # 转换为本地时区时间
                expire_local = datetime.datetime.fromtimestamp(expire_ts)
                now_local = datetime.datetime.now()
                remaining = expire_local - now_local
                days = remaining.days

                level, color = get_alert_level(days)
                return {
                    "success": True,
                    "days": days,
                    "expire": expire_local.strftime("%Y-%m-%d %H:%M:%S"),
                    "level": level,
                    "color": color
                }
    except Exception as e:
        error_msg = str(e).split("] ")[-1]
        return {
            "success": False,
            "error": error_msg,
            "level": "失败",
            "color": "#999999"
        }

# ---------------------------------------------------------
# 会话拦截器
# ---------------------------------------------------------
@app.before_request
def check_authentication():
    # 放行的 API 列表
    public_apis = [
        '/api/auth/status',
        '/api/auth/login',
        '/api/auth/register',
        '/api/domains'
    ]
    
    # 1. 拦截未授权的受保护 API 请求 (直接返回 401 状态码)
    if request.path.startswith('/api/') and request.path not in public_apis:
        if 'username' not in session:
            log_warn(f"Unauthorized API request: {request.method} {request.path} from IP {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
    
    # 2. 拦截未授权的受保护后台页面请求 (域名管理和设置路径未授权时直接重定向至 /login)
    protected_pages = [
        '/dashboard/database',
        '/dashboard/settings'
    ]
    if request.path in protected_pages:
        if 'username' not in session:
            log_warn(f"Unauthorized Page Access: {request.path} from {request.remote_addr}, redirecting to /login")
            from flask import redirect
            return redirect('/login')
            
    # 3. 已登录用户访问 /login 自动重定向到 /dashboard
    if request.path == '/login' and 'username' in session:
        from flask import redirect
        return redirect('/dashboard')
    
    # 4. 根路径 / 智能分流
    if request.path == '/':
        from flask import redirect
        return redirect('/dashboard')
    
    # 审计记录 API 访问日志
    if request.path.startswith('/api/'):
        log_info(f"API Access: {request.method} {request.path} from IP {request.remote_addr}")

# ---------------------------------------------------------
# HTTP 路由控制
# ---------------------------------------------------------

# 前端物理路由映射均指向 templates/index.html
@app.route('/')
@app.route('/login')
@app.route('/dashboard')
@app.route('/dashboard/database')
@app.route('/dashboard/settings')
def index_page():
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")
    if not os.path.exists(template_path):
        template_path = os.path.join("templates", "index.html")
        
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        log_error("Frontend templates/index.html file is missing!")
        return "<h3>SSL Monitor: 前端资源文件 templates/index.html 缺失，请检查配置。</h3>", 404

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
    # 已经有管理员账号时，禁止未登录状态下注册
    if len(users) > 0 and 'username' not in session:
        log_warn(f"Blocked unauthorized registration attempt from IP {request.remote_addr}")
        return jsonify({"error": "Unauthorized"}), 401

    if username in users:
        return jsonify({"error": "用户名已存在"}), 400

    # PBKDF2 哈希注册
    pwd_hash, salt = hash_password(password)
    users[username] = {"pwd_hash": pwd_hash, "salt": salt}
    save_users(users)
    
    log_ok(f"Registered new user '{username}' from IP {request.remote_addr}")
    return jsonify({"success": True})

# 3. 安全用户登录（防暴破阻尼延迟与 IP 锁死）
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    ip = request.remote_addr
    now_ts = time.time()

    # 1. 检查 IP 锁定状态
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
    
    # 定义登录验证失败后的处理（递增延迟与锁死）
    def handle_login_failure():
        failed_count = attempt["failed_count"] + 1
        # 计算阻尼延迟延迟：每次错误增加 1.5s，最长 10s
        delay = min(failed_count * 1.5, 10.0)
        log_warn(f"Login failed for user '{username}' from IP {ip}. Triggering delay: {delay:.1f}s")
        time.sleep(delay)
        
        # 如果连续失败 >= 5 次，锁定 5 分钟 (300 秒)
        lock_until = now_ts + 300.0 if failed_count >= 5 else 0.0
        LOGIN_ATTEMPTS[ip] = {"failed_count": failed_count, "lock_until": lock_until}
        
        if failed_count >= 5:
            log_alert(f"IP {ip} has failed login 5 times. Lock triggered until {datetime.datetime.fromtimestamp(lock_until).strftime('%H:%M:%S')}")
            return jsonify({"error": "密码连续错误多次，该 IP 已被临时锁定 5 分钟，请稍后重试"}), 429
        return jsonify({"error": "用户名或密码错误"}), 400

    # 2. 检查用户是否存在
    if username not in users:
        return handle_login_failure()

    user_info = users[username]
    check_hash, _ = hash_password(password, user_info['salt'])
    
    # 3. 校验密码哈希
    if check_hash != user_info['pwd_hash']:
        return handle_login_failure()

    # 4. 验证成功，重置 IP 计数器，并建立 session
    LOGIN_ATTEMPTS[ip] = {"failed_count": 0, "lock_until": 0.0}
    session['username'] = username
    session.permanent = True  # 启用 session 的永久化配置（使用 PERMANENT_SESSION_LIFETIME 的时间）
    
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
    result = []
    for d in domains:
        ssl_info = check_ssl(d)
        result.append({"domain": d, "ssl": ssl_info})
    return jsonify(result)

# 6. 单个域名清洗与添加
@app.route('/api/domains', methods=['POST'])
def add_domain():
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "域名不能为空"}), 400

    # 安全清洗
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

# 8. 批量域名去重安全导入
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
    ssl_info = check_ssl(domain)
    return jsonify({"domain": domain, "ssl": ssl_info})

# 10. 系统参数配置读取
@app.route('/api/settings', methods=['GET'])
def get_settings():
    json_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                json_config = json.load(f)
        except Exception as e:
            log_error(f"加载系统配置出错: {e}")

    # 脱敏输出发信口令
    smtp_pass = json_config.get('smtp_pass', '')
    if smtp_pass:
        json_config['smtp_pass'] = '******'

    return jsonify({
        "smtp_host": json_config.get('smtp_host', ''),
        "smtp_port": int(json_config.get('smtp_port', 465)),
        "smtp_user": json_config.get('smtp_user', ''),
        "smtp_pass": json_config.get('smtp_pass', ''),
        "email_to": json_config.get('email_to', ''),
        "dingtalk_webhook": json_config.get('dingtalk_webhook', ''),
        "dingtalk_secret": json_config.get('dingtalk_secret', ''),
        "dingtalk_keyword": json_config.get('dingtalk_keyword', ''),
        "alert_info_days": int(json_config.get('alert_info_days', 14)),
        "alert_warning_days": int(json_config.get('alert_warning_days', 7)),
        "alert_critical_days": int(json_config.get('alert_critical_days', 3))
    })

# 11. 系统参数配置更改
@app.route('/api/settings', methods=['POST'])
def save_settings():
    new_cfg = request.get_json() or {}

    old_cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_cfg = json.load(f)
        except Exception:
            pass

    merged_cfg = old_cfg.copy()
    fields = [
        'smtp_host', 'smtp_port', 'smtp_user', 'email_to',
        'dingtalk_webhook', 'dingtalk_secret', 'dingtalk_keyword',
        'alert_info_days', 'alert_warning_days', 'alert_critical_days'
    ]
    for field in fields:
        if field in new_cfg:
            merged_cfg[field] = new_cfg[field]

    smtp_pass = new_cfg.get('smtp_pass', '')
    if smtp_pass == '******':
        merged_cfg['smtp_pass'] = old_cfg.get('smtp_pass', '')
    else:
        merged_cfg['smtp_pass'] = smtp_pass

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged_cfg, f, indent=4, ensure_ascii=False)
        log_ok(f"System settings successfully updated by user '{session.get('username')}'")
        return jsonify({"success": True})
    except Exception as e:
        log_error(f"更新系统设置文件失败: {e}")
        return jsonify({"error": f"保存配置失败: {str(e)}"}), 500

# ---------------------------------------------------------
# 程序入口与子进程拉起
# ---------------------------------------------------------
if __name__ == "__main__":
    import subprocess
    import sys
    import atexit

    # 自动拉起后台巡检进程 (ssl_monitor.py)
    monitor_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ssl_monitor.py")
    if not os.path.exists(monitor_script) and os.path.exists("ssl_monitor.py"):
        monitor_script = "ssl_monitor.py"

    if os.path.exists(monitor_script):
        log_system(f"Starting background monitor daemon: {monitor_script}")
        monitor_process = subprocess.Popen([sys.executable, "-u", monitor_script])
        
        def cleanup_subprocess():
            if monitor_process and monitor_process.poll() is None:
                log_system("Terminating background monitor process daemon...")
                monitor_process.terminate()
                try:
                    monitor_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    monitor_process.kill()
        atexit.register(cleanup_subprocess)
    else:
        log_warn("ssl_monitor.py not found. Background monitor daemon will not run.")

    port = int(os.getenv("WEB_PORT", "8080"))
    log_system(f"SSL Monitor Web Server running on http://0.0.0.0:{port}")
    # 生产部署关闭 debug 机制
    app.run(host="0.0.0.0", port=port, debug=False)
