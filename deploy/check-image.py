"""Real local image verification and transport archive. No registry writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid


def docker(*args, **kwargs):
    return subprocess.check_output(['docker',*args],text=True,**kwargs).strip()


def verify(architecture, version, commit, output):
    image='alterecho:release-'+architecture
    inspected=json.loads(docker('image','inspect',image))[0]
    assert inspected['Architecture']==architecture,inspected['Architecture']
    assert inspected['Os']=='linux'
    assert inspected['Config']['Cmd']==['alterecho','serve','--foreground']
    assert inspected['Config']['User'] not in {'','0','root','0:0'}
    labels=inspected['Config']['Labels']
    assert labels['org.opencontainers.image.version']==version
    assert labels['org.opencontainers.image.revision']==commit
    assert labels['org.opencontainers.image.source'].startswith('https://github.com/')
    assert inspected['Config']['Healthcheck']['Test']
    for language, heading in [('en', 'Usage:'), ('it', 'Uso:')]:
        assert heading in docker('run','--rm','--entrypoint','alterecho',image,'--lang',language,'help')
    subprocess.run(['docker','run','--rm','--entrypoint','codex',image,'--version'],check=True)
    subprocess.run(['docker','run','--rm','--entrypoint','codex',image,'app-server','--help'],check=True,stdout=subprocess.DEVNULL)
    name='ae-release-'+uuid.uuid4().hex
    docker('volume','create','--label','org.alterecho.test='+name,name)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    created=False
    try:
        docker('run','-d','--name',name,'--label','org.alterecho.test='+name,
               '-p',f'127.0.0.1:{port}:8765','-v',name+':/var/lib/alterecho',
               '-e','ALTERECHO_TOKEN=fixture-token-with-at-least-32-characters',image)
        created=True
        env=dict(os.environ,ALTERECHO_TEST_URL=f'http://127.0.0.1:{port}')
        script=str(Path(__file__).with_name('docker-smoke.py'))
        subprocess.run([sys.executable,script],env=env,check=True)
        docker('exec',name,'python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health',timeout=3).read()")
        docker('stop','--timeout','45',name)
        logs=docker('logs',name,stderr=subprocess.STDOUT)
        assert 'Application shutdown complete' in logs,logs
        docker('start',name)
        subprocess.run([sys.executable,script,'--check-persisted'],env=env,check=True)
    finally:
        if created:
            owned=json.loads(docker('inspect',name))[0]
            assert owned['Config']['Labels']['org.alterecho.test']==name
            assert any(m.get('Name')==name for m in owned['Mounts'])
            docker('stop','--timeout','45',name)
            docker('rm',name)
        volume=json.loads(docker('volume','inspect',name))[0]
        assert volume['Labels']['org.alterecho.test']==name
        docker('volume','rm',name)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    tar=output/'image.tar'
    if tar.exists():
        raise RuntimeError('Use an empty output directory')
    subprocess.run(['docker','save','--output',str(tar),image],check=True)
    with tar.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    (output/'verified.json').write_text(json.dumps({'architecture':architecture,'commit':commit,'version':version,'sha256':digest}),encoding='utf-8')
    print('Verified local image archive: '+architecture)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--architecture',choices=['amd64','arm64'],required=True)
    parser.add_argument('--version',required=True);parser.add_argument('--commit',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();verify(args.architecture,args.version,args.commit,args.output)
