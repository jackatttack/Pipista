# -*- coding: utf-8 -*-
"""Launch Pipista in Pythonista's editor panel."""

import os
import sys


ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
    )
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipista_core import main


if __name__ == '__main__':
    main('panel')
