import contextlib
import os

from cya_server.settings import MODELS_FILE
from cya_server.concurrently import json_data, json_get
from cya_server.dict_model import Field, Model, ModelArrayField


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
        ModelArrayField('containers', Container),
    ]

    def __repr__(self):
        return self.data['name']


class ServerModel(Model):
    FIELDS = [
        ModelArrayField('hosts', Host),
    ]


@contextlib.contextmanager
def load(read_only=True, models_file=MODELS_FILE):
    path = os.path.join(models_file)
    if read_only:
        data = json_get(path, create=True)
        yield ServerModel(data)
    else:
        with json_data(path, create=True) as data:
            yield ServerModel(data)
