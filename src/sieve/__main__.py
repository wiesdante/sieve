"""Entry point: ``python -m sieve`` and the packaged executable."""

import sys

from sieve.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
