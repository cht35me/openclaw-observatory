"""Entry point: ``python -m observatory_collectors.host_pi``."""

import sys

from observatory_collectors.host_pi.collector import main

if __name__ == "__main__":
    sys.exit(main())
