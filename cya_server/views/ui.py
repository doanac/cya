import os
import subprocess
import tempfile

from flask import (
    g, flash, redirect, render_template, request, session, url_for
)
from flask.ext.openid import OpenID

from cya_server import app, concurrently, models, settings

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
        admin = False
        if len(m.users) == 0:
            approved = True
            admin = True
        m.users.create({
            'email': request.values['email'],
            'nickname': request.values['name'],
            'openid': session['openid'],
            'approved': approved,
            'admin': admin,
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


@app.route('/settings/', methods=['POST', 'GET'])
def user_settings():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        names = request.form.getlist('script-name')
        scripts = request.form.getlist('script-content')
        data = [{'name': x[0], 'content': x[1]} for x in zip(names, scripts)]
        with models.load(read_only=False) as m:
            u = m.get_user_by_openid(g.user.openid)
            u.init_scripts.replace(data)
            g.user = u
            return redirect(url_for('user_settings'))

    with models.load(read_only=True) as m:
        return render_template(
            'settings.html', settings=settings, users=m.users)


@app.route('/global_settings/', methods=['POST'])
def global_settings():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))

    updates = {}
    fields = ['DEBUG', 'AUTO_ENLIST_HOSTS', 'AUTO_APPROVE_USER']
    for f in fields:
        v = request.form.get(f, False)
        if v == 'on':
            v = True
        if getattr(settings, f) != v:
            updates[f] = v

    lines = []
    with concurrently.open_for_write(settings.LOCAL_SETTINGS, True) as f:
        f.seek(0)
        for line in f:
            if line.strip() not in updates.keys():
                lines.append(line)
        f.seek(0)
        f.truncate()
        for line in lines:
            f.write(line)
        f.write('\n')
        for key, val in updates.items():
            f.write('%s = %s\n' % (key, val))
            setattr(settings, key, val)

    return redirect(url_for('user_settings'))


@app.route('/user_admin/', methods=['POST'])
def user_admin():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to try and edit users')
        return redirect(url_for('login'))

    with models.load(read_only=False) as m:
        for u in m.users:
            data = {'approved': False, 'admin': False}
            data['approved'] = request.form.get('approved-' + u.openid) == 'on'
            data['admin'] = request.form.get('admin-' + u.openid) == 'on'
            u.update(data)

    return redirect(url_for('user_settings'))


@app.route('/host/<string:name>/')
def host(name):
    with models.load(read_only=True) as m:
        h = m.get_host(name)
    return render_template('host.html', host=h)


@app.route('/create_container/', methods=['POST', 'GET'])
def create_container():
    if g.user is None or 'openid' not in session:
        flash('You must be logged in to create a container')
        return redirect(url_for('login'))

    if request.method == 'POST':
        template, release = request.form['container-type'].split(':')
        max_mem = int(request.form['max-memory']) * 1000000000
        init_script = request.form['init-script'].replace('\r', '')
        with models.load(read_only=False) as m:
            m.create_container(
                request.form['name'], template, release, max_mem, init_script)
        flash('Container requested')
        return redirect(url_for('index'))

    return render_template('create_container.html',
                           common_init_scripts=settings.INIT_SCRIPTS,
                           container_types=settings.CONTAINER_TYPES)


@app.route('/recreate_container/', methods=['POST'])
def recreate_container():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to re-create a container')
        return redirect(url_for('login'))

    with models.load(read_only=False) as m:
        host = m.get_host(request.form['host'])
        container = host.get_container(request.form['name'])
        container.update({'re_create': True})
        flash('Container re-created: %s' % request.form['name'])
    return redirect(url_for('host', name=request.form['host']))


@app.route('/remove_container/', methods=['POST'])
def remove_container():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to create a container')
        return redirect(url_for('login'))

    with models.load(read_only=False) as m:
        host = m.get_host(request.form['host'])
        container = host.get_container(request.form['name'])
        container.delete()
        flash('Deleted container: %s' % request.form['name'])
    return redirect(url_for('host', name=request.form['host']))


@app.route('/git_bundle')
def git_bundle():
    here = os.path.dirname(__file__)
    with tempfile.NamedTemporaryFile() as f:
        subprocess.check_call(
            ['git', 'bundle', 'create', f.name, '--all'], cwd=here)
        with open(f.name, 'rb') as f:
            return f.read()


@app.route('/client_install.sh')
def install_script():
    base = url_for('index', _external=True)
    if base.endswith('/'):
        base = base[:-1]
    bundle = url_for('git_bundle', _external=True)
    return render_template(
        'client_install.sh', base_url=base, bundle_url=bundle)
