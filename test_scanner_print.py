"""Port probing, scanner row order and printing (offline, no real printer)."""
import os
import socket
import stat
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import nettalabbo


def listener():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(8)
    return sock


def free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class OpenPortsTest(unittest.TestCase):
    def test_finds_open_and_skips_closed(self):
        servers = [listener(), listener()]
        try:
            open_ports = sorted(s.getsockname()[1] for s in servers)
            closed = [free_port() for _ in range(5)]
            found = nettalabbo.open_tcp_ports('127.0.0.1', closed + open_ports, 1.0)
            self.assertEqual(found, open_ports)
        finally:
            for s in servers:
                s.close()

    def test_batches_larger_than_limit(self):
        servers = [listener() for _ in range(3)]
        try:
            ports = [s.getsockname()[1] for s in servers] + [free_port() for _ in range(40)]
            found = nettalabbo.open_tcp_ports('127.0.0.1', ports, 1.0, batch=8)
            self.assertEqual(found, sorted(s.getsockname()[1] for s in servers))
        finally:
            for s in servers:
                s.close()

    def test_silent_host_costs_one_timeout_per_batch(self):
        # 192.0.2.0/24 is reserved for documentation: connections never complete.
        started = time.monotonic()
        nettalabbo.open_tcp_ports('192.0.2.1', range(1000, 1064), 0.3)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_stop_and_bad_host(self):
        stop = threading.Event()
        stop.set()
        self.assertEqual(nettalabbo.open_tcp_ports('127.0.0.1', [free_port()], 1.0, stop), [])
        self.assertEqual(nettalabbo.open_tcp_ports('no-such-host.invalid', [80], 0.2), [])


class GuiCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.patch = patch.dict(os.environ, {'HOME': self.home.name})
        self.patch.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'No display: {exc}')
        self.root.withdraw()
        self.app = nettalabbo.App(self.root)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.patch.stop()
        self.home.cleanup()


class SortedRowsTest(GuiCase):
    def test_rows_follow_address_order(self):
        for number in (7, 2, 10, 3):
            self.app.add_sorted_row('Scanner', (number, f'10.0.0.{number}', '', '22 (SSH)'))
        tree = self.app.trees['Scanner']
        numbers = [int(tree.item(i)['values'][0]) for i in tree.get_children()]
        self.assertEqual(numbers, [2, 3, 7, 10])


class ScannerDefaultsTest(GuiCase):
    def test_default_port_range_is_accepted(self):
        self.app.scan_ports.set(True)
        self.assertEqual((self.app.scan_pstart.get(), self.app.scan_pend.get()), (1, 1024))
        with patch.object(nettalabbo.messagebox, 'showerror') as error, \
                patch.object(nettalabbo, 'open_tcp_ports', return_value=[]):
            self.app.execute_scan()
            for _ in range(40):
                self.root.update()
                if 'Scanner' not in self.app.tasks:
                    break
                time.sleep(0.05)
        error.assert_not_called()

    def test_too_many_ports_rejected(self):
        self.app.scan_ports.set(True)
        self.app.scan_pend.set(nettalabbo.MAX_SCAN_PORTS + 1)
        with patch.object(nettalabbo.messagebox, 'showerror') as error:
            self.app.execute_scan()
        error.assert_called_once()


class LayoutTest(GuiCase):
    def test_footer_visible_at_start(self):
        self.root.deiconify()
        for page in ('Overview', 'Legacy Navigator', 'Diagnose'):
            self.app.select_page(page)
            self.root.update()
            footer = [w for w in self.root.winfo_children() if isinstance(w, tk.Frame)][-1]
            self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), self.root.winfo_height(), page)


class TerminalKeysTest(GuiCase):
    def send_key(self, keysym, ctrl=False, char=''):
        sent = []

        class Session:
            def send(self, data):
                sent.append(data)

        class Event:
            pass
        event = Event()
        event.keysym, event.state, event.char = keysym, (0x4 if ctrl else 0), char
        self.app.remote_sessions['Telnet'] = Session()
        try:
            result = self.app.remote_key('Telnet', event)
        finally:
            self.app.remote_sessions['Telnet'] = None
        return sent, result

    def test_control_symbols_reach_the_remote_client(self):
        self.assertEqual(self.send_key('bracketright', ctrl=True)[0], ['\x1d'])  # telnet escape
        self.assertEqual(self.send_key('backslash', ctrl=True)[0], ['\x1c'])
        self.assertEqual(self.send_key('bracketleft', ctrl=True)[0], ['\x1b'])
        self.assertEqual(self.send_key('d', ctrl=True)[0], ['\x04'])
        self.assertEqual(self.send_key('a', char='a')[0], ['a'])

    def test_status_changes_when_session_produces_output(self):
        created = {}

        class FakeSession:
            def __init__(self, on_text, on_exit):
                created['on_text'] = on_text

            def start(self, command):
                pass

        self.app.inputs['Telnet_host'].set('127.0.0.1')
        with patch.object(nettalabbo, 'PtySession', FakeSession), \
                patch.object(nettalabbo.messagebox, 'askokcancel', return_value=True), \
                patch.object(nettalabbo, 'connection_command', return_value=['true']):
            self.app.connect_remote('Telnet')
            created['on_text']('Connected to 127.0.0.1.\r\n')
            for _ in range(10):
                self.root.update()
                time.sleep(0.02)
        self.assertIn('Session running', self.app.footer_status.get())
        self.assertIn('Session running', self.app.remote_status['Telnet'].get())
        self.app.remote_sessions['Telnet'] = None


class PrintTest(GuiCase):
    def fake_tools(self, folder, default='Office_Laser'):
        bin_dir = Path(folder)
        log = bin_dir / 'printed.txt'
        (bin_dir / 'lp').write_text(f'#!/bin/sh\necho "$@" > "{log}.args"\ncat > "{log}"\necho "request id is {default}-1 (1 file(s))"\n')
        answer = f'system default destination: {default}' if default else 'no system default destination'
        (bin_dir / 'lpstat').write_text(f'#!/bin/sh\necho "{answer}"\n')
        for name in ('lp', 'lpstat'):
            (bin_dir / name).chmod(stat.S_IRWXU)
        return log

    def run_print(self, page='Ping', confirm=True, default='Office_Laser'):
        with tempfile.TemporaryDirectory() as folder:
            log = self.fake_tools(folder, default)
            env = {'PATH': f'{folder}{os.pathsep}' + os.environ.get('PATH', '')}
            with patch.dict(os.environ, env), \
                    patch.object(nettalabbo.messagebox, 'askyesno', return_value=confirm) as ask, \
                    patch.object(nettalabbo.messagebox, 'showerror') as error, \
                    patch.object(nettalabbo.messagebox, 'showinfo') as info:
                self.app.print_output(page)
                for _ in range(60):
                    self.root.update()
                    if log.exists() and Path(f'{log}.args').exists():
                        break
                    time.sleep(0.05)
                time.sleep(0.1)
                self.root.update()
                printed = log.read_text() if log.exists() else None
                args = Path(f'{log}.args').read_text() if Path(f'{log}.args').exists() else ''
            return printed, args, ask, error, info

    def test_prints_after_confirmation(self):
        self.app.add_row('Ping', ('1', '127.0.0.1', '', '0.05 ms'))
        printed, args, ask, error, _info = self.run_print()
        self.assertIn('127.0.0.1', printed)
        self.assertIn('Nettalabbo Ping', args)
        self.assertIn('Office_Laser', ask.call_args[0][1])
        error.assert_not_called()

    def test_nothing_sent_when_declined(self):
        self.app.add_row('Ping', ('1', '127.0.0.1', '', '0.05 ms'))
        printed, _args, _ask, _error, _info = self.run_print(confirm=False)
        self.assertIsNone(printed)

    def test_no_default_printer(self):
        self.app.add_row('Ping', ('1', '127.0.0.1', '', '0.05 ms'))
        printed, _args, ask, error, _info = self.run_print(default='')
        self.assertIsNone(printed)
        ask.assert_not_called()
        error.assert_called_once()

    def test_empty_page(self):
        printed, _args, ask, _error, info = self.run_print()
        self.assertIsNone(printed)
        ask.assert_not_called()
        info.assert_called_once()


if __name__ == '__main__':
    unittest.main()
