from flask import render_template

from cya_server import app, models


@app.route('/')
def index():
    with models.load(read_only=True) as m:
        hosts = m.hosts
    return render_template('index.html', hosts=hosts)


@app.route('/<string:name>/')
def host(name):
    with models.load(read_only=True) as m:
        h = m.get_host(name)
    return render_template('host.html', host=h)
