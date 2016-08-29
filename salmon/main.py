from __future__ import absolute_import

import argparse
import sys
import logging
import yaml
import shutil
import tempfile
import dnf
import dnf.callback

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

    def end(self,payload, status, msg):
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


# Simple tool to bootstrap a SystemD Nspawn container
class Salmon(object):
    def __init__(self, argv=None):
        parser = argparse.ArgumentParser(description="Create an nspawn container")
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
        if argv:
            self.args = parser.parse_args(argv)
        else:
            # This case is really just meant for when the class is instantiated for unit tests.
            self.args = argparse.Namespace()

    def run(self):
        if self.args.verbose:
            log.setLevel(logging.DEBUG)

        config = yaml.load(self.args.manifest)
        log.info("Config is %s" % config)
        self.validate_config(config)
        self.dnf_temp_cache = tempfile.mkdtemp(prefix="salmon_")

        try:
            dnf_base = self.build_dnf(config)
            self.run_dnf(dnf_base, config)
        finally:
            shutil.rmtree(self.dnf_temp_cache)

        return 0

    def build_dnf(self, config):
        dnf_base = dnf.Base()

        # Disable everything to start
        for repo in dnf_base.repos.all():
            repo.disable()

        for name, repo_opts in config['repos'].items():
            repo = dnf.repo.Repo(name, self.dnf_temp_cache)
            repo.enable()
            repo.id = name
            for opt, val in repo_opts.items():
                setattr(repo, opt, val)
            dnf_base.repos.add(repo)
            log.debug("Defined repo %s" % repo.id)

        return dnf_base

    def run_dnf(self, dnf_base, config):
        dnf_base.conf.installroot = config['destination']
        # Do not consider *anything* to be installed
        dnf_base.fill_sack(load_system_repo=False)
        for p in config['packages']:
            dnf_base.install(p)

        resolution = dnf_base.resolve()
        if resolution:
            to_fetch = [p.installed for p in dnf_base.transaction]
            dnf_base.download_packages(to_fetch, Progress())
            print(dnf_base.do_transaction())
        else:
            raise RuntimeError("DNF depsolving failed.")

    def validate_config(self, config):
        required_top_options = {'name', 'destination', 'repos', 'packages'}
        top_options = set(config.keys())

        errors = []
        errors.extend([
            "Missing required config section %s" % s for s in required_top_options.difference(top_options)
        ])

        if len(config['repos']) == 0:
            errors.append("No repos are defined")

        if errors:
            error_string = "\n".join(errors)
            raise RuntimeError(error_string)

