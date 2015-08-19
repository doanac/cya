import contextlib
import json
import os
import unittest
import tempfile

from cya_server import app, models

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
        _, self.tmpfile = tempfile.mkstemp()
        self.addCleanup(os.unlink, self.tmpfile)
        self.orig_load = models.load
        models.load = self.mock_load
        app.config['TESTING'] = True
        self.app = app.test_client()

    def tearDown(self):
        models.load = self.orig_load

    @contextlib.contextmanager
    def mock_load(self, read_only=True, models_file=None):
        with self.orig_load(read_only, self.tmpfile) as m:
            yield m

    def post_json(self, url, data, status_code=201):
        data = json.dumps(data)
        resp = self.app.post(url, data=data, content_type='application/json')
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
        with models.load() as m:
            self.assertEqual(1, len(m.hosts))
            self.assertEqual('host_1', m.hosts[0].name)

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
        with models.load() as m:
            self.assertEqual(1, len(m.hosts))
            self.assertEqual('host_1', m.hosts[0].name)
            self.assertEqual(123, m.hosts[0].cpu_total)

    def test_delete_host(self):
        resp = self.post_json('/api/v1/host/', h1)
        self.assertEqual('http://localhost/api/v1/host/host_1/', resp.location)

        headers = [('Authorization', 'Token ' + h1['api_key'])]
        resp = self.app.delete(
            resp.location, headers=headers, content_type='application/json')
        with models.load() as m:
            self.assertEqual(0, len(m.hosts))


if __name__ == '__main__':
    unittest.main()
