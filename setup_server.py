#!/usr/bin/env python3

from setuptools import setup, find_packages


setup(
    name='cya_server',

    version='1.0.0',

    description='The Flask web server component of the CYA project',
    long_description='TODO',
    url='https://github.com/pypa/sampleproject',
    author='Andy Doan',
    author_email='doanac@beadoan.com',
    license='GPL',
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3',
    ],
    keywords='lxc containers',
    packages=find_packages(exclude=['cya_client', 'tests*']),
    install_requires=['Flask', 'flask-openid'],

    entry_points={
        'console_scripts': [
            'cya_server=cya_server.manage:main',
        ],
    },
)
