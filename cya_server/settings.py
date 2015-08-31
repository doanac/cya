import os
import textwrap

_here = os.path.realpath(os.path.dirname(__file__))

DEBUG = os.environ.get('DEBUG', '0')
DEBUG = bool(int(DEBUG))

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


MODELS_FILE = os.path.join(_here, '../models.json')
SECRET_KEY = None
AUTO_APPROVE_USER = True
OPENID_STORE = os.path.join(_here, '../.openid')
AUTO_ENLIST_HOSTS = True


_settings_files = (
    '/etc/cya_server.conf',
    os.path.join(_here, 'local_settings.conf'),
)


for fname in _settings_files:
    if os.path.exists(fname):
        with open(fname) as f:
            for line in f:
                line = line.strip()
                if line and line[0] != '#':
                    key, val = line.split('=', 2)
                    globals()[key.strip()] = val.strip()

if not SECRET_KEY:
    local_settings = _settings_files[-1]
    print('Generating random secret key in: ' + local_settings)
    import string
    import random
    with open(local_settings, 'a') as f:
        SECRET_KEY = ''.join(
            random.choice(string.printable) for _ in range(16))
        SECRET_KEY = SECRET_KEY.replace('\n', '_')
        f.write('\n# Randomly generated:\nSECRET_KEY = %s\n' % SECRET_KEY)
