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
        return jsonify(h.data)
