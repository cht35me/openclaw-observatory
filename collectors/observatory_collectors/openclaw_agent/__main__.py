"""Entry point: ``python -m observatory_collectors.openclaw_agent``."""

import sys

from observatory_collectors.openclaw_agent.collector import main

if __name__ == "__main__":
    sys.exit(main())
