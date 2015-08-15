import unittest
import unittest.mock

from cya_server.dict_model import Field, Model, ModelError, ModelArrayField


class TestFields(unittest.TestCase):
    def test_int_field_good(self):
        f = Field('name', int)
        f.validate(1)

    def test_int_field_bad(self):
        with self.assertRaises(ModelError):
            Field('f', int, '12')
        f = Field('f', int, 12)
        with self.assertRaises(ModelError):
            f.validate('12')
        with self.assertRaises(ModelError):
            f.validate(None)

    def test_str_field_bad(self):
        with self.assertRaises(ModelError):
            Field('f', str, 12)
        f = Field('f', str, '12')
        with self.assertRaises(ModelError):
            f.validate(12)
        with self.assertRaises(ModelError):
            f.validate(None)


class MyModel(Model):
    FIELDS = [
        Field('strfield', str, ''),
        Field('intfield', int, 0),
    ]


class MyModel2(Model):
    FIELDS = [
        ModelArrayField('models', MyModel)
    ]


class TestModel(unittest.TestCase):
    def test_load_good(self):
        data = {
            'strfield': 'foo',
            'intfield': 12,
        }
        m = MyModel(data)
        self.assertEqual('foo', m.strfield)
        self.assertEqual(12, m.intfield)
        self.assertEqual(MyModel.FIELDS[0], m.strfield_field)

    def test_load_bad(self):
        data = {
            'strfield': 'foo',
        }
        with self.assertRaises(ModelError):
            MyModel(data)

    def test_load_array(self):
        data = {
            'models': [
                {'strfield': 'foo', 'intfield': 12},
                {'strfield': 'FOO', 'intfield': 21},
            ]
        }
        m = MyModel2(data)
        self.assertEqual(2, len(m.models))
        self.assertEqual('foo', m.models[0].strfield)
        self.assertEqual(21, m.models[-1].intfield)

    def test_update(self):
        data = {
            'models': [
                {'strfield': 'foo', 'intfield': 12},
                {'strfield': 'FOO', 'intfield': 21},
            ]
        }
        m = MyModel2(data)
        m.models[0].update({'intfield': 10})
        m.models[1].update({'strfield': 'bar'})
        self.assertEqual(10, data['models'][0]['intfield'])
        self.assertEqual('bar', data['models'][1]['strfield'])

    def test_delete(self):
        data = {
            'models': [
                {'strfield': 'foo', 'intfield': 12},
                {'strfield': 'FOO', 'intfield': 21},
            ]
        }
        MyModel2(data).models[0].delete()
        self.assertEqual(1, len(data['models']))
        self.assertEqual('FOO', data['models'][0]['strfield'])

    def test_create(self):
        data = {
            'models': [
            ]
        }
        m = MyModel2(data)
        self.assertEqual(0, len(m.models))

        m.models.create({'strfield': 'foo', 'intfield': 12})
        self.assertEqual(1, len(data['models']))
        self.assertEqual('foo', data['models'][0]['strfield'])
        self.assertEqual(12, m.models[0].intfield)

        m.models.create({'strfield': 'bar', 'intfield': 12})
        self.assertEqual(2, len(data['models']))
        self.assertEqual('bar', m.models[1].strfield)

    def test_create_invalid(self):
        data = {
            'models': [
            ]
        }
        m = MyModel2(data)
        with self.assertRaises(ModelError):
            m.models.create({})
