import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

import httpx

from alterecho.cli import parser
from alterecho.config import BridgeError
from alterecho.managed import background, control, down, local_status, metadata_path, read_metadata
from alterecho.server_settings import ServerSettings, ServerLease


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.port = free_port()
        self.env = patch.dict(os.environ, {'ALTERECHO_HOME': str(self.root),
            'ALTERECHO_TOKEN': 'managed-fixture-token-'+'x'*32, 'ALTERECHO_TOKEN_FILE': '',
            'ALTERECHO_HOST': '127.0.0.1', 'ALTERECHO_PORT': str(self.port),
            'ALTERECHO_ORIGINS': '', 'ALTERECHO_ALLOWED_HOSTS': '',
            'ALTERECHO_MANAGED_ID': '', 'ALTERECHO_MANAGED_SECRET': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.settings = ServerSettings.from_env()
        self.addCleanup(self.stop_owned)

    def stop_owned(self):
        meta = read_metadata(self.settings)
        if meta and control(meta):
            down()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'alterecho', *args], capture_output=True, text=True,
                              encoding='utf-8', timeout=50)

    def test_background_survives_launcher_exit_authenticated_ready_and_down(self):
        for args in (('serve',), ('serve', '--detach')):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                meta = read_metadata(self.settings)
                self.assertTrue(control(meta))
                self.assertNotEqual(meta['pid'], os.getpid())
                self.assertIn(str(meta['pid']), result.stdout)
                self.assertTrue(Path(meta['log']).is_file())
                if os.name == 'nt':
                    from tests.windows_console_probe import console_state
                    console = console_state(meta['pid'])
                    self.assertFalse(console['visible'], console)
                    if not console['attached']:
                        self.assertEqual(console['error'], 6, console)  # No console, not an inaccessible PID.
                with httpx.Client(base_url=meta['url'], trust_env=False) as client:
                    self.assertEqual(client.get('/api/v1/status').status_code, 401)
                    state = client.get('/api/v1/status', headers={'Authorization':'Bearer '+self.settings.token}).json()
                    self.assertEqual(state['managed']['pid'], meta['pid'])
                    self.assertNotIn('secret', json.dumps(state))
                    self.assertEqual(client.post('/api/v1/shutdown', json={}, headers={'Authorization':'Bearer '+self.settings.token}).status_code, 404)
                duplicate = self.cli('serve')
                self.assertEqual(duplicate.returncode, 1)
                self.assertEqual(self.cli('down').returncode, 0)
                self.assertIsNone(local_status())

    def test_down_checkpoints_active_demo_and_restart_preserves_history(self):
        result = background()
        headers = {'Authorization':'Bearer '+self.settings.token}
        with httpx.Client(base_url=result['url'], headers=headers, trust_env=False) as client:
            cid = client.post('/api/v1/conversations', json={'demo':True,'configuration':{'max_turns':20,'delay':60}}).json()['id']
            time.sleep(.3)
        down()
        files = list((self.root/'data/conversations').rglob('*.json'))
        saved = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertIn(saved['status'], {'interrupted','stopped'})
        self.assertLess(len(saved['messages']),20)
        background()
        with httpx.Client(base_url=result['url'], headers=headers, trust_env=False) as client:
            state = client.get('/api/v1/conversations/'+cid).json()
            self.assertEqual(len(state['messages']),len(saved['messages']))
            self.assertFalse(state['active'])

    def test_occupied_port_propagates_failure_without_false_ready(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',self.port));sock.listen()
            with self.assertRaisesRegex(BridgeError,'Avvio fallito'):
                background(timeout=10)

    def test_stale_pid_never_signals_foreign_process(self):
        file = metadata_path(self.settings);file.parent.mkdir(parents=True)
        file.write_text(json.dumps({'format':1,'pid':os.getpid(),'control_port':free_port(),
            'instance':'f'*32,'secret':'x'*40}),encoding='utf-8')
        with self.assertRaisesRegex(BridgeError,'Nessun server locale'):
            down()
        self.assertFalse(file.exists())
        self.assertIsNotNone(os.getpid())

    def test_bad_identity_cannot_stop_verified_server(self):
        background()
        meta = read_metadata(self.settings)
        for key,value in [('pid',os.getpid()),('instance','b'*32),('secret','bad'*20)]:
            self.assertFalse(control(dict(meta,**{key:value}),'stop'))
            self.assertTrue(control(meta))

    def test_readiness_respects_restricted_host_and_invalid_port(self):
        with self.assertRaisesRegex(BridgeError,'Porta'):background(port=0)
        with patch.dict(os.environ,{'ALTERECHO_ALLOWED_HOSTS':'echo.example','ALTERECHO_ORIGINS':'https://echo.example'}):
            self.assertTrue(background())

    def test_supervised_instance_lock_is_respected(self):
        lease = ServerLease(self.settings.runtime/'server.lock');lease.acquire()
        try:
            with self.assertRaises(BridgeError):down()
            with self.assertRaises(BridgeError):background()
        finally:
            lease.release()

    def test_foreground_cli_and_supervisor_templates(self):
        from alterecho.cli import main
        from alterecho.ui import Terminal
        with patch('alterecho.managed.background', return_value={'url':'http://127.0.0.1:1','pid':123,'log':'fixture.log'}) as launch, patch('alterecho.server.serve') as foreground, patch.object(Terminal,'say'):
            self.assertEqual(main(['serve']),0)
            launch.assert_called_once_with(None,None)
            foreground.assert_not_called()
        self.assertTrue(parser().parse_args(['serve','--foreground']).foreground)
        with self.assertRaises(SystemExit):parser().parse_args(['serve','--foreground','--detach'])
        root = Path(__file__).resolve().parents[1]
        for name in ['Dockerfile','deploy/systemd/alterecho.service','deploy/windows/AlterEcho.xml','deploy/launchd/org.alterecho.server.plist']:
            self.assertIn('--foreground',(root/name).read_text(encoding='utf-8'))

    def test_startup_timeout_has_watchdog_and_no_success(self):
        # Deliberately less than Python/server import time; the unadopted child
        # stops itself instead of becoming an orphan after the launcher exits.
        with self.assertRaisesRegex(BridgeError,'Timeout'):
            background(timeout=.001)
        deadline=time.monotonic()+10
        time.sleep(2)
        while time.monotonic()<deadline and local_status():time.sleep(.1)
        self.assertIsNone(local_status())

    def test_foreground_crash_stale_metadata_and_relaunch(self):
        # A fixture crashes ITSELF; the test never signals a stored PID.
        marker=self.root/'crash-now'
        code="""import os,time,threading
from pathlib import Path
from alterecho.cli import main
def crash():
 while not Path(os.environ['FIXTURE_CRASH_FILE']).exists():time.sleep(.02)
 os._exit(23)
threading.Thread(target=crash,daemon=True).start()
main(['serve','--foreground'])
"""
        env=dict(os.environ,ALTERECHO_MANAGED_ID='d'*32,ALTERECHO_MANAGED_SECRET='x'*40,FIXTURE_CRASH_FILE=str(marker))
        process=subprocess.Popen([sys.executable,'-c',code],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                meta=read_metadata(self.settings)
                if meta and control(meta,'adopt'):break
                time.sleep(.05)
            else:self.fail('Foreground fixture did not become ready')
            self.assertIsNone(process.poll())
            marker.touch();self.assertEqual(process.wait(timeout=10),23)
            self.assertFalse(control(meta))
            with self.assertRaisesRegex(BridgeError,'Nessun server locale'):down()
            self.assertFalse(metadata_path(self.settings).exists())
            self.assertTrue(background())
        finally:
            marker.touch()
            process.wait(timeout=10)

    def test_shutdown_with_attached_sse_client_does_not_wait_for_generation(self):
        result=background();headers={'Authorization':'Bearer '+self.settings.token}
        with httpx.Client(base_url=result['url'],headers=headers,trust_env=False) as client:
            cid=client.post('/api/v1/conversations',json={'demo':True,'configuration':{'max_turns':10,'delay':60}}).json()['id']
        entered=threading.Event()
        def observe():
            with httpx.Client(trust_env=False,timeout=10) as client:
                with client.stream('GET',result['url']+'/api/v1/conversations/'+cid+'/events',headers=headers) as stream:
                    for line in stream.iter_lines():
                        if line.startswith('data:'):entered.set()
        thread=threading.Thread(target=observe);thread.start()
        self.assertTrue(entered.wait(5));start=time.monotonic();down();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertLess(time.monotonic()-start,10)
