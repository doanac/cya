import contextlib
import crypt
import datetime
import hmac
import os
import time

from cya_server.settings import MODELS_FILE, CONTAINER_TYPES
from cya_server.concurrently import json_data, json_get
from cya_server.dict_model import Field, Model, ModelArrayField, ModelError


class SecretField(Field):
    def __init__(self, name):
        super(SecretField, self).__init__(
            name, data_type=str, def_value='', required=False)

    def pre_save(self, value):
        return crypt.crypt(value, crypt.mksalt())

    def verify(self, value, hashed):
        return hmac.compare_digest(crypt.crypt(value, hashed), hashed)


class Container(Model):
    FIELDS = [
        Field('name', data_type=str),
        Field('template', data_type=str, required=False),
        Field('release', data_type=str, required=False),
        Field('init_script', data_type=str, required=False),
        Field('date_requested', int, required=False),
        Field('date_created', int, required=False),
        Field('max_memory', int, required=False),
        Field('re_create', data_type=bool, def_value=False, required=False),
    ]

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
        if data.get('date_created', 0) > self.date_created:
            data['re_create'] = False
        return super(Container, self).update(data)

    def __repr__(self):
        return self.data['name']

    @staticmethod
    def validate_template_release(template, release):
        releases = CONTAINER_TYPES.get(template)
        if not releases:
            raise KeyError('Invalid template type: %s' % template)
        if release not in releases:
            raise KeyError('Invalid release for template: %s' % release)


class Host(Model):
    FIELDS = [
        Field('name', data_type=str),
        Field('distro_id', data_type=str),
        Field('distro_release', data_type=str),
        Field('distro_codename', data_type=str),
        Field('mem_total', data_type=int),
        Field('cpu_total', data_type=int),
        Field('cpu_type', data_type=str),
        Field('enlisted', data_type=bool, def_value=False, required=False),
        SecretField('api_key'),
        ModelArrayField('containers', Container, 'name'),
    ]

    def __repr__(self):
        return self.data['name']

    def get_container(self, name):
        for c in self.containers:
            if c.name == name:
                return c
        raise ModelError('Container not found: %s' % name, 404)


class InitScript(Model):
    FIELDS = [
        Field('name', data_type=str),
        Field('content', data_type=str),
    ]


class User(Model):
    FIELDS = [
        Field('email', data_type=str),
        Field('nickname', data_type=str),
        Field('openid', data_type=str),
        Field('approved', data_type=bool, def_value=False),
        Field('admin', data_type=bool, def_value=False, required=False),
        ModelArrayField('init_scripts', InitScript, 'name'),
    ]


class ServerModel(Model):
    FIELDS = [
        ModelArrayField('hosts', Host, 'name'),
        ModelArrayField('users', User, 'email'),
    ]

    def get_host(self, name):
        for x in self.hosts:
            if x.name == name:
                return x
        raise ModelError('Host not found: %s' % name, 404)

    def get_user_by_openid(self, openid):
        for x in self.users:
            if x.openid == openid:
                return x
        return None

    def find_best_host(self):
        '''way too simplistic way to find a good host. should try and determine
        when a host seems to be offline and find the 2nd best etc
        '''
        best_host = None
        best_count = 0
        for h in self.hosts:
            count = len(h.containers)
            if not best_host or count < best_count:
                best_host = h
                best_count = count
        return best_host

    def create_container(self, name, template, release, max_mem, init_script):
        Container.validate_template_release(template, release)
        h = self.find_best_host()
        data = {
            'name': name,
            'template': template,
            'release': release,
            'init_script': init_script,
            'max_memory': max_mem,
            'date_requested': int(time.time()),
        }
        # TODO this is tied to find_best_host being dumb, these should get
        # queued and not be tied to a host instantly, or moving a container
        # that doesn't get created within some amount of time
        h.containers.create(data)
        return h


@contextlib.contextmanager
def load(read_only=True, models_file=MODELS_FILE):
    path = os.path.join(models_file)
    if read_only:
        data = json_get(path, create=True)
        yield ServerModel(data)
    else:
        with json_data(path, create=True) as data:
            yield ServerModel(data)
