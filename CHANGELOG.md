## 0.5.4 Debian revision 4 (22 November 2026)

- Legacy Navigator: adjustable text size with A− / A+ (and Ctrl + / Ctrl − / Ctrl 0), 8 to 28 points, default raised from 10 to 12, remembered between sessions; the text stays monospaced so Gopher menus and ASCII art stay aligned.
- Legacy Navigator: Gopher file items (images, archives, binaries, sound, PDF), Gopher documents containing binary data and Gemini non-text responses are handled as files up to 20 MB instead of being shown as garbled text: name, type and size, Save file, GIF/PNG preview in the page, hex dump in Raw, incomplete downloads clearly marked.
- Gemini: status 10 and 11 input requests now ask the question (11 with hidden typing) and repeat the request with the answer, so Gemini search engines work; cancelling is reported.
- Gemini: very large text pages are shown up to 300 KB so the window stays responsive.

## 0.5.4 Debian revision 3 (22 November 2026)

- Trace: new built-in tracer for the Auto, UDP and ICMP methods. It works for normal users on every supported Ubuntu release, without root rights and without depending on the installed traceroute version. Before, the default ICMP method ran `traceroute -I`, which as a normal user either needs privileges or, with some traceroute versions and kernels, returns only asterisks.
- Trace: Auto sends UDP and, where the system allows unprivileged ICMP, ICMP echo probes together and keeps the first answer per hop; two tries per hop; hops answered in parallel are listed in order.
- Trace: stops at the destination, at an unreachable answer (with an explanation of !N, !H, !P, !X), or after 8 consecutive silent hops (likely a firewall), instead of printing asterisks up to the maximum.
- Trace: a host reachable only over IPv6 on a computer without IPv6 is explained instead of failing; TCP (still the external traceroute, administrator rights required) suggests Auto when privileges are missing.
- Fix: a failure in a table page (Ping, Trace, Port Scan) is now shown as a table row; before, the message went to a text area those pages do not have, so nothing appeared.

## 0.5.4 Debian revision 2 (22 November 2026)

- Packaging: the source and the .deb no longer include internal pre-release working notes; the README ends with the project contact.
- Verification: the package name in the GitHub workflow is read from packaging/control, and the workflow fails if internal review notes are ever packaged again.
- No application feature changes.

## 0.5.4 Debian revision 1 (19 November 2026)

- Diagnose: DNS and mail checks for A, AAAA, MX, SPF, DMARC, optional DKIM selector, MTA STS and TLS RPT; SMTP connectivity and DNSBL require explicit opt in.
- Mail policy review distinguishes publication from verification; duplicate/invalid policies and provider access errors receive explicit statuses.
- SSH and Telnet: ANSI 16/256/true-colour rendering; cursor and scrollback hardening. A complete terminal emulator is not claimed.
- Legacy Navigator: Classic, Dark and Monochrome palettes without changing links, Back/Forward/Home/Stop or Raw view.
- Updates: a redirect away from GitHub is now rejected before any request is sent to the new host, not only checked afterwards.
- Diagnose: SPF review accepts CIDR lengths on `a` and `mx` (for example `a/24`, `mx:host/24`) and ignores unknown modifiers as RFC 7208 requires; TXT values without quotes are read correctly.
- Diagnose (after live testing against local DNS, SMTP and DNSBL test servers): MTA-STS and TLS-RPT records are read without quotes and checked for the right version and duplicates; an untrusted STARTTLS certificate is reported as a warning with an explanation; a refused port 25 mentions that many providers block it; a skipped IP blacklist check is now stated; multi-line results are indented; the page no longer repeats its title.
- Port Scan: the default port range 1-1024 is now accepted (the limit was 128 ports, so enabling Scan Ports with the defaults showed an error); the limit is now 1024 ports, made practical by concurrent probing.
- Window: the status bar with Help and Quit was hidden at the default window size (the content needed 953 pixels in an 820-pixel window); it is now always visible, and the first window size fits smaller laptop screens.
- Updates: a failed automatic check counts as the daily check, so an unreachable release page is not contacted at every start.
- SSH: the information line no longer gets cut off; DNS page description mentions record types.
- Telnet: 14 more public Telnet services in the server catalogue (MapSCII world map, Star Wars ASCII animation over IPv6, Wikipedia over Telnet, Doom, a classic Mac desktop demo, Galacticomm and Archaic Binary BBS, Legend of the Red Dragon, Achaea, Avalon, ZombieMUD, Igor MUD, Forgotten Kingdoms), each with its source; listed as online by telnet.org in November 2026, not a live availability guarantee.
- SSH and Telnet: Ctrl with symbol keys now reaches the remote side, so Ctrl+] opens the telnet> escape prompt (and Ctrl+backslash, Ctrl+[ work); the status line changes from "Connecting" to "Session running" when the session produces output.
- Verification: a second GitHub Actions job runs every test inside Ubuntu 20.04 with its own Python 3.8 and Tk, then installs the built package with APT and starts it.
- Legal: a third-party services notice in the server catalogue, DISCLAIMER.md, CREDITS.md and HISTORIC_SERVERS.md: listed BBS, games and other services are run independently by their operators; Nettalabbo only connects to them and does not guarantee that they hold the licences or rights for what they offer.
- Packaging: GitHub Actions builds the .deb and SHA256SUMS on every push to main (workflow artifact) and publishes a GitHub Release for each new version.
- Added regression tests and verification workflow for the new components. Live network, SMTP, DNSBL and Xubuntu installation checks are still required before public release.

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
- Provenance and third-party notices bundled in the source archive and .deb.
- No application feature changes.

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
