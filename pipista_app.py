# -*- coding: utf-8 -*-
"""Public Pipista app module.

Users can import or run this module directly. The implementation is split into
internal base/frontend modules so there is still one clear public app file.
"""

import sys

from _pipista_app_base import *  # noqa: F401,F403

# If this file is executed directly, make the partially initialized module
# available under its normal import name before the frontend imports it.
sys.modules.setdefault('pipista_app', sys.modules[__name__])

from _pipista_frontend import PipistaApp, main  # noqa: E402,F401

__all__ = ['PipistaApp', 'main']


if __name__ == '__main__':
    main()
