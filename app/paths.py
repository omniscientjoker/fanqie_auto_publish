import os
import shutil
import zipfile
from pathlib import Path
import sys


APP_SUPPORT_DIR_NAME = "FanqiePublisher"


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return _source_root()


def _runtime_data_root() -> Path:
    if not getattr(sys, "frozen", False):
        return _source_root() / "data"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SUPPORT_DIR_NAME

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        return base / APP_SUPPORT_DIR_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else (Path.home() / ".local" / "share")
    return base / APP_SUPPORT_DIR_NAME


PROJECT_ROOT = _source_root()
BUNDLE_ROOT = _bundle_root()
APP_DIR = BUNDLE_ROOT / "app"
WEB_DIR = APP_DIR / "web"
ASSETS_DIR = BUNDLE_ROOT / "assets"
BUNDLED_PLAYWRIGHT_DIR = BUNDLE_ROOT / "playwright-browsers"
PLAYWRIGHT_BROWSERS_ZIP = BUNDLED_PLAYWRIGHT_DIR / "playwright-browsers.zip"
DATA_DIR = _runtime_data_root()
DOCS_DIR = PROJECT_ROOT / "docs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

STATE_FILE = DATA_DIR / "state.json"
CONFIG_FILE = DATA_DIR / "config.json"
LOGO_FILE = ASSETS_DIR / "logo.ico"
MACOS_ICON_FILE = ASSETS_DIR / "logo.icns"


def _extract_zip_with_permissions(zip_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            destination = target_dir / info.filename
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)

            mode = info.external_attr >> 16
            if mode:
                os.chmod(destination, mode)


def _repair_zip_permissions(zip_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            destination = target_dir / info.filename
            if not destination.exists():
                continue
            mode = info.external_attr >> 16
            if mode and (destination.stat().st_mode & 0o777) != (mode & 0o777):
                os.chmod(destination, mode)


def configure_runtime_environment() -> None:
    if not getattr(sys, "frozen", False):
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    extracted_dir = DATA_DIR / "ms-playwright"

    if not extracted_dir.exists() and PLAYWRIGHT_BROWSERS_ZIP.exists():
        _extract_zip_with_permissions(PLAYWRIGHT_BROWSERS_ZIP, extracted_dir)
    elif extracted_dir.exists() and PLAYWRIGHT_BROWSERS_ZIP.exists():
        _repair_zip_permissions(PLAYWRIGHT_BROWSERS_ZIP, extracted_dir)

    if extracted_dir.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(extracted_dir)
