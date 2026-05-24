#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="FanqiePublisher"
BUNDLE_ID="com.jiangmiao.fanqiepublisher"

echo "==> Ensuring dependencies"
python3 -m pip install -r requirements.txt pyinstaller

echo "==> Ensuring Playwright Chromium"
python3 -m playwright install chromium

BROWSERS_DIR="${HOME}/Library/Caches/ms-playwright"
if [ ! -d "$BROWSERS_DIR" ]; then
  echo "Playwright browser cache not found: $BROWSERS_DIR" >&2
  exit 1
fi

BUILD_SUPPORT_DIR="build-support"
PLAYWRIGHT_ZIP="${BUILD_SUPPORT_DIR}/playwright-browsers.zip"
mkdir -p "$BUILD_SUPPORT_DIR"

echo "==> Packing Playwright browsers"
python3 - <<'PY'
from pathlib import Path
import shutil

project_root = Path.cwd()
source_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
output_base = project_root / "build-support" / "playwright-browsers"
zip_path = shutil.make_archive(str(output_base), "zip", root_dir=source_dir)
print(f"packed: {zip_path}")
PY

echo "==> Generating macOS icon"
python3 scripts/generate_macos_icon.py

echo "==> Building macOS app bundle"
python3 -m PyInstaller \
  --clean \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  --icon "assets/logo.icns" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --add-data "app/web:app/web" \
  --add-data "assets:assets" \
  --add-data "${PLAYWRIGHT_ZIP}:playwright-browsers" \
  main_webview.py

echo "==> Build complete"
echo "App bundle: dist/${APP_NAME}.app"
