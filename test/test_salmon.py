#! /usr/bin/env python
from __future__ import absolute_import

import os
import unittest
import salmon.main as main
import logging
import argparse
import tempfile
import mock
import dnf
import shutil

logging.basicConfig(level=logging.DEBUG, format="%(levelname)5s [%(name)s:%(lineno)s] %(message)s")
logger = logging.getLogger('')
logger.setLevel(logging.INFO)


class BuildCommandTest(unittest.TestCase):
    def setUp(self):
        self.good_config = {
            'repos': {
                'centos_7_2': {
                    'baseurl': 'http://example.com',
                    'inject': False,
                },
                'external_repo_1': {
                    'baseurl': 'http://example.com',
                    'inject': True,
                },
                'external_repo_2': {
                    'baseurl': 'http://example.com',
                    'inject': True,
                },
            },
            'destination': '/var/lib/machines',
            'name': 'CentOS_7_2-base',
            'packages': ['systemd', 'passwd', 'vim-minimal', 'redhat-release', 'yum'],
            'subvolume': True,
            'disable_securetty': True,
        }
        self.dummy_parser = argparse.ArgumentParser()
        self.cmd_class = main.BuildCommand.get_instance(self.dummy_parser.add_subparsers())
        self.dnf_temp_cache = tempfile.mkdtemp(prefix="salmon_unit_test_dnf_cache_")

    def tearDown(self):
        shutil.rmtree(self.dnf_temp_cache)

    def test_validate_required_with_missing_sections(self):
        args = self.dummy_parser.parse_args(['build'])

        bad_config = {'repos': {}, 'destination': ''}
        with self.assertRaises(RuntimeError):
            self.cmd_class(args).validate_config(bad_config)

    def test_validate_required_with_missing_repos(self):
        args = self.dummy_parser.parse_args(['build'])

        bad_config = {'repos': {}, 'destination': '', 'name': '', 'packages': []}
        with self.assertRaisesRegexp(RuntimeError, 'No repos'):
            self.cmd_class(args).validate_config(bad_config)

    def test_validate_required_with_good_config(self):
        args = self.dummy_parser.parse_args(['build'])
        self.cmd_class(args).validate_config(self.good_config)

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

    def test_post_dnf_run(self):
        args = self.dummy_parser.parse_args(['build'])
        cmd_instance = self.cmd_class(args)
        cmd_instance.dnf_temp_cache = self.dnf_temp_cache

        with mock.patch.object(dnf.repo.Repo, 'load'), mock.patch.object(dnf.Base, 'fill_sack'):
            dnf_base = cmd_instance.build_dnf(self.good_config)

        m = mock.mock_open()

        with mock.patch('__builtin__.open', m, create=True):
            cmd_instance.container_dir = '/does/not/exist'
            cmd_instance.post_dnf_run(dnf_base, self.good_config)
            m.assert_called_with('/does/not/exist/etc/yum.repos.d/salmon.repo', 'w')

    def test_post_dnf_run_no_inject(self):
        args = self.dummy_parser.parse_args(['build'])
        cmd_instance = self.cmd_class(args)
        cmd_instance.dnf_temp_cache = self.dnf_temp_cache

        del(self.good_config['repos']['external_repo_1'])
        del(self.good_config['repos']['external_repo_2'])

        with mock.patch.object(dnf.repo.Repo, 'load'), mock.patch.object(dnf.Base, 'fill_sack'):
            dnf_base = cmd_instance.build_dnf(self.good_config)

        m = mock.mock_open()

        with mock.patch('__builtin__.open', m, create=True):
            cmd_instance.container_dir = '/does/not/exist'
            cmd_instance.post_dnf_run(dnf_base, self.good_config)
            self.assertEqual([], m.mock_calls)

    def test_creates_subvolume(self):
        args = self.dummy_parser.parse_args(['build'])
        cmd_instance = self.cmd_class(args)
        cmd_instance.config = self.good_config

        # stub out all the subsequent methods that actually do work
        with mock.patch('subprocess.check_output') as mock_subprocess, \
            mock.patch.object(main.BuildCommand, 'build_dnf'), \
            mock.patch.object(main.BuildCommand, 'run_dnf'), \
            mock.patch.object(main.BuildCommand, 'post_dnf_run'), \
            mock.patch.object(main.BuildCommand, 'remove_securetty'), \
            mock.patch.object(main.BuildCommand, 'fix_context'):

            mock_subprocess.return_value = "OK"
            cmd_instance.do_command()

        subvolume_name = os.path.join(self.good_config['destination'], self.good_config['name'])
        expected_calls = [mock.call(['btrfs', 'subvolume', 'create', subvolume_name])]
        self.assertEqual(expected_calls, mock_subprocess.mock_calls)

    def test_creates_directory(self):
        args = self.dummy_parser.parse_args(['build'])
        cmd_instance = self.cmd_class(args)
        self.good_config['subvolume'] = False
        cmd_instance.config = self.good_config

        # tempfile.mkdtemp uses os.mkdir under the covers so we need to stub out
        # salmon's attempt to clean up the temp directory it creates.
        with mock.patch('os.mkdir') as mock_mkdir, \
            mock.patch.object(main.BuildCommand, 'build_dnf'), \
            mock.patch.object(main.BuildCommand, 'run_dnf'), \
            mock.patch.object(main.BuildCommand, 'post_dnf_run'), \
            mock.patch.object(main.BuildCommand, 'fix_context'), \
            mock.patch.object(main.BuildCommand, 'remove_securetty'), \
            mock.patch('shutil.rmtree'):
            cmd_instance.do_command()

        directory_name = os.path.join(self.good_config['destination'], self.good_config['name'])
        mock_mkdir.assert_called_with(directory_name)


class DeleteCommandTest(unittest.TestCase):
    def setUp(self):
        self.dummy_parser = argparse.ArgumentParser()
        self.cmd_class = main.DeleteCommand.get_instance(self.dummy_parser.add_subparsers())

    def test_command_fails_fast_on_nonsubvolumes(self):
        no_subvolume_config = {
            'repos': {
                'centos_7_2': {
                    'baseurl': 'http://example.com'
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
