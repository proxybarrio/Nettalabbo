## 0.5.3 Debian revision 8 (19 November 2026)

- Trace: default ICMP probes when the local traceroute implementation supports them.
- Trace: selectable Auto, ICMP, TCP and UDP methods; Auto retries alternate supported probe methods if no hop replies.
- Trace: improved IPv4/IPv6 parsing, errors for missing tools and zero replies, and partial route status when arrival cannot be confirmed.
- Ping: flag zero replies as failed rather than falsely completed.
- SSH/Telnet PTY: attach a controlling terminal with util-linux setsid to allow OpenSSH to request authentication directly, rather than falling back to ssh_askpass.
- Added offline regression tests for Trace, its fallback behaviour, and controlling-terminal support.
- Functional correction still requires live verification on Xubuntu and varied networks; existing release blockers remain.

## 0.5.3 Debian revision 7 (19 November 2026)

- Corrected the Debian archive root directory permissions from 0700 to 0755 (packaging defect).
- Added installed file checksums and standard package metadata.
- Rebuilt using gzip compression for broad compatibility with graphical installers on older Ubuntu systems.
- Documented a reliable APT install path if graphical installers keep loading.
- No changes to network tools or application interface.

## 0.5.3 Debian revision 6 (19 November 2026)

- Prepared GitHub issue templates and publication documentation.
- Updated GitHub feedback references and package maintainer metadata.
- No runtime feature changes from revision 5.

## Debian revision 0.5.3-5 (19 November 2026)

- About legal and historical documents now display as non-selectable, read-only text.
- Removed the About document `Copy full text` button and text copying shortcuts.
- Document scrolling and Close/Escape remain available; other output and terminal copy functions are unchanged.
- No network behaviour or other application features changed.

## Debian revision 0.5.3-4 (19 November 2026)

- About Nettalabbo now has four explicit, offline, scrollable document links: Why Nettalabbo?, Credits & Legal Terms, Experimental Software & Disclaimer, and the full MIT License.
- Added the approved English project story, the full legal notice and the short experimental software warning as distributable documents, without changing network behaviour.
- Replaced the placeholder Debian maintainer email with the approved public contact proxybar@gmail.com.
- Preserves software version 0.5.3 and Debian upgrade compatibility.

## Package revision 0.5.3-3 (19 November 2026)

- Private configuration writes (0600 file and 0700 directory), with atomic replacement.
- Preliminary copyright, trademark, provenance, third-party and security audit documents bundled in the source archive and .deb.
- No application feature changes. The maintainer contact is still pending approval before any public release.

# Changelog

This file summarises important project milestones and packaging changes. Nettalabbo is experimental: these entries are not guarantees of complete interoperability with public servers.

## 0.5.3-2 · 18 November 2026

**Packaging and documentation update only.** Reworked the Debian package description, application metadata, launcher description, GitHub-ready README and project documentation. No changes to the network features or the application version displayed in the interface.

## 0.5.3-1 · 18 November 2026

- Recognise supported URLs appearing directly inside plain-text protocol responses.
- Display them as permanently underlined, coloured links, including in the Links menu.
- Preserve Raw view for inspection of responses.

## 0.5.2 · 18 November 2026

- Added browser-style navigation for supported legacy protocols: Go, Back, Forward, Home and Stop.
- Introduced coloured, underlined hyperlinks in structured documents and Rendered / Raw views.

## 0.5.1 · 18 November 2026

- Added a historic server reference directory with separate SSH and Telnet choices.
- Continued usability improvements to diagnostics and remote terminal screens.

## 0.5.0 · 18 November 2026

- Added Mail Server Inspector and limited mail-protocol connectivity testing.
- Introduced experimental protocol capabilities, including limited Scorpion, Molerat and Titan support.
- Renamed the project from Netlabbo to Nettalabbo while retaining version progression.

## Earlier development · November 2026

- Implemented classic network tools, Domain Inspector, experimental alternative-network browsing and the independent sidebar user interface.
