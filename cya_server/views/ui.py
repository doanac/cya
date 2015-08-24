from flask import (
    g, flash, redirect, render_template, request, session, url_for
)
from flask.ext.openid import OpenID

from cya_server import app, models, settings

oid = OpenID(app, settings.OPENID_STORE, safe_roots=[])


@app.before_request
def lookup_current_user():
    g.user = None
    if 'openid' in session:
        openid = session['openid']
        with models.load(read_only=True) as m:
            g.user = m.get_user_by_openid(openid)


@app.route('/login', methods=['GET', 'POST'])
@oid.loginhandler
def login():
    if g.user is not None:
        return redirect(oid.get_next_url())
    if request.method == 'POST':
        openid = request.form.get('openid')
        if openid:
            return oid.try_login(openid, ask_for=['email', 'nickname'])
    return render_template('login.html', next=oid.get_next_url(),
                           error=oid.fetch_error())


@oid.after_login
def create_or_login(resp):
    session['openid'] = resp.identity_url
    with models.load(read_only=True) as m:
        user = m.get_user_by_openid(resp.identity_url)
        if user is not None:
            flash('Successfully signed in')
            g.user = user
            return redirect(oid.get_next_url())
    return redirect(url_for('create_user', next=oid.get_next_url(),
                            name=resp.nickname, email=resp.email))


@app.route('/create-user', methods=['GET', 'POST'])
def create_user():
    if g.user is not None or 'openid' not in session:
        return redirect(url_for('index'))
    with models.load(read_only=False) as m:
        approved = settings.AUTO_APPROVE_USER
        if len(m.users) == 0:
            approved = True
        m.users.create({
            'email': request.values['email'],
            'nickname': request.values['name'],
            'openid': session['openid'],
            'approved': approved,
        })
    flash('Profile successfully created')
    return redirect(oid.get_next_url())


@app.route('/logout')
def logout():
    session.pop('openid', None)
    flash('You were signed out')
    return redirect(oid.get_next_url())


@app.route('/')
def index():
    with models.load(read_only=True) as m:
        hosts = m.hosts
    return render_template('index.html', hosts=hosts)


@app.route('/settings/')
def settings():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    return render_template('settings.html')


@app.route('/host/<string:name>/')
def host(name):
    with models.load(read_only=True) as m:
        h = m.get_host(name)
    return render_template('host.html', host=h)