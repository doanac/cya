import functools

from flask import g, jsonify, request

from cya_server import app, settings
from cya_server.models import (
    client_version, container_requests, hosts, users, ModelError, SecretField)


def _is_host_authenticated(host):
    key = request.headers.get('Authorization', None)
    if key:
        parts = key.split(' ')
        if len(parts) == 2 and parts[0] == 'Token':
            return SecretField.verify(parts[1], host.api_key)
    return False


def host_authenticated(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('Authorization', None)
        if not key:
            resp = jsonify({'Message': 'No Authorization header provided'})
            resp.status_code = 401
            return resp
        parts = key.split(' ')
        if len(parts) != 2 or parts[0] != 'Token':
            resp = jsonify({'Message': 'Invalid Authorization header'})
            resp.status_code = 401
            return resp
        host = hosts.get(kwargs['name'])
        if not SecretField.verify(parts[1], host.api_key):
            resp = jsonify({'Message': 'Incorrect API key for host'})
            resp.status_code = 401
            return resp
        return f(*args, **kwargs)
    return wrapper


def user_authenticated(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('Authorization', None)
        if not key:
            resp = jsonify({'Message': 'No Authorization header provided'})
            resp.status_code = 401
            return resp
        parts = key.split(' ')
        if len(parts) != 2 or parts[0] != 'Token':
            resp = jsonify({'Message': 'Invalid Authorization header'})
            resp.status_code = 401
            return resp
        parts = parts[1].split(':')
        if len(parts) != 2:
            resp = jsonify({'Message': 'Invalid Authorization header'})
            resp.status_code = 401
            return resp
        user = users.get(parts[0].strip())
        if parts[1].strip() != user.api_key:
            resp = jsonify({'Message': 'Incorrect API key for user'})
            resp.status_code = 401
            return resp
        g.user = user
        return f(*args, **kwargs)
    return wrapper


@app.errorhandler(ModelError)
def _model_error_handler(error):
    return str(error) + '\n', error.status_code


@app.route('/api/v1/container_request/', methods=['POST'])
@user_authenticated
def container_create():
    name = request.json.pop('name')
    request.json['requested_by'] = g.user.nickname
    container_requests.create(name, request.json)
    resp = jsonify({})
    resp.status_code = 202
    return resp


@app.route('/api/v1/host/', methods=['GET'])
def host_list():
    return jsonify({'hosts': [x for x in hosts.list()]})


@app.route('/api/v1/host/', methods=['POST'])
def host_create():
    if 'api_key' not in request.json:
        raise ModelError('Missing required field: api_key')
    request.json['enlisted'] = settings.AUTO_ENLIST_HOSTS
    name = request.json['name']
    del request.json['name']
    hosts.create(name, request.json)
    resp = jsonify({})
    resp.status_code = 201
    resp.headers['Location'] = '/api/v1/host/%s/' % name
    return resp


@app.route('/api/v1/host/<string:name>/', methods=['PATCH'])
@host_authenticated
def host_update(name):
    if 'enlisted' in request.json:
        raise ModelError('"enlisted" field cannot be updated via API', 403)

    hosts.get(name).update(request.json)
    return jsonify({})


@app.route('/api/v1/host/<string:name>/', methods=['DELETE'])
@host_authenticated
def host_delete(name):
    hosts.get(name).delete()
    return jsonify({})


@app.route('/api/v1/host/<string:name>/', methods=['GET'])
def host_get(name):
    h = hosts.get(name)
    if _is_host_authenticated(h):
        h.ping()
        container_requests.handle(h)

    data = h.to_dict()
    data['client_version'] = client_version()
    withcontainers = request.args.get('with_containers') is not None
    if not withcontainers and 'containers' in h.data:
        del data['containers']
    if 'api_key' in data:
        del data['api_key']
    return jsonify(data)


@app.route('/api/v1/host/<string:name>/container/', methods=['GET'])
def host_container_list(name):
    h = hosts.get(name)
    return jsonify({'containers': [x for x in h.containers.list()]})


@app.route('/api/v1/host/<string:name>/container/<string:c>/', methods=['GET'])
def host_container_get(name, c):
    c = hosts.get(name).containers.get(c)
    return jsonify(c.to_dict())


@app.route('/api/v1/host/<string:name>/container/<string:c>/',
           methods=['PATCH'])
@host_authenticated
def host_container_update(name, c):
    c = hosts.get(name).containers.get(c)
    if c.one_shot and request.json.get('state') == 'DESTROY':
        c.delete()
    else:
        c.update(request.json)
    return jsonify({})


@app.route('/api/v1/host/<string:name>/container/<string:c>/logs/<string:l>',
           methods=['POST'])
@host_authenticated
def host_container_logs_update(name, c, l):
    c = hosts.get(name).containers.get(c)
    c.append_log(l, request.data.decode())
    resp = jsonify({})
    resp.status_code = 201
    return resp
