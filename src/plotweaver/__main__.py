"""python -m plotweaver."""

import plotweaver.startup_mark as _startup_mark
from plotweaver.cli import main

# Imported first so the startup probe includes parser and window imports.
_ = _startup_mark.STARTED

if __name__ == "__main__":
    raise SystemExit(main())
