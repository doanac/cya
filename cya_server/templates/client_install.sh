#!/bin/sh -ex

mkdir cya
cd cya
wget -O cya_client.py "{{client_url}}"
chmod +x cya_client.py
./cya_client.py register "{{base_url}}" "{{version}}"

