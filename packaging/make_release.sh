#!/usr/bin/env bash
# Build the .deb and SHA256SUMS that the in-app updater expects on a GitHub Release.
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$SOURCE_DIR/dist}"
VERSION="$(sed -n 's/^Version: //p' "$SOURCE_DIR/packaging/control" | head -n 1)"
grep -q "^PACKAGE_VERSION = '$VERSION'" "$SOURCE_DIR/nettalabbo.py" \
    || { echo "PACKAGE_VERSION in nettalabbo.py does not match packaging/control ($VERSION)" >&2; exit 1; }
mkdir -p "$OUT_DIR"
PACKAGE="$(bash "$SOURCE_DIR/packaging/build_deb.sh" "$OUT_DIR" | tail -n 1)"
( cd "$OUT_DIR" && sha256sum "$(basename "$PACKAGE")" > SHA256SUMS )
printf '\nRelease files in %s:\n' "$OUT_DIR"
ls -l "$PACKAGE" "$OUT_DIR/SHA256SUMS"
printf '\nPublish with the GitHub CLI (tag must be v%s):\n' "$VERSION"
printf '  gh release create v%s "%s" "%s/SHA256SUMS" --title "Nettalabbo %s" --notes-file CHANGELOG.md\n' \
    "$VERSION" "$PACKAGE" "$OUT_DIR" "$VERSION"
