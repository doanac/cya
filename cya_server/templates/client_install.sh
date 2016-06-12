#!/bin/sh
set -ex
wget -O cya_client.py "{{client_url}}"
chmod +x cya_client.py
./cya_client.py register "{{base_url}}" "{{version}}"
cat << EOF | sudo tee /etc/cron.d/cya_client_lxd
* * * * *	root `pwd`/cya_client.py check
EOF
