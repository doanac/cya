import os

_here = os.path.realpath(os.path.dirname(__file__))

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))

MODELS_FILE = os.path.join(_here, '../models.json')

CONTAINER_TYPES = {
    'ubuntu-cloud': ['trusty', 'vivid', 'precise'],
    'debian': ['jessie'],
}
