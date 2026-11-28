# Nettalabbo

**Network Laboratory app for Xubuntu and other Ubuntu systems**

**Current version:** 0.5.5 (Debian packaging revision 2)  
**Status:** experimental / active testing  
**Platform:** Xubuntu and other Ubuntu-based Linux systems  
**Written by:** Proxybarrio, with AI-assisted development  
**Licence:** MIT

Nettalabbo is an independent, open source desktop network laboratory. It brings classic Internet diagnostics, modern domain and mail inspection, and clients for historic or alternative Internet protocols into one practical application with a retro-inspired visual identity.

## What you can do

| Area | Tools | Notes |
| --- | --- | --- |
| Domain research | Domain Inspector, DNS, Raw WHOIS | RDAP/WHOIS discovery depends on the relevant registry's public services and policies. |
| Network checks | Ping, Trace, Port Scan | System utilities and target network permissions determine available capabilities. |
| Mail systems | Mail Server Inspector | MX and limited SMTP recipient acceptance testing; **never proof of mailbox existence**. |
| Remote access | SSH, Telnet | SSH uses the system OpenSSH client. Telnet is unencrypted. |
| Classic services | Finger, Time, Quote | Availability depends on public servers, many of which are historic. |
| Alternative networks | Gopher, Gophers, Gemini, Spartan, Nex, NNTP, DICT, FTP, and others | Capabilities vary; some protocols have limited or experimental support. |
| Application | Info, Options, About | Includes an independent project credit and testing notice. |

### Alternative-network browser

The alternative-network viewer supports **coloured, permanently underlined hyperlinks** in menus and supported text documents, including URLs found inside plain text. Click a link to navigate, or use **Links**, **Go / Enter**, **Back**, **Forward**, **Home** and **Stop**. Switch between **Rendered** and **Raw** to inspect the original response when available. External web links require confirmation. Some experimental protocols have limited rendering or lack complete interoperability.

For supported and planned protocols, see [LEGACY_PROTOCOLS.md](LEGACY_PROTOCOLS.md). For reference servers, see [HISTORIC_SERVERS.md](HISTORIC_SERVERS.md).

## Install or upgrade on Xubuntu

Download the `.deb` release and, from its directory, run:

```bash
sudo apt update
sudo apt install ./nettalabbo_0.5.5-2_all.deb
```

APT resolves and installs required system packages from your configured Ubuntu repositories. The package uses the identity `nettalabbo` and replaces packages previously named `netlabbo`, `network-laboratory-xubuntu` or `netlab-xubuntu`, preserving personal configuration files for migration. Launch the app from the Xubuntu menu or run:

```bash
nettalabbo
```

Nettalabbo works on the current Xubuntu and Ubuntu release and on older releases back to 20.04 LTS, where it has been tested. Releases older than 20.04 have not been tested. Ubuntu 20.04 is outside standard security support; keep it covered by extended security maintenance if you use it for network work.

See [INSTALL_XUBUNTU.md](INSTALL_XUBUNTU.md) and [UPGRADE_POLICY.md](UPGRADE_POLICY.md).

## New in 0.5.5

- **Newsgroups:** a three-pane Usenet reader in the tradition of the Netscape and SeaMonkey news readers: groups, threaded discussions and messages, replies with quoting and new posts. Ready-made public servers (Paganini, Gmane, the Linux kernel lists, Rocksolid, Eternal September, NNTP4) and your own servers; anonymous or with a user name and password, with or without TLS. A password is saved only if you ask.
- **Legacy Navigator:** a start page that explains every service in plain words, with clickable examples.

## New in 0.5.4

- **Diagnose:** DNS and mail configuration assessment (MX, SPF, DMARC, DKIM selector, MTA STS, TLS RPT). Optional SMTP connectivity and domain/IP DNSBL queries require consent. DNSBL access errors and indeterminate responses are not treated as clean reputation; a successful result does not guarantee email delivery.
- **SSH and Telnet:** ANSI colour presentation and additional limits for hostile cursor sequences; this is **not** a full xterm emulator.
- **Legacy Navigator:** optional Classic, Dark and Monochrome colours without changing clickable links, history or original Raw responses.
- All features require live validation on Xubuntu and suitable test servers before a public release.

## Important limitations

- This is a **test release**, not production-ready software. Known and unknown bugs may affect reliability.
- A successful SMTP `RCPT TO` response is not proof an email address exists; a rejection can have causes other than nonexistence. See [MAIL_INSPECTOR.md](MAIL_INSPECTOR.md).
- Port scanning and SMTP probes should only be used where you have permission and a legitimate reason.
- Server availability and protocol support can change without warning. Historical entries are examples, not uptime guarantees.
- Telnet transfers data and credentials without encryption. Prefer SSH where supported.
- Some legacy protocol clients are experimental, incomplete or documented as potential future work. See [LEGACY_PROTOCOLS.md](LEGACY_PROTOCOLS.md).
- Installers that do not use APT to resolve local `.deb` dependencies may be unable to install the application automatically.

## Feedback and development

Feedback, bug reports and contributions are welcome via the **Proxybarrio/Nettalabbo** GitHub repository. Please report sensitive security vulnerabilities privately by email rather than publicly. Please include the Nettalabbo version, Xubuntu/Ubuntu version, exact steps and diagnostic output, removing usernames, passwords and other sensitive information first.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and [ROADMAP.md](ROADMAP.md).

## About, project story and legal notices

Open **About Nettalabbo** from the application sidebar. You can click **Why Nettalabbo? 🤌🏻**, **Credits & Legal Terms**, **Experimental Software & Disclaimer**, or **Read full MIT License**. Each item opens a complete, scrollable, read-only document, locally installed with the program and available offline.

For the same text in this repository, see [WHY_NETTALABBO.md](WHY_NETTALABBO.md), [CREDITS.md](CREDITS.md), [DISCLAIMER.md](DISCLAIMER.md) and [LICENSE](LICENSE).

**Contact:** proxybar@gmail.com. Please do not include confidential or identifying information in public bug reports.

## Credit and independence

**Created by Proxybarrio, with AI-assisted development.** The project is released under the [MIT License](LICENSE).

Nettalabbo is freely inspired by the *idea* of an accessible network toolkit, including the historical **NetLab / NetLab95** for Windows, created in the 1990s by **Alexander Danileiko**. It is a personal tribute, not an official Linux port or continuation. Nettalabbo is independently implemented and is **not affiliated with or endorsed by the original author or rights holders**. No original NetLab code, executable, artwork or manual is redistributed.

See [CREDITS.md](CREDITS.md) and [PROVENANCE.md](PROVENANCE.md) for the full statement.

## Contact

Feedback and bug reports: [proxybar@gmail.com](mailto:proxybar@gmail.com)
