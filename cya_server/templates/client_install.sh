#!/bin/sh
set -ex
user=`whoami`
sudo mkdir cya
sudo chown $user cya
cd cya
wget -O cya_client.py "{{client_url}}"
chmod +x cya_client.py
./cya_client.py register "{{base_url}}" "{{version}}"
{% if lxd %}
cat << EOF | sudo tee /etc/cron.d/cya_client_lxd
* * * * *	$user `pwd`/cya_client.py check
EOF
{% endif %}
