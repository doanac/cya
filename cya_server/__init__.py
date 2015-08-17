import flask

app = flask.Flask(__name__)
app.config.from_object('cya_server.settings')


import cya_server.views.api  # NOQA
