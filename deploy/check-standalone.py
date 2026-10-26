"""Exercise a freshly built standalone outside the checkout; mock demo only."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.request import Request, urlopen

exe=Path(sys.argv[1] if len(sys.argv)>1 else 'dist/alterecho.exe').resolve()
expected_version=tomllib.loads((Path(__file__).resolve().parents[1]/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
with tempfile.TemporaryDirectory() as tmp:
    env=dict(os.environ,ALTERECHO_HOME=str(Path(tmp)/'home'),ALTERECHO_TOKEN='standalone-test-service-token-2026-abcdefgh')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    log=Path(tmp)/'server.log'
    with log.open('w',encoding='utf-8') as output:
        process=subprocess.Popen([str(exe),'serve','--foreground','--port',str(port)],cwd=tmp,env=env,stdout=output,stderr=output,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        try:
            for _ in range(100):
                try:
                    with urlopen(base+'/api/v1/health',timeout=1) as r:assert r.status==200
                    break
                except OSError:
                    if process.poll() is not None:raise RuntimeError(log.read_text(encoding='utf-8'))
                    time.sleep(.1)
            else:raise RuntimeError('Standalone server not ready: '+log.read_text(encoding='utf-8'))
            with urlopen(base,timeout=3) as r:assert b'<html' in r.read()
            with urlopen(Request(base+'/api/v1/version',headers={'Authorization':'Bearer '+env['ALTERECHO_TOKEN']})) as r:
                assert json.load(r)['version']==expected_version
            cli=subprocess.run([str(exe),'--server',base,'demo','--turns','2'],cwd=tmp,env=env,capture_output=True,timeout=30)
            assert cli.returncode==0,cli.stdout.decode(errors='replace')+cli.stderr.decode(errors='replace')
            with urlopen(Request(base+'/api/v1/conversations',headers={'Authorization':'Bearer '+env['ALTERECHO_TOKEN']})) as r:
                histories=json.load(r)
            assert len(histories)==1 and histories[0]['message_count']==2,histories
            assert list((Path(tmp)/'home/data/conversations').rglob('*.html'))
        finally:
            if process.poll() is None:
                process.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGTERM)
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill();process.wait();raise RuntimeError('Standalone failed to shut down gracefully')
    assert 'Application shutdown complete' in log.read_text(encoding='utf-8'),log.read_text(encoding='utf-8')
    env['ALTERECHO_PORT']=str(port)
    launch=subprocess.run([str(exe),'serve'],cwd=tmp,env=env,capture_output=True,timeout=45)
    assert launch.returncode==0,launch.stdout.decode(errors='replace')+launch.stderr.decode(errors='replace')
    try:
        # The original onefile launcher has exited and cleaned its extraction.
        time.sleep(1)
        with urlopen(base,timeout=5) as r:assert b'<html' in r.read()
        if os.name=='nt':
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
            from tests.windows_console_probe import console_state
            with urlopen(Request(base+'/api/v1/status',headers={'Authorization':'Bearer '+env['ALTERECHO_TOKEN']})) as r:
                managed=json.load(r)['managed']
            console=console_state(managed['pid'])
            assert not console['visible'],console
            assert console['attached'] or console['error']==6,console
        status=subprocess.run([str(exe),'--server',base,'status'],cwd=tmp,env=env,capture_output=True,timeout=20)
        assert status.returncode==0,status.stdout.decode(errors='replace')
    finally:
        stopped=subprocess.run([str(exe),'down'],cwd=tmp,env=env,capture_output=True,timeout=50)
        assert stopped.returncode==0,stopped.stdout.decode(errors='replace')
print('Standalone foreground + detached server + down + HTTP CLI + static Web + persistence + graceful shutdown: OK')
