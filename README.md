CYA - Contain Your Assets
=========================

This is a simple client/server program to allow a pool of bare-metal systems
provide LXC containers on-demand. Think of it like OpenStack minus the insane
complexity and, until recently, lack of container support.

You setup a "cya server" on one system and then install clients as you wish.
Then you can request containers as you need them and the server will try and
pick the best client for creating the container on. The clients check with the
server once a minute to find out if there are new containers it should create.

See what I'm running here:

 https://cya.bettykrocks.com/

Setting Up The Server
---------------------

* Clone the repo to your favorite place like /srv/cya or /usr/local/cya.
* Run your distro script: sudo ./distro/trusty_install.sh
* Start the server with "sudo start cya"
* log into to server at http://<server>:8000/

The initial user that logs in via OpenID will automatically be an admin. From
the settings page you can create your own script to be run when containers are
created.

Setting Up The Client(s)
------------------------

* Go to your favorite install place like /srv
* curl http:<cya server>:8000/client_install.sh | sudo bash

The install step will register with the server and import all local containers
into the cya server so they can be managed from there.

Example Init Script
-------------------

Here's a script I use at home to set up my Ubuntu containers with::

 #!/bin/sh

 cat >/etc/cloud/cloud.cfg.d/99_doanac.cfg <<EOF
 runcmd:
   - usermod -g users ubuntu
   - sudo -i -u ubuntu ssh-import-id doanac
   - echo "0,30 * * * * ubuntu ssh-import-id doanac" > /etc/cron.d/sshkey-sync
   - mkdir /code /storage
   - echo "reckless:/code   /code   nfs    auto  0  0" >> /etc/fstab
   - echo "storage:/home   /storage   nfs    auto  0  0" >> /etc/fstab
   - apt-get update
   - apt-get install -y ssl-cert git
   - apt-get install -y nfs-common
   - mount -a
 EOF
