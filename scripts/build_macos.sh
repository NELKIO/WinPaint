#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

echo "==> Building WinPaint for macOS..."

# Check dependencies
if ! python3 -c 'import PyInstaller' 2>/dev/null; then
    echo "ERROR: PyInstaller not found. Install it: pip3 install pyinstaller"
    exit 1
fi
if ! python3 -c 'import PyQt5' 2>/dev/null; then
    echo "ERROR: PyQt5 not found. Install it: pip3 install PyQt5"
    exit 1
fi

# Create macOS icon (.icns) from PNG
echo "==> Creating macOS icon..."
ICONSET="$ROOT/build/WinPaint.iconset"
mkdir -p "$ICONSET"
for size in 16 32 64 128 256; do
    cp "assets/icon_${size}.png" "$ICONSET/icon_${size}x${size}.png"
done
# Create @2x variants
cp "assets/icon_32.png" "$ICONSET/icon_16x16@2x.png"
cp "assets/icon_64.png" "$ICONSET/icon_32x32@2x.png"
cp "assets/icon_128.png" "$ICONSET/icon_64x64@2x.png" 2>/dev/null || true
cp "assets/icon_256.png" "$ICONSET/icon_128x128@2x.png"
cp "assets/icon_256.png" "$ICONSET/icon_256x256.png"
cp "assets/icon_256.png" "$ICONSET/icon_256x256@2x.png" 2>/dev/null || true
iconutil -c icns "$ICONSET" -o "$ROOT/build/WinPaint.icns" 2>/dev/null || {
    echo "  (iconutil failed, building without .icns)"
}

# Build with PyInstaller
echo "==> Running PyInstaller..."
ICNS_OPT=""
if [ -f "$ROOT/build/WinPaint.icns" ]; then
    ICNS_OPT="--icon=$ROOT/build/WinPaint.icns"
fi

python3 -m PyInstaller \
    --noconfirm \
    --windowed \
    --name WinPaint \
    $ICNS_OPT \
    --add-data "$ROOT/assets:assets" \
    --hidden-import PyQt5.sip \
    --collect-all PyQt5 \
    --distpath "$ROOT/dist/macos" \
    --workpath "$ROOT/build/macos" \
    --specpath "$ROOT/build" \
    "$ROOT/src/run.py"

# Enforce Light Mode on macOS (keeps title bar white/gray)
echo "==> Forcing Light Mode in Info.plist..."
PLIST="$ROOT/dist/macos/WinPaint.app/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    plutil -insert NSRequiresAquaSystemAppearance -bool YES "$PLIST" || true
    
    # Re-sign the app since modifying Info.plist breaks the signature
    echo "==> Re-signing app bundle..."
    codesign --force --deep -s - "$ROOT/dist/macos/WinPaint.app" || true
fi

# Package as zip
echo "==> Packaging WinPaint-macOS.zip..."
cd "$ROOT/dist/macos"
zip -r -y "$ROOT/dist/WinPaint-macOS.zip" WinPaint.app

echo ""
echo "============================================================"
echo "  macOS build complete!"
echo "  App:  dist/macos/WinPaint.app"
echo "  Zip:  dist/WinPaint-macOS.zip"
echo "============================================================"
