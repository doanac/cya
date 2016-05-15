import shutil
import tempfile
import unittest

from cya_server.simplemodels import Field, Model, ModelManager, ModelError


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


class TestModel(unittest.TestCase):
    def setUp(self):
        super(TestModel, self).setUp()
        self.modeldir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.modeldir)
        self.models = ModelManager(self.modeldir, MyModel)

    def test_create_validate(self):
        with self.assertRaises(ModelError):
            self.models.create('m1', {'strfield': 'x'})
        with self.assertRaises(ModelError):
            self.models.create('m1', {'strfield': 'x', 'intfield': 'x'})

    def test_create(self):
        self.models.create('m1', {'strfield': 'x', 'intfield': 42})
        m = self.models.get('m1')
        self.assertIn('intfield', dir(m))
        self.assertIn('strfield', dir(m))
        self.assertEqual('x', m.strfield)
        self.assertEqual(42, m.intfield)

    def test_update(self):
        self.models.create('m1', {'strfield': 'x', 'intfield': 42})
        m = self.models.get('m1')
        m.update({'strfield': 'y'})
        m = self.models.get('m1')
        self.assertEqual('y', m.strfield)
        self.assertEqual(42, m.intfield)

        with self.assertRaises(ModelError):
            m.update({'intfield': '12'})

    def test_delete(self):
        self.models.create('m1', {'strfield': 'x', 'intfield': 42})
        m = self.models.get('m1')
        m.delete()
        with self.assertRaises(ModelError):
            m = self.models.get('m1')
