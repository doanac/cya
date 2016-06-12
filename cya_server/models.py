import datetime
import os
import time

from cya_server.settings import (
    MODELS_DIR, CONTAINER_TYPES, CLIENT_SCRIPT)
from cya_server.simplemodels import (
    Field, Model, ModelManager, ModelError, SecretField)


def client_version():
    return str(os.stat(CLIENT_SCRIPT).st_mtime)


class ContainerMount(Model):
    FIELDS = [
        Field('type', data_type=str),
        Field('source', data_type=str),
        Field('directory', data_type=str),
    ]


class Container(Model):
    FIELDS = [
        Field('template', data_type=str, required=False),
        Field('release', data_type=str, required=False),
        Field('init_script', data_type=str, required=False),
        Field('date_requested', int, required=False),
        Field('date_created', int, required=False),
        Field('max_memory', int, required=False),
        Field('re_create', data_type=bool, def_value=False, required=False),
        Field('state', data_type=str, def_value='UNKNOWN', required=False),
        Field('keep_running', data_type=bool, def_value=True, required=False),
        Field('ips', data_type=str, required=False),
    ]
    CHILDREN = [ContainerMount]

    @property
    def requested_str(self):
        v = self.date_requested
        if v:
            return datetime.datetime.fromtimestamp(v)
        return '?'

    @property
    def created_str(self):
        v = self.date_created
        if v:
            return datetime.datetime.fromtimestamp(v)
        return '?'

    def update(self, data):
        if self.date_created and \
                data.get('date_created', 0) > self.date_created:
            data['re_create'] = False
        return super(Container, self).update(data)

    def _get_log_file(self, logname):
        logdir = os.path.join(self._modeldir, 'logs')
        if not os.path.exists(logdir):
            os.mkdir(logdir)
        return os.path.join(logdir, logname)

    def append_log(self, logname, content):
        with open(self._get_log_file(logname), 'a') as f:
            f.write(content)

    def get_log_names(self):
        logdir = os.path.join(self._modeldir, 'logs')
        if os.path.exists(logdir):
            return os.listdir(logdir)
        return []

    def get_log(self, logname):
        with open(self._get_log_file(logname)) as f:
            return f.read()

    def __repr__(self):
        return self.name

    @staticmethod
    def validate_template_release(template, release):
        releases = CONTAINER_TYPES.get(template)
        if not releases:
            raise KeyError('Invalid template type: %s' % template)
        if release not in releases:
            raise KeyError('Invalid release for template: %s' % release)


class Host(Model):
    FIELDS = [
        Field('distro_id', data_type=str),
        Field('distro_release', data_type=str),
        Field('distro_codename', data_type=str),
        Field('mem_total', data_type=int),
        Field('cpu_total', data_type=int),
        Field('cpu_type', data_type=str),
        Field('enlisted', data_type=bool, def_value=False, required=False),
        SecretField('api_key'),
    ]
    CHILDREN = [
        Container,
    ]

    def __repr__(self):
        return self.name

    def get_container(self, name):
        for c in self.containers:
            if c.name == name:
                return c
        raise ModelError('Container not found: %s' % name, 404)

    def _get_ping_file(self):
        return os.path.join(self._modeldir, 'pings.log')

    def ping(self):
        with open(self._get_ping_file(), mode='a') as f:
            f.write('%d\n' % time.time())

    @property
    def online(self):
        """Online means we've been "pinged" in the last 3 minutes."""
        ping_file = self._get_ping_file()
        if not os.path.exists(ping_file):
            return False
        now = time.time()
        mtime = os.path.getmtime(self._get_ping_file())
        return now - mtime < 180  # pinged in last 3 minutes


class InitScript(Model):
    FIELDS = [
        Field('content', data_type=str),
    ]


class User(Model):
    FIELDS = [
        Field('nickname', data_type=str),
        Field('openid', data_type=str),
        Field('approved', data_type=bool, def_value=False),
        Field('admin', data_type=bool, def_value=False, required=False),
    ]
    CHILDREN = [
        InitScript,
    ]


class SharedStorage(Model):
    FIELDS = [
        Field('type', data_type=str),
        Field('source', data_type=str)
    ]


class ContainerRequest(Container):
    pass


hosts = ModelManager(MODELS_DIR, Host)
users = ModelManager(MODELS_DIR, User)
shared_storage = ModelManager(MODELS_DIR, SharedStorage)
container_requests = ModelManager(MODELS_DIR, ContainerRequest)


def _get_user_by_openid(openid):
    for x in users.list():
        x = users.get(x)
        if x.openid == openid:
            return x
    return None
users.get_user_by_openid = _get_user_by_openid


def _container_request_handle(host):
    '''Dumb logic but find host with least number of containers'''
    requests = list(container_requests.list())
    if not requests:
        return
    h = [hosts.get(x) for x in hosts.list()]
    h = [x for x in h if x.online]
    h = sorted(h, key=lambda x: len(list(x.containers.list())))
    match = host.name == h[0].name

    if match:
        print("MOVING REQUEST to host")
        r = container_requests.get(requests[0])
        host.containers.create(r.name, r.to_dict())
        r.delete()
container_requests.handle = _container_request_handle


def create_container(name, template, release, max_mem, init_script,
                     mounts=None):
    Container.validate_template_release(template, release)
    data = {
        'template': template,
        'release': release,
        'init_script': init_script,
        'max_memory': max_mem,
        'date_requested': int(time.time()),
        'state': 'QUEUED',
    }
    if mounts:
        container_mounts = []
        for ss_name, directory in mounts:
            ss = shared_storage.get(ss_name)
            container_mounts.append({
                'name': ss.name,
                'type': ss.type,
                'source': ss.source,
                'directory': directory
            })
        data['containermounts'] = container_mounts
    container_requests.create(name, data)
