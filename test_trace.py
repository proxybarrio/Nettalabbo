"""Offline regression tests for traceroute protocols, output, and error handling."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from nettalabbo import App

class Value:
    def __init__(self, value): self.value = value
    def get(self): return self.value

def app_for_trace(mode='Auto'):
    app=App.__new__(App)
    app.probe_vars={'Trace': {key: Value(value) for key,value in {
        'Resolve IP address':True,'Maximum hops':30,'Start from hop':1,
        'Timeout (s)':2,'Parallel Trace':False,'Delay (ms)':0,
        'Probe method':mode,'Data size':56}.items()}}
    app.tasks={'Trace':(threading.Event(),None)}
    app.failed_tasks=set()
    app.rows=[]
    app.post=lambda fn,*args: fn(*args)
    app.add_row=lambda page,row: app.rows.append(row)
    app.set_status=lambda page,text: None
    return app

class FakeProcess:
    def __init__(self, lines, code=0):
        self.stdout=iter(lines)
        self.returncode=code
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def poll(self): return self.returncode
    def terminate(self): self.returncode=-15
    def kill(self): self.returncode=-9
    def wait(self, timeout=None): return self.returncode

class TraceTests(unittest.TestCase):
    def test_parse_ipv4_name_ipv6_and_timeout(self):
        self.assertEqual(App.parse_trace_hop(' 1  gw.lan (192.0.2.1)  1.2 ms'), ('1','192.0.2.1','gw.lan','1.2 ms'))
        self.assertEqual(App.parse_trace_hop(' 2  2001:db8::1  3.4 ms'), ('2','2001:db8::1','2001:db8::1','3.4 ms'))
        self.assertEqual(App.parse_trace_hop(' 3  *'), ('3','*','*','*'))
        self.assertIsNone(App.parse_trace_hop('traceroute to example.net'))
    def test_default_icmp_and_manual_tcp_udp(self):
        for mode,flag in [('Auto','-I'),('ICMP','-I'),('TCP','-T'),('UDP',None)]:
            a=app_for_trace(mode)
            with patch.object(App,'traceroute_supports',return_value=True):
                cmd,_=a.build_probe_command('Trace','example.org')
            self.assertIn('example.org',cmd)
            if flag:self.assertIn(flag,cmd)
            else:
                self.assertNotIn('-I',cmd)
                self.assertNotIn('-T',cmd)
    def test_zero_responses_are_failure(self):
        a=app_for_trace('UDP')
        cmd=['traceroute','-q','1','example.org','56']
        with patch('nettalabbo.shutil.which',return_value='/usr/bin/traceroute'),patch('nettalabbo.subprocess.Popen',return_value=FakeProcess(['traceroute to example.org\n',' 1 *\n',' 2 *\n'])):
            a.run_probe('Trace','example.org',cmd,True,a.tasks['Trace'][0])
        self.assertIn('Trace',a.failed_tasks)
        self.assertTrue(any('No reply received' in str(row) for row in a.rows))
    def test_auto_tcp_fallback(self):
        a=app_for_trace()
        cmd=['traceroute','-q','1','-I','example.org','56']
        attempted=[]
        def run(argv,**kwargs):
            attempted.append(argv)
            return FakeProcess([' 1 *\n'] if '-I' in argv else [' 1 192.0.2.1 1.1 ms\n'])
        with patch('nettalabbo.shutil.which',return_value='/usr/bin/traceroute'),patch.object(App,'traceroute_supports',return_value=True),patch('nettalabbo.subprocess.Popen',side_effect=run):
            a.run_probe('Trace','example.org',cmd,True,a.tasks['Trace'][0])
        self.assertEqual(len(attempted),2)
        self.assertIn('-T',attempted[1]); self.assertNotIn('-I',attempted[1])
        self.assertNotIn('Trace',a.failed_tasks)
    def test_missing_executable_is_failure(self):
        a=app_for_trace()
        with patch('nettalabbo.shutil.which',return_value=None):
            a.run_probe('Trace','example.org',['traceroute'],True,a.tasks['Trace'][0])
        self.assertIn('Trace',a.failed_tasks)

if __name__=='__main__': unittest.main()
