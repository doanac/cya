from flask import jsonify, request

from cya_server import app, models
from cya_server.dict_model import ModelError


@app.errorhandler(ModelError)
def _model_error_handler(error):
    return str(error) + '\n', error.status_code


@app.route('/api/v1/host/', methods=['GET'])
def host_list():
    with models.load() as m:
        return jsonify({'hosts': [x.name for x in m.hosts]})


@app.route('/api/v1/host/<string:name>/', methods=['GET'])
def host_get(name):
    with models.load() as m:
        h = m.get_host(name)
        if not request.args.get('with_containers') and 'containers' in h.data:
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
