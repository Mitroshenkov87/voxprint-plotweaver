"""Version stamp. The Windows installer reads the string constants below."""

APP_NAME = "Voxprint AI Plotweaver"
APP_VERSION = "0.1.0"
APP_BUILD = 0
# Torah word for a first build: "in the beginning".
CODENAME = "Bereshit"
GITHUB_REPO = "Mitroshenkov87/voxprint-plotweaver"
LOCK_OWNER = "plotweaver"


def version_label() -> str:
    """Human-readable version, build offset, and codename."""
    return f'{APP_VERSION} · build {APP_BUILD} "{CODENAME}"'
