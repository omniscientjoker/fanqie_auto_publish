from pathlib import Path
import sys


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
APP_DIR = PROJECT_ROOT / "app"
WEB_DIR = APP_DIR / "web"
ASSETS_DIR = PROJECT_ROOT / "assets"
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

STATE_FILE = DATA_DIR / "state.json"
CONFIG_FILE = DATA_DIR / "config.json"
LOGO_FILE = ASSETS_DIR / "logo.ico"

