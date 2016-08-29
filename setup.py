#! /usr/bin/env python
from setuptools import setup

install_requires = [
    'PyYAML',
]

tests_require = install_requires + [
    'mock',
]

setup(
    name='salmon',
    version='1.0',
    description='systemd nspawn container tool',
    author='Alex Wood',
    license='GPLv3',
    packages=[
        'salmon',
    ],
    scripts=[
        'salmon.py',
    ],
    tests_require=tests_require,
    install_requires=install_requires,
)
