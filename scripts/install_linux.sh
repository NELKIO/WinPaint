#!/usr/bin/env bash
#
# Installer for WinPaint on Linux.
# Run: sudo bash install.sh
#
set -e

APP_DIR="/opt/winpaint"
BIN="/usr/local/bin/winpaint"
DESKTOP="/usr/share/applications/winpaint.desktop"
ICON_BASE="/usr/share/icons/hicolor"

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing WinPaint"

# Check root
if [ "$(id -u)" -ne 0 ]; then
    echo "This installer requires root privileges."
    echo "Run: sudo bash install.sh"
    exit 1
fi

# Copy application files
echo "==> Copying application to ${APP_DIR}..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -r "$SRC/"* "$APP_DIR/"
chmod -R a+rX "$APP_DIR"
chmod 755 "$APP_DIR/WinPaint"

# Create launch symlink
echo "==> Creating launch command ${BIN}..."
ln -sf "$APP_DIR/WinPaint" "$BIN"

# Install icons
echo "==> Installing icons..."
if [ -d "$SRC/icons" ]; then
    for s in 16 32 48 64 128 256; do
        dir="${ICON_BASE}/${s}x${s}/apps"
        mkdir -p "$dir"
        if [ -f "$SRC/icons/icon_${s}.png" ]; then
            cp "$SRC/icons/icon_${s}.png" "$dir/winpaint.png"
        fi
    done
fi

# Install .desktop file
echo "==> Registering in application menu..."
if [ -f "$SRC/winpaint.desktop" ]; then
    cp "$SRC/winpaint.desktop" "$DESKTOP"
    chmod 644 "$DESKTOP"
fi

update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -f "$ICON_BASE" 2>/dev/null || true

echo ""
echo "============================================================"
echo "  Done! WinPaint is installed."
echo ""
echo "  • Find 'Paint' in your applications menu."
echo "  • Launch from terminal: winpaint"
echo ""
echo "  Uninstall: sudo bash /opt/winpaint/uninstall.sh"
echo "============================================================"
