#! /usr/bin/env python
import salmon.main

# This file is not packaged with Salmon!  It's merely intended as a convenience during
# development.  When installed from Pip, Salmon uses setuptools entry_points to define
# its command-line tool.
if __name__ == "__main__":
    salmon.main.main()
