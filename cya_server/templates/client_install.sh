#!/bin/sh -ex

repo_root=$(pwd)/cya
bundle=`mktemp`

curl {{bundle_url}} > $bundle
git clone $bundle $repo_root
rm $bundle

${repo_root}/cya_client/main.py register "{{base_url}}"
