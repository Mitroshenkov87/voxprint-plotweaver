"""Clock for the process, recorded when this module is first imported.

``python -m plotweaver`` imports this before the command parser so a startup
probe can measure time to the first window, including the remaining imports.
"""

from __future__ import annotations

import time

STARTED = time.perf_counter()
