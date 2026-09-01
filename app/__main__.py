"""Entry point for CLI when running `python -m app`."""

import sys

from app.cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
