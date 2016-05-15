import binascii
import fcntl
import fnmatch
import hashlib
import json
import os
import functools
import logging

from shutil import rmtree

log = logging.getLogger()


class ModelError(Exception):
    def __init__(self, msg, code=500):
        super(ModelError, self).__init__(msg)
        self.status_code = code


class Field(object):
    def __init__(self, name, data_type, def_value=None, required=True):
        self.name = name
        self.required = required
        self.def_value = def_value
        self.data_type = data_type
        if def_value:
            self.validate(def_value)

    def validate(self, value):
        if value is not None and type(value) != self.data_type:
            raise ModelError(
                'Field(%s) must be: %r' % (self.name, self.data_type), 400)
        return value

    def save(self, value):
        return value


class SecretField(Field):
    def __init__(self, name):
        super(SecretField, self).__init__(
            name, data_type=str, def_value='', required=False)

    def save(self, value):
        salt = os.urandom(16)
        hashed = hashlib.pbkdf2_hmac('sha256', value.encode(), salt, 100000)
        return (
            binascii.hexlify(salt) + b':' + binascii.hexlify(hashed)).decode()

    @staticmethod
    def verify(value, encrypted):
        salt, hashed = encrypted.split(':')
        salt = binascii.unhexlify(salt)
        new = hashlib.pbkdf2_hmac('sha256', value.encode(), salt, 100000)
        return binascii.unhexlify(hashed) == new


class ModelManager(object):
    def __init__(self, parent_dir, model_class):
        self._model_class = model_class
        self._model_dir = os.path.join(
            parent_dir, model_class.__name__.lower() + 's')

    def list(self, pattern=None):
        try:
            for item in os.listdir(self._model_dir):
                if not pattern or fnmatch.fnmatch(item, pattern):
                    yield item
        except FileNotFoundError as e:
            if e.filename == self._model_dir:
                log.warn('%s directory(%s) missing',
                         self._model_class.__name__, self._model_dir)
            else:
                raise

    def get(self, name):
        return self._model_class(name, os.path.join(self._model_dir, name))

    def _create_children(self, name, props):
        parent_model = None
        for child in self._model_class.CHILDREN:
            cname = child.__name__.lower() + 's'
            if cname in props:
                kids_props = props[cname]
                del props[cname]
                for child_props in kids_props:
                    n = child_props['name']
                    del child_props['name']
                    if not parent_model:
                        parent_model = self.get(name)
                    getattr(parent_model, cname).create(n, child_props)

    def create(self, name, props):
        self._model_class.validate_props(props, save=True)
        try:
            path = os.path.join(self._model_dir, name)
            os.makedirs(path)
            with open(os.path.join(path, 'props.json'), 'w') as f:
                json.dump(props, f)
            try:
                self._create_children(name, props)
            except:
                rmtree(path)
                raise
        except FileExistsError:
            raise ModelError('Item(%s) already exists' % name, 409)


class Model(object):
    FIELDS = []
    CHILDREN = []

    @classmethod
    def validate_props(clazz, props, ignore_required=False, save=False):
        fields = {x.name: x for x in clazz.FIELDS}
        kids = {x.__name__.lower() + 's': x for x in clazz.CHILDREN}
        for key, value in props.items():
            try:
                field = fields[key]
                field.validate(value)
                if save:
                    props[key] = field.save(value)
                del fields[key]
            except KeyError:
                if key not in kids:
                    raise ModelError(
                        '%s: Unknown field: %s' % (clazz.__name__, key))

        if not ignore_required:
            required = []
            for name, field in fields.items():
                if field.required:
                    required.append(name)
                else:
                    props[name] = field.def_value
            if required:
                raise ModelError(
                    '%s: Missing required field(s): %s' % (
                        clazz.__name__, ', '.join(required)))
        return props

    @staticmethod
    def getfield(field, self):
        if isinstance(self._props, str):
            # we haven't loaded in the properties yet
            with open(self._props) as f:
                self._props = self.validate_props(json.load(f))
        return self._props[field.name]

    @classmethod
    def _class_init(clazz):
        # a clever way to give us lazy-loadable object properies
        flag = clazz.__name__ + '_fields_set'
        if getattr(clazz, flag, None):
            return
        for f in clazz.FIELDS:
            setattr(
                Model, f.name, property(functools.partial(Model.getfield, f)))
        setattr(clazz, flag, True)

    def __init__(self, name, modeldir):
        self._class_init()
        self._modeldir = modeldir
        for clazz in self.CHILDREN:
            attr = clazz.__name__.lower() + 's'
            setattr(self, attr, ModelManager(modeldir, clazz))

        if not os.path.exists(modeldir):
            raise ModelError('%s does not exist' % name, 404)

        self.name = name
        self._props = os.path.join(modeldir, 'props.json')
        if not os.path.exists(self._props):
            raise ModelError('props.json not found for ' + name)

    def to_dict(self):
        data = {}
        for f in self.FIELDS:
            data[f.name] = self.getfield(f, self)
        return data

    def update(self, props):
        p = os.path.join(self._modeldir, 'props.json')
        temp = p + '.tmp'
        props = self.validate_props(props, ignore_required=True, save=True)
        with open(temp, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            oldprops = self.to_dict()
            oldprops.update(props)
            json.dump(oldprops, f)
            f.flush()
            os.rename(temp, p)

    def delete(self):
        rmtree(self._modeldir)
