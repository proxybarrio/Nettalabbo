# Mail Server Inspector 0.5.0

Nettalabbo provides **one-address-at-a-time**, manually initiated mail-server
checks. It does not claim to establish whether a person or mailbox exists.

## Inspect an address

1. Open **Mail systems > Mail Server Inspector**.
2. Enter a single conventional mailbox address (`person@example.org`).
3. Click **Inspect address**. The app asks DNS for MX records (`dig`, installed
   automatically by the Debian `dnsutils` dependency).
4. If there is no MX, it checks whether an A/AAAA fallback route exists, as
   allowed by SMTP. A published Null MX (`0 .`) is clearly identified.
5. Optionally tick the **single-recipient SMTP test** and confirm the warning.
   The app contacts at most three published MX hosts **until one responds**, and
   sends `EHLO`, an empty `MAIL FROM` and **one** `RCPT TO` for the manually
   entered address. It never sends `DATA`, a message body, or `VRFY`/`EXPN`.

The SMTP result has **no definitive exists/does-not-exist label**. A 2xx
response means the server accepted the recipient at that point in a transaction,
not that a mailbox exists or delivery will work. 4xx is transient; 5xx may
reflect user absence, sender policy, rate limiting, privacy restrictions, or
other rules. Catch-all domains, forwarding and delayed validation are common.
No guesses, bulk imports, random-address comparison or background probes exist.

Server operators can log SMTP commands. Use only where you have a legitimate
reason and respect their policies. Firewalls and mail providers frequently block
outbound TCP 25. The tool does not circumvent such controls.

## Test a mail protocol service

Select `SMTP`, `IMAP` or `POP3`, supply an explicit server hostname and port,
then press **Test server**. The default secure ports are SMTP 465, IMAP 993 and
POP3 995. This checks only the greeting or service handshake; SMTP's TLS
support is negotiated where offered. There is **no login**, no password storage
and no attempt to list mailboxes. A mail exchanger (MX host) is not necessarily
the host for POP3 or IMAP, so the program does not fill these fields from MX.

## Privacy and limitations

No telemetry, address lists or automatic background checks. Addresses are not
persisted in settings or saved to a server; the user can save a report locally.
A network server necessarily sees the query that reaches it. Server diagnostics
may reveal the test host and TLS capabilities. DNS outcomes are not cached here.

Standards: RFC 5321 (SMTP), RFC 7505 (Null MX), RFC 9051 (IMAP), RFC 1939
(POP3). Tests use mock DNS and an isolated loopback SMTP endpoint. Live public
SMTP/IMAP/POP3 tests must still be verified on the user's environment.
