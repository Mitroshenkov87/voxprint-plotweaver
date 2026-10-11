"""Shared BUILD.json identity for the suite splash.

``plotweaver --version`` keeps the Plotweaver label
``X.Y.Z RC · build N "Codename"``. The splash widget paints the label from
voxprint-common, which uses a different word order.
"""

from __future__ import annotations

from voxprint_common.buildinfo import BuildInfo, load

from plotweaver.appinfo import APP_NAME, build_json_path


def suite_build_info() -> BuildInfo:
    """Read BUILD.json the way the rest of the suite does, including older shapes."""
    return load(build_json_path(), app=APP_NAME)
