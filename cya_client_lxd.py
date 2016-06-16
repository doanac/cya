#!/usr/bin/env python3

import argparse
import fcntl
import json
import logging
import os
import platform
import select
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


def _mount_container_volumes(container_props, unmount=False):
    name = container_props['name']
    mounts = os.path.join(os.path.dirname(script), 'shared_storage', name)
    for mount in container_props.get('containermounts', []):
        mount_dir = os.path.join(mounts, mount['name'])
        if unmount and os.path.exists(mount_dir):
            log.debug('unmounting: %s', mount_dir)
            subprocess.check_call(['umount', mount_dir])
            os.rmdir(mount_dir)
        elif not unmount:
            if not os.path.exists(mount_dir):
                os.makedirs(mount_dir)
            log.debug('mounting: %s', mount_dir)
            subprocess.check_call(
                ['mount', '-t', mount['type'],  mount['source'], mount_dir])
    if unmount and os.path.exists(mounts):
        os.rmdir(mounts)


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


def lxc_container_stop(container, container_props):
    log.debug('stopping container: %s', container['name'])
    subprocess.check_call(['lxc', 'stop', container['name']])
    _mount_container_volumes(container_props, unmount=True)
    container['status'] = 'Stopped'


def lxc_container_start(container, container_props):
    log.debug('starting container: %s', container['name'])
    _mount_container_volumes(container_props)
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
    image = subprocess.check_output(
        ['lxc', 'image', 'show', image], stderr=subprocess.DEVNULL).decode()
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


def _post_logs(container, logname, data):
    if type(data) == str:
        data = data.encode()
    headers = _auth_headers()
    headers['content-type'] = 'text/plain'
    resource = '/api/v1/host/%s/container/%s/logs/%s' % (
        config.get('cya', 'hostname'), container, logname)
    try:
        return _http_resp(resource, headers, data, method='POST')
    except:
        return False


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
    props = {
        'name': container['name'],
        'max_memory': max_mem,
        'date_created': int(created),
        'state': container['status'].upper(),
        'init_script': container['config'].get('user.cya_init', ''),
        'ips': container['ips'],
    }
    try:
        os, release = lxd_image_info(container)
        props['template'] = os
        props['release'] = release
    except:
        log.debug('image info for %s no longer available', container['name'])
    return props


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


def _create_shared_mounts(container_props):
    mounts = os.path.join(
        os.path.dirname(script), 'shared_storage', container_props['name'])
    for mount in container_props.get('containermounts', []):
        log.debug('adding device to container')
        mp = os.path.join(mounts, mount['name'])
        subprocess.check_call([
            'lxc', 'config', 'device', 'add', container_props['name'],
            mount['name'], 'disk', 'source=' + mp,
            'path=%s' % mount['directory']])


def _run_init(container_name, name, script):
    log.info('Running init script: %s', name)
    buff = ('\n== CYA-INIT-SCRIPT(%s) STARTED at: %s\n' % (
        name, time.asctime())).encode()
    if _post_logs(container_name, name, buff):
        buff = b''
    else:
        log.error('Unable to post log start, will try again')
    p = subprocess.Popen(['lxc', 'exec', container_name, 'bash'],
                         stdin=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdout=subprocess.PIPE, close_fds=True)
    p.stdin.write(script.encode())
    p.stdin.close()

    poller = select.poll()
    RONLY = select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR
    poller.register(p.stdout.fileno(), RONLY)
    last_update = 0
    while poller:
        events = poller.poll()
        for fd, flag in events:
            data = os.read(fd, 1024)
            if data:
                buff += data
                now = time.time()
                # update server log ever 20s or 8k bytes
                if now - last_update > 20 or len(buff) > 8192:
                    if _post_logs(container_name, name, buff):
                        last_update = now
                        buff = b''
                    else:
                        log.error('Unable to update log, will try again')
            else:
                poller = None
    p.wait()
    buff += b'\n== RC=%d' % p.returncode
    buff = '\n== CYA-INIT-SCRIPT(%s) ENDED at: %s RC=%d\n' % (
        name, time.asctime(), p.returncode)
    if not _post_logs(container_name, name, buff.encode()):
        log.error('Unable to update script finish log, ignoring')
    return p.returncode


def _run_init_scripts(container_props):
    log.info('Fork and run init script')
    if os.fork():
        return
    lockfile.close()
    for script in container_props['initscripts']:
        _run_init(container_props['name'], script['name'], script['content'])

    if container_props.get('one_shot'):
        data = {'state': 'DESTROY'}
        _patch('/api/v1/host/%s/container/%s/' %
               (config.get('cya', 'hostname'), container_props['name']), data)
        _handle_dels([container_props['name']])
        sys.exit(0)


def _create_container(container_props):
    log.debug('container props: %r', container_props)
    arch = IMAGE_ARCH[platform.processor()]
    image = 'images:%s/%s/%s' % (
        container_props['template'], container_props['release'], arch)
    args = ['lxc', 'init', image, container_props['name']]

    mem = container_props.get('max_memory')
    if mem:
        args.append('--config=limits.memory=%dMB' % (mem / 1000000))
    init = container_props.get('initscripts', [])
    for name, content in init:
        args.append('--config=user.cya_%s=%s' % (name, content))

    subprocess.check_call(args)
    _create_shared_mounts(container_props)
    lxc_container_start({'name': container_props['name']}, container_props)

    if init:
        _run_init_scripts(container_props)


def _update_container(container):
    data = _container_props(container)
    del data['name']
    _patch('/api/v1/host/%s/container/%s/' %
           (config.get('cya', 'hostname'), container['name']), data)


def _upgrade_client(version):
    script = _http_resp('/cya_client.py', {}).read()
    with open(__file__, 'wb') as f:
        f.write(script)
        f.flush()
    args = [__file__, 'register', config.get('cya', 'server_url'), version]
    os.execv(args[0], args)


def _handle_start_stop(container, container_props):
    name = container['name']
    status = container['status'].upper()
    should_run = container_props[name].get('keep_running', True)
    if should_run and status != 'RUNNING':
        lxc_container_start(container, container_props[name])
        return True
    elif not should_run and status != 'STOPPED':
        lxc_container_stop(container, container_props[name])
        return True
    elif container_props[name].get('state') != status:
        log.debug('updating container(%s) state to: %s', name, status)
        return True
    return False


def _handle_ips(container, cache):
    name = container['name']
    status = container['status']
    cached_ips = cache.setdefault(name, {}).get('ips', '')
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
        mounts = os.path.join(os.path.dirname(script), 'shared_storage', x)
        if os.path.exists(mounts):
            for mount in os.listdir(mounts):
                mount = os.path.join(mounts, mount)
                subprocess.check_call(['umount', mount])
                os.rmdir(mount)
            os.rmdir(mounts)


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
        global lockfile
        lockfile = f
        main(get_args())
