#! /usr/bin/env python
import salmon
import sys
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)5s [%(name)s:%(lineno)s] %(message)s")
    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)

    sys.exit(
        salmon.Salmon(sys.argv[1:]).run()
    )
