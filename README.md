CYA - Contain Your Assets
=========================

This is a simple client/server program to allow a pool of bare-metal systems
provide LXC containers on-demand. Think of it like OpenStack minus the insane
complexity and, until recently, lack of container support.

You setup a "cya server" on one system and then install clients as you wish.
Then you can request containers as you need them and the server will try and
pick the best client for creating the container on. The clients check with the
server once a minute to find out if there are new containers it should create.

Setting Up The Server
---------------------

* Clone the repo to your favorite place like /srv/cya or /usr/local/cya.
* Run your distro script: sudo ./distro/trusty_install.sh
* Start the server with "sudo start cya"

Setting Up The Client(s)
------------------------

* Go to your favorite install place like /srv
* curl http:<cya server>:8000/client_install.sh | sudo bash
* ./cya_client/main.py register

The register step will import all local containers into the cya server so they
can be managed from there.
