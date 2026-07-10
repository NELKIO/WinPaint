#!/usr/bin/env bash
#
# Uninstall WinPaint.  Run: sudo bash uninstall.sh
#
set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with root privileges: sudo bash uninstall.sh"
    exit 1
fi

echo "==> Uninstalling WinPaint..."
rm -rf /opt/winpaint
rm -f /usr/local/bin/winpaint
rm -f /usr/share/applications/winpaint.desktop
for s in 16 32 48 64 128 256; do
    rm -f "/usr/share/icons/hicolor/${s}x${s}/apps/winpaint.png"
done
update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
echo "==> Done. WinPaint has been uninstalled."
