import contextlib
import crypt
import hmac
import os

from cya_server.settings import MODELS_FILE
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
        Field('template', data_type=str, def_value='ubuntu-cloud'),
        Field('release', data_type=str, def_value='trusty', required=False),
        Field('init_script', data_type=str, required=False),
        Field('date_requested', int, required=False),
        Field('date_created', int, required=False),
    ]

    def __repr__(self):
        return self.data['name']


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
        ModelArrayField('containers', Container),
    ]

    def __repr__(self):
        return self.data['name']

    def get_container(self, name):
        for c in self.containers:
            if c.name == name:
                return c
        raise ModelError('Container not found: %s' % name, 404)


class ServerModel(Model):
    FIELDS = [
        ModelArrayField('hosts', Host),
    ]

    def get_host(self, name):
        for x in self.hosts:
            if x.name == name:
                return x
        raise ModelError('Host not found: %s' % name, 404)


@contextlib.contextmanager
def load(read_only=True, models_file=MODELS_FILE):
    path = os.path.join(models_file)
    if read_only:
        data = json_get(path, create=True)
        yield ServerModel(data)
    else:
        with json_data(path, create=True) as data:
            yield ServerModel(data)
