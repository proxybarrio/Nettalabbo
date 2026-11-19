"""Checks for conservative terminal clipboard and traceroute compatibility."""
import pathlib
import types
import unittest
from unittest import mock

import nettalabbo

class TraceCompatibilityTests(unittest.TestCase):
    def test_unsupported_flags_omitted(self):
        app = nettalabbo.App.__new__(nettalabbo.App)
        def setting(num): return types.SimpleNamespace(get=lambda: num)
        app.probe_vars={'Trace': {
            'Resolve IP address': setting(True),
            'Maximum hops': setting(30), 'Start from hop': setting(1),
            'Timeout (s)': setting(2), 'Data size': setting(56),
            'Parallel Trace': setting(True), 'Delay (ms)': setting(1000)}}
        with mock.patch.object(app, 'traceroute_supports', return_value=False):
            cmd, resolve = app.build_probe_command('Trace', 'example.org')
        self.assertTrue(resolve)
        self.assertEqual(cmd[0], 'traceroute')
        self.assertNotIn('-N', cmd)
        self.assertNotIn('-z', cmd)
        self.assertEqual(cmd[-2:], ['example.org', '56'])

    def test_supported_parallel_flag(self):
        app = nettalabbo.App.__new__(nettalabbo.App)
        def setting(num): return types.SimpleNamespace(get=lambda: num)
        app.probe_vars={'Trace': {
            'Resolve IP address': setting(True), 'Maximum hops': setting(30),
            'Start from hop': setting(1), 'Timeout (s)': setting(2),
            'Data size': setting(56), 'Parallel Trace': setting(True),
            'Delay (ms)': setting(0)}}
        with mock.patch.object(app, 'traceroute_supports', return_value=True):
            cmd, _ = app.build_probe_command('Trace', 'example.org')
        self.assertIn('-N', cmd)
        self.assertNotIn('-z', cmd)

class TerminalSemanticsTests(unittest.TestCase):
    def test_ctrl_c_is_interrupt_even_with_selection(self):
        app = nettalabbo.App.__new__(nettalabbo.App)
        payloads=[]
        app.remote_sessions={'SSH': types.SimpleNamespace(send=payloads.append)}
        app.remote_consoles={'SSH': types.SimpleNamespace(tag_ranges=lambda name: ('1.0', '1.4'))}
        app.remote_copy=lambda page: self.fail('Ctrl+C must not copy in terminals')
        result=app.remote_key('SSH', types.SimpleNamespace(keysym='c', state=4, char='\x03'))
        self.assertEqual(result,'break')
        self.assertEqual(payloads,['\x03'])

    def test_source_has_right_click_copy(self):
        src=(pathlib.Path(nettalabbo.__file__)).read_text()
        self.assertIn('remote_context_menu', src)
        self.assertIn("text.bind('<Button-3>'", src)
        self.assertIn("text.bind('<Control-c>'", src)
        self.assertIn("self.activity_bar.start", src)
        self.assertIn("'Sample servers...'", src)

if __name__ == '__main__': unittest.main()
