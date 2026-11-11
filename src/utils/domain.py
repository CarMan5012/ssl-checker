import ipaddress
import re


def normalize_domain(value):
    value = value.split('#', 1)[0].strip()
    if value.lower().startswith('http://'):
        value = value[7:]
    elif value.lower().startswith('https://'):
        value = value[8:]
    value = value.split('/', 1)[0].strip()
    if not value or any(char.isspace() for char in value):
        return None

    if value.startswith('['):
        match = re.fullmatch(r'\[([^\]]+)\](?::(\d+))?', value)
        if not match:
            return None
        try:
            host = str(ipaddress.IPv6Address(match.group(1)))
        except ValueError:
            return None
        port_text = match.group(2)
        port = int(port_text) if port_text else 443
        return f'[{host}]:{port}' if 1 <= port <= 65535 and port != 443 else (host if port == 443 else None)

    if value.count(':') > 1:
        try:
            return str(ipaddress.IPv6Address(value))
        except ValueError:
            return None

    host, separator, port_text = value.rpartition(':')
    if not separator:
        host, port_text = value, '443'
    if not port_text.isdigit():
        return None
    port = int(port_text)
    if not 1 <= port <= 65535:
        return None
    try:
        ascii_host = host.encode('idna').decode('ascii')
    except UnicodeError:
        return None
    if len(ascii_host) > 253 or not all(
        re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
        for label in ascii_host.split('.')
    ):
        return None
    return host.lower() if port == 443 else f'{host.lower()}:{port}'
