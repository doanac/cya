from flask import jsonify

from cya_server import app, models
from cya_server.dict_model import ModelError


@app.errorhandler(ModelError)
def _model_error_handler(error):
    return str(error) + '\n', error.status_code


@app.route('/api/v1/host/', methods=['GET'])
def host_list():
    with models.load() as m:
        return jsonify({'hosts': [x.name for x in m.hosts]})
