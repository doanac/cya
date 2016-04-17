function removeContainer(host, container) {
  var form = document.createElement("form");
  form.setAttribute("method", "post");
  form.setAttribute("action", "{{url_for('remove_container')}}");
  var hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "host");
  hiddenField.setAttribute("value", host);
  form.appendChild(hiddenField);

  hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "name");
  hiddenField.setAttribute("value", container);
  form.appendChild(hiddenField);
  document.body.appendChild(form);
  form.submit();
}
function reCreateContainer(host, container) {
  var form = document.createElement("form");
  form.setAttribute("method", "post");
  form.setAttribute("action", "{{url_for('recreate_container')}}");
  var hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "host");
  hiddenField.setAttribute("value", host);
  form.appendChild(hiddenField);

  hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "name");
  hiddenField.setAttribute("value", container);
  form.appendChild(hiddenField);
  document.body.appendChild(form);
  form.submit();
}
function containerState(host, container, keep_running) {
  var form = document.createElement("form");
  form.setAttribute("method", "post");
  form.setAttribute("action", "{{url_for('start_container')}}");
  var hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "host");
  hiddenField.setAttribute("value", host);
  form.appendChild(hiddenField);

  hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "name");
  hiddenField.setAttribute("value", container);
  form.appendChild(hiddenField);

  hiddenField = document.createElement("input");
  hiddenField.setAttribute("type", "hidden");
  hiddenField.setAttribute("name", "keep_running");
  hiddenField.setAttribute("value", keep_running);
  form.appendChild(hiddenField);
  document.body.appendChild(form);
  form.submit();
}
