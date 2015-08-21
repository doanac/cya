#!/usr/bin/env python3

import argparse
import json
import logging
import os
import platform
import stat
import sys
import urllib.error
import urllib.request
import urllib.parse

from multiprocessing import cpu_count

import lxc

from cya_client import settings

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
log = logging.getLogger('cya-client')


def _http_resp(resource, headers=None, data=None, method=None):
    url = urllib.parse.urljoin(settings.CYA_SERVER_URL, resource)
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
        'Authorization': 'Token ' + settings.HOST_API_KEY,
    }
    return _http_resp(resource, headers, data, method='PATCH')


def _host_props():
    mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    distro, release, name = platform.dist()
    return {
        'name': settings.HOST_NAME,
        'api_key': settings.HOST_API_KEY,
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
        max_mem = int(max_mem)
    else:
        max_mem = 0
    return {
        'name': name,
        'max_memory': max_mem,
        'date_created': int(os.stat(c.config_file_name).st_ctime),
    }


def _register_host(args):
    data = _host_props()
    data['api_key'] = settings.HOST_API_KEY
    containers = []
    for c in lxc.list_containers():
        containers.append(_container_props(c))
    data['containers'] = containers
    _post('/api/v1/host/', data)


def _update_host(args):
    data = _host_props()
    _patch('/api/v1/host/%s/' % settings.HOST_NAME, data)


def _create_container(container_props):
    log.debug('container props: %r', container_props)
    ct = lxc.Container(container_props['name'])
    ct.create(container_props['template'],
              args={'release': container_props['release']})
    init = container_props.get('init_script')
    if init:
        path = os.path.join(ct.get_config_item('lxc.rootfs'), 'cya_init')
        with open(path, 'w') as f:
            f.write(init)
            os.fchmod(f.fileno(), stat.S_IRWXG)
        ct.start(cmd=('/cya_init',))
    ct.start()


def _check(args):
    c = _get('/api/v1/host/%s/?with_containers' % settings.HOST_NAME)
    rem_containers = {x['name']: x for x in c.get('containers', [])}
    rem_names = set(rem_containers.keys())
    local_names = set(lxc.list_containers())

    to_add = rem_names - local_names
    to_del = local_names - rem_names

    for x in to_add:
        print('Creating: container: %s' % x)
        _create_container(rem_containers[x])

    for x in to_del:
        print('TODO del container: %s' % x)


def main(args):
    if getattr(args, 'func', None):
        log.debug('running: %s', args.func.__name__)
        args.func(args)


def get_args():
    parser = argparse.ArgumentParser('Client API to cya server')
    sub = parser.add_subparsers(help='sub-command help')
    p = sub.add_parser('register', help='Register this host with the server')
    p.set_defaults(func=_register_host)

    p = sub.add_parser('update', help='Update host props with the server')
    p.set_defaults(func=_update_host)

    p = sub.add_parser('check', help='Check in with server for updates')
    p.set_defaults(func=_check)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    if not os.geteuid() == 0 or 'SUDO_USER' not in os.environ:
        sys.exit('Must be root or sudo to execute')
    main(get_args())
