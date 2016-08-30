#! /usr/bin/env python
from __future__ import absolute_import

import os
import unittest
import salmon.main as main
import logging
import argparse

import mock

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
            main.Salmon(args)


class DeleteCommandTest(unittest.TestCase):
    def setUp(self):
        self.dummy_parser = argparse.ArgumentParser()
        self.cmd_class = main.DeleteCommand.get_instance(self.dummy_parser.add_subparsers())

    def test_command_fails_fast_on_nonsubvolumes(self):
        no_subvolume_config = {
            'repos': {
                'centos_7_2': {
                    'url': 'http://example.com'
                }
            },
            'destination': '/var/lib/machines',
            'name': 'CentOS_7_2-base',
            'packages': [],
            'subvolume': False,
        }
        args = self.dummy_parser.parse_args(['delete'])

        with self.assertRaisesRegexp(RuntimeError, 'only be used with .* subvolumes'):
            self.cmd_class(args).validate_config(no_subvolume_config)

    @mock.patch('os.walk', autospec=True)
    @mock.patch('os.stat', autospec=True)
    @mock.patch('subprocess.check_output', autospec=True)
    def test_do_command(self, mock_subprocess, mock_stat, mock_walk):
        dummy_config = {
            'destination': '/does/not',
            'name': 'exist',
        }

        root = '/does/not/exist%s'
        # We are asking os.walk to go depth-first
        mock_walk.return_value = [
            (root % '/top_btrfs/child_btrfs', [], []),
            (root % '/top_btrfs/other', [], []),
            (root % '/top_btrfs', ['child_btrfs', 'other'], []),
            (root % '', ['top_btrfs'], []),
        ]

        def get_ino(*args):
            d = args[0]
            if 'btrfs' in os.path.basename(d):
                return mock.NonCallableMock(st_ino=256)
            return mock.NonCallableMock(st_ino=0)

        mock_stat.side_effect = get_ino
        mock_subprocess.return_value = "OK"

        args = self.dummy_parser.parse_args(['delete'])
        cmd_instance = self.cmd_class(args)
        cmd_instance.config = dummy_config
        cmd_instance.do_command()

        expected_calls = []
        for sub_dir in ['/top_btrfs/child_btrfs', '/top_btrfs', '']:
            expected_calls.append(mock.call(['btrfs', 'subvolume', 'delete', root % sub_dir]))
        self.assertEqual(expected_calls, mock_subprocess.mock_calls)

if __name__ == "__main__":
    unittest.main(module="salmon")
