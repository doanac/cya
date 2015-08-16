import contextlib
import fcntl
import json


@contextlib.contextmanager
def open_for_read(filename):
    f = open(filename, 'a+')
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        f.cya_size = f.tell()
        f.seek(0)
        yield f
    finally:
        f.close()


@contextlib.contextmanager
def open_for_write(filename, append=False):
    f = open(filename, 'a+')
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.cya_size = f.tell()
        if not append:
            f.seek(0)
            f.truncate()
        yield f
    finally:
        f.close()


def json_create(filename, data):
    with open_for_write(filename, append=False) as f:
        if f.cya_size > 0:
            raise OSError(17, 'File already exists: "%s"' % filename)
        json.dump(data, f, indent=2)


def json_get(filename, create=True):
    with open_for_read(filename) as f:
        if f.cya_size == 0:
            if create:
                return {}
            # We had a file that didn't exist or was zero bytes. We treat
            # both as a non-existant file in this API
            raise OSError(2, 'No such file: "%s"' % filename)
        return json.load(f)


@contextlib.contextmanager
def json_data(filename, create=True):
    with open_for_write(filename, append=True) as f:
        if f.cya_size == 0:
            if create:
                data = {}
            else:
                # We had a file that didn't exist or was zero bytes. We treat
                # both as a non-existant file in this API
                raise OSError(2, 'No such file: "%s"' % filename)
        else:
            f.seek(0)
            data = json.load(f)
        yield data
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)
