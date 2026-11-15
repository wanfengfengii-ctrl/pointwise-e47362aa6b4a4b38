#!/usr/bin/env python3
"""Repository-root launcher: ``python3 run.py verify|demo|bench``.

Using a script instead of ``python3 -m paretolayers`` keeps the package
importable no matter which directory the caller runs from, because a script's
own directory is placed on ``sys.path``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paretolayers.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
