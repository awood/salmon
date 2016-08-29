# Salmon

Salmon is a tool used to bootstrap Systemd Nspawn containers.  Most of the
configuration is given via a manifest file.

## Manifest Structure

Let's look at an example

```yaml
name: "CentOS7_2-base"
destination: "/var/lib/machines"

repos:
  centos7_2:
    baseurl: "http://mirror.centos.org/centos/7.2.1511/os/x86_64"

packages:
  - systemd
  - passwd
  - vim-minimal
  - redhat-release
  - yum
```

The file is in YAML and has four top-level settings:

* `name`: the name to use for this container
* `destination`: the file path that the container will be written to
* `repos`: DNF repo definitions to pull content from
* `packages`: packages to install into the container.

The `repos` section can have multiple sub-sections.  Each sub-section should be 
a repo ID and then underneath that repo ID, you may define any option that DNF
will recognize (e.g. `gpgcheck`).  Note that these repo definitions are **not**
currently written into the container.

## Command Line Options

* `--verbose`: print additional debugging information
* `--destination`: replace the destination given in the manifest file.  Useful
  for ad hoc tests.

## Examples

```
% sudo ./salmon.py --destination $(mktemp -d /tmp/salmon_dest_XXXX) sample_manifest.yaml
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
