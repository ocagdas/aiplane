"""AI environment doctor and configuration compiler."""

import sys

if sys.version_info < (3, 13):
    raise RuntimeError(
        "aiplane requires Python 3.13 or newer; select a supported interpreter or recreate the environment."
    )

__version__ = "0.2.26"
