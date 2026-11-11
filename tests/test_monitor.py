import datetime
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from src import monitor
from src.utils import config
from src.utils.cert import parse_domain_and_port
from src.utils.domain import normalize_domain
from src.utils.file_io import atomic_write_file


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp_dir.cleanup)
        list_file = os.path.join(self.temp_dir.name, 'domains.txt')
        state_file = os.path.join(self.temp_dir.name, 'state.json')
        with open(list_file, 'w', encoding='utf-8') as file:
            file.write('example.com\n')
        config_patch = patch.multiple(
            config, LIST_FILE=list_file, STATE_FILE=state_file, TEST_MODE=False,
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


if __name__ == '__main__':
    unittest.main()
