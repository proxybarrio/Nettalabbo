"""Embedded, deliberately limited line-oriented terminals for Nettalabbo.

OpenSSH and telnet handle the network protocols and authentication;
this module provides a Linux pseudo-terminal bridge and a basic ANSI screen.
Passwords, typed commands and terminal transcripts are not written to disk.
"""
from __future__ import annotations

import codecs
import fcntl
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import termios
import threading

HOST_PATTERN = re.compile(r'[A-Za-z0-9_.:\-\[\]]{1,253}\Z')
USER_PATTERN = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')


def valid_endpoint(host: str, port: int) -> tuple[str, int]:
    host = host.strip()
    if not HOST_PATTERN.fullmatch(host) or host.startswith('-') or host.startswith('.'):
        raise ValueError('Enter a valid host, IPv4 / IPv6 address, or SSH host alias.')
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError('Port must be a number.') from None
    if not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535.')
    return host, port


def connection_command(protocol: str, host: str, port: int, user: str = '', key: str = '') -> list[str]:
    host, port = valid_endpoint(host, port)
    if protocol == 'SSH':
        exe = shutil.which('ssh')
        if not exe:
            raise FileNotFoundError('OpenSSH is unavailable. Install openssh-client.')
        args = [exe, '-tt', '-o', 'StrictHostKeyChecking=ask',
                '-o', 'ConnectTimeout=12', '-o', 'ForwardAgent=no',
                '-o', 'ForwardX11=no', '-p', str(port)]
        user = user.strip()
        if user:
            if not USER_PATTERN.fullmatch(user) or user.startswith('-'):
                raise ValueError('SSH username contains unsupported characters.')
            args.extend(['-l', user])
        if key.strip():
            from pathlib import Path
            path = Path(key.strip()).expanduser()
            if not path.is_file():
                raise ValueError('The selected SSH key file does not exist.')
            args.extend(['-i', str(path)])
        args.append(host)
        return args
    if protocol == 'Telnet':
        exe = shutil.which('telnet')
        if not exe:
            raise FileNotFoundError('Telnet client is unavailable. Install telnet.')
        return [exe, host, str(port)]
    raise ValueError('Unsupported connection protocol.')


class PtySession:
    """One SSH or Telnet process, attached to a pseudo-terminal.

    on_text and on_exit are invoked from a background thread. Callers must
    dispatch GUI updates to their main GUI thread.
    """

    def __init__(self, on_text, on_exit):
        self.on_text = on_text
        self.on_exit = on_exit
        self.stop_event = threading.Event()
        self._lock = threading.RLock()
        self._proc = None
        self._master = None
        self._thread = None

    def start(self, argv: list[str]):
        if self._thread is not None:
            raise RuntimeError('Session is already started.')
        self._thread = threading.Thread(target=self._run, args=(argv,), daemon=True)
        self._thread.start()

    def _run(self, argv):
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        master = slave = None
        proc = None
        try:
            master, slave = pty.openpty()
            # Reasonable terminal dimensions for ordinary shell commands.
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 120, 0, 0))
            # OpenSSH reads passwords and host-key confirmations from /dev/tty.
            # Merely connecting stdio to the PTY is not sufficient: the child
            # must have the PTY as its *controlling terminal*. util-linux setsid
            # provides this without the unsafe preexec_fn in a threaded Tk app.
            setsid_exe = shutil.which('setsid')
            command = ([setsid_exe, '--ctty', '--wait'] + argv) if setsid_exe else argv
            proc = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                                    close_fds=True, start_new_session=not bool(setsid_exe),
                                    env={**os.environ, 'TERM': 'vt100'})
            os.close(slave)
            slave = None
            with self._lock:
                self._proc, self._master = proc, master
            while not self.stop_event.is_set():
                if proc.poll() is not None:
                    # Read any final buffered output before reporting exit.
                    ready, _, _ = select.select([master], [], [], 0.08)
                    if not ready:
                        break
                else:
                    ready, _, _ = select.select([master], [], [], 0.15)
                if ready:
                    try:
                        block = os.read(master, 8192)
                    except OSError:
                        break
                    if not block:
                        break
                    decoded = decoder.decode(block)
                    if decoded:
                        self.on_text(decoded)
            tail = decoder.decode(b'', final=True)
            if tail:
                self.on_text(tail)
            if proc.poll() is None:
                if self.stop_event.is_set():
                    self._terminate(proc)
                else:
                    proc.wait(timeout=1)
            self.on_exit(proc.returncode)
        except Exception as exc:
            self.on_text(f'\r\n[Session error: {exc}]\r\n')
            self.on_exit(None)
        finally:
            if proc is not None and proc.poll() is None:
                self._terminate(proc)
            with self._lock:
                self._proc = self._master = None
            for fd in (master, slave):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def send(self, value: str):
        with self._lock:
            if self.stop_event.is_set() or self._master is None:
                return False
            try:
                os.write(self._master, value.encode('utf-8'))
                return True
            except OSError:
                return False

    @staticmethod
    def _terminate(proc):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=1.2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass

    def close(self):
        self.stop_event.set()
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            # Close is called on the Tk event loop: avoid blocking it.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


class TerminalScreen:
    """Basic ANSI-aware text screen for SSH/Telnet, not a complete VT emulator.

    Supports output, carriage return, cursor movement, clearing and escape
    removal. Full screen interactive curses apps aren't guaranteed to render.
    """

    def __init__(self, max_lines: int = 1200):
        self.max_lines = max_lines
        self.lines = [[]]
        self.x = self.y = 0
        self.mode = 'text'
        self.params = ''

    def clear(self):
        self.lines = [[]]
        self.x = self.y = 0
        self.mode = 'text'
        self.params = ''

    def _row(self):
        while self.y >= len(self.lines):
            self.lines.append([])
        while len(self.lines) > self.max_lines:
            self.lines.pop(0)
            self.y -= 1

    def _put(self, char):
        self._row()
        if self.x > 300:
            return
        row = self.lines[self.y]
        while len(row) < self.x:
            row.append(' ')
        if len(row) == self.x:
            row.append(char)
        else:
            row[self.x] = char
        self.x += 1

    def _csi(self, seq, cmd):
        if seq.startswith('?'):
            return  # display modes / bracketed paste
        args = [int(a) if a.isdigit() else 0 for a in seq.split(';') if a == '' or a.isdigit()]
        n = (args[0] if args else 0)
        if cmd == 'K':
            self._row()
            row = self.lines[self.y]
            if n == 2:
                self.lines[self.y] = []
            elif n == 1:
                row[:self.x + 1] = [' '] * min(self.x + 1, len(row))
            else:
                del row[self.x:]
        elif cmd == 'J' and n in (2, 3):
            self.clear()
        elif cmd == 'A': self.y = max(0, self.y - (n or 1))
        elif cmd == 'B': self.y += (n or 1)
        elif cmd == 'C': self.x = min(300, self.x + (n or 1))
        elif cmd == 'D': self.x = max(0, self.x - (n or 1))
        elif cmd in ('H', 'f'):
            self.y = max(0, (args[0] if args else 1) - 1)
            self.x = max(0, (args[1] if len(args) > 1 else 1) - 1)
        elif cmd == 'G': self.x = max(0, (n or 1) - 1)
        # Text styling (SGR), private modes and unhandled CSI are ignored.

    def feed(self, data):
        for ch in data:
            if self.mode == 'text':
                if ch == '\x1b': self.mode = 'esc'
                elif ch == '\r': self.x = 0
                elif ch == '\n': self.y += 1; self.x = 0; self._row()
                elif ch in ('\b', '\x7f'): self.x = max(0, self.x - 1)
                elif ch == '\t':
                    for _ in range(8 - self.x % 8): self._put(' ')
                elif ch.isprintable(): self._put(ch)
            elif self.mode == 'esc':
                if ch == '[': self.params = ''; self.mode = 'csi'
                elif ch == ']': self.mode = 'osc'
                elif ch in '()': self.mode = 'esc_one'
                elif ch == 'c': self.clear()
                else: self.mode = 'text'
            elif self.mode == 'esc_one': self.mode = 'text'
            elif self.mode == 'osc':
                if ch == '\x07': self.mode = 'text'
                elif ch == '\x1b': self.mode = 'osc_esc'
            elif self.mode == 'osc_esc': self.mode = 'text' if ch == '\\' else 'osc'
            elif self.mode == 'csi':
                if '@' <= ch <= '~':
                    self._csi(self.params, ch)
                    self.mode = 'text'
                elif len(self.params) < 48:
                    self.params += ch
                else: self.mode = 'text'
        return '\n'.join(''.join(line) for line in self.lines)
