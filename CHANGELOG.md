## 0.5.3 Debian revision 9 (19 November 2026)

- Updates: Nettalabbo can check GitHub Releases once a day (asked once at first start; toggle and manual "Check for updates" in About). A newer `nettalabbo_<version>_all.deb` is downloaded to a private temporary folder, checked against the release's SHA256SUMS and its package metadata, then installed with `pkexec apt-get install` after confirmation and the administrator password. "Later" and "Skip this version" are available. Copies run from source are only told that a new version exists.
- Time: suggested servers per protocol, including INRiM (time.inrim.it, ntp1/ntp2.inrim.it), NIST, PTB, METAS, Netnod, NTP Pool and the major public services, plus an optional list of historic time servers.
- Time: if the chosen server does not answer, the other listed servers are tried in turn; the page reports which ones failed.
- SNTP: version 4 request, clock offset and round-trip delay computed from all four timestamps with fractions, stratum and reference shown, replies validated (mode, originate timestamp, Kiss-o'-Death, unsynchronised servers), IPv6 support and correct dates after 2036.
- Daytime and RFC 868 Time: IPv6 support, complete reads, indicative offset.
- WhoIs: when querying whois.iana.org, the referral to the responsible registry is followed automatically; suggested servers include the regional registries, whois.nic.it and historic servers.
- Quote: suggested public QOTD servers (default djxmmx.net), followed by historic ones.
- Privacy: on every start, tighten configuration directories (current and legacy) to 0700 and the files inside them to 0600, fixing permissions left by earlier releases; symlinks and files owned by other users are left untouched.
- DNS: choose the record type (A, AAAA, CNAME, MX, NS, TXT, SOA, SRV, CAA, PTR, or all common records at once) and optionally a DNS server to ask; results show name, type, TTL and data, with clear messages for non-existent names and server failures. The previous address lookup through the system resolver remains the default.
- Port Scan: ports on each address are probed concurrently in batches, so a silent host costs about one timeout per batch instead of one per port; results are numbered by their position in the range and listed in address order.
- Print: the Print button now prints the page results on the default CUPS printer (`lp`), after confirmation showing the printer name; it reports when there is nothing to print, no printer is set or `lp` is missing.
- Documentation: one installation guide for every supported release, from the current Xubuntu/Ubuntu back to 20.04 LTS, explaining why 20.04 is the oldest supported release; the outdated separate 20.04 guide is removed.
- Installer: `install-nettalabbo.sh` no longer hard-codes version 0.5.0-4; it installs the single `nettalabbo_<version>_all.deb` placed beside it and verifies that version.
- Packaging: new modules added to the .deb; `packaging/make_release.sh` builds the release package and SHA256SUMS; a test checks that every local module is packaged.

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
