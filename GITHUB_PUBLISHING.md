# Publishing Nettalabbo on GitHub

Suggested repository: `proxybarrio/nettalabbo` (not created by this package).

This repository is an experimental software project under the MIT License. Author: Proxybarrio, with AI assistance. Approved public project contact: proxybar@gmail.com. Do not include personal identity information or private credentials.

## First publication

1. Create a new **private** GitHub repository named `nettalabbo` in the authenticated `proxybarrio` account without initializing a README, License or `.gitignore`. This is the conservative option pending outstanding trademark review.
2. Upload or push the source tree with `README.md` at repository root. Do not add the 1998 NetLab95 executable or manual.
3. Before making the repository public, review `TRADEMARK_PRECHECK.md`, `SECURITY_REVIEW_2026-11-19.md`, `RELEASE_REVIEW_2026-11-19.md`, and the security disclaimer.
4. Only after creating and checking the repository, confirm the Issues and private security-contact instructions.
5. If releasing Debian binaries, attach the `.deb` to a GitHub Release rather than committing it into source history.

## Releases and in-app updates

The updater in Nettalabbo reads `https://api.github.com/repos/proxybarrio/nettalabbo/releases/latest`. It only works when the repository (or at least its releases) is public; while it is private, users see "No public release found".

For each release:

1. Increase `Version:` in `packaging/control` and `PACKAGE_VERSION` in `nettalabbo.py` to the same value (a test enforces this).
2. Run `bash packaging/make_release.sh`. It writes `dist/nettalabbo_<version>_all.deb` and `dist/SHA256SUMS`.
3. Create a GitHub Release whose tag is `v<version>` (for example `v0.5.3-9`), not marked as draft or pre-release, with exactly those two files attached. The script prints the `gh release create` command.

The checksum protects against corrupted or substituted downloads, but both files come from the same GitHub account. Protect that account with two-factor authentication. A signing key embedded in the application would be the next step if stronger guarantees are needed.

## Developer notes

The current source and compiled `.deb` are test releases, not certified production software. The original NetLab95 application and original copyright assets are not included.
