#!/usr/bin/env python3
import argparse

from cya_server import app


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

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
