import os
import shutil
import tempfile
import unittest

from cya_server.models import hosts, SecretField

h1 = {
    'distro_id': 'ubuntu',
    'distro_release': '14.12',
    'distro_codename': 'TRSUY',
    'mem_total': 5,
    'cpu_total': 5,
    'cpu_type': 'arm',
}


class TestModels(unittest.TestCase):
    def setUp(self):
        # todo patch the models dir and start testing
        self.modelsdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.modelsdir)
        hosts._model_dir = os.path.join(self.modelsdir, 'hosts')
        os.mkdir(hosts._model_dir)

    def test_empty_get(self):
        self.assertEqual(0, len(list(hosts.list())))

    def test_empty_update(self):
        hosts.create('host_1', h1)

        self.assertEqual(1, len(list(hosts.list())))
        self.assertEqual('ubuntu', hosts.get('host_1').distro_id)

    def test_container_create(self):
        h = h1.copy()
        h['containers'] = [{'name': 'c1', 'template': 'foo'}]

        hosts.create('host_1', h)
        h = hosts.get('host_1')
        self.assertEqual(1, len(list(h.containers.list())))
        self.assertEqual('foo', h.containers.get('c1').template)

    def test_secret(self):
        sf = SecretField('test')
        password = 'foobar'
        hashed = sf.save(password)
        self.assertTrue(password != hashed)
        self.assertTrue(sf.verify(password, hashed))

    def test_secret_create(self):
        data = h1.copy()
        data['api_key'] = '123'
        hosts.create('host_1', data)
        h = hosts.get('host_1')
        self.assertNotEqual('123', h.api_key)
        self.assertTrue(SecretField.verify('123', h.api_key))
