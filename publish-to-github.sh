#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TARGET="https://github.com/proxybarrio/nettalabbo.git"
if ! command -v git >/dev/null 2>&1; then
    echo 'Git is required. Install using: sudo apt install git' >&2
    exit 1
fi
if [ ! -f README.md ] || [ ! -f LICENSE ] || [ ! -f nettalabbo.py ]; then
    echo 'Run this script from the extracted Nettalabbo source folder.' >&2
    exit 1
fi
printf '
Target GitHub repository: %s
' "$TARGET"
printf '%s
' 'Create it under the proxybarrio account, preferably Private,'   'without adding a README, licence or .gitignore on GitHub.'   'GitHub authentication is handled by Git. NEVER paste credentials into chat.'
read -r -p 'Have you created the empty repository and want to publish source files? [y/N] ' reply
case "$reply" in y|Y|yes|YES) ;; *) echo 'No changes made.'; exit 0;; esac
if [ ! -d .git ]; then
    git init
    git checkout -b main
fi
# Scope the identity to this repository only, avoiding disclosure of global git config.
git config --local user.name 'Proxybarrio'
git config --local user.email 'proxybar@gmail.com'
git add -A
if ! git diff --staged --quiet; then
    git commit -m 'Initial experimental Nettalabbo 0.5.3 source release'
else
    echo 'No new files to commit.'
fi
if git remote get-url origin >/dev/null 2>&1; then
    if [ "$(git remote get-url origin)" != "$TARGET" ]; then
      echo 'Existing origin differs from intended repository. Refusing to push.' >&2
      exit 1
    fi
else
    git remote add origin "$TARGET"
fi
git push -u origin main
printf '
Push successful. Review the private repository before changing visibility:
'
printf 'https://github.com/proxybarrio/nettalabbo
'
