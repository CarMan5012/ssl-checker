import datetime
import json
import io
import logging
import os
import sys
import threading
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch
from contextlib import redirect_stdout

from src import monitor
from src.utils import config
from src.utils.cert import parse_domain_and_port
from src.utils.domain import normalize_domain
from src.utils.file_io import atomic_write_file
from src.utils.disabled import load_disabled_domains, save_disabled_domains
from src.utils.logger import redact_sensitive, log_info, log_error, log_context, JsonFormatter


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp_dir.cleanup)
        list_file = os.path.join(self.temp_dir.name, 'domains.txt')
        state_file = os.path.join(self.temp_dir.name, 'state.json')
        disabled_file = os.path.join(self.temp_dir.name, 'disabled.json')
        with open(list_file, 'w', encoding='utf-8') as file:
            file.write('example.com\n')
        config_patch = patch.multiple(
            config, LIST_FILE=list_file, STATE_FILE=state_file,
            DISABLED_FILE=disabled_file, TEST_MODE=False,
            SMTP_HOST='smtp.example.com', SMTP_USER='sender@example.com',
            EMAIL_TO='receiver@example.com', DINGTALK_WEBHOOK=''
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)
        for target, name, value in (
            (config, 'load_all_configs', None),
            (monitor, 'check_is_workday', True),
        ):
            mocked = patch.object(target, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def state(self):
        return monitor.load_state()['example.com']

    def make_retry_due(self):
        state = monitor.load_state()
        state['example.com']['retry_at'] = (
            datetime.datetime.now() - datetime.timedelta(minutes=1)
        ).isoformat()
        monitor.save_state(state)

    def test_failed_certificate_retries_and_stops_after_successful_alert(self):
        failure = {'level': '失败', 'success': False, 'days': None,
                   'error': 'timeout', 'color': '#999999'}
        with patch.object(monitor, 'check_ssl', return_value=failure), \
                patch.object(monitor, 'send_email_alert', side_effect=[False, True]) as email:
            monitor.run_task()
            self.assertEqual(self.state()['email_alert_level'], '正常')
            self.assertIsNotNone(self.state()['retry_at'])
            self.make_retry_due()
            monitor.run_task(retry_only=True)
            self.assertEqual(self.state()['email_alert_level'], '失败')
            monitor.run_task()
            self.assertEqual(email.call_count, 2)

    def test_page_refresh_does_not_suppress_notification(self):
        state = {'example.com': {'level': '严重', 'alert_level': '正常'}}
        monitor.save_state(state)
        result = {'level': '严重', 'success': True, 'days': 1, 'expire': 'tomorrow'}
        with patch.object(monitor, 'check_ssl', return_value=result), \
                patch.object(monitor, 'send_email_alert', return_value=True) as email:
            monitor.run_task()
            email.assert_called_once()
            self.assertEqual(self.state()['email_alert_level'], '严重')

    def test_channels_retry_independently(self):
        result = {'level': '严重', 'success': True, 'days': 1}
        with patch.object(config, 'DINGTALK_WEBHOOK', 'https://example.com/robot'), \
                patch.object(monitor, 'check_ssl', return_value=result), \
                patch.object(monitor, 'send_email_alert', return_value=True) as email, \
                patch.object(monitor, 'send_dingtalk_alert', side_effect=[False, True]) as ding:
            monitor.run_task()
            self.assertEqual(self.state()['email_alert_level'], '严重')
            self.assertEqual(self.state()['dingtalk_alert_level'], '正常')
            self.make_retry_due()
            monitor.run_task(retry_only=True)
            email.assert_called_once()
            self.assertEqual(ding.call_count, 2)
            self.assertEqual(self.state()['dingtalk_alert_level'], '严重')

    def test_failed_domain_retry_limit(self):
        failure = {'level': '失败', 'success': False, 'error': 'timeout', 'days': None}
        with patch.object(monitor, 'check_ssl', return_value=failure), \
                patch.object(monitor, 'send_email_alert', return_value=True):
            monitor.run_task()
            for count in range(1, 4):
                self.make_retry_due()
                monitor.run_task(retry_only=True)
                self.assertEqual(self.state()['retry_count'], count)
            self.assertIsNone(self.state()['retry_at'])
            self.assertFalse(monitor.retry_due(datetime.datetime.now() + datetime.timedelta(days=1)))

    def test_daily_schedule_uses_persisted_date(self):
        at_915 = datetime.datetime.now().replace(hour=9, minute=15)
        self.assertFalse(monitor.daily_due(at_915 - datetime.timedelta(minutes=1)))
        self.assertTrue(monitor.daily_due(at_915))
        result = {'level': '正常', 'success': True, 'days': 90}
        with patch.object(monitor, 'check_ssl', return_value=result):
            monitor.run_task()
        self.assertFalse(monitor.daily_due(at_915))
        self.assertTrue(monitor.daily_due(at_915 + datetime.timedelta(days=1)))

    def test_missing_list_does_not_record_daily_completion(self):
        os.remove(config.LIST_FILE)
        with patch.object(monitor, 'send_system_error_alert'):
            monitor.run_task()
        self.assertTrue(monitor.daily_due(datetime.datetime.now().replace(hour=9, minute=16)))

    def test_background_error_is_persisted_and_cleared(self):
        monitor.record_monitor_error('巡检任务异常，请查看服务日志')
        self.assertEqual(monitor.load_state()['__meta__']['last_error'], '巡检任务异常，请查看服务日志')
        self.assertEqual(monitor.RUNTIME_ERROR, '巡检任务异常，请查看服务日志')
        with patch.object(monitor, 'check_ssl', return_value={
            'level': '正常', 'success': True, 'days': 90
        }):
            monitor.run_task()
        self.assertIsNone(monitor.load_state()['__meta__']['last_error'])
        self.assertIsNone(monitor.RUNTIME_ERROR)

    def test_ipv6_and_dingtalk_response(self):
        self.assertEqual(parse_domain_and_port('2001:db8::1'), ('2001:db8::1', 443))
        self.assertEqual(parse_domain_and_port('[2001:db8::1]:8443'), ('2001:db8::1', 8443))
        response = Mock(status_code=200, text='not json')
        response.json.side_effect = ValueError('invalid JSON')
        with patch.object(monitor.requests, 'post', return_value=response):
            success, _ = monitor.post_to_dingtalk(
                {'msgtype': 'text', 'text': {'content': 'test'}},
                webhook='https://example.com/robot', secret='', keyword=''
            )
        self.assertFalse(success)

    def test_domain_input_validation(self):
        self.assertEqual(normalize_domain('https://example.com/path'), 'example.com')
        self.assertEqual(normalize_domain('2001:db8::1'), '2001:db8::1')
        self.assertEqual(normalize_domain('[2001:db8::1]:8443'), '[2001:db8::1]:8443')
        self.assertIsNone(normalize_domain('example.com:70000'))
        self.assertIsNone(normalize_domain('example.com\nother.example'))
        self.assertIsNone(normalize_domain('invalid host'))

    def test_parallel_atomic_writes_use_distinct_temporary_files(self):
        target = os.path.join(self.temp_dir.name, 'parallel.json')
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda value: atomic_write_file(target, {'value': value}, is_json=True),
                (1, 2)
            ))
        self.assertEqual(results, [True, True])
        with open(target, encoding='utf-8') as file:
            self.assertIn(json.load(file)['value'], (1, 2))

    def test_disabled_domain_is_not_checked_or_retried(self):
        self.assertTrue(save_disabled_domains({'example.com'}))
        self.assertEqual(load_disabled_domains(), {'example.com'})
        with patch.object(monitor, 'check_ssl') as check:
            monitor.run_task()
            check.assert_not_called()
        self.assertFalse(monitor.retry_due(datetime.datetime.now()))

    def test_log_redacts_webhook_and_password(self):
        with patch.object(config, 'SMTP_PASS', 'mail-secret'), \
                patch.object(config, 'DINGTALK_TOKEN', 'robot-secret'):
            message = redact_sensitive(
                'password=mail-secret https://oapi.dingtalk.com/send?access_token=robot-secret&sign=abc'
            )
        self.assertNotIn('mail-secret', message)
        self.assertNotIn('robot-secret', message)
        self.assertNotIn('sign=abc', message)
        output = io.StringIO()
        with patch.object(config, 'SMTP_PASS', 'mail-secret'), redirect_stdout(output):
            log_info('发送测试消息', reason='password=mail-secret',
                     endpoint='https://example.com?access_token=robot-secret',
                     credentials={'smtp_pass': 'mail-secret'})
        line = output.getvalue().strip()
        event = json.loads(line)
        self.assertEqual(event['level'], 'INFO')
        self.assertEqual(event['credentials']['smtp_pass'], '[REDACTED]')
        self.assertNotIn('mail-secret', line)
        self.assertNotIn('robot-secret', line)
        record = logging.LogRecord('waitress', logging.WARNING, __file__, 1,
                                   'access_token=robot-secret', (), None)
        server_event = json.loads(JsonFormatter().format(record))
        self.assertEqual(server_event['logger'], 'waitress')
        self.assertNotIn('robot-secret', json.dumps(server_event))

    def test_json_log_redacts_generic_credentials_and_stays_line_delimited(self):
        raw = ('secret=example-secret api_key=example-key '
               'Authorization: Bearer example-bearer')
        cleaned = redact_sensitive(raw)
        for secret in ('example-secret', 'example-key', 'example-bearer'):
            self.assertNotIn(secret, cleaned)
        self.assertNotIn('example-secret', redact_sensitive('{"secret":"example-secret"}'))

        output = io.StringIO()
        with redirect_stdout(output), log_context(task_id='test-task'):
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda index: log_info('并发日志', index=index), range(40)))
            logging.getLogger('waitress').warning('api_key=example-key')
            try:
                raise ValueError('api_key=example-key')
            except ValueError:
                log_error('测试异常', exc_info=True)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 42)
        events = [json.loads(line) for line in lines]
        self.assertEqual(events[-2]['logger'], 'waitress')
        self.assertNotIn('example-key', events[-2]['message'])
        self.assertTrue(all(event['task_id'] == 'test-task' for event in events[-1:]))
        self.assertEqual(events[-1]['level'], 'ERROR')
        self.assertNotIn('example-key', events[-1]['exception'])

        hook_output = io.StringIO()
        with redirect_stdout(hook_output):
            try:
                raise RuntimeError('secret=example-secret')
            except RuntimeError as error:
                sys.excepthook(type(error), error, error.__traceback__)
        unhandled = json.loads(hook_output.getvalue())
        self.assertEqual(unhandled['event'], 'unhandled_exception')
        self.assertNotIn('example-secret', hook_output.getvalue())

        thread_output = io.StringIO()
        with redirect_stdout(thread_output):
            thread = threading.Thread(
                target=lambda: (_ for _ in ()).throw(RuntimeError('secret=example-secret')),
                name='test-background-error',
            )
            thread.start()
            thread.join()
        thread_error = json.loads(thread_output.getvalue())
        self.assertEqual(thread_error['event'], 'thread_exception')
        self.assertNotIn('example-secret', thread_output.getvalue())

    def test_dingtalk_failure_does_not_log_response_body(self):
        response = Mock(status_code=500, text='secret=server-only-value')
        response.json.return_value = {'errcode': 400, 'errmsg': 'failed'}
        output = io.StringIO()
        with redirect_stdout(output), patch.object(monitor.requests, 'post', return_value=response):
            success, _ = monitor.post_to_dingtalk(
                {'msgtype': 'text', 'text': {'content': 'test'}},
                webhook='https://example.com?access_token=example-token', secret='', keyword=''
            )
        self.assertFalse(success)
        self.assertNotIn('server-only-value', output.getvalue())
        self.assertNotIn('example-token', output.getvalue())
        event = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(event['http_status'], 500)
        self.assertEqual(event['response_size'], len(response.text))


if __name__ == '__main__':
    unittest.main()
