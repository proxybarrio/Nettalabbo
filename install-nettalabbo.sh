#!/usr/bin/env bash
# Nettalabbo 0.5.0 installation helper for Xubuntu / Ubuntu.
# Packages are installed from configured Ubuntu repositories, never from third-party websites.
# This script runs interactively and uses APT for dependency checks and installation.
set -Eeuo pipefail

fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE="$DIR/nettalabbo_0.5.0-4_all.deb"
[[ -f "$PACKAGE" ]] || fail "Missing .deb beside this installer: $PACKAGE"
command -v apt-get >/dev/null || fail "APT is not available."
command -v dpkg-deb >/dev/null || fail "dpkg-deb is not available."
command -v apt-cache >/dev/null || fail "apt-cache is not available."
command -v sudo >/dev/null || fail "sudo is required."

# Validate the package name and revision before elevating privileges.
[[ "$(dpkg-deb -f "$PACKAGE" Package)" == "nettalabbo" ]] || fail "Invalid local Debian package."
[[ "$(dpkg-deb -f "$PACKAGE" Version)" == "0.5.0-4" ]] || fail "Wrong package version."

if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  case "${ID:-}:${ID_LIKE:-}" in
    ubuntu:*|*:ubuntu*|*:*ubuntu*) ;;
    *) fail "This installer targets Xubuntu and other Ubuntu-based systems; found ${PRETTY_NAME:-unknown}." ;;
  esac
  info "Detected: ${PRETTY_NAME:-Ubuntu}"
  if [[ "${VERSION_ID:-}" == '20.04' ]]; then
    printf '%s\n' 'Note: Ubuntu 20.04 is past standard security maintenance. Review Ubuntu Pro / ESM.'
  fi
fi

# Find installed older package identities before the APT replacement transaction.
# Do not purge: settings in user home directories must be preserved.
LEGACY_PACKAGES=(netlabbo netlab-xubuntu network-laboratory-xubuntu)
legacy_is_installed() {
  local current_status
  current_status="$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null || true)"
  case "$current_status" in
    'install ok installed'|'install ok unpacked'|'install ok half-configured'|'install ok half-installed'|    'install ok triggers-awaited'|'install ok triggers-pending') return 0 ;;
    *) return 1 ;;
  esac
}
INSTALLED_LEGACY=()
for old_name in "${LEGACY_PACKAGES[@]}"; do
  if legacy_is_installed "$old_name"; then
    INSTALLED_LEGACY+=("$old_name")
    info "Existing package detected: $old_name (will be replaced)"
  fi
done

info 'Checking official APT repositories and dependencies'
sudo -v
sudo apt-get update

# DNS utility naming changed across Ubuntu releases. Choose an available provider.
can_install() {
  local candidate
  candidate="$(apt-cache policy "$1" | sed -n 's/^[[:space:]]*Candidate: //p' | head -n 1)"
  [[ -n "$candidate" && "$candidate" != '(none)' ]]
}
if can_install bind9-dnsutils; then
  DNS_PACKAGE=bind9-dnsutils
elif can_install dnsutils; then
  DNS_PACKAGE=dnsutils
else
  fail 'Neither bind9-dnsutils nor dnsutils is available. Check enabled Ubuntu repositories (including universe).'
fi

NEEDED=(python3 python3-tk iputils-ping traceroute openssh-client telnet ca-certificates "$DNS_PACKAGE")

info 'Planning the dependency installation (no changes yet)'
apt-get -s install "${NEEDED[@]}" || fail 'APT cannot resolve dependencies on this system. Nothing was installed.'

info 'Installing or updating all mandatory dependencies FIRST'
sudo apt-get install "${NEEDED[@]}"

info 'Checking Python, Tkinter and the required networking programs'
python3 - <<'PYTHON'
import sys, tkinter, ssl, smtplib, imaplib, poplib, socket, ftplib
if sys.version_info < (3, 8):
    raise SystemExit('Python 3.8 or newer is required.')
print('Python {} and Tkinter: OK'.format(sys.version.split()[0]))
PYTHON
for program in ping traceroute ssh telnet dig; do
  command -v "$program" >/dev/null || fail "Dependency installed but '$program' is not available in PATH."
  printf '  %s: OK\n' "$program"
done

info 'All dependencies are ready. Planning Nettalabbo installation and automatic removal of older package names'
PLAN="$(apt-get -s install "$PACKAGE")" || fail 'APT preflight for Nettalabbo failed. No installation attempted.'
# When old packages are installed, APT must plan to remove them as part of
# the same transaction. Never uninstall them first and risk leaving no working application.
for old_name in "${INSTALLED_LEGACY[@]}"; do
  if ! printf '%s\n' "$PLAN" | grep -Eq "^Remv ${old_name}( |$)"; then
    printf '%s\n' "$PLAN" >&2
    fail "APT did not plan removal of the old package: $old_name. Stopping safely."
  fi
done
printf '%s\n' "$PLAN"
info 'Installing Nettalabbo; APT removes legacy packages in the same operation'
sudo apt-get install "$PACKAGE"

info 'Verifying installation and removal of all older package identities'
for old_name in "${LEGACY_PACKAGES[@]}"; do
  if legacy_is_installed "$old_name"; then
    fail "Old package $old_name is still installed. The replacement did not complete."
  fi
done
info 'Verifying installation' 
status="$(dpkg-query -W -f='${db:Status-Abbrev}' nettalabbo 2>/dev/null || true)"
[[ "$status" == ii* ]] || fail "Nettalabbo package is not fully installed: $status"
installed_version="$(dpkg-query -W -f='${Version}' nettalabbo)"
[[ "$installed_version" == '0.5.0-4' ]] || fail "Installed version differs: $installed_version"
printf '\nSUCCESS: Nettalabbo %s is installed, with all declared dependencies.\n' "$installed_version"
printf '%s\n' 'Open Nettalabbo from the application menu or run: nettalabbo'
