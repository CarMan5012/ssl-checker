import datetime
import json
import logging
import os
import re
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar

_SENSITIVE_KEYS = {
    'password', 'smtp_pass', 'smtp_password', 'dingtalk_secret',
    'dingtalk_token', 'dingtalk_webhook', 'access_token', 'token',
    'sign', 'secret', 'flask_secret_key', 'api_key', 'authorization',
    'cookie', 'set-cookie', 'webhook',
}
_KEY_PATTERN = '|'.join(re.escape(key) for key in sorted(_SENSITIVE_KEYS, key=len, reverse=True))
_LOG_CONTEXT = ContextVar('ssl_checker_log_context', default={})
_APP_LOGGER = logging.getLogger('ssl_checker')
_LEVELS = {
    'SYSTEM': logging.INFO,
    'INFO': logging.INFO,
    'OK': logging.INFO,
    'WARN': logging.WARNING,
    'ALERT': logging.WARNING,
    'ERROR': logging.ERROR,
}


def redact_sensitive(message, extra_secrets=()):
    value = str(message)
    try:
        from src.utils import config
        known = (config.SMTP_PASS, config.DINGTALK_TOKEN,
                 config.DINGTALK_SECRET, config.DINGTALK_WEBHOOK)
    except Exception:
        known = ()
    for secret in (*known, *extra_secrets):
        if isinstance(secret, str) and len(secret) >= 4:
            value = value.replace(secret, '[REDACTED]')
    value = re.sub(r'(?i)\bBearer\s+[^\s,;]+', 'Bearer [REDACTED]', value)
    value = re.sub(r'(?i)\b(?:Authorization|Cookie|Set-Cookie)\s*:\s*[^\r\n,}]+',
                   lambda match: match.group(0).split(':', 1)[0] + ': [REDACTED]', value)
    value = re.sub(rf'(?i)(\b(?:{_KEY_PATTERN})\b["\']?\s*[:=]\s*["\'])[^"\']*(["\'])',
                   r'\1[REDACTED]\2', value)
    return re.sub(rf'(?i)(\b(?:{_KEY_PATTERN})\b\s*[:=]\s*)[^&\s,}}]+',
                  r'\1[REDACTED]', value)


def _sanitize(value, key=None):
    if key and key.lower() in _SENSITIVE_KEYS:
        return '[REDACTED]'
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return redact_sensitive(value)


@contextmanager
def log_context(**fields):
    token = _LOG_CONTEXT.set({**_LOG_CONTEXT.get(), **fields})
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            'time': datetime.datetime.fromtimestamp(record.created).astimezone().isoformat(timespec='seconds'),
            'level': record.levelname,
            'message': redact_sensitive(record.getMessage()),
            'logger': record.name,
        }
        event.update({key: _sanitize(value, key) for key, value in _LOG_CONTEXT.get().items()})
        if hasattr(record, 'event_type'):
            event['event'] = record.event_type
        details = getattr(record, 'details', {})
        event.update({key: _sanitize(value, key) for key, value in details.items()})
        if record.exc_info:
            event['exception'] = redact_sensitive(self.formatException(record.exc_info))
        return json.dumps(event, ensure_ascii=False, separators=(',', ':'))


class DynamicStdoutHandler(logging.StreamHandler):
    def emit(self, record):
        self.stream = sys.stdout
        super().emit(record)


def _unhandled_exception(exc_type, exc_value, exc_tb):
    _APP_LOGGER.error('未捕获异常', extra={
        'event_type': 'unhandled_exception',
        'details': {'error_type': exc_type.__name__},
    }, exc_info=(exc_type, exc_value, exc_tb))


def _thread_exception(args):
    _APP_LOGGER.error('后台线程未捕获异常', extra={
        'event_type': 'thread_exception',
        'details': {'thread': args.thread.name if args.thread else None,
                    'error_type': args.exc_type.__name__},
    }, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def configure_json_logging():
    handler = DynamicStdoutHandler()
    handler.setFormatter(JsonFormatter())
    level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, level_name) if level_name in {
        'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    } else logging.INFO
    logging.basicConfig(level=level, handlers=[handler], force=True)
    sys.excepthook = _unhandled_exception
    threading.excepthook = _thread_exception


def _log(event_type, message, **details):
    if not any(isinstance(handler, DynamicStdoutHandler) for handler in logging.getLogger().handlers):
        configure_json_logging()
    exc_info = details.pop('exc_info', None)
    _APP_LOGGER.log(_LEVELS[event_type], message,
                    extra={'event_type': event_type.lower(), 'details': details},
                    exc_info=exc_info)


def log_system(message, **details):
    _log('SYSTEM', message, **details)


def log_info(message, **details):
    _log('INFO', message, **details)


def log_ok(message, **details):
    _log('OK', message, **details)


def log_warn(message, **details):
    _log('WARN', message, **details)


def log_alert(message, **details):
    _log('ALERT', message, **details)


def log_error(message, **details):
    _log('ERROR', message, **details)
