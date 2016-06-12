import os
import textwrap

_here = os.path.realpath(os.path.dirname(__file__))

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))

CLIENT_SCRIPT = os.path.join(_here, '../cya_client_lxd.py')

CONTAINER_TYPES = {
    'ubuntu': ['xenial', 'trusty', 'wily', 'precise'],
    'debian': ['jessie'],
}

INIT_SCRIPTS = [
    {
        'name': 'wait-for-network',
        'content': textwrap.dedent('''\
            #!/bin/sh
            # wait for network
            set -ex
            for x in 1 2 3 4 5 ; do
                sleep 3
                ping -c1 google.com && break || true
            done
        ''')
    },
]


MODELS_DIR = os.path.join(_here, '../models')
SECRET_KEY = None
AUTO_APPROVE_USER = True
OPENID_STORE = os.path.join(_here, '../.openid')
AUTO_ENLIST_HOSTS = True


LOCAL_SETTINGS = os.path.join(_here, 'local_settings.conf')
_settings_files = (
    '/etc/cya_server.conf',
    LOCAL_SETTINGS,
)


for fname in _settings_files:
    if os.path.exists(fname):
        with open(fname) as f:
            for line in f:
                line = line.strip()
                if line and line[0] != '#':
                    key, val = line.split('=', 2)
                    key = key.strip()
                    val = val.strip()
                    if val.lower() in ('true', 'false'):
                        val = val.lower() == 'true'
                    globals()[key] = val

if not SECRET_KEY:
    local_settings = _settings_files[-1]
    print('Generating random secret key in: ' + local_settings)
    import string
    import random
    with open(local_settings, 'a') as f:
        SECRET_KEY = ''.join(
            random.choice(
                string.ascii_letters + string.digits) for _ in range(16))
        f.write('\n# Randomly generated:\nSECRET_KEY = %s\n' % SECRET_KEY)
