#!/usr/bin/env python3

import argparse
import fcntl
import json
import logging
import os
import platform
import stat
import sys
import urllib.error
import urllib.request
import urllib.parse

from configparser import ConfigParser
from multiprocessing import cpu_count

import lxc

script = os.path.abspath(__file__)
config_file = os.path.join(os.path.dirname(script), 'settings.conf')
config = ConfigParser()
config.read([config_file])

logging.basicConfig(
    level=getattr(logging, config.get('cya', 'log_level', fallback='INFO')))
log = logging.getLogger('cya-client')


def _create_conf(server_url):
    import string
    import random
    config.add_section('cya')
    config['cya']['server_url'] = server_url
    config['cya']['log_level'] = 'INFO'
    chars = string.ascii_letters + string.digits + '!@#$%^&*~'
    config['cya']['host_api_key'] =\
        ''.join(random.choice(chars) for _ in range(32))
    with open('/etc/hostname') as f:
        config['cya']['hostname'] = f.read().strip()
    with open(config_file, 'w') as f:
        config.write(f, True)


def _create_cron():
    with open('/etc/cron.d/cya_client') as f:
        f.write('* * * * *	root %s check\n' % script)
        f.write('* 2 * * *	root %s update\n' % script)


def _http_resp(resource, headers=None, data=None, method=None):
    url = urllib.parse.urljoin(config.get('cya', 'server_url'), resource)
    req = urllib.request.Request(
        url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return resp
    except urllib.error.URLError as e:
        if hasattr(e, 'reason'):
            sys.stderr.write('Failed to issue request: %s\n' % e.reason)
            sys.stderr.write('  ' + e.read().decode())
        elif hasattr(e, 'code'):
            print('The server couldn\'t fulfill the request.')
            print('Error code: ', e.code)
        sys.exit(1)


def _get(resource):
    return json.loads(_http_resp(resource, headers={}).read().decode())


def _post(resource, data):
    data = json.dumps(data).encode('utf8')
    headers = {'content-type': 'application/json'}
    return _http_resp(resource, headers, data, method='POST')


def _patch(resource, data):
    data = json.dumps(data).encode('utf8')
    headers = {
        'content-type': 'application/json',
        'Authorization': 'Token ' + config.get('cya', 'host_api_key')
    }
    return _http_resp(resource, headers, data, method='PATCH')


def _host_props():
    mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    distro, release, name = platform.dist()
    return {
        'name': config.get('cya', 'hostname'),
        'api_key': config.get('cya', 'host_api_key'),
        'cpu_total': cpu_count(),
        'cpu_type': platform.processor(),
        'mem_total': mem,
        'distro_id': distro,
        'distro_release': release,
        'distro_codename': name,
    }


def _container_props(name):
    c = lxc.Container(name)
    max_mem = c.get_config_item('lxc.cgroup.memory.limit_in_bytes')
    if max_mem:
        max_mem = int(max_mem[0])
    else:
        max_mem = 0
    return {
        'name': name,
        'max_memory': max_mem,
        'date_created': int(os.stat(c.config_file_name).st_ctime),
    }


def _register_host(args):
    _create_conf(args.server_url)
    data = _host_props()
    data['api_key'] = config.get('cya', 'host_api_key')
    containers = []
    for c in lxc.list_containers():
        containers.append(_container_props(c))
    data['containers'] = containers
    _post('/api/v1/host/', data)
    _create_cron()


def _uninstall(args):
    os.unlink('/etc/cron.d/cya_client')
    os.unlink(config_file)
    os.unlink(script)
    os.rmdir(os.path.dirname(script))


def _update_host(args, with_containers=False):
    data = _host_props()
    if with_containers:
        containers = []
        for c in lxc.list_containers():
            containers.append(_container_props(c))
        data['containers'] = containers
    _patch('/api/v1/host/%s/' % config.get('cya', 'hostname'), data)


def _create_container(container_props):
    log.debug('container props: %r', container_props)
    ct = lxc.Container(container_props['name'])
    ct.create(container_props['template'],
              args={'release': container_props['release']})
    mem = container_props.get('max_memory')
    if mem:
        ct.set_config_item('lxc.cgroup.memory.limit_in_bytes', str(mem))
        ct.save_config()
    init = container_props.get('init_script')
    if init:
        path = os.path.join(ct.get_config_item('lxc.rootfs'), 'cya_init')
        with open(path, 'w') as f:
            f.write(init)
            os.fchmod(f.fileno(), stat.S_IRWXG)
        if not ct.start(daemonize=False, cmd=('/cya_init',)):
            log.error('unable to run init_script')

    if not ct.start():
        log.error('unable to start container')


def _update_container(name):
    data = _container_props(name)
    _patch('/api/v1/host/%s/container/%s/' %
           (config.get('cya', 'hostname'), name), data)


def _check(args):
    c = _get(
        '/api/v1/host/%s/?with_containers' % config.get('cya', 'hostname'))
    rem_containers = {x['name']: x for x in c.get('containers', [])}
    rem_names = set(rem_containers.keys())
    local_names = set(lxc.list_containers())

    to_add = rem_names - local_names
    to_del = local_names - rem_names

    for x in rem_names & local_names:
        if rem_containers[x].get('re_create'):
            print('Re-creating container: %s' % x)
            c = lxc.Container(x)
            log.debug('stopping')
            c.stop()
            log.debug('destroying')
            c.destroy()
            _create_container(rem_containers[x])
            log.debug('updating container info on server')
            _update_container(x)

    for x in to_add:
        print('Creating: container: %s' % x)
        _create_container(rem_containers[x])
        log.debug('updating container info on server')
        _update_container(x)

    for x in to_del:
        print('Deleting container: %s' % x)
        c = lxc.Container(x)
        c.stop()
        c.destroy()


def main(args):
    if getattr(args, 'func', None):
        log.debug('running: %s', args.func.__name__)
        args.func(args)


def get_args():
    parser = argparse.ArgumentParser('Client API to cya server')
    sub = parser.add_subparsers(help='sub-command help')
    p = sub.add_parser('register', help='Register this host with the server')
    p.set_defaults(func=_register_host)
    p.add_argument('server_url')

    p = sub.add_parser('update', help='Update host props with the server')
    p.set_defaults(func=_update_host)

    p = sub.add_parser('check', help='Check in with server for updates')
    p.set_defaults(func=_check)

    p = sub.add_parser('uninstall', help='Uninstall the client')
    p.set_defaults(func=_uninstall)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    if os.geteuid() != 0 and 'SUDO_USER' not in os.environ:
        sys.exit('Must be root or sudo to execute')

    # Ensure no other copy of this script is running
    with open('/tmp/cya_client.lock', 'w+') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            log.debug('Script is already running')
            sys.exit(0)
        main(get_args())
