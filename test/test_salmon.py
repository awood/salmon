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
                'centos_7_2': {
                    'url': 'http://example.com'
                }
            },
            'destination': '/var/lib/machines',
            'name': 'CentOS_7_2-base',
            'packages': ['systemd', 'passwd', 'vim-minimal', 'redhat-release', 'yum'],
            'subvolume': True,
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

    def test_cli_overrides_config_subvolume_to_true(self):
        args = ['build', '--subvolume']
        s = main.Salmon(args)
        self.good_config['subvolume'] = False
        result_config = s.build.validate_config(self.good_config)
        self.assertEqual(True, result_config['subvolume'])

    def test_cli_overrides_config_subvolume_to_false(self):
        args = ['build', '--no-subvolume']
        s = main.Salmon(args)
        result_config = s.build.validate_config(self.good_config)
        self.assertEqual(False, result_config['subvolume'])

    def test_subvolume_options_mutually_exclusive(self):
        args = ['build', '--no-subvolume', '--subvolume']
        with self.assertRaises(SystemExit):
            s = main.Salmon(args)


class DeleteCommandTest(unittest.TestCase):
    def setUp(self):
        self.no_subvolume_config = {
            'repos': {
                'centos_7_2': {
                    'url': 'http://example.com'
                }
            },
            'destination': '/var/lib/machines',
            'name': 'CentOS_7_2-base',
            'packages': ['systemd', 'passwd', 'vim-minimal', 'redhat-release', 'yum'],
            'subvolume': False,
        }
        self.dummy_parser = argparse.ArgumentParser()

    def test_command_fails_fast_on_nonsubvolumes(self):
        c = main.DeleteCommand.get_instance(self.dummy_parser.add_subparsers())
        args = self.dummy_parser.parse_args(['delete'])

        with self.assertRaisesRegexp(RuntimeError, 'only be used with containers that are subvolumes'):
            c(args).validate_config(self.no_subvolume_config)

if __name__ == "__main__":
    unittest.main(module="salmon")
