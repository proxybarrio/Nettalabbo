"""Offline automated checks for SSH/Telnet tab support (no external hosts)."""
import threading
import time
import unittest
from unittest.mock import patch
from remote_terminal import connection_command, valid_endpoint, PtySession, TerminalScreen

class RemoteTests(unittest.TestCase):
    def test_valid_endpoint(self):
        self.assertEqual(valid_endpoint('example.org', '22'), ('example.org',22))
        self.assertEqual(valid_endpoint('2001:db8::1', 2222), ('2001:db8::1',2222))
        for host,port in [('-oStrictHostKeyChecking=no',22), ('some host',22), ('ok\nbar',22), ('a',0), ('a',65536)]:
            with self.assertRaises(ValueError): valid_endpoint(host,port)

    @patch('remote_terminal.shutil.which')
    def test_ssh_argv_protected(self, which):
        which.return_value = '/usr/bin/ssh'
        cmd = connection_command('SSH','example.org',2222,'alice')
        self.assertEqual(cmd[-1], 'example.org')
        self.assertEqual(cmd[-3:-1], ['-l','alice'])
        self.assertIn('StrictHostKeyChecking=ask', cmd)
        with self.assertRaises(ValueError):
            connection_command('SSH','example.org',22,'-oProxyCommand=bad')

    @patch('remote_terminal.shutil.which')
    def test_telnet_argv(self, which):
        which.return_value = '/usr/bin/telnet'
        self.assertEqual(connection_command('Telnet','example.org',23), ['/usr/bin/telnet','example.org','23'])

    def test_ansi_screen_and_stream(self):
        screen = TerminalScreen()
        self.assertEqual(screen.feed('connecting\rconnected\nnext'), 'connectedg\nnext')
        self.assertEqual(screen.feed('\r\x1b[2Kdone'), 'connectedg\ndone')
        self.assertEqual(screen.feed('\x1b[2JReady\x1b[1;34m!'), 'Ready!')
        screen.feed('\x1b]0;secret-window-title\x07\nOK')
        self.assertEqual(screen.feed(''), 'Ready!\nOK')

    def test_ssh_style_controlling_terminal(self):
        """SSH authentication requires /dev/tty, not just redirected stdio."""
        import os
        if not __import__('shutil').which('setsid'):
            self.skipTest('util-linux setsid not available')
        out = []
        done = threading.Event()
        session = PtySession(out.append, lambda code: done.set())
        try:
            session.start(['/usr/bin/env', 'python3', '-u', '-c',
                           "import os; fd=os.open('/dev/tty', os.O_RDWR); print('CONTROLLING_TTY_OK', flush=True); os.close(fd)"])
            self.assertTrue(done.wait(10), ''.join(out))
            self.assertIn('CONTROLLING_TTY_OK', ''.join(out))
        finally:
            session.close()

    def test_local_pty_process(self):
        out = []
        hello = threading.Event()
        done = threading.Event()
        def on_text(value):
            out.append(value)
            if 'HELLO' in ''.join(out):
                hello.set()
        session = PtySession(on_text, lambda code: done.set())
        try:
            session.start(['/usr/bin/env','python3','-u','-c',
              'import sys; print("HELLO",flush=True); line=sys.stdin.readline(); print("ECHO:"+line.rstrip(),flush=True)'])
            self.assertTrue(hello.wait(10), ''.join(out))
            self.assertTrue(session.send('test123\n'))
            self.assertTrue(done.wait(10), ''.join(out))
            self.assertIn('ECHO:test123', ''.join(out))
        finally:
            session.close()

if __name__ == '__main__': unittest.main()
