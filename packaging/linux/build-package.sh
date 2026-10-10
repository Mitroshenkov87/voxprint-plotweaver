#!/usr/bin/env bash
# Full Linux package: relocatable CPython, dependencies, and llama.cpp b11476.
# Model weights are not included.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$ROOT/src/plotweaver/appinfo.py")"
DIST="$ROOT/dist"
PKG="$ROOT/packaging/linux/pkg"
STAGE="$ROOT/build/stage"
APP="$PKG/opt/voxprint-plotweaver"

rm -rf "$PKG" "$DIST" "$STAGE"
mkdir -p "$DIST" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/DEBIAN"

if command -v python >/dev/null 2>&1; then
  PY=python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "python is required" >&2
  exit 1
fi
if ! "$PY" -m uv --version >/dev/null 2>&1; then
  "$PY" -m pip install -q "uv==0.13.0"
fi
"$PY" packaging/assemble.py --dest "$STAGE"

mkdir -p "$APP"
cp -a "$STAGE/." "$APP/"

cp "$ROOT/packaging/linux/plotweaver.desktop" "$PKG/usr/share/applications/plotweaver.desktop"
cp "$ROOT/branding/plotweaver-256.png" "$PKG/usr/share/icons/hicolor/256x256/apps/plotweaver.png"

cat > "$PKG/DEBIAN/control" << EOF
Package: voxprint-plotweaver
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Aleksandr Mitroshenkov <https://github.com/Mitroshenkov87/voxprint-plotweaver>
Depends: libglib2.0-0t64 | libglib2.0-0, libegl1, libgl1, libxkbcommon0, libfontconfig1, libdbus-1-3, libx11-6, libxcb1, libvulkan1
Description: Voxprint AI Plotweaver
 Local synopsis-to-novel app. Python, dependencies, and llama.cpp b11476
 are included. Model weights download on first run.
EOF

TAR="voxprint-plotweaver-${VERSION}-linux-x86_64.tar.gz"
DEB="voxprint-plotweaver_${VERSION}_amd64.deb"
tar -C "$PKG/opt" -czf "$DIST/$TAR" voxprint-plotweaver
dpkg-deb --root-owner-group --build "$PKG" "$DIST/$DEB"

(
  cd "$DIST"
  sha256sum -- "$TAR" "$DEB" > SHA256SUMS
  sha256sum -c SHA256SUMS
)
echo "$DIST"
