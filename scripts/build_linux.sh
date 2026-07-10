#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

echo "==> Building WinPaint for Linux..."

# Check dependencies
if ! python3 -c 'import PyInstaller' 2>/dev/null; then
    echo "ERROR: PyInstaller not found. Install it: pip3 install pyinstaller"
    exit 1
fi
if ! python3 -c 'import PyQt5' 2>/dev/null; then
    echo "ERROR: PyQt5 not found. Install it: pip3 install PyQt5"
    exit 1
fi

# Build with PyInstaller
echo "==> Running PyInstaller..."
python3 -m PyInstaller \
    --noconfirm \
    --name WinPaint \
    --add-data "assets:assets" \
    --hidden-import PyQt5.sip \
    --collect-all PyQt5 \
    --distpath "$ROOT/dist/linux" \
    --workpath "$ROOT/build/linux" \
    --specpath "$ROOT/build" \
    src/run.py

# Prepare release directory
echo "==> Packaging release..."
RELEASE="$ROOT/dist/linux/WinPaint-Linux-x86_64"
mkdir -p "$RELEASE"
cp -r "$ROOT/dist/linux/WinPaint/"* "$RELEASE/"
cp "$ROOT/scripts/install_linux.sh" "$RELEASE/install.sh"
cp "$ROOT/scripts/uninstall_linux.sh" "$RELEASE/uninstall.sh"
cp "$ROOT/assets/winpaint.desktop" "$RELEASE/"
mkdir -p "$RELEASE/icons"
cp "$ROOT/assets/icon_"*.png "$RELEASE/icons/"

# Compress
cd "$ROOT/dist/linux"
tar czf "$ROOT/dist/WinPaint-Linux-x86_64.tar.gz" WinPaint-Linux-x86_64

echo ""
echo "============================================================"
echo "  Linux build complete!"
echo "  Dir:     dist/linux/WinPaint-Linux-x86_64/"
echo "  Archive: dist/WinPaint-Linux-x86_64.tar.gz"
echo "============================================================"
