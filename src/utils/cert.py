import ssl
import socket
import datetime
from src.utils.logger import log_error

def parse_domain_and_port(domain_str):
    """
    智能解析域名/IP和端口，支持 IPv6 (如 [2001:db8::1]:443 或 2001:db8::1)
    """
    domain_str = domain_str.strip()
    if domain_str.startswith("http://"):
        domain_str = domain_str[7:]
    elif domain_str.startswith("https://"):
        domain_str = domain_str[8:]
    if "/" in domain_str:
        domain_str = domain_str.split("/")[0]
        
    # 处理带方括号的 IPv6 地址，例如 [2001:db8::1]:443
    if domain_str.startswith("["):
        end_bracket = domain_str.find("]")
        if end_bracket != -1:
            hostname = domain_str[1:end_bracket]
            port_part = domain_str[end_bracket + 1:]
            if port_part.startswith(":"):
                try:
                    port = int(port_part[1:])
                except ValueError:
                    port = 443
            else:
                port = 443
            return hostname, port

    # 普通 IPv6 地址但没有端口，例如 2001:db8::1（包含了多个冒号，但没有方括号）
    if domain_str.count(":") > 1:
        # 尝试检查最后一部分是不是端口
        parts = domain_str.rsplit(":", 1)
        try:
            port = int(parts[1])
            hostname = parts[0]
        except ValueError:
            hostname = domain_str
            port = 443
        return hostname, port

    # 普通域名/IPv4 且带端口，例如 example.com:8080 或 127.0.0.1:8080
    if ":" in domain_str:
        parts = domain_str.split(":", 1)
        hostname = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            port = 443
    else:
        hostname = domain_str
        port = 443
        
    return hostname, port

def get_alert_level(days, info_days=14, warn_days=7, crit_days=3):
    """
    根据剩余天数和动态阈值配置策略评估风险级别：
    - <= crit_days: 严重
    - <= warn_days: 警告
    - <= info_days: 提醒
    - 其余: 正常
    """
    if days is None:
        return "严重", "#FF0000"
    elif days <= crit_days:
        return "严重", "#FF0000"
    elif days <= warn_days:
        return "警告", "#FF8C00"
    elif days <= info_days:
        return "提醒", "#1E90FF"
    return "正常", "#32CD32"

def resolve_ip(hostname):
    """
    智能解析域名 IP，同时支持 IPv4 (A 记录) 和 IPv6 (AAAA 记录)
    """
    try:
        # AF_UNSPEC 自动匹配 v4 和 v6 记录
        addrinfo = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if addrinfo:
            # 提取 sockaddr 元组的第一个元素（IP 地址字符串）
            return addrinfo[0][4][0]
    except Exception:
        pass
    return None

def check_ssl(domain_with_port, info_days=14, warn_days=7, crit_days=3):
    """
    统一检测 SSL 证书有效期状态。
    返回结构:
    - 成功: {"success": True, "days": int, "expire": str, "level": str, "color": str, "ip": str}
    - 失败: {"success": False, "error": str, "level": "失败", "color": "#999999", "days": None, "ip": str}
    """
    hostname, port = parse_domain_and_port(domain_with_port)
    ip_address = None
    encoded_hostname = hostname

    try:
        encoded_hostname = hostname.encode('idna').decode('ascii')
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((encoded_hostname, port), timeout=10) as sock:
            try:
                ip_address = sock.getpeername()[0]
            except Exception:
                pass
            with context.wrap_socket(sock, server_hostname=encoded_hostname) as ssock:
                cert_bin = ssock.getpeercert(binary_form=True)
                if not cert_bin:
                    return {
                        "success": False, "error": "无法获取证书二进制数据",
                        "level": "失败", "color": "#999999", "days": None, "ip": ip_address
                    }

        # 优先使用 cryptography 解析二进制证书，未安装则进行 CERT_REQUIRED 握手降级
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            has_crypto = True
        except ImportError:
            has_crypto = False

        issuer_org = None

        if has_crypto:
            cert = x509.load_der_x509_certificate(cert_bin, default_backend())
            try:
                # 优先使用 cryptography 42.0.0+ timezone-aware 接口
                expire_date = cert.not_valid_after_utc
                expire_ts = expire_date.timestamp()
            except AttributeError:
                # 向后兼容旧版本 cryptography
                expire_date = cert.not_valid_after
                expire_ts = expire_date.replace(tzinfo=datetime.timezone.utc).timestamp()

            # 解析颁发者组织 (O)
            try:
                org_attrs = cert.issuer.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)
                if org_attrs:
                    issuer_org = org_attrs[0].value
                else:
                    cn_attrs = cert.issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
                    if cn_attrs:
                        issuer_org = cn_attrs[0].value
            except Exception:
                pass
        else:
            # 降级方案：使用内置 ssl 重新建立验证连接
            context_req = ssl.create_default_context()
            with socket.create_connection((encoded_hostname, port), timeout=10) as sock_req:
                with context_req.wrap_socket(sock_req, server_hostname=encoded_hostname) as ssock_req:
                    cert_dict = ssock_req.getpeercert()
                    if not cert_dict:
                        return {
                            "success": False, "error": "无法解析对端证书字典",
                            "level": "失败", "color": "#999999", "days": None, "ip": ip_address, "issuer": None
                        }
                    not_after = cert_dict.get("notAfter")
                    if not not_after:
                        return {
                            "success": False, "error": "证书缺少到期时间",
                            "level": "失败", "color": "#999999", "days": None, "ip": ip_address, "issuer": None
                        }
                    expire_ts = ssl.cert_time_to_seconds(not_after)

                    # 提取降级方案中的 issuer 组织
                    issuer_tuples = cert_dict.get("issuer", ())
                    for rdn in issuer_tuples:
                        for k, v in rdn:
                            if k == 'organizationName':
                                issuer_org = v
                                break
                        if issuer_org:
                            break
                    if not issuer_org:
                        for rdn in issuer_tuples:
                            for k, v in rdn:
                                if k == 'commonName':
                                    issuer_org = v
                                    break
                            if issuer_org:
                                break

        if not issuer_org:
            issuer_org = "未知"

        # 转换为本地时区时间
        expire_local = datetime.datetime.fromtimestamp(expire_ts)
        now_local = datetime.datetime.now()
        remaining = expire_local - now_local
        days = remaining.days

        level, color = get_alert_level(days, info_days, warn_days, crit_days)
        return {
            "success": True,
            "days": days,
            "expire": expire_local.strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "color": color,
            "ip": ip_address,
            "issuer": issuer_org
        }

    except Exception as e:
        if not ip_address:
            ip_address = resolve_ip(encoded_hostname)
        error_msg = str(e).split('] ')[-1]
        log_error(f"获取 {hostname}:{port} 证书失败: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "level": "失败",
            "color": "#999999",
            "days": None,
            "ip": ip_address,
            "issuer": None
        }
