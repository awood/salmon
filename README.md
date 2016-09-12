# Salmon

Salmon is a tool used to bootstrap Systemd Nspawn containers. Most of the
configuration is given via a manifest file.

## Getting Started

Salmon has a few dependencies, so be sure to run `pip install -r
requirements.txt` before you get started. Salmon also requires the `python-dnf`
package to be installed. You can install this via DNF: `sudo dnf install
python-dnf`

## Installing via DNF

Salmon is also [available](https://copr.fedorainfracloud.org/coprs/awood/salmon/)
in Fedora via COPR.  Run `dnf copr enable awood/salmon` and then
`dnf install salmon` and it will be installed with all the required dependencies.

## Manifest Structure

Let's look at an example

```yaml
name: "CentOS7_2-base"
destination: "/var/lib/machines"
as_subvolume: True
disable_securetty: True

repos:
  centos7_2:
    baseurl: "http://mirror.centos.org/centos/7.2.1511/os/x86_64"

packages:
  - systemd
  - passwd
  - vim-minimal
  - redhat-release
  - yum
  - https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm

nspawn_file: |
  [Network]
  Private=no
```

The file is in YAML and has several top-level settings:

* `name`: the name to use for this container
* `destination`: the file path that the container will be written to
* `subvolume`: instructs Salmon to create a Btrfs sub-volume for this container
* `repos`: DNF repo definitions to pull content from
* `packages`: packages to install into the container.  You can also include a
  URL to an RPM and that DNF will grab it and install it.

There are also some optional settings:
* `disable_securetty`: instructs Salmon to remove `/etc/securetty` from the
  finished container so that `machinectl login` will work.  Esentially a clumsy
  workaround for [this issue](https://github.com/systemd/systemd/issues/852).
  If you do not set this setting to True explicitly, Salmon will **not** remove
  `/etc/securetty`.
* `root_password`: what to set the container's root password to.  You may
  provide a plaintext string, a [modular crypt format](https://pythonhosted.org/passlib/modular_crypt_format.html)
  style string (i.e. what `passwd` generates), False for no password at all,
  or null to leave the file untouched.
* `nspawn_file`: The contents of this value will be written verbatim to a
  .nspawn file under `/etc/systemd/nspawn`.  See
  [the documentation](https://www.freedesktop.org/software/systemd/man/systemd.nspawn.html)
  for more detail on what you can put here.  It is also convenient to use the
  YAML [indented delimiting](https://en.wikipedia.org/wiki/YAML#Indented_delimiting)
  feature.

The `repos` section can have multiple sub-sections.  Each sub-section should be
a repo ID and then underneath that repo ID, you may define any option that DNF
will recognize (e.g. `gpgcheck`).  You may also define an option `inject` which
will cause Salmon to write that repo definition into a file within the
container.  `inject` is useful if you want to have internal repos available from
the start, for example.

## Subcommands

Salmon is made up of sub-commands.  Currently the only sub-command is `build`
but more are planned.

### `Build` Subcommand

Options:

* `--verbose`: print additional debugging information
* `--destination=DESTINATION`: replace the destination given in the manifest
  file.  Useful for ad hoc tests
* `--[no-]subvolume`: override whether the manifest file should use a btrfs
  subvolume or not
* `--root-password=PASSWORD`: override what the manifest sets the root password
  to
* `--no-root-password`: use no root password at all.  Mutually exclusive with
  `--root-password`.

Arguments:

* manifest file

This command builds an nspawn container based on the configuration in the
manifest.  After building the container, it will set the correct SELinux context
on the container files and optionally delete `/etc/securetty` to work around an
[issue](https://github.com/systemd/systemd/issues/852) with `machinectl login`.

### `Delete` Subcommand

Options:

* `--verbose`: print additional debugging information

Arguments:

* manifest file

This command deletes the subvolume that the manifest file points to.  Note that
this command will not work if manifest does not actually use a subvolume.

## Examples

```
% sudo ./salmon.py build --destination $(mktemp -d /tmp/salmon_dest_XXXX) --no-subvolume sample-manifest.yaml
```

The above example will bootstrap a container into a temporary directory based on
the configuration in `sample_manfest.yaml`.  This command is a good way to test
out a manifest and make sure it's working.

For a container you actually want to use, you'll probably want to bootstrap to a
btrfs mount.  If you don't have a btrfs mount already, here's a quick way to get
one started:

```
% touch ~/containers/btrfs-loop
% truncate ~/containers/btrfs-loop -s 10G
% mkfs.btrfs ~/containers/btrfs-loop
% sudo mount -o loop ~/containers/btrfs-loop /var/lib/machines
```

Now you have a 10G file under `~/containers` loop mounted to `/var/lib/machines`
that you can use to experiment with.

## Other Notes

* While Salmon is building your container, it will acquire the global DNF lock
  and prevent DNF from completing other transactions.

## Acknowledgments

Thanks to [Vincent Batts](http://www.hashbangbash.com)
[John M. Harris, Jr.](https://fedoramagazine.org/container-technologies-fedora-systemd-nspawn/)
