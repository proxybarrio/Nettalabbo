# Legacy & Alternative Networks in Nettalabbo 0.5.5

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

### Reading size, files and questions (0.5.4)

* **Text size:** the **A−** and **A+** buttons (or Ctrl + / Ctrl − / Ctrl 0)
  change the reading size from 8 to 28 points; the default is 12 and the
  choice is remembered. The text stays monospaced, so Gopher menus and ASCII
  art stay aligned.
* **Files:** Gopher items of file types (5, 9, g, I, s, ;, d, p, P, <),
  Gopher documents that contain binary data, and Gemini responses with a
  non-text MIME type are treated as files, up to 20 MB, kept in memory until
  you choose **Save file** (or **Save**). GIF and PNG images are previewed in
  the page; other formats are offered for saving. **Raw** shows the first
  bytes as a hex dump. An incomplete download is clearly marked.
* **Gemini questions:** status 10 asks for text and status 11 for sensitive
  input (typed hidden); the answer is sent back as the URL query, as the
  Gemini specification requires. Cancelling leaves the page unchanged.

### Newsgroups reader (0.5.5)

`nntp://` addresses in the Navigator still give a quick read-only look at a
group. For real use there is the **Newsgroups** page: a three-pane reader
(groups, threads, message) that can also reply and post. It speaks NNTP as
described in RFC 3977, with AUTHINFO USER/PASS (RFC 4643) for accounts and
implicit TLS on port 563. Ready-made servers cover anonymous Usenet reading
(Paganini, Rocksolid), mailing lists as newsgroups (Gmane, lore.kernel.org)
and free accounts (Eternal September, NNTP4); any other server can be added.
Passwords are kept only for the session unless you choose to remember them.

### Services start page (0.5.4)

The Navigator opens on a page that explains each service in plain words and
groups it by what you can do: read it directly, try an experimental reader,
open an interactive terminal (Telnet and SSH), upload (Titan), or learn that it
is not available yet. A one-click index at the top jumps to each explanation,
and public examples open with a click. **☰ Services** returns to this page at
any time; **Home** does the same when the address bar is empty. The examples
are independent services run by third parties and may change or be offline.


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
