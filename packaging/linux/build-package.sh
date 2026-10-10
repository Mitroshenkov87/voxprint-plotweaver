#!/usr/bin/env bash
# Source tarball and a simple .deb: checkout, desktop file, and icons.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$ROOT/src/plotweaver/appinfo.py")"
DIST="$ROOT/dist"
PKG="$ROOT/packaging/linux/pkg"
STAGE="$PKG/opt/voxprint-plotweaver"
rm -rf "$PKG" "$DIST"
mkdir -p "$STAGE" "$DIST" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/DEBIAN"

copy() {
  mkdir -p "$STAGE/$1"
  cp -a "$ROOT/$1/." "$STAGE/$1/"
}

copy src
copy bakeoff
copy scenarios
copy docs
copy branding
copy scripts
cp "$ROOT/pyproject.toml" "$ROOT/requirements.txt" "$ROOT/README.md" "$ROOT/LICENSE" "$ROOT/NOTICE" "$ROOT/BUILD.json" "$STAGE/"
cat > "$STAGE/plotweaver-gui.sh" << 'EOF'
#!/bin/sh
cd /opt/voxprint-plotweaver
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m plotweaver gui "$@"
fi
exec python3 -m plotweaver gui "$@"
EOF
chmod 755 "$STAGE/plotweaver-gui.sh" "$STAGE/scripts/"*.sh

cp "$ROOT/packaging/linux/plotweaver.desktop" "$PKG/usr/share/applications/plotweaver.desktop"
cp "$ROOT/branding/plotweaver-256.png" "$PKG/usr/share/icons/hicolor/256x256/apps/plotweaver.png"

cat > "$PKG/DEBIAN/control" << EOF
Package: voxprint-plotweaver
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Aleksandr Mitroshenkov <https://github.com/Mitroshenkov87/voxprint-plotweaver>
Description: Voxprint AI Plotweaver
 Local synopsis-to-novel app. Install Python 3.14 and run
 /opt/voxprint-plotweaver/scripts/e2e_mars.sh after unpacking,
 or create a venv in /opt/voxprint-plotweaver.
EOF

tar -C "$PKG/opt" -czf "$DIST/voxprint-plotweaver-${VERSION}-linux-x86_64.tar.gz" voxprint-plotweaver
dpkg-deb --root-owner-group --build "$PKG" "$DIST/voxprint-plotweaver_${VERSION}_amd64.deb"
echo "$DIST"
