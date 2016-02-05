#!/bin/sh -x

apt-get install -y python3-flask

# deps not in ubuntu
wget http://ftp.us.debian.org/debian/pool/main/p/python3-openid/python3-openid_3.0.2+git20140828-1_all.deb
wget http://ftp.us.debian.org/debian/pool/main/f/flask-openid/python3-flask-openid_1.2.5+dfsg-2_all.deb
dpkg -i python3-*.deb
rm python3-*.deb

# Create an upstart entry to launch this service
CYA_ROOT=$(readlink -f $(dirname $0)/../)

cat >/etc/init/cya.conf <<EOF
# cya - Contain Your Assents orchestration daemon
description "CYA"

start on (starting network-interface
          or starting network-manager
          or starting networking)

stop on runlevel [!023456]

respawn
respawn limit 10 5

env PYTHONPATH=$CYA_ROOT
exec $CYA_ROOT/cya_server/manage.py runserver
EOF

echo "You can now start the daemon with 'sudo start cya'"
