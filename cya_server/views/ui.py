import time

from flask import (
    g, flash, redirect, render_template, request, Response, session, url_for
)
from flask.ext.openid import OpenID

from cya_server import app, settings
from cya_server.models import (
    client_version, container_requests, hosts, shared_storage, users)

oid = OpenID(app, settings.OPENID_STORE, safe_roots=[])


@app.before_request
def lookup_current_user():
    g.user = None
    if 'openid' in session:
        openid = session['openid']
        g.user = users.get_user_by_openid(openid)


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
    user = users.get_user_by_openid(resp.identity_url)
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
    approved = settings.AUTO_APPROVE_USER
    admin = False
    if users.count() == 0:
        approved = True
        admin = True
    users.create(request.values['email'], {
        'nickname': request.values['name'],
        'openid': session['openid'],
        'approved': approved,
        'admin': admin,
        'api_key': users.generate_api_key(),
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
    host_list = [hosts.get(x) for x in hosts.list()]
    for h in host_list:
        h.container_list = [h.containers.get(x) for x in h.containers.list()]
    requests = [container_requests.get(x) for x in container_requests.list()]
    return render_template('index.html', hosts=host_list, requests=requests)


@app.route('/settings/', methods=['POST', 'GET'])
def user_settings():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        names = request.form.getlist('script-name')
        scripts = request.form.getlist('script-content')
        data = {x[0]: {'content': x[1]} for x in zip(names, scripts)}
        u = users.get_user_by_openid(g.user.openid)
        defined = set([x for x in u.initscripts.list()])
        for remove in defined - set(names):
            u.initscripts.get(remove).delete()
        for add in set(names) - defined:
            u.initscripts.create(add, data[add])
        for update in set(names) & defined:
            u.initscripts.get(update).update(data[update])
        g.user = users.get(u.name)
        return redirect(url_for('user_settings'))

    u = [users.get(x) for x in users.list()]
    scripts = g.user.to_dict().get('initscripts', [])
    ss = [shared_storage.get(x) for x in shared_storage.list()]
    return render_template(
        'settings.html', settings=settings, users=u, user_scripts=scripts,
        shared_storage=ss)


@app.route('/shared_storage/', methods=['POST'])
def shared_storage_settings():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to change shared storage')
        return redirect(url_for('login'))

    name = request.form.get('volname')
    voltype = request.form.get('voltype')
    source = request.form.get('volsource')

    if name and voltype and source:
        shared_storage.create(name, {'type': voltype, 'source': source})
    else:
        flash('Name, Type, and Source are all required', category='Error')
    return redirect(url_for('user_settings'))


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

    with open(settings.LOCAL_SETTINGS, 'a') as f:
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

    for u in users.list():
        u = users.get(u)
        data = {'approved': False, 'admin': False}
        data['approved'] = request.form.get('approved-' + u.openid) == 'on'
        data['admin'] = request.form.get('admin-' + u.openid) == 'on'
        u.update(data)

    return redirect(url_for('user_settings'))


@app.route('/host/<string:name>/')
def host(name):
    host = hosts.get(name)
    host.container_list = [
        host.containers.get(x) for x in host.containers.list()]
    return render_template('host.html', host=host)


@app.route('/host/<string:host>/<string:container>')
def host_container(host, container):
    h = hosts.get(host)
    c = h.containers.get(container)
    s = [c.initscripts.get(x) for x in c.initscripts.list()]
    return render_template('container.html', host=h, container=c, scripts=s)


@app.route('/host/<string:host>/<string:container>/log/<string:logname>')
def host_container_log(host, container, logname):
    if g.user is None or 'openid' not in session:
        flash('You must be logged in to view container logs')
        return redirect(url_for('login'))
    try:
        log = hosts.get(host).containers.get(container).get_log(logname)
        return Response(log, 200, mimetype='text/plain')
    except FileNotFoundError:
        return ('This container has no %s log' % logname, 404)


@app.route('/create_container/', methods=['POST', 'GET'])
def ui_create_container():
    if g.user is None or 'openid' not in session:
        flash('You must be logged in to create a container')
        return redirect(url_for('login'))

    if request.method == 'POST':
        template, release = request.form['container-type'].split(':')
        data = {
            'requested_by': g.user.nickname,
            'state': 'QUEUED',
            'date_requested': int(time.time()),
            'template': template,
            'release': release,
            'max_memory': int(request.form['max-memory']) * 1000000000,
            'containermounts': [],
        }
        init_script = request.form['init-script'].replace('\r', '')
        if init_script:
            data['initscripts'] = [{'name': 'init', 'content': init_script}]

        print("ANDY", data)
        for x in request.form.keys():
            if x[:3] == 'ss_':
                directory = request.form[x]
                if directory:
                    ss = shared_storage.get(x[3:])
                    data['containermounts'].append({
                        'name': ss.name,
                        'type': ss.type,
                        'source': ss.source,
                        'directory': directory,
                    })
        container_requests.create(request.form['name'], data)
        flash('Container requested')
        return redirect(url_for('index'))

    ss = [shared_storage.get(x) for x in shared_storage.list()]
    scripts = g.user.to_dict()['initscripts']
    return render_template('create_container.html',
                           common_init_scripts=settings.INIT_SCRIPTS,
                           user_scripts=scripts, shared_storage=ss,
                           container_types=settings.CONTAINER_TYPES)


@app.route('/recreate_container/', methods=['POST'])
def recreate_container():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to re-create a container')
        return redirect(url_for('login'))

    host = hosts.get(request.form['host'])
    container = host.containers.get(request.form['name'])
    container.update({'re_create': True})
    flash('Container re-created: %s' % request.form['name'])
    return redirect(request.form['url'])


@app.route('/start_container/', methods=['POST'])
def start_container():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to update container state')
        return redirect(url_for('login'))

    host = hosts.get(request.form['host'])
    container = host.containers.get(request.form['name'])
    keep_running = request.form['keep_running'].lower() in (1, 'true')
    if keep_running:
        state = 'STARTING'
    else:
        state = 'STOPPING'
    container.update({'keep_running': keep_running, 'state': state})
    flash('Container requeste queued')
    return redirect(request.form['url'])


@app.route('/remove_container/', methods=['POST'])
def remove_container():
    if g.user is None or 'openid' not in session:
        return redirect(url_for('login'))
    if not g.user.admin:
        flash('you must be an admin to create a container')
        return redirect(url_for('login'))

    host = hosts.get(request.form['host'])
    container = host.containers.get(request.form['name'])
    container.delete()
    flash('Deleted container: %s' % request.form['name'])
    return redirect(request.form['url'])


@app.route('/cya_client.py')
def client_py():
    with open(settings.CLIENT_SCRIPT, 'rb') as f:
        return f.read()


@app.route('/client_install.sh')
def install_script():
    base = url_for('index', _external=True)
    if base.endswith('/'):
        base = base[:-1]
    client = url_for('client_py', _external=True)
    return render_template('client_install.sh', base_url=base,
                           client_url=client, version=client_version())
