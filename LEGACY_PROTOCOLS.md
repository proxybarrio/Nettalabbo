# Legacy & Alternative Networks in Nettalabbo 0.5.3

The Legacy Navigator provides explicitly triggered and bounded protocol tools.
There is no automatic browsing at startup and no remote code execution.

### Hypertext navigation in version 0.5.3

Gopher menus and Gemtext-based documents render text with **permanently
underlined** links: blue for directories, green for text documents and orange
for external destinations. Links can be opened directly by clicking them or
through the **Links** dropdown at the top right. The status strip shows their
URL on hover. Use **Go/Enter**, **Back**, **Forward**, **Home** and **Stop**;
**Rendered** / **Raw** toggles formatting without requesting the page again.
Links to HTTP/HTTPS sites are opened externally only with confirmation.
'Raw' shows the actual response bytes when retained or explicitly warns when
only the decoded body is available. 'Stop' closes active sockets used by the
common TCP adapter; other adapters use bounded network timeouts.


## Present in Nettalabbo

* Gopher/Gophers, Gemini, Spartan, Nex, Scroll, Finger, NNTP, anonymous FTP,
  DICT, Guppy, TEXT and Mercury: limited read clients, as in v0.4.0.
* Scorpion (`scorpion://`, port 1517): **experimental read-only R-subprotocol**,
  with plaintext transport. A `scorpions://` variant allows TLS testing.
  A successful status line does not imply full Scorpion document rendering.
* Molerat (`molerat://`, port 2693): **experimental read-only GET** over TLS,
  based on v0.1.0 alpha specification; parse content and response headers.
  No PUT/DEL, interactive forms or authentication; limited interoperability.
* Titan (`titan://`, port 1965): a separate **explicit file upload** button,
  not a Browse operation. It asks the user to choose and confirm a nonempty file,
  at most 256 KiB, before initiating TLS. It never sends a zero-byte upload
  because that may delete content. Only tokenless MIME `application/octet-stream`
  uploads are offered initially; server-specific upload tokens and advanced
  editing are not supported. This is experimental and should be used only with
  authorised destinations.
* SSH/Telnet: the existing remote terminal panels, not part of the read client.

## Could be implemented in future releases

* Terse (`terse://`): **not implemented**. Public references use the name for
  unrelated formats and services, but no verified, interoperable small-web
  transport specification was identified. A client must not guess its wire
  format. Continue investigating and add only after confirming the protocol.
* Full Scorpion and Molerat feature sets (beyond read-only retrieval), including
  richer metadata, negotiated security options and write operations.
* Titan token-based uploads, approved deletion workflows, client certificates,
  transfer progress, and custom MIME types.
* Gemini and alternative-web document rendering beyond the current plain text.

## Original technical references

* Titan protocol: https://transjovian.org/titan and https://docs.rs/gemini-protocol/latest/gemini_protocol/titan/index.html
* Scorpion specification and reference software: https://github.com/zzo38/scorpion
* Molerat protocol v0.1.0 alpha: https://molerat.trinket.icu/v0-1-0-alpha
* Gemini: https://gemini.flounder.online/docs/specification.gmi
* Gopher RFC 1436: https://www.rfc-editor.org/rfc/rfc1436
* NNTP RFC 3977: https://www.rfc-editor.org/rfc/rfc3977
* DICT RFC 2229: https://www.rfc-editor.org/rfc/rfc2229

Notes: these are public protocol descriptions, not copied source code. Tests
have been performed against local synthetic servers or mocked transports, not
against the full range of live servers. Trust-on-first-use pins are an explicit
user decision when system certificate validation fails; they are not a guarantee
of authenticity for a first visit.

### Inline URL recognition (0.5.3)
Plain text response documents from Gopher, Finger, DICT, NNTP, and other read clients show supported URLs as coloured and underlined hyperlinks. These appear in the Links menu. HTTP(S) destinations require confirmation before launching the system browser. No arbitrary URL scheme is executed. Raw view preserves the original response.