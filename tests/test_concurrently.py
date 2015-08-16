import os
import tempfile
import threading
import time
import unittest

from cya_server import concurrently


def reader_thread(data):
    with concurrently.open_for_read(data['filename']) as f:
        data['event'].wait()
        data['read'] = f.read()


def writer_thread(data):
    with concurrently.open_for_write(data['filename'], append=True) as f:
        # first wait is to wait to make sure we get blocked by readers
        # the second is to wait to test we block a reader
        data['event'].wait()
        data['event'].wait()
        f.write('\n4')


class TestConcurrently(unittest.TestCase):
    def setUp(self):
        fd, self.tmpfile = tempfile.mkstemp()
        self.addCleanup(os.unlink, self.tmpfile)

        self.contents = '1\n2\n3'
        os.write(fd, self.contents.encode())
        os.close(fd)

    def test_simple_read(self):
        with concurrently.open_for_read(self.tmpfile) as f:
            self.assertEqual(self.contents, f.read())

    def test_concurrent_read_write(self):
        # we'll have 2 readers that won't block each other,
        # then a writer that will block all
        # and a reader blocked by the writer
        d1 = {
            'event': threading.Event(),
            'filename': self.tmpfile,
            'name': 'd1',
        }
        d2 = {
            'event': threading.Event(),
            'filename': self.tmpfile,
            'name': 'd2',
        }
        d3 = {
            'event': threading.Event(),
            'filename': self.tmpfile,
        }
        d4 = {
            'event': threading.Event(),
            'filename': self.tmpfile,
            'name': 'd4',
        }

        t1 = threading.Thread(target=reader_thread, args=(d1,))
        t1.start()
        t2 = threading.Thread(target=reader_thread, args=(d2,))
        t2.start()
        time.sleep(.1)  # try and make sure writer thread doesn't lock first
        t3 = threading.Thread(target=writer_thread, args=(d3,))
        t3.start()

        # ensures both t1 and t2 have access to the file at the same time
        d3['event'].set()
        d2['event'].set()
        d1['event'].set()
        t1.join()
        t2.join()
        self.assertEqual(self.contents, d1['read'])
        self.assertEqual(self.contents, d2['read'])

        t4 = threading.Thread(target=reader_thread, args=(d4,))
        t4.start()
        # ensure t4 was blocked by t3
        d4['event'].set()
        d3['event'].set()
        t3.join()
        t4.join()
        self.assertEqual(self.contents + '\n4', d4['read'])

    def test_create_json(self):
        '''we can create a json file'''

        # we fail if it already exists
        with self.assertRaises(OSError):
            concurrently.json_create(self.tmpfile, {})
        os.unlink(self.tmpfile)

        # we can create
        concurrently.json_create(self.tmpfile, {})

    def test_json_get(self):
        # we fail if file doesn't exist
        os.unlink(self.tmpfile)
        with self.assertRaises(OSError):
            concurrently.json_get(self.tmpfile, False)

        # we can also pass if requested
        os.unlink(self.tmpfile)
        self.assertEqual({}, concurrently.json_get(self.tmpfile, True))

        # we can read a good file
        concurrently.json_create(self.tmpfile, {'key': 'val'})
        data = concurrently.json_get(self.tmpfile)
        self.assertEqual('val', data['key'])

    def test_json_data(self):
        os.unlink(self.tmpfile)
        concurrently.json_create(self.tmpfile, {'key': 'val'})

        with concurrently.json_data(self.tmpfile) as d:
            self.assertEqual(d['key'], 'val')
            d['key'] = 'updated'
        self.assertEqual('updated', concurrently.json_get(self.tmpfile)['key'])
