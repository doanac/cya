import datetime
import os
import random
import time
import string

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


class InitScript(Model):
    FIELDS = [
        Field('content', data_type=str),
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
        Field('one_shot', data_type=bool, def_value=False, required=False),
        Field('requested_by', data_type=str, required=False),
    ]
    CHILDREN = [ContainerMount, InitScript]

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
        Field('max_containers', data_type=int, def_value=0, required=False),
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


class User(Model):
    FIELDS = [
        Field('nickname', data_type=str),
        Field('openid', data_type=str),
        Field('approved', data_type=bool, def_value=False),
        Field('admin', data_type=bool, def_value=False, required=False),
        Field('api_key', data_type=str, required=False)
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


def _generate_api_key():
    chars = string.ascii_letters + string.digits + '!@#$%^&*~-+'
    return ''.join(random.choice(chars) for _ in range(32))
users.generate_api_key = _generate_api_key


def _container_request_handle(host):
    '''Dumb logic but find host with least number of containers.
       It also honors allowing max_containers on a host.
    '''
    if host.max_containers and host.max_containers <= host.containers.count():
        return  # no point in checking

    requests = list(container_requests.list())
    if not requests:
        return
    candidates = []
    for h in hosts.list():
        h = hosts.get(h)
        h.count_cache = h.containers.count()
        if h.online and (h.max_containers == 0 or
                         h.count_cache < h.max_containers):
                candidates.append(h)

    candidates = sorted(candidates, key=lambda x: x.count_cache)
    candidates = sorted(candidates, key=lambda x: -1 * x.mem_total)
    match = candidates and host.name == candidates[0].name

    if match:
        r = container_requests.get(requests[0])
        host.containers.create(r.name, r.to_dict())
        r.delete()
container_requests.handle = _container_request_handle
