#! /usr/bin/env python
from __future__ import absolute_import

import os
import unittest
import salmon.main as main
import logging
import argparse

logging.basicConfig(level=logging.DEBUG, format="%(levelname)5s [%(name)s:%(lineno)s] %(message)s")
logger = logging.getLogger('')
logger.setLevel(logging.INFO)


class BuildCommandTest(unittest.TestCase):
    def setUp(self):
        self.good_config = {
            'repos': {
                'rhel7_2': {
                    'url': 'http://download.eng.rdu2.redhat.com/released/RHEL-7/7.2/Server/x86_64/os/'
                }
            },
            'destination': '/var/lib/machines',
            'name': 'RHEL7_2-base',
            'packages': ['systemd', 'passwd', 'vim-minimal', 'redhat-release', 'yum']
        }
        self.dummy_parser = argparse.ArgumentParser()

    def test_validate_required_with_missing_sections(self):
        c = main.BuildCommand.get_instance(self.dummy_parser.add_subparsers())
        args = self.dummy_parser.parse_args(['build'])

        bad_config = {'repos': {}, 'destination': ''}
        with self.assertRaises(RuntimeError):
            c(args).validate_config(bad_config)

    def test_validate_required_with_missing_repos(self):
        c = main.BuildCommand.get_instance(self.dummy_parser.add_subparsers())
        args = self.dummy_parser.parse_args(['build'])

        bad_config = {'repos': {}, 'destination': '', 'name': '', 'packages': []}
        with self.assertRaisesRegexp(RuntimeError, 'No repos'):
            c(args).validate_config(bad_config)

    def test_validate_required_with_good_config(self):
        c = main.BuildCommand.get_instance(self.dummy_parser.add_subparsers())
        args = self.dummy_parser.parse_args(['build'])

        c(args).validate_config(self.good_config)

    def test_cli_overrides_config_destination(self):
        args = ['build', '--destination', os.getcwd()]
        s = main.Salmon(args)
        result_config = s.build.validate_config(self.good_config)
        self.assertEqual(os.getcwd(), result_config['destination'])


if __name__ == "__main__":
    unittest.main(module="salmon")
