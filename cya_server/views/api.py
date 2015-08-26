import functools

from flask import jsonify, request

from cya_server import app, models, settings
from cya_server.dict_model import ModelError


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
        with models.load(read_only=False) as m:
            host = m.get_host(kwargs['name'])
            if host.api_key_field.verify(parts[1], host.api_key):
                resp = jsonify({'Message': 'Incorrect API key for host'})
                resp.status_code = 401
                return resp
        return f(*args, **kwargs)
    return wrapper


@app.errorhandler(ModelError)
def _model_error_handler(error):
    return str(error) + '\n', error.status_code


@app.route('/api/v1/host/', methods=['GET'])
def host_list():
    with models.load() as m:
        return jsonify({'hosts': [x.name for x in m.hosts]})


@app.route('/api/v1/host/', methods=['POST'])
def host_create():
    if 'api_key' not in request.json:
        raise models.ModelError('Missing required field: api_key')
    request.json['enlisted'] = settings.AUTO_ENLIST_HOSTS
    with models.load(read_only=False) as m:
        m.hosts.create(request.json)
    resp = jsonify({})
    resp.status_code = 201
    resp.headers['Location'] = '/api/v1/host/%s/' % request.json['name']
    return resp


@app.route('/api/v1/host/<string:name>/', methods=['PATCH'])
@host_authenticated
def host_update(name):
    if 'enlisted' in request.json:
        raise ModelError('"enlisted" field cannot be updated via API')

    with models.load(read_only=False) as m:
        m.get_host(name).update(request.json)
    return jsonify({})


@app.route('/api/v1/host/<string:name>/', methods=['DELETE'])
@host_authenticated
def host_delete(name):
    with models.load(read_only=False) as m:
        m.get_host(name).delete()
    return jsonify({})


@app.route('/api/v1/host/<string:name>/', methods=['GET'])
def host_get(name):
    with models.load() as m:
        h = m.get_host(name)
        withcontainers = request.args.get('with_containers') is not None
        if not withcontainers and 'containers' in h.data:
            del h.data['containers']
        if 'api_key' in h.data:
            del h.data['api_key']
        return jsonify(h.data)


@app.route('/api/v1/host/<string:name>/container/', methods=['GET'])
def host_container_list(name):
    with models.load() as m:
        h = m.get_host(name)
        return jsonify({'containers': [x.name for x in h.containers]})


@app.route('/api/v1/host/<string:name>/container/<string:c>/', methods=['GET'])
def host_container_get(name, c):
    with models.load() as m:
        h = m.get_host(name)
        c = h.get_container(c)
        return jsonify(c.data)


@app.route('/api/v1/host/<string:name>/container/<string:c>/',
           methods=['PATCH'])
@host_authenticated
def host_container_update(name, c):
    with models.load(read_only=False) as m:
        h = m.get_host(name)
        h.get_container(c).update(request.json)
    return jsonify({})
