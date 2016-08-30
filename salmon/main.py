from __future__ import absolute_import

import os
import abc
import argparse
import sys
import logging
import yaml
import copy
import shutil
import tempfile
import subprocess

import dnf
import dnf.repo
import dnf.callback
import dnf.yum.config

log = logging.getLogger(__name__)


# Thanks to https://github.com/timlau/dnf-apiex/
class Progress(dnf.callback.DownloadProgress):
    def __init__(self):
        super(Progress, self).__init__()
        self.total_files = 0
        self.total_size = 0.0
        self.download_files = 0
        self.download_size = 0.0
        self.dnl = {}
        self.last_pct = 0

    def start(self, total_files, total_size):
        print("Downloading: %d files, %d bytes" % (total_files, total_size))
        self.total_files = total_files
        self.total_size = total_size
        self.download_files = 0
        self.download_size = 0.0

    def end(self, payload, status, msg):
        if not status:
            # payload download complete
            self.download_files += 1
            self.update()
        else:
            # dnl end with errors
            self.update()

    def progress(self, payload, done):
        pload = str(payload)
        if pload not in self.dnl:
            self.dnl[pload] = 0.0
            log.debug("Downloading: %s " % str(payload))
        else:
            self.dnl[pload] = done
            pct = self.get_total()
            if pct > self.last_pct:
                self.last_pct = pct
                self.update()

    def get_total(self):
        """ Get the total downloaded percentage"""
        tot = 0.0
        for value in self.dnl.values():
            tot += value
        pct = int((tot / float(self.total_size)) * 100)
        return pct

    def update(self):
        """ Output the current progress"""
        sys.stdout.write("Progress: %02d%% (%d/%d)\r" % (self.last_pct, self.download_files, self.total_files))


class Salmon(object):
    def __init__(self, argv=None):
        parser = argparse.ArgumentParser(description="nspawn container tools")
        subparsers = parser.add_subparsers(
            title="subcommands",
            description="valid subcommands",
            help='subcommand help',
            dest='subcommand'
        )

        # Create an instance of each subcommand with a populated subparser
        # The indirection here is primarily aimed at ensuring that the subcommand
        # is populated with the argparser.Namespace object before attempting to
        # run.  Without the factory pattern, we would need manually inject the
        # args object into each subcommand instance.  Although this pattern is
        # esoteric, I deemed it better than setting attributes on classes externally
        # or dealing with bugs where the args object was not injected properly.
        self.build_class = BuildCommand.get_instance(subparsers)
        self.delete_class = DeleteCommand.get_instance(subparsers)

        self.args = parser.parse_args(argv)

        # Populate the factory generated subcommand classes with the results
        # from the argument parser.  These attributes need to match the name
        # the subparser registers.
        self.build = self.build_class(self.args)
        self.delete = self.delete_class(self.args)

    def run(self):
        # Get the attribute containing the factory generated class and invoke run()
        getattr(self, self.args.subcommand).run()


class BaseCommand(object):
    """BaseCommand inheritors should also implement a classmethod get_instance that is
    responsible for building the subparser used to parse the subcommand's arguments."""
    __metaclass__ = abc.ABCMeta

    def __init__(self, args):
        self.args = args
        if hasattr(self.args, 'verbose') and self.args.verbose:
            log.setLevel(logging.DEBUG)

    def run(self):
        raw_config = yaml.load(self.args.manifest)
        log.info("Config is %s" % raw_config)
        self.config = self.validate_config(raw_config)
        self.do_command()

    @abc.abstractmethod
    def do_command(self):
        pass

    def validate_config(self, raw_config):
        config = copy.deepcopy(raw_config)
        required_top_options = {'name', 'destination', 'repos', 'packages', 'subvolume'}
        top_options = set(config.keys())

        errors = []
        errors.extend([
            "Missing required config section %s" % s for s in required_top_options.difference(top_options)
        ])

        if len(config['repos']) == 0:
            errors.append("No repos are defined")

        self.validate_subcommand_config(self.args, config, errors)

        if errors:
            error_string = "\n".join(errors)
            raise RuntimeError(error_string)

        return config

    @abc.abstractmethod
    def validate_subcommand_config(self, args, config, errors):
        pass


class DeleteCommand(BaseCommand):
    @classmethod
    def get_instance(cls, subparsers):
        parser = subparsers.add_parser('delete', help='delete a container (must be a subvolume)')
        parser.add_argument(
            "manifest",
            nargs="?",
            type=argparse.FileType('r'),
            default=sys.stdin,
            help="Manifest file"
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Show extra output"
        )
        return cls

    def __init__(self, args):
        super(DeleteCommand, self).__init__(args)

    def validate_subcommand_config(self, args, config, errors):
        if not config['subvolume']:
            errors.append("'delete' can only be used with containers that are subvolumes")
        return errors

    def do_command(self):
        """Systemd itself checks during init, whether the device backing /var/lib/machines is btrfs, and if
        it is then it makes a subvolume for it.  This behavior results in two btrfs subvolumes: one for our
        container and one within our container for its /var/lib/machines.  As a result, we need to delete
        two btrfs subvolumes with this command.  We'll do a depth first search through the tree looking for
        directories with an inode number of 256 (which identifies a btrfs subvolume) and then delete each
        volume in the order we found it.

        See also http://stackoverflow.com/a/32865333
        """
        container_root = os.path.join(self.config['destination'], self.config['name'])

        btrfs_dirs = []
        for root, dirs, files in os.walk(container_root, topdown=False):
            btrfs_dirs.extend(
                [os.path.join(root, d) for d in dirs if os.stat(os.path.join(root, d)).st_ino == 256]
            )
        btrfs_dirs.append(container_root)

        for d in btrfs_dirs:
            cmd = ['btrfs', 'subvolume', 'delete', d]
            output = subprocess.check_output(cmd)
            log.info('`%s` returned "%s"' % (" ".join(cmd), output))


class BuildCommand(BaseCommand):
    @classmethod
    def get_instance(cls, subparsers):
        parser = subparsers.add_parser('build', help='build an nspawn container')
        parser.add_argument(
            "manifest",
            nargs="?",
            type=argparse.FileType('r'),
            default=sys.stdin,
            help="Manifest file"
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Show extra output"
        )
        parser.add_argument(
            "--destination",
            default=None,
            help="Destination directory"
        )

        subvolume_group = parser.add_mutually_exclusive_group()
        subvolume_group.add_argument(
            "--subvolume",
            action="store_true",
            dest="subvolume",
            default=None,
            help="Use a btrfs subvolume for this container"
        )
        subvolume_group.add_argument(
            "--no-subvolume",
            action="store_false",
            dest="subvolume",
            default=None,
            help="Do not use a btrfs subvolume for this container"
        )
        return cls

    def __init__(self, args):
        super(BuildCommand, self).__init__(args)

    def validate_subcommand_config(self, args, config, errors):
        if args.destination:
            path = os.path.normpath(os.path.expanduser(args.destination))
            if os.access(path, os.W_OK):
                config['destination'] = path
                log.info("Using destination '%s' from the command line" % args.destination)
            else:
                errors.append("Cannot write to directory %s" % path)

        if args.subvolume is not None:
            config['subvolume'] = args.subvolume
            log.info("Using subvolume '%s' from the command line" % args.subvolume)

        return errors

    def do_command(self):
        self.dnf_temp_cache = tempfile.mkdtemp(prefix="salmon_dnf_cache_")
        self.container_dir = os.path.join(self.config['destination'], self.config['name'])

        if self.config['subvolume']:
            # Not a huge fan of shelling out, but didn't see any mature Python Btrfs bindings
            cmd = ['btrfs', 'subvolume', 'create', self.container_dir]

            output = subprocess.check_output(cmd)
            log.info("%s returned %s" % (" ".join(cmd), output))
        else:
            os.mkdir(self.container_dir)

        try:
            dnf_base = self.build_dnf(self.config)
            self.run_dnf(dnf_base, self.config)
            self.post_dnf_run(dnf_base, self.config)
        finally:
            shutil.rmtree(self.dnf_temp_cache)

        return 0

    def build_dnf(self, config):
        dnf_base = dnf.Base()

        for repo in dnf_base.repos.all():
            repo.disable()

        for repo_id, repo_opts in config['repos'].items():
            repo = dnf.repo.Repo(repo_id, self.dnf_temp_cache)
            repo.enable()
            for opt, val in repo_opts.items():
                # Inject is a custom option and DNF won't recognize it
                if opt == "inject":
                    continue
                setattr(repo, opt, val)

            repo.load()
            dnf_base.repos.add(repo)
            log.debug("Defined repo %s" % repo.id)

        # Do not consider *anything* to be installed
        dnf_base.fill_sack(load_system_repo=False, load_available_repos=True)

        return dnf_base

    def run_dnf(self, dnf_base, config):
        dnf_base.conf.installroot = self.container_dir

        for p in config['packages']:
            dnf_base.install(p)

        resolution = dnf_base.resolve()
        if resolution:
            to_fetch = [p.installed for p in dnf_base.transaction]
            dnf_base.download_packages(to_fetch, Progress())
            dnf_base.do_transaction()
        else:
            raise RuntimeError("DNF depsolving failed.")

    def post_dnf_run(self, dnf_base, config):
        injected_repos = [
            dnf_base.repos[repo_id] for repo_id, repo_opts in config['repos'].items() if repo_opts.get('inject', False)
        ]

        # TODO: dump() results in pretty ugly output since it creates lines for *all* repo options.
        output = "\n".join([x.dump() for x in injected_repos])
        with open(os.path.join(self.container_dir, 'etc', 'yum.repos.d', 'salmon.repo'), 'w') as f:
            log.debug("Writing %s" % output)
            f.write(output)
