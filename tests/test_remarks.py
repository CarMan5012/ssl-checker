import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils import config
from src.utils.remarks import load_domain_remarks, save_domain_remarks, normalize_remark

try:
    import flask  # noqa: F401
except ImportError:
    FLASK_AVAILABLE = False
else:
    FLASK_AVAILABLE = True

@unittest.skipUnless(FLASK_AVAILABLE, 'Flask is not installed')
class DomainRemarkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp_dir.cleanup)
        list_file = os.path.join(self.temp_dir.name, 'domains.txt')
        with open(list_file, 'w', encoding='utf-8') as file:
            file.write('example.com\n')
        config_patch = patch.multiple(
            config,
            LIST_FILE=list_file,
            STATE_FILE=os.path.join(self.temp_dir.name, 'state.json'),
            DISABLED_FILE=os.path.join(self.temp_dir.name, 'disabled.json'),
            REMARKS_FILE=os.path.join(self.temp_dir.name, 'remarks.json'),
            CONFIG_FILE=os.path.join(self.temp_dir.name, 'config.json'),
            TEST_MODE=True,
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.app_module = importlib.import_module('src.app')
        self.client = self.app_module.app.test_client()
        with self.client.session_transaction() as session:
            session['username'] = 'tester'

    def test_remark_only_update_and_clear_do_not_check_certificate(self):
        with patch.object(self.app_module, 'check_ssl') as check:
            response = self.client.put('/api/domains', json={
                'old_domain': 'example.com', 'new_domain': 'example.com',
                'remark': '生产环境网关',
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['remark'], '生产环境网关')
            self.assertEqual(load_domain_remarks(), {'example.com': '生产环境网关'})
            check.assert_not_called()

            response = self.client.put('/api/domains', json={
                'old_domain': 'example.com', 'new_domain': 'example.com',
                'remark': '',
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(load_domain_remarks(), {})
            check.assert_not_called()

    def test_list_rename_and_delete_keep_remarks_in_sync(self):
        self.client.put('/api/domains', json={
            'old_domain': 'example.com', 'new_domain': 'example.com',
            'remark': '入口服务',
        })
        certificate = {'success': True, 'level': '正常', 'days': 30,
                       'expire': '2027-01-01 00:00:00'}
        with patch.object(self.app_module, 'check_ssl', return_value=certificate):
            listed = self.client.get('/api/domains')
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json[0]['remark'], '入口服务')

            renamed = self.client.put('/api/domains', json={
                'old_domain': 'example.com', 'new_domain': 'new.example.com',
                'remark': '入口服务',
            })
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(load_domain_remarks(), {'new.example.com': '入口服务'})

        deleted = self.client.delete('/api/domains', json={'domain': 'new.example.com'})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(load_domain_remarks(), {})

    def test_remark_validation(self):
        response = self.client.put('/api/domains', json={
            'old_domain': 'example.com', 'new_domain': 'example.com',
            'remark': 'x' * 201,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(load_domain_remarks(), {})


class RemarkValidationTests(unittest.TestCase):
    def test_rejects_long_and_multiline_remarks(self):
        self.assertIsNone(normalize_remark('x' * 201))
        self.assertIsNone(normalize_remark('first\nsecond'))
        self.assertEqual(normalize_remark('  生产环境  '), '生产环境')

    def test_persists_remark_mapping(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            with patch.object(config, 'REMARKS_FILE', os.path.join(directory, 'remarks.json')):
                self.assertEqual(load_domain_remarks(), {})
                self.assertTrue(save_domain_remarks({'example.com': '入口服务'}))
                self.assertEqual(load_domain_remarks(), {'example.com': '入口服务'})


if __name__ == '__main__':
    unittest.main()
