# Install and upgrade Nettalabbo on Xubuntu and Ubuntu

## Which versions

Nettalabbo works on the current Xubuntu and Ubuntu release and on older releases back to 20.04 LTS, where it has been tested. The same package and the same commands are used on all of them. Releases older than 20.04 have not been tested, and we do not know whether Nettalabbo works there.

Other Ubuntu flavours (Kubuntu, Lubuntu, Ubuntu MATE and so on) use the same packages, so they should behave the same way, but they have not been tested specifically.

### Why 20.04 is the oldest supported release

- **Python 3.8.** Ubuntu 20.04 ships Python 3.8, and Nettalabbo is written to need nothing newer. Every new feature is checked against Python 3.8 before release.
- **Standard library only.** Nettalabbo uses Python's own library and the system's Tk toolkit. Nothing is installed with `pip`, so there are no extra versions to match.
- **Packages present in every release.** All the system tools it needs are in the official Ubuntu repositories from 20.04 onwards. Where a package changed name between releases, the package accepts either name (for example `bind9-dnsutils` or the older `dnsutils`).
- **Older releases** ship Python versions earlier than 3.8 and older system tools, so they are outside what Nettalabbo is built for.

Ubuntu 20.04 reached the end of standard support in May 2025. It still receives security updates only through Ubuntu Pro (ESM). Nettalabbo runs there, but the operating system itself is better kept up to date where possible.

## Install

Open a terminal in the folder containing the downloaded package (usually `~/Downloads`):

```bash
sudo apt update
sudo apt install ./nettalabbo_0.5.4-5_all.deb
```

APT reads the package's dependencies and installs everything that is missing in the same step. Internet access to the Ubuntu repositories is needed. The package does not download anything from third-party websites.

Required system packages: Python 3 (3.8 or newer), Python Tkinter, Ping, Traceroute, OpenSSH client, Telnet client, CA certificates, and `bind9-dnsutils` or `dnsutils` for the DNS tools.

Alternatively, place `install-nettalabbo.sh` in the same folder as the package and run `bash install-nettalabbo.sh`. It checks the package, installs it with APT and confirms the installed version.

### If something goes wrong

- If the graphical software installer keeps loading forever, or shows a generic icon and a "Proprietary" label before installation, close it and use the APT command above. Some versions of the graphical installer do not read local packages correctly; the icon and the MIT licence are shown correctly once Nettalabbo is installed.
- Do not use `dpkg -i` as a first attempt: it does not install dependencies.
- If APT reports an error, keep its full output to report the problem, after removing usernames or private paths.

## Run

Open Nettalabbo from the application menu, or run:

```bash
nettalabbo
```

## Updates

New versions keep the package name `nettalabbo`. Installing a newer `.deb` with the command above replaces the previous version and keeps your settings. When GitHub releases are published, Nettalabbo can also check for, download and verify new versions itself (see the About page); installing still asks for your password.

The package replaces earlier packages named `netlabbo`, `netlab-xubuntu` and `network-laboratory-xubuntu`. Settings saved by those versions are migrated on first start, and their permissions are tightened. Do not delete old configuration folders unless you want to lose those settings.

## Printing

The Print button sends the current results to the system's default printer through CUPS (the `lp` command, from the `cups-client` package, present by default on Xubuntu and Ubuntu desktops). If no default printer is set, use Save Output instead, or set a default printer in the system's Printers settings.

## Metadata and icon

The package includes an AppStream description, the MIT licence, a desktop launcher and application icons. How the icon and licence appear **before** installation depends on the graphical installer and cannot be controlled by the package.
