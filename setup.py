#! /usr/bin/env python
from setuptools import setup

install_requires = [
    'PyYAML',
]

tests_require = install_requires + [
    'mock',
    'nose',
    'coverage',
]

setup(
    name='salmon',
    version='1.0.0',
    description='systemd nspawn container tool',
    author='Alex Wood',
    author_email='awood@redhat.com',
    license='GPLv3',
    packages=[
        'salmon',
    ],
    entry_points={
        'console_scripts': [
            'salmon = salmon.main:main'
        ]
    },
    tests_require=tests_require,
    install_requires=install_requires,
    test_suite='nose.collector',
)
