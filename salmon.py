#! /usr/bin/env python
import salmon
import os
import sys
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)5s [%(name)s:%(lineno)s] %(message)s")
    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)

    if os.geteuid() != 0:
        sys.stderr.write("Error: This command has to be run under the root user.\n")
        sys.exit(1)

    sys.exit(
        salmon.Salmon(sys.argv[1:]).run()
    )
