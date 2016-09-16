- Set up continuous integration to run nosetests.  The tricky part is that we have to have the python2-dnf package
  installed which isn't available in PyPi or Ubuntu (which Travis CI uses).  The best bet might be to have Travis
  spin up a Fedora Docker container with the requisite dependencies and then run nosetests inside the container.
  See [here](https://github.com/projectatomic/skopeo) for someone doing something similar.
