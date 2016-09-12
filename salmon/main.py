from __future__ import absolute_import

import crypt
import os
import abc
import argparse
import re
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
        # has registered its options with the parent parser before attempting to
        # run.  Without the builder pattern, we would need to remember to manually
        # inject the subparsers object into each subcommand instance.  Although this
        # pattern is esoteric, I deemed it better than setting attributes on classes
        # externally or dealing with bugs where the args object was not injected properly.
        # I also feel that it makes testing a little more flexible.
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
        log.debug("Raw Config is %s" % self.redact(raw_config))
        self.config = self.validate_config(raw_config)
        log.debug("Calculated Config is %s" % self.redact(self.config))
        return self.do_command()

    def redact(self, config):
        redacted_config = copy.deepcopy(config)
        if 'root_password' in redacted_config:
            redacted_config['root_password'] = 'REDACTED'
        return redacted_config

    @abc.abstractmethod
    def do_command(self):
        return 0

    def validate_config(self, raw_config):
        config = copy.deepcopy(raw_config)
        required_top_options = {
            'name',
            'destination',
            'repos',
            'packages',
            'subvolume',
        }
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

        if self.config['nspawn_file']:
            nspawn_file = os.path.join('/', 'etc', 'systemd', 'nspawn', '%s.nspawn' % self.config['name'])
            try:
                os.unlink(nspawn_file)
                log.info("Deleted %s" % nspawn_file)
            except OSError:
                log.info("Didn't find %s to delete" % nspawn_file)


class BuildCommand(BaseCommand):
    # See documentation on Modular Crypt Format (https://pythonhosted.org/passlib/modular_crypt_format.html)
    # Note that this regex will only support MD5, SHA256, SHA512, and bcrypt styles
    CRYPT_RE = re.compile(r"\$(1|5|6|2|2a|2x|2y)\$[a-zA-Z0-9./]+\$?[a-zA-Z0-9./]+")

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
            help="Override destination directory"
        )

        root_password_group = parser.add_mutually_exclusive_group()
        root_password_group.add_argument(
            "--root-password",
            help="Override root password to set on the container"
        )
        # Note that argparser's semantics around defaults for store_true/store_false
        # are weird.  Default to None instead of argparser's attempt to be helpful.
        # The default of None here will result in Salmon leaving the root password alone.
        root_password_group.add_argument(
            "--no-root-password",
            action="store_false",
            dest="root_password",
            default=None,
            help="Enable password-less login for root on the container."
        )

        subvolume_group = parser.add_mutually_exclusive_group()
        # Note that argparsers semantics around defaults for store_true/store_false
        # are weird.  Default to None instead of argparser's attempt to be helpful.
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

        # Make sure disable_securetty is set with something and default that setting to False.
        if config.setdefault('disable_securetty', False) not in [True, False]:
            config['disable_securetty'] = False
            log.warning(
                "The 'disable_securetty' setting must be either True or False.  Falling back to False."
            )

        config.setdefault('root_password', None)
        if args.root_password is not None:
            config['root_password'] = args.root_password

        config.setdefault('nspawn_file', None)
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

        self.post_creation(self.config)
        log.info("Finished %s" % self.config['name'])
        return 0

    def post_creation(self, config):
        self.fix_context()
        self.remove_securetty(config)
        if config['root_password'] is not None:
            self.set_root_password(config)
        if config['nspawn_file'] is not None:
            self.create_nspawn_file(config)

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
            try:
                if '://' in p:
                    local_pkg = dnf_base.add_remote_rpm(p)
                    dnf_base.package_install(local_pkg, strict=True)
                else:
                    dnf_base.install(p)
            except dnf.exceptions.Error:
                log.exception("Could not install %s" % p)
                sys.exit(1)

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

        output = ""
        for inj in injected_repos:
            # dump() results in broken output since it creates lines with blank values that
            # DNF chokes on during a run.  Strip those out.
            output += "\n".join([o for o in inj.dump().split('\n') if not re.match(r"^\w+\s=\s*$", o)])

        if output:
            with open(os.path.join(self.container_dir, 'etc', 'yum.repos.d', 'salmon.repo'), 'w') as f:
                log.debug("Writing %s" % output)
                f.write(output)

    def fix_context(self):
        """Fix the SELinux contexts on the container's files.  I believe this is only necessary for containers
        that are not in a subvolume, but not certain.  It's run regardless of the container destination type
        currently."""
        log.info("Fixing SELinux contexts")
        # Note that the (/.*)? is not interpreted by the shell, but by semanage-fcontext directly.
        subprocess.check_output([
            'semanage', 'fcontext', '--add', '--type', 'svirt_sandbox_file_t', '%s(/.*)?' % self.container_dir
        ])
        subprocess.check_output([
            'restorecon', '-R', self.container_dir
        ])

    def remove_securetty(self, config):
        """Remove /etc/securetty from the resultant container to allow machinectl login.  This workaround is
        to address https://github.com/systemd/systemd/issues/852."""
        # I want to be picky about this setting.  Only True should work; anything else should not
        if config['disable_securetty'] is True:
            log.info("Removing securetty from container")
            os.unlink(os.path.join(self.container_dir, 'etc', 'securetty'))

    def set_root_password(self, config):
        """Set the root password in /etc/shadow for the container.  Valid values for
        the root_password configuration option are False (for no password at all), plaintext
        strings, or already encrypted strings matching the Modular Crypt Format."""
        destination_shadow = os.path.join(self.container_dir, 'etc', 'shadow')
        with open(destination_shadow, 'r') as shadow:
            entries = [l.strip() for l in shadow]

        shadow_items = [
            # See shadow.h
            'sp_nam',  # login name
            'sp_pwd',  # encrypted password
            'sp_lstchg',  # date of last change
            'sp_min',  # min #days between changes
            'sp_max',  # max #days between changes
            'sp_warn',  # days before pw expires to warn user about it
            'sp_inact',  # days after pw expires until account is blocked
            'sp_expire',  # days since 1970-01-01 until account is disabled
            'sp_flag',  # reserved
        ]

        new_entries = []
        for entry in entries:
            items = str.split(entry, ':', 9)
            if len(items) != 9:
                log.debug("Couldn't read '%s' in /etc/shadow" % entry)
                new_entries.append(entry)
                continue

            shadow_line = dict(zip(shadow_items, items))

            if shadow_line['sp_nam'] == "root" and config['root_password'] is not None:
                if config['root_password'] is False:
                    log.info("Disabling root password")
                    shadow_line['sp_pwd'] = ''
                elif self.CRYPT_RE.match(config['root_password']):
                    log.info("Setting root password")
                    shadow_line['sp_pwd'] = config['root_password']
                else:
                    log.info("Setting root password")
                    shadow_line['sp_pwd'] = crypt.crypt(config['root_password'])

            new_entries.append(shadow_line)

        with open(destination_shadow, 'w') as shadow:
            for entry in new_entries:
                if isinstance(entry, dict):
                    shadow.write(':'.join([entry[x] for x in shadow_items]))
                else:
                    shadow.write(entry)
                shadow.write('\n')

    def create_nspawn_file(self, config):
        nspawn_file_directory = os.path.join('/', 'etc', 'systemd', 'nspawn')

        # For some reason the systemd RPM doesn't create /etc/systemd/nspawn/ by default
        # so we need to make sure it's there.  Try to make it and fail gracefully if not.
        try:
            # Thanks http://stackoverflow.com/a/14364249/6124862 for this idiom
            os.mkdir(nspawn_file_directory)
        except OSError:
            if not os.path.isdir(nspawn_file_directory):
                raise

        nspawn_file = os.path.join(nspawn_file_directory, "%s.nspawn" % config['name'])
        if os.path.exists(nspawn_file):
            log.warn("%s already exists. Cowardly refusing to overwrite it!" % nspawn_file)
            return

        with open(nspawn_file, 'w') as f:
            f.write(config['nspawn_file'])
        log.info("Wrote %s" % nspawn_file)


def main(args=None):
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)5s [%(name)s:%(lineno)s] %(message)s")
    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)

    if os.geteuid() != 0:
        sys.stderr.write("Error: This command has to be run under the root user.\n")
        sys.exit(1)

    sys.exit(
        Salmon(sys.argv[1:]).run()
    )


if __name__=="__main__":
    main()
