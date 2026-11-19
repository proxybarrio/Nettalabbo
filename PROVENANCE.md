# Nettalabbo implementation and asset provenance

Nettalabbo is a new Python/Tkinter application. It is not a code fork of the historical NetLab/NetLab95 application.

## New work

- Application and network service modules: Python and Python standard library, written for this project.
- Main interface: independent sidebar navigation, Overview dashboard, workspaces and task panels. Historical executable dialog resources were not embedded or reused.
- Laboratory icon: original image developed for Nettalabbo through an AI-assisted creative process and approved by the project creator. The historical program's icons and bitmaps are not shipped.
- Help and credits: newly written for Nettalabbo.
- The original Windows program's files, images and manual are not included with the public source release or Debian package.

## External runtime programs

The program invokes operating system tools provided by Ubuntu packages, including OpenSSH, ping, traceroute and telnet. Those tools retain their respective licences; they are separate system dependencies and are not relicensed by the Nettalabbo MIT licence.

## History and identification

The historical NetLab name is used in CREDITS.md for attribution and comparison, not for branding or to claim an official relationship. The development team should keep this separation for future releases.

This documentation records development intent and checks; it is not a legal clearance opinion or a guarantee against an intellectual property claim. Before a larger public release, independent legal review of naming and distribution may be prudent.

## Scope of the 19 November 2026 source audit

The source archive `nettalabbo-source-0.5.3-rev2.zip` was examined alongside
the supplied `netlab14.zip` archive. None of the 62 current source files
matched the SHA-256 digest of any of the 18 archive entries from the original
NetLab 1.4. File-format inspection found Python source, newly developed image
assets and project-specific documentation, not the old Windows executables or
historical help file. The current image `assets/nettalabbo_original.png` is
byte-for-byte identical to the Amiga-style image selected during this project's
image generation discussions.

These findings are evidence about the supplied artifacts only. They cannot
prove that no protected expression was ever copied, that AI-generated material
is fully protectable or exclusive, or that the product name clears all earlier
trade mark rights. Historic product functionality may be studied, but avoid
reproducing wording or layout that is distinctive and nonfunctional.