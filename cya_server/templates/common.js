function do_submit(url, keyvals) {
  var form = document.createElement("form");
  form.setAttribute("method", "post");
  form.setAttribute("action", url);

  for(var key in keyvals){
    var hiddenField = document.createElement("input");
    hiddenField.setAttribute("type", "hidden");
    hiddenField.setAttribute("name", key);
    hiddenField.setAttribute("value", keyvals[key]);
    form.appendChild(hiddenField);
  }
  document.body.appendChild(form);
  form.submit();
}
function removecontainer(host, container) {
  var props = {host: host, name: container, url: location.href};
  do_submit("{{url_for('remove_container')}}", props);
}
function reCreateContainer(host, container) {
  var props = {host: host, name: container, url: location.href};
  do_submit("{{url_for('recreate_container')}}", props);
}
function containerState(host, container, keep_running) {
  var props = {host: host, name: container, url: location.href, keep_running: keep_running};
  do_submit("{{url_for('start_container')}}", props);
}
