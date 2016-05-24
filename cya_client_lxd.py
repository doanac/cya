#!/usr/bin/env python3

import argparse
import fcntl
import json
import logging
import os
import platform
import sys
import subprocess
import time
import urllib.error
import urllib.request
import urllib.parse

from configparser import ConfigParser
from multiprocessing import cpu_count

import yaml
import dateutil.parser

IMAGE_ARCH = {
    'x86_64': 'amd64',
    'aarch64': 'arm64',
}

script = os.path.abspath(__file__)
hostprops_cached = os.path.join(os.path.dirname(script), 'hostprops.cache')
container_cached = os.path.join(os.path.dirname(script), 'containers.cache')
config_file = os.path.join(os.path.dirname(script), 'settings.conf')
config = ConfigParser()
config.read([config_file])

logging.basicConfig(
    level=getattr(logging, config.get('cya', 'log_level', fallback='DEBUG')))
log = logging.getLogger('cya-client')


def lxd_containers():
    containers = subprocess.check_output(['lxc', 'list', '--format=json'])
    containers = json.loads(containers.decode())
    for x in containers:
        ips = []
        if x['state']:
            for adapter, props in x['state'].get('network', {}).items():
                if adapter != 'lo':
                    ips.extend([i['address'] for i in props['addresses']])
        x['ips'] = ', '.join(ips)
    return {x['name']: x for x in containers}


def lxc_container_stop(container):
    log.debug('stopping container: %s', container['name'])
    subprocess.check_call(['lxc', 'stop', container['name']])
    container['status'] = 'Stopped'


def lxc_container_start(container):
    log.debug('starting container: %s', container['name'])
    subprocess.check_call(['lxc', 'start', container['name']])
    container['status'] = 'Running'


def lxd_container_get_max_memory(name):
    mem = subprocess.check_output(
        ['lxc', 'config', 'get', name, 'limits.memory'])
    mem = mem.decode().strip()
    if not mem:
        return 0
    amount = int(mem[:-2])
    unit = mem[-2:]
    if unit == 'MB':
        return amount * 1000000
    elif unit == 'GB':
        return amount * 1000000000
    else:
        raise RuntimeError('Unknown unit of memory: %s' % mem)


def lxd_image_info(container):
    image = container['config']['volatile.base_image']
    image = subprocess.check_output(['lxc', 'image', 'show', image]).decode()
    image = yaml.load(image)
    os = image['properties'].get('os', image['properties'].get('distribution'))
    return os, image['properties']['release']


def _create_conf(server_url, version):
    import string
    import random
    if os.path.exists(config_file):
        log.info('updating config settings')
        config['cya']['server_url'] = server_url
        config['cya']['version'] = version
        with open(config_file, 'w') as f:
            config.write(f, True)
        _check(None)
        sys.exit()

    config.add_section('cya')
    config['cya']['server_url'] = server_url
    config['cya']['version'] = version
    config['cya']['log_level'] = 'DEBUG'
    chars = string.ascii_letters + string.digits + '!@#$^&*~'
    config['cya']['host_api_key'] =\
        ''.join(random.choice(chars) for _ in range(32))
    with open('/etc/hostname') as f:
        config['cya']['hostname'] = f.read().strip()
    with open(config_file, 'w') as f:
        config.write(f, True)


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


def _auth_headers():
    return {
        'content-type': 'application/json',
        'Authorization': 'Token ' + config.get('cya', 'host_api_key')
    }


def _get(resource):
    return json.loads(_http_resp(resource, _auth_headers()).read().decode())


def _post(resource, data):
    data = json.dumps(data).encode('utf8')
    headers = {'content-type': 'application/json'}
    return _http_resp(resource, headers, data, method='POST')


def _patch(resource, data):
    data = json.dumps(data).encode('utf8')
    return _http_resp(resource, _auth_headers(), data, method='PATCH')


def _post_logs(container, data):
    headers = _auth_headers()
    headers['content-type'] = 'text/plain'
    resource = '/api/v1/host/%s/container/%s/logs' % (
        config.get('cya', 'hostname'), container)
    return _http_resp(resource, headers, data.encode(), method='POST')


def _host_props():
    mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    distro, release, name = platform.dist()
    return {
        'name': config.get('cya', 'hostname'),
        'cpu_total': cpu_count(),
        'cpu_type': platform.processor(),
        'mem_total': mem,
        'distro_id': distro,
        'distro_release': release,
        'distro_codename': name,
    }


def _container_props(container):
    max_mem = lxd_container_get_max_memory(container['name'])
    created = time.mktime(
        dateutil.parser.parse(container['created_at']).timetuple())
    os, release = lxd_image_info(container)
    return {
        'name': container['name'],
        'max_memory': max_mem,
        'date_created': int(created),
        'state': container['status'].upper(),
        'init_script': container['config'].get('user.user-data', ''),
        'ips': container['ips'],
        'template': os,
        'release': release,
    }


def _register_host(args):
    _create_conf(args.server_url, args.version)
    data = _host_props()
    data['api_key'] = config.get('cya', 'host_api_key')
    containers = []
    for name, container in lxd_containers().items():
        containers.append(_container_props(container))
    data['containers'] = containers
    _post('/api/v1/host/', data)


def _uninstall(args):
    os.unlink('/etc/cron.d/cya_client')
    os.unlink(config_file)
    os.unlink(script)
    os.rmdir(os.path.dirname(script))


def _update_host(args):
    data = _host_props()
    del data['name']
    try:
        with open(hostprops_cached) as f:
            cached = json.load(f)
    except:
        cached = {}

    if cached != data:
        log.info('updating host properies on server: %s', data)
        _patch('/api/v1/host/%s/' % config.get('cya', 'hostname'), data)
        with open(hostprops_cached, 'w') as f:
            json.dump(data, f)


def _create_container(container_props):
    log.debug('container props: %r', container_props)
    has_cloud_init = container_props['template'] == 'ubuntu'
    if has_cloud_init:
        image = container_props['template'] + ':' + container_props['release']
    else:
        arch = IMAGE_ARCH[platform.processor()]
        image = 'images:%s/%s/%s' % (
            container_props['template'], container_props['release'], arch)
    args = ['lxc', 'launch', image, container_props['name']]

    mem = container_props.get('max_memory')
    if mem:
        args.append('--config=limits.memory=%dMB' % (mem / 1000000))
    init = container_props.get('init_script')

    if init:
        args.append('--config=user.user-data=%s' % init)

    # TODO console logs?
    subprocess.check_call(args)
    if init and not has_cloud_init:
        log.info('Running init script')
        p = subprocess.Popen(['lxc', 'exec', container_props['name'], 'bash'],
                             stdin=subprocess.PIPE)
        stdout, stderr = p.communicate(input=init.encode())
        if p.returncode != 0:
            log.error('Unable to run initscript: stdout(%s), stderr(%s)',
                      stdout, stderr)


def _update_container(container):
    data = _container_props(container)
    del data['name']
    _patch('/api/v1/host/%s/container/%s/' %
           (config.get('cya', 'hostname'), container['name']), data)


def _upgrade_client(version):
    script = _http_resp('/cya_client.py', {}).read()
    with open(__file__, 'wb') as f:
        f.write(script)
    p = os.fork()
    if p == 0:
        log.debug('waiting 2 seconds for parent to exit')
        time.sleep(2)
        args = [__file__, 'register', config.get('cya', 'server_url'), version]
        os.execv(args[0], args)
    else:
        log.debug('exiting client to let child run')
        sys.exit()


def _update_logs(ct, cache):
    # TODO
    '''try:
        clog = ct.get_config_item('lxc.console.logfile')
    except KeyError:
        # no log file defined
        return
    cur_pos = cache.setdefault(ct.name, {}).get('logpos', 0)
    try:
        with open(clog) as f:
            if os.fstat(f.fileno()).st_size > cur_pos:
                log.debug('appending console log for %s', ct.name)
                f.seek(cur_pos)
                _post_logs(ct.name, f.read())
                cache[ct.name]['logpos'] = f.tell()
    except OSError:
        pass  # log doesn't exist'''


def _handle_start_stop(container, container_props):
    name = container['name']
    status = container['status'].upper()
    should_run = container_props[name].get('keep_running', True)
    if should_run and status != 'RUNNING':
        lxc_container_start(container)
        return True
    elif not should_run and status != 'STOPPED':
        lxc_container_stop(container)
        return True
    elif container_props[name].get('state') != status:
        log.debug('updating container(%s) state to: %s', name, status)
        return True
    return False


def _handle_ips(container, cache):
    name = container['name']
    status = container['status']
    cached_ips = cache.setdefault(name, {'ips': ''})['ips']
    if status == 'Running' and container['ips'] != cached_ips:
        cache[name]['ips'] = container['ips']
        return True
    elif cached_ips:
        cache[container['name']]['ips'] = ''
        return True
    return False


def _handle_adds(container_props, to_add):
    for x in to_add:
        print('Creating: container: %s' % x)
        _create_container(container_props[x])
        log.debug('updating container info on server')
        _update_container(lxd_containers()[x])


def _handle_dels(to_del):
    for x in to_del:
        print('Deleting container: %s' % x)
        subprocess.check_call(['lxc', 'delete', '--force', x])


def _handle_existing(lxc_containers, container_props, names):
    try:
        with open(container_cached) as f:
            cache = json.load(f)
    except:
        cache = {}

    for name in names:
        container = lxc_containers[name]
        if container_props[name].get('re_create'):
            _handle_dels([name])
            _handle_adds(container_props, [name])
        else:
            changed = _handle_start_stop(container, container_props)
            if changed or _handle_ips(container, cache):
                _update_container(container)
            _update_logs(container, cache)

    with open(container_cached, 'w') as f:
        json.dump(cache, f)


def _check(args):
    c = _get(
        '/api/v1/host/%s/?with_containers' % config.get('cya', 'hostname'))

    if c['client_version'] != config.get('cya', 'version'):
        log.warn('Upgrading client to: %s', c['client_version'])
        _upgrade_client(c['client_version'])

    _update_host(args)

    rem_containers = {x['name']: x for x in c.get('containers', [])}
    rem_names = set(rem_containers.keys())
    containers = lxd_containers()
    local_names = set(containers.keys())

    _handle_adds(rem_containers, rem_names - local_names)
    _handle_dels(local_names - rem_names)
    _handle_existing(containers, rem_containers, rem_names & local_names)


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
    p.add_argument('version')

    p = sub.add_parser('update', help='Update host props with the server')
    p.set_defaults(func=_update_host)

    p = sub.add_parser('check', help='Check in with server for updates')
    p.set_defaults(func=_check)

    p = sub.add_parser('uninstall', help='Uninstall the client')
    p.set_defaults(func=_uninstall)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    # Ensure no other copy of this script is running
    with open('/tmp/cya_client_lxd.lock', 'w+') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            log.debug('Script is already running')
            sys.exit(0)
        main(get_args())
