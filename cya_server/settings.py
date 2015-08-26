import os
import textwrap

_here = os.path.realpath(os.path.dirname(__file__))

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))

MODELS_FILE = os.path.join(_here, '../models.json')
SECRET_KEY = '12345'
AUTO_APPROVE_USER = True
OPENID_STORE = os.path.join(_here, '.openid')

AUTO_ENLIST_HOSTS = True

CONTAINER_TYPES = {
    'ubuntu-cloud': ['trusty', 'vivid', 'precise'],
    'debian': ['jessie'],
}

INIT_SCRIPTS = [
    {
        'name': 'ubuntu-cloud ssh-import keys',
        'content': textwrap.dedent('''\
            #!/bin/sh
            cat >/etc/cloud/cloud.cfg.d/99_cya.cfg <<EOF
            runcmd:
              - sudo -i -u ubuntu ssh-import-id YOUR_USERNAME
            EOF
        ''')
    },
]
