#!/bin/sh
# Install a per-user launcher for this checkout (no root needed).
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DEST"
sed "s|@REPO@|$REPO|g" "$REPO/data/io.github.gunnoej5.Dialtone.desktop" > "$DEST/io.github.gunnoej5.Dialtone.desktop"
echo "installed $DEST/io.github.gunnoej5.Dialtone.desktop"
