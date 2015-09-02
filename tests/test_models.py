import os
import tempfile
import unittest
import unittest.mock

from cya_server.models import load, SecretField

h1 = {
    'name': 'host_1',
    'distro_id': 'ubuntu',
    'distro_release': '14.12',
    'distro_codename': 'TRSUY',
    'mem_total': 5,
    'cpu_total': 5,
    'cpu_type': 'arm',
}


class TestModels(unittest.TestCase):
    def setUp(self):
        _, self.tmpfile = tempfile.mkstemp()
        self.addCleanup(self.safe_unlink)

    def safe_unlink(self):
        if os.path.exists(self.tmpfile):
            os.unlink(self.tmpfile)

    def test_empty_get(self):
        with load(read_only=True, models_file=self.tmpfile) as m:
            self.assertEqual(0, len(m.hosts))

    def test_empty_update(self):
        with load(read_only=False, models_file=self.tmpfile) as m:
            self.assertEqual(0, len(m.hosts))
            m.hosts.create(h1)

        with load(read_only=True, models_file=self.tmpfile) as m:
            self.assertEqual(1, len(m.hosts))
            self.assertEqual('host_1', m.hosts[0].name)

    def test_container_create(self):
        h1['containers'] = [
            {'name': 'c1', 'template': 'foo'}
        ]

        with load(read_only=False, models_file=self.tmpfile) as m:
            self.assertEqual(0, len(m.hosts))
            m.hosts.create(h1)

        with load(read_only=True, models_file=self.tmpfile) as m:
            self.assertEqual(1, len(m.hosts[0].containers))
            self.assertEqual('c1', m.hosts[0].containers[0].name)

    def test_secret(self):
        sf = SecretField('test')
        password = 'foobar'
        hashed = sf.pre_save(password)
        self.assertTrue(password != hashed)
        self.assertTrue(sf.verify(password, hashed))

    def test_secret_create(self):
        data = h1.copy()
        data['api_key'] = '123'
        with load(read_only=False, models_file=self.tmpfile) as m:
            self.assertEqual(0, len(m.hosts))
            m.hosts.create(data)
        with load(read_only=True, models_file=self.tmpfile) as m:
            self.assertNotEqual('123', m.hosts[0].api_key)
            self.assertTrue(
                m.hosts[0].api_key_field.verify('123', m.hosts[0].api_key))
