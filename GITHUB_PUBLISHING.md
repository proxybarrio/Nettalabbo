# Publishing Nettalabbo on GitHub

Suggested repository: `proxybarrio/nettalabbo` (not created by this package).

This repository is an experimental software project under the MIT License. Author: Proxybarrio, with AI assistance. Approved public project contact: proxybar@gmail.com. Do not include personal identity information or private credentials.

## First publication

1. Create a new **private** GitHub repository named `nettalabbo` in the authenticated `proxybarrio` account without initializing a README, License or `.gitignore`. This is the conservative option pending outstanding trademark review.
2. Upload or push the source tree with `README.md` at repository root. Do not add the 1998 NetLab95 executable or manual.
3. Before making the repository public, review the security disclaimer.
4. Only after creating and checking the repository, confirm the Issues and private security-contact instructions.
5. If releasing Debian binaries, attach the `.deb` to a GitHub Release rather than committing it into source history.

## Releases and in-app updates

The updater in Nettalabbo reads `https://api.github.com/repos/proxybarrio/nettalabbo/releases/latest`. It only works when the repository (or at least its releases) is public; while it is private, users see "No public release found".

Publishing is automatic. On every push to `main`, after the tests and the Ubuntu 20.04 job pass, the `publish-deb` job of `.github/workflows/verify.yml`:

1. builds `nettalabbo_<version>_all.deb` and `SHA256SUMS` with `packaging/make_release.sh`;
2. keeps them as the `nettalabbo-deb` artifact of that workflow run (latest build of `main`);
3. creates the GitHub Release `v<version>` with those two files and the matching CHANGELOG section, when that version has not been released yet. Existing releases are never overwritten.

To publish a new version, increase `Version:` in `packaging/control` and `PACKAGE_VERSION` in `nettalabbo.py` to the same value (a test enforces this), add its CHANGELOG section, and push to `main`. `bash packaging/make_release.sh` still builds the same files locally.

The checksum protects against corrupted or substituted downloads, but both files come from the same GitHub account. Protect that account with two-factor authentication. A signing key embedded in the application would be the next step if stronger guarantees are needed.

## Developer notes

The current source and compiled `.deb` are test releases, not certified production software. The original NetLab95 application and original copyright assets are not included.
