#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$SOURCE_DIR}"
# Derive the filename from Debian control metadata, so future upgrades retain
# the same package identity while incrementing the Debian package version.
PACKAGE_NAME="$(sed -n 's/^Package: //p' "$SOURCE_DIR/packaging/control" | head -n 1)"
PACKAGE_VERSION="$(sed -n 's/^Version: //p' "$SOURCE_DIR/packaging/control" | head -n 1)"
if [ "$PACKAGE_NAME" != nettalabbo ] || [ -z "$PACKAGE_VERSION" ]; then
    echo "Invalid package metadata: $PACKAGE_NAME $PACKAGE_VERSION" >&2
    exit 1
fi
PACKAGE="$OUT_DIR/${PACKAGE_NAME}_${PACKAGE_VERSION}_all.deb"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
mkdir -p "$BUILD_DIR/DEBIAN" "$BUILD_DIR/usr/bin" "$BUILD_DIR/usr/share/nettalabbo/assets" "$BUILD_DIR/usr/share/doc/nettalabbo" "$BUILD_DIR/usr/share/applications" "$BUILD_DIR/usr/share/metainfo"
cp "$SOURCE_DIR/packaging/control" "$BUILD_DIR/DEBIAN/control"
cp "$SOURCE_DIR/packaging/nettalabbo.desktop" "$BUILD_DIR/usr/share/applications/nettalabbo.desktop"
mkdir -p "$BUILD_DIR/usr/share/pixmaps"
cp "$SOURCE_DIR/assets/nettalabbo_128.png" "$BUILD_DIR/usr/share/pixmaps/nettalabbo.png"
cp "$SOURCE_DIR/org.nettalabbo.Nettalabbo.metainfo.xml" "$BUILD_DIR/usr/share/metainfo/"
for filename in nettalabbo.py about_documents.py domain_rdap.py remote_terminal.py legacy_protocols.py legacy_view.py mail_inspector.py historic_servers.py time_services.py service_catalog.py updater.py dns_lookup.py; do
    cp "$SOURCE_DIR/$filename" "$BUILD_DIR/usr/share/nettalabbo/"
done
cp "$SOURCE_DIR/assets/"* "$BUILD_DIR/usr/share/nettalabbo/assets/"
cp "$SOURCE_DIR/README.md" "$SOURCE_DIR/WHY_NETTALABBO.md" "$SOURCE_DIR/DISCLAIMER.md" "$SOURCE_DIR/CHANGELOG.md" "$SOURCE_DIR/INSTALL_XUBUNTU.md" "$SOURCE_DIR/CONTRIBUTING.md" "$SOURCE_DIR/ROADMAP.md" "$SOURCE_DIR/CREDITS.md" "$SOURCE_DIR/PROVENANCE.md" "$SOURCE_DIR/LEGACY_PROTOCOLS.md" "$SOURCE_DIR/MAIL_INSPECTOR.md" "$SOURCE_DIR/HISTORIC_SERVERS.md" "$SOURCE_DIR/LICENSE" "$SOURCE_DIR/RELEASE_REVIEW_2026-11-19.md" "$SOURCE_DIR/TRADEMARK_PRECHECK.md" "$SOURCE_DIR/THIRD_PARTY_NOTICES.md" "$SOURCE_DIR/SECURITY_REVIEW_2026-11-19.md" "$SOURCE_DIR/PUBLISHING_BLOCKERS.md" "$BUILD_DIR/usr/share/doc/nettalabbo/"
cp "$SOURCE_DIR/packaging/copyright" "$BUILD_DIR/usr/share/doc/nettalabbo/copyright"
cat > "$BUILD_DIR/usr/bin/nettalabbo" <<'EOF'
#!/bin/sh
exec python3 /usr/share/nettalabbo/nettalabbo.py "$@"
EOF
chmod 755 "$BUILD_DIR/usr/bin/nettalabbo"
for icon in "$SOURCE_DIR"/assets/nettalabbo_{16,24,32,48,64,128,192,256,512}.png; do
    size="${icon##*_}"; size="${size%.png}"
    mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/${size}x${size}/apps"
    cp "$icon" "$BUILD_DIR/usr/share/icons/hicolor/${size}x${size}/apps/nettalabbo.png"
done
# Ensure the filesystem archive's root is world traversable. mktemp -d
# defaults to 0700, which must never leak into a Debian payload.
chmod 0755 "$BUILD_DIR"
chmod 0755 "$BUILD_DIR/DEBIAN"
find "$BUILD_DIR/usr" -type d -exec chmod 0755 {} +
find "$BUILD_DIR/usr" -type f -exec chmod 0644 {} +
chmod 0755 "$BUILD_DIR/usr/bin/nettalabbo"
# File checksums permit package managers to verify the installed payload.
(
    cd "$BUILD_DIR"
    find usr -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum > DEBIAN/md5sums
)
chmod 0644 "$BUILD_DIR/DEBIAN/control" "$BUILD_DIR/DEBIAN/md5sums"
mkdir -p "$OUT_DIR"
# Gzip is widely supported by older Debian package readers on Xubuntu 20.04.
dpkg-deb --root-owner-group -Zgzip -z6 --build "$BUILD_DIR" "$PACKAGE"
echo "$PACKAGE"
