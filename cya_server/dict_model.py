import functools


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

    def get_def_value(self, name, data):
        return data.get(name, self.def_value)

    def validate(self, value):
        if type(value) != self.data_type:
            raise ModelError(
                'Field(%s) must be: %r' % (self.name, self.data_type), 400)

    def pre_save(self, value):
        return value

    def as_object(self, val):
        return val


class _model_array_list(list):
    create = None  # allows adding a "create" function on the list in the model


class ModelArrayField(Field):
    def __init__(self, name, model_class, unique_model_attr=None):
        super(ModelArrayField, self).__init__(name, list, [], False)
        self.model_cls = model_class
        self.unique_model_attr = unique_model_attr

    def validate(self, value):
        super(ModelArrayField, self).validate(value)
        for x in value:
            self.model_cls(x)

    def get_def_value(self, name, data):
        if name not in data:
            data[name] = []
        return data[name]

    @staticmethod
    def delete(val, item):
        val.remove(item)

    def replace(self, val, data):
        for d in data:
            self.model_cls(d)
        val.clear()
        val.extend(data)

    def create(self, val, data):
        m = self.model_cls(data)
        if self.unique_model_attr:
            for v in val:
                if v[self.unique_model_attr] == data[self.unique_model_attr]:
                    raise ModelError(
                        'Item(%s) already exists' % v[self.unique_model_attr],
                        409)
        m.update(data)  # ensure pre_save gets run
        val.append(data)

    def as_object(self, val):
        objects = _model_array_list()
        objects.create = functools.partial(self.create, val)
        objects.replace = functools.partial(self.replace, val)
        for x in val:
            o = self.model_cls(x)
            o.delete = functools.partial(self.delete, val, x)
            objects.append(o)
        return objects


class Model(object):
    def __init__(self, data):
        required = [x.name for x in self.FIELDS if x.required]
        for key, value in data.items():
            try:
                field = getattr(self, key + '_field')
                field.validate(value)
                if field.required:
                    required.remove(key)
            except AttributeError:
                raise ModelError(
                    '%s: Unknown field: %s' % (self.__class__.__name__, key))
        if required:
            raise ModelError(
                '%s: Missing required field(s): %s' % (
                    self.__class__.__name__, ', '.join(required)))
        self.data = data

    def update(self, data):
        for key, value in data.items():
            try:
                field = getattr(self, key + '_field')
                field.validate(value)
                data[key] = field.pre_save(value)
            except AttributeError:
                raise ModelError('Unknown field: %s' % key)
        self.data.update(data)

    def __getattr__(self, name):
        for field in self.FIELDS:
            if field.name == name:
                val = field.get_def_value(name, self.data)
                return field.as_object(val)
            if field.name + '_field' == name:
                return field
        raise AttributeError("'%s' object has no attribute '%s'" % (
            self.__class__.__name__, name))
