import json
import os
import shutil
import tempfile
import unittest

from cya_server import app
from cya_server.models import container_requests, hosts, users

h1 = {
    'name': 'host_1',
    'distro_id': 'ubuntu',
    'distro_release': '14.12',
    'distro_codename': 'TRSUY',
    'mem_total': 5,
    'cpu_total': 5,
    'cpu_type': 'arm',
    'api_key': '12345',
}


class ApiTests(unittest.TestCase):

    def setUp(self):
        self.modelsdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.modelsdir)
        hosts._model_dir = os.path.join(self.modelsdir, 'hosts')
        users._model_dir = os.path.join(self.modelsdir, 'users')
        container_requests._model_dir = os.path.join(self.modelsdir, 'reqs')
        os.mkdir(hosts._model_dir)
        app.config['TESTING'] = True
        self.app = app.test_client()

    def post_json(self, url, data, status_code=201, headers=None):
        data = json.dumps(data)
        resp = self.app.post(
            url, data=data, headers=headers, content_type='application/json')
        self.assertEqual(status_code, resp.status_code)
        return resp

    def patch_json(self, url, data, api_key):
        data = json.dumps(data)
        headers = [('Authorization', 'Token ' + api_key)]
        resp = self.app.patch(
            url, data=data, headers=headers, content_type='application/json')
        self.assertEqual(200, resp.status_code)

    def get_json(self, url, status_code=200):
        resp = self.app.get(url)
        self.assertEqual(200, resp.status_code)
        return json.loads(resp.data.decode())

    def test_create_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)
        h = list(hosts.list())
        self.assertEqual(1, len(h))
        self.assertEqual('host_1', h[0])

        data = self.get_json('/api/v1/host/')
        self.assertEqual(1, len(data['hosts']))
        self.assertEqual('host_1', data['hosts'][0])

    def test_create_host_dup(self):
        self.post_json('/api/v1/host/', h1)
        self.post_json('/api/v1/host/', h1, 409)

    def test_update_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)

        self.patch_json(resp.location, {'cpu_total': 123}, h1['api_key'])
        h = hosts.get('host_1')
        self.assertEqual(123, h.cpu_total)

    def test_delete_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)

        headers = [('Authorization', 'Token ' + h1['api_key'])]
        resp = self.app.delete(
            resp.location, headers=headers, content_type='application/json')
        h = list(hosts.list())
        self.assertEqual(0, len(h))

    def test_container_request_auth(self):
        users.create('a@b.com', {'openid': 'oid', 'approved': True,
                                 'nickname': 'nn', 'api_key': 'blahBlah'})
        u = users.get('a@b.com')
        auth_headers = [('Authorization', 'Token %s:%s' % (u.name, 'bl'))]
        self.post_json('/api/v1/container_request/', {}, 401)
        self.post_json('/api/v1/container_request/', {}, 401, auth_headers)

    def test_container_request(self):
        data = {
            'name': 'container_foo',
            'template': 'ubuntu',
            'release': 'xenial',
        }
        users.create('a@b.com', {'openid': 'oid', 'approved': True,
                                 'nickname': 'nn', 'api_key': 'blahBlah'})
        u = users.get('a@b.com')
        auth_headers = [('Authorization', 'Token %s:%s' % (u.name, u.api_key))]
        self.post_json('/api/v1/container_request/', data, 202, auth_headers)

        queue = list(container_requests.list())
        self.assertEqual(['container_foo'], queue)

if __name__ == '__main__':
    unittest.main()
