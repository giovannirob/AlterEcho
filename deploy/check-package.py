"""Inspect wheel/sdist contents and import the wheel outside the checkout."""
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

root=Path(__file__).resolve().parents[1]
wheel=max((root/'dist').glob('*.whl'),key=lambda p:p.stat().st_mtime)
sdist=max((root/'dist').glob('*.tar.gz'),key=lambda p:p.stat().st_mtime)
with zipfile.ZipFile(wheel) as archive:
    names=archive.namelist()
    assert 'alterecho/server.py' in names
    assert 'alterecho/client.py' in names
    assert 'alterecho/static/index.html' in names
    assert any(n.startswith('alterecho/static/assets/') and n.endswith('.js') for n in names)
    assert 'alterecho/exporters/templates/conversation.html' in names
    assert not any(n.endswith(('auth.json','config.json','adapters.json','server-token')) for n in names)
with tarfile.open(sdist) as archive:
    names=archive.getnames()
    assert any(n.endswith('/web/src/App.svelte') for n in names)
    assert any(n.endswith('/Dockerfile') for n in names)
    assert not any('/node_modules/' in n or '/outputs/' in n or '/.venv/' in n for n in names)
with tempfile.TemporaryDirectory() as tmp:
    target=Path(tmp)/'installed'
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-deps','--no-compile','--target',str(target),str(wheel)],check=True)
    code="import sys; sys.path.insert(0,sys.argv[1]); import alterecho; from importlib.resources import files; assert alterecho.__version__=='1.0.0'; assert files('alterecho').joinpath('static/index.html').is_file(); from alterecho.cli import main; assert main(['help'])==0"
    subprocess.run([sys.executable,'-I','-c',code,str(target)],cwd=tmp,check=True,stdout=subprocess.DEVNULL)
print('Wheel, sdist, static resources and isolated installed CLI: OK')
