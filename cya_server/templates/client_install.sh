#!/bin/sh -ex

repo_root=$(pwd)/cya
bundle=`mktemp`

curl {{bundle_url}} > $bundle
git clone $bundle $repo_root
rm $bundle

${repo_root}/cya_client/main.py register "{{base_url}}"

cat > /etc/cron.d/cya_client <<EOF
#* * * * *	root ${repo_root}/cya_client/main.py check
#0 2 * * *	root ${repo_root}/cya_client/main.py update
EOF

cat > $repo_root/uninstall_client.sh <<EOF
#!/bin/sh

rm -rf $repo_root
rm /etc/cron.d/cya_client
EOF
