"""map-helper core: canonical mapping model, resolver and emulator adapters."""

from pathlib import Path

__version__ = "0.0.1"

# The shipped data (controllers, defaults, layouts, adapter tables). Installed (docs/14 §6) it sits next to the
# package, versions/<ver>/{mh_entry.py, maphelper/, data/}; in the repo the package is in core/ and data/ one up.
_BASE = Path(__file__).resolve().parent.parent
DATA = _BASE / "data" if (_BASE / "data").is_dir() else _BASE.parent / "data"
