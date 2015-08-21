import os
import sys

_here = os.path.realpath(os.path.dirname(__file__))

with open('/etc/hostname') as f:
    HOST_NAME = f.read().strip()


_settings_files = (
    '/etc/cya.conf',
    os.path.join(_here, 'local_settings.conf'),
)

HOST_API_KEY = None
CYA_SERVER_URL = None
LOG_LEVEL = 'INFO'

last_file = None
for fname in _settings_files:
    if os.path.exists(fname):
        with open(fname) as f:
            for line in f:
                line = line.strip()
                if line and line[0] != '#':
                    key, val = line.split('=', 2)
                    globals()[key.strip()] = val.strip()
            last_file = fname

if not last_file:
    sys.exit('No settings file found at: ' + ', '.join(_settings_files))

if not HOST_API_KEY:
    print('Generating random host api key in: ' + last_file)
    import string
    import random
    with open(last_file, 'a') as f:
        HOST_API_KEY = ''.join(
            random.choice(string.printable) for _ in range(16))
        f.write('\n# Randomly generated:\nHOST_API_KEY = %s\n' % HOST_API_KEY)

if not CYA_SERVER_URL:
    sys.exit(
        'CYA_SERVER_URL must be defined in: ' + ', '.join(_settings_files))
