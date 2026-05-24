import subprocess
import tempfile
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
SOURCE_ICON = ASSETS_DIR / "logo.ico"
OUTPUT_ICON = ASSETS_DIR / "logo.icns"

ICONSET_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def main():
    if not SOURCE_ICON.exists():
        raise SystemExit(f"missing source icon: {SOURCE_ICON}")

    with Image.open(SOURCE_ICON) as img:
        base = img.convert("RGBA")

    with tempfile.TemporaryDirectory() as tmp_dir:
        iconset_dir = Path(tmp_dir) / "logo.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        for filename, size in ICONSET_FILES.items():
            resized = base.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(iconset_dir / filename, format="PNG")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(OUTPUT_ICON)],
            check=True,
        )

    print(f"generated macOS icon: {OUTPUT_ICON}")


if __name__ == "__main__":
    main()
