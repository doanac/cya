#!/usr/bin/env python3
import argparse

from cya_server import app, models


def _create_container(args):
    with models.load(read_only=False) as m:
        m.create_container(args.name, args.template, args.release,
                           args.max_megs, args.init_script)


def _run(args):
    app.run(args.host, args.port)


def main():
    parser = argparse.ArgumentParser(
        description='Manage cya application')

    sub = parser.add_subparsers(title='Commands', metavar='')
    p = sub.add_parser('runserver', help='Run webserver')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('-p', '--port', type=int, default=8000)
    p.set_defaults(func=_run)

    p = sub.add_parser('create-container', help='Create a container')
    p.add_argument('-n', '--name', required=True)
    p.add_argument('-t', '--template', required=True)
    p.add_argument('-r', '--release', required=True)
    p.add_argument('-m', '--max-megs', type=int, default=2000)
    p.add_argument('--init-script', default='')
    p.set_defaults(func=_create_container)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
