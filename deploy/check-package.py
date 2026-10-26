"""Inspect release archives; optionally install BOTH in clean Python venvs."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from urllib.request import Request, urlopen
import venv
import zipfile

from packaging.version import Version
from release import assert_safe_members


ROOT=Path(__file__).resolve().parents[1]


def exercise(python, directory, version):
    env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','ALTERECHO_','OPENAI_','OPENROUTER_','CODEX_'))}
    env.update(ALTERECHO_HOME=str(directory/'home'),ALTERECHO_TOKEN='package-fixture-token-'+'x'*32,
               ALTERECHO_HOST='127.0.0.1')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env['ALTERECHO_PORT']=str(port)
    base=f'http://127.0.0.1:{port}'
    command=[str(python),'-I','-m','alterecho']
    def run(*args):
        result=subprocess.run([*command,*args],cwd=directory,env=env,capture_output=True,timeout=60)
        assert result.returncode==0,result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace')
        return result
    def api(path):
        with urlopen(Request(base+'/api/v1'+path,headers={'Authorization':'Bearer '+env['ALTERECHO_TOKEN']}),timeout=5) as response:
            return json.load(response)
    started=False
    try:
        for language, heading in [('en', b'Usage:'), ('it', b'Uso:')]:
            assert heading in run('--lang', language, 'help').stdout
        run('serve');started=True
        assert api('/version')['version']==version
        assert {p['id'] for p in api('/providers')}=={'codex','ollama','openai','openrouter'}
        with urlopen(base,timeout=5) as response:html=response.read().decode()
        assets=re.findall(r'(?:src|href)="(/assets/[^\"]+)"',html)
        assert any(a.endswith('.js') for a in assets) and any(a.endswith('.css') for a in assets)
        for asset in assets:
            with urlopen(base+asset,timeout=5) as response:assert response.read()
        run('--server',base,'demo','--turns','2')
        histories=api('/conversations')
        assert len(histories)==1 and histories[0]['message_count']==2
        run('--server',base,'watch',histories[0]['id'])
        assert list((directory/'home/data/conversations').rglob('*.html'))
        run('down');started=False
        run('serve');started=True
        assert api('/conversations')[0]['message_count']==2
    finally:
        if started:run('down')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean-install',action='store_true',help='Network install in fresh venv for wheel AND sdist')
    parser.add_argument('--directory',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    raw=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    version=str(Version(raw))
    wheel=args.directory/f'alterecho-{version}-py3-none-any.whl'
    sdist=args.directory/f'alterecho-{version}.tar.gz'
    with zipfile.ZipFile(wheel) as archive:
        names=archive.namelist();assert_safe_members(names)
        assert not any(stat.S_ISLNK(info.external_attr >> 16) for info in archive.infolist())
        for name in ('server.py','client.py','managed.py','coordinator.py','cli.py'):
            assert 'alterecho/'+name in names,name
        assert 'alterecho/static/index.html' in names
        for language in ('en', 'it'):
            assert f'alterecho/locales/{language}.json' in names
        assert any(n.startswith('alterecho/static/assets/') and n.endswith('.js') for n in names)
        assert 'alterecho/exporters/templates/conversation.html' in names
    with tarfile.open(sdist) as archive:
        names=archive.getnames();assert_safe_members(names)
        assert not any(member.issym() or member.islnk() for member in archive.getmembers())
        for name in ('web/src/App.svelte','Dockerfile','deploy/release.py','.github/workflows/release.yml'):
            assert any(n.endswith('/'+name) for n in names),name
    if args.clean_install:
        for package in (wheel,sdist):
            with tempfile.TemporaryDirectory(prefix='alterecho-package-') as temporary:
                directory=Path(temporary).resolve()
                venv.EnvBuilder(with_pip=True).create(directory/'venv')
                python=directory/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
                env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'}}
                subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',str(package.resolve())+'[server]'],env=env,cwd=directory,check=True)
                exercise(python,directory,raw)
                print('Clean install, HTTP/CLI/static/demo/restart outside checkout: '+package.name)
    print('Wheel/sdist version, resources and credential-file exclusion: OK')


if __name__=='__main__':main()
