#!/usr/bin/env python3

import argparse
import fcntl
import json
import logging
import os
import platform
import stat
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

from configparser import ConfigParser
from multiprocessing import cpu_count

import lxc

script = os.path.abspath(__file__)
hostprops_cached = os.path.join(os.path.dirname(script), 'hostprops.cache')
logs_info = os.path.join(os.path.dirname(script), 'logs.info')
config_file = os.path.join(os.path.dirname(script), 'settings.conf')
config = ConfigParser()
config.read([config_file])

logging.basicConfig(
    level=getattr(logging, config.get('cya', 'log_level', fallback='INFO')))
log = logging.getLogger('cya-client')


def _create_conf(server_url, version):
    import string
    import random
    if os.path.exists(config_file):
        log.info('updating config settings')
        config['cya']['server_url'] = server_url
        config['cya']['version'] = version
        with open(config_file, 'w') as f:
            config.write(f, True)
        _create_cron()
        _check(None)
        sys.exit()

    config.add_section('cya')
    config['cya']['server_url'] = server_url
    config['cya']['version'] = version
    config['cya']['log_level'] = 'INFO'
    chars = string.ascii_letters + string.digits + '!@#$^&*~'
    config['cya']['host_api_key'] =\
        ''.join(random.choice(chars) for _ in range(32))
    with open('/etc/hostname') as f:
        config['cya']['hostname'] = f.read().strip()
    with open(config_file, 'w') as f:
        config.write(f, True)


def _create_cron():
    with open('/etc/cron.d/cya_client', 'w') as f:
        f.write('* * * * *	root %s check\n' % script)


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
        'state': c.state,
    }


def _register_host(args):
    _create_conf(args.server_url, args.version)
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


def _update_host(args):
    data = _host_props()
    try:
        with open(hostprops_cached) as f:
            cached = json.load(f)
    except:
        cached = {}

    if cached != data:
        log.info('updating host properies on server')
        _patch('/api/v1/host/%s/' % config.get('cya', 'hostname'), data)
        with open(hostprops_cached, 'w') as f:
            json.dump(data, f)


def _create_container(container_props):
    log.debug('container props: %r', container_props)
    ct = lxc.Container(container_props['name'])
    ct.create(container_props['template'],
              args={'release': container_props['release']})

    console = os.path.join(os.path.dirname(ct.config_file_name), 'console.log')
    ct.set_config_item('lxc.console.logfile', console)
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


def _update_logs(containers):
    try:
        with open(logs_info) as f:
            logs = json.load(f)
    except:
        logs = {}

    for x in containers:
        ct = lxc.Container(x)
        clog = os.path.join(os.path.dirname(ct.config_file_name), 'console.log')
        cur_pos = logs.get(x, 0)
        try:
            with open(clog) as f:
                if os.fstat(f.fileno()).st_size > cur_pos:
                    log.debug('appending console log for %s', x)
                    f.seek(cur_pos)
                    _post_logs(x, f.read())
                    logs[x] = f.tell()
        except OSError:
            pass  # log doesn't exist

    with open(logs_info, 'w') as f:
        json.dump(logs, f)


def _handle_adds(containers, to_add):
    for x in to_add:
        print('Creating: container: %s' % x)
        _create_container(containers[x])
        log.debug('updating container info on server')
        _update_container(x)


def _handle_dels(containers, to_del):
    for x in to_del:
        print('Deleting container: %s' % x)
        c = lxc.Container(x)
        c.stop()
        c.destroy()


def _check(args):
    c = _get(
        '/api/v1/host/%s/?with_containers' % config.get('cya', 'hostname'))

    if c['client_version'] != config.get('cya', 'version'):
        log.warn('Upgrading client to: %s', c['client_version'])
        _upgrade_client(c['client_version'])

    _update_host(args)

    rem_containers = {x['name']: x for x in c.get('containers', [])}
    rem_names = set(rem_containers.keys())
    local_names = set(lxc.list_containers())

    to_add = rem_names - local_names
    to_del = local_names - rem_names

    for x in rem_names & local_names:
        c = lxc.Container(x)
        if rem_containers[x].get('re_create'):
            print('Re-creating container: %s' % x)
            log.debug('stopping')
            c.stop()
            log.debug('destroying')
            c.destroy()
            _create_container(rem_containers[x])
            log.debug('updating container info on server')
            _update_container(x)
        else:
            changed = False
            should_run = rem_containers[x].get('keep_running', True)
            if should_run and c.state != 'RUNNING':
                c.start()
                changed = True
            elif not should_run and c.state != 'STOPPED':
                c.stop()
                changed = True
            if changed or rem_containers[x].get('state') != c.state:
                log.debug('updating container state to: %s', c.state)
                _update_container(x)

    _handle_adds(rem_containers, to_add)
    _handle_dels(rem_containers, to_del)
    _update_logs(rem_containers)


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
