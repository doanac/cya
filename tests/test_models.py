import os
import shutil
import tempfile
import unittest

from cya_server.models import container_requests, hosts, SecretField

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
        self.modelsdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.modelsdir)
        hosts._model_dir = os.path.join(self.modelsdir, 'hosts')
        os.mkdir(hosts._model_dir)

    def test_empty_get(self):
        self.assertEqual(0, hosts.count())

    def test_empty_update(self):
        hosts.create('host_1', h1)

        self.assertEqual(1, hosts.count())
        self.assertEqual('ubuntu', hosts.get('host_1').distro_id)

    def test_container_create(self):
        h = h1.copy()
        h['containers'] = [{'name': 'c1', 'template': 'foo'}]

        hosts.create('host_1', h)
        h = hosts.get('host_1')
        self.assertEqual(1, h.containers.count())
        self.assertEqual('foo', h.containers.get('c1').template)
        self.assertEqual('c1', h.to_dict()['containers'][0]['name'])

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


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.modelsdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.modelsdir)
        hosts._model_dir = os.path.join(self.modelsdir, 'hosts')
        container_requests._model_dir = os.path.join(self.modelsdir, 'reqs')
        os.mkdir(hosts._model_dir)
        os.mkdir(container_requests._model_dir)

        hosts.create('host1', h1)
        hosts.create('host2', h1)
        self.host1 = hosts.get('host1')
        self.host2 = hosts.get('host2')

        self.container_data = {
            'template': 'ubuntu',
            'release': 'xenial',
        }

    def test_offline(self):
        """The scheduler is okay if everything is offline"""
        container_requests.create('container_foo', self.container_data)
        container_requests.handle(self.host1)
        self.assertEqual(1, container_requests.count())

    def test_one_online(self):
        """The scheduler finds one host online"""
        self.host1.ping()
        container_requests.create('container_foo', self.container_data)
        container_requests.handle(self.host1)
        self.assertEqual(0, container_requests.count())
        containers = list(self.host1.containers.list())
        self.assertEqual(1, len(containers))
        self.assertEqual('container_foo', containers[0])

    def test_max_containers(self):
        """Ensure we honor max_containers"""
        self.host1.ping()
        self.host1.update({'max_containers': 1})
        self.host1 = hosts.get(self.host1.name)

        # create one container
        container_requests.create('container_foo', self.container_data)
        container_requests.handle(self.host1)
        self.assertEqual(0, container_requests.count())
        self.assertEqual(1, self.host1.containers.count())

        # create 2nd container, will stay stuck in queued
        container_requests.create('container_foo', self.container_data)
        container_requests.handle(self.host1)
        self.assertEqual(1, container_requests.count())
        self.assertEqual(1, self.host1.containers.count())

    def test_mem_total(self):
        """Ensure we honor max_containers"""
        self.host1.ping()
        self.host1.update({'max_containers': 1, 'mem_total': 6})
        self.host2.ping()
        self.host2.update({'max_containers': 1, 'mem_total': 5})
        self.host1 = hosts.get(self.host1.name)

        # create one container, it should go to host1 (more memory)
        container_requests.create('container_foo', self.container_data)
        container_requests.handle(self.host1)
        self.assertEqual(0, container_requests.count())
        self.assertEqual(1, self.host1.containers.count())
