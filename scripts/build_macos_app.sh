#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="FanqiePublisher"
BUNDLE_ID="com.jiangmiao.fanqiepublisher"
APP_VERSION="1.0.0"

prompt_package_type() {
  printf '==> 请选择输出格式\n' >&2
  printf '1) dmg\n' >&2
  printf '2) pkg\n' >&2
  printf '输入 1 或 2: ' >&2
  read -r choice

  case "$choice" in
    1) echo "dmg" ;;
    2) echo "pkg" ;;
    *) echo "无效选择: $choice" >&2; exit 1 ;;
  esac
}

PACKAGE_TYPE="${1:-}"
if [ -z "$PACKAGE_TYPE" ]; then
  PACKAGE_TYPE="$(prompt_package_type)"
fi

case "$PACKAGE_TYPE" in
  dmg|pkg) ;;
  *)
    echo "不支持的输出格式: $PACKAGE_TYPE" >&2
    echo "用法: bash scripts/build_macos_app.sh [dmg|pkg]" >&2
    exit 1
    ;;
esac

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

APP_BUNDLE="dist/${APP_NAME}.app"
DMG_PATH="dist/${APP_NAME}.dmg"
PKG_PATH="dist/${APP_NAME}.pkg"

create_dmg() {
  local dmg_stage="${BUILD_SUPPORT_DIR}/dmg-root"
  rm -rf "$dmg_stage" "$DMG_PATH"
  mkdir -p "$dmg_stage"
  cp -R "$APP_BUNDLE" "$dmg_stage/"
  ln -s /Applications "$dmg_stage/Applications"

  echo "==> Creating DMG package"
  hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$dmg_stage" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

  echo "==> DMG complete"
  echo "Artifact: $DMG_PATH"
}

create_pkg() {
  rm -f "$PKG_PATH"

  echo "==> Creating PKG installer"
  pkgbuild \
    --component "$APP_BUNDLE" \
    --install-location "/Applications" \
    --identifier "${BUNDLE_ID}.installer" \
    --version "$APP_VERSION" \
    "$PKG_PATH"

  echo "==> PKG complete"
  echo "Artifact: $PKG_PATH"
}

echo "==> App bundle ready"
echo "App bundle: $APP_BUNDLE"

case "$PACKAGE_TYPE" in
  dmg) create_dmg ;;
  pkg) create_pkg ;;
esac
