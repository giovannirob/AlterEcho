"""Tag-gated release tooling. Network writes exist only in explicit publish commands.

Unit tests inject HTTP/registry clients; default test execution never publishes.
"""
import argparse
import ast
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import zipfile

from packaging.version import Version, InvalidVersion


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z", re.ASCII)
PLATFORMS = ('windows-x64', 'linux-x64', 'linux-arm64', 'macos-arm64', 'macos-x64')
FORBIDDEN = {'auth.json', 'config.json', 'adapters.json', 'client.json', 'server-token', 'managed-server.json', '.env'}


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseVersion:
    tag: str
    version: str
    python: str
    docker: str
    minor: str
    prerelease: bool


def parse_tag(tag):
    match = SEMVER.fullmatch(tag)
    if not match:
        raise ReleaseError('Tag non valido: usa vMAJOR.MINOR.PATCH, eventualmente -rc.N / -alpha.N / -beta.N / -dev.N e +build.metadata.')
    major, minor, patch, pre, build = match.groups()
    core = f'{major}.{minor}.{patch}'
    python = core
    if pre:
        phase = re.fullmatch(r'(alpha|beta|rc|dev)\.(0|[1-9]\d*)', pre)
        if not phase:
            raise ReleaseError('Prerelease SemVer valida ma non rappresentabile dai pacchetti Python: usa alpha.N, beta.N, rc.N o dev.N.')
        python += {'alpha':'a','beta':'b','rc':'rc','dev':'.dev'}[phase[1]] + phase[2]
    if build:
        python += '+' + build
    python = str(Version(python))
    docker = tag[1:].replace('+', '_')
    if len(docker) > 128:
        raise ReleaseError('Versione troppo lunga per un tag Docker (massimo 128 caratteri).')
    return ReleaseVersion(tag, tag[1:], python, docker, f'{major}.{minor}', bool(pre))


def validate_versions(tag, root=ROOT):
    release = parse_tag(tag)
    project = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    try:
        Version(project)
        if project != release.python:
            raise ReleaseError(f'Tag {tag} e pyproject.toml ({project}) non corrispondono; atteso {release.python}.')
    except InvalidVersion as error:
        raise ReleaseError('Versione Python non valida.') from error
    module = ast.parse((root/'alterecho/__init__.py').read_text(encoding='utf-8'))
    runtime = next((ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='__version__' for t in n.targets)), None)
    if runtime != project:
        raise ReleaseError('La versione runtime/CLI/server deve essere identica a pyproject.toml.')
    web = json.loads((root/'web/package.json').read_text(encoding='utf-8'))
    lock = json.loads((root/'web/package-lock.json').read_text(encoding='utf-8'))
    if any(v != release.version for v in (web['version'], lock['version'], lock['packages']['']['version'])):
        raise ReleaseError(f'Frontend e lock npm devono dichiarare {release.version}.')
    return release


def validate_event(event, ref, event_name):
    if event_name != 'push' or not ref.startswith('refs/tags/') or event.get('deleted') or event.get('forced') or event.get('created') is not True:
        raise ReleaseError('La distribuzione richiede esclusivamente il push di un NUOVO tag; branch, PR, tag spostati o cancellati sono rifiutati.')
    return parse_tag(ref.removeprefix('refs/tags/'))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GitHub:
    def __init__(self, repository=None, token=None):
        self.repository = repository or os.environ['GITHUB_REPOSITORY']
        self.token = token or os.environ['GITHUB_TOKEN']

    def request(self, method, path, body=None, binary=None):
        url = path if path.startswith('https://') else 'https://api.github.com/repos/'+self.repository+path
        if urlsplit(url).hostname not in {'api.github.com','uploads.github.com'}:
            raise ReleaseError('Host GitHub inatteso.')
        data = binary if binary is not None else json.dumps(body).encode() if body is not None else None
        headers = {'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',
                   'Content-Type':'application/octet-stream' if binary is not None else 'application/json'}
        try:
            with build_opener(NoRedirect()).open(Request(url,data=data,headers=headers,method=method),timeout=120) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and method == 'GET':
                return None
            # Do not echo credentials, URLs with signed parameters or API bodies.
            raise ReleaseError(f'GitHub ha rifiutato {method} (HTTP {error.code}).') from None

    def releases(self):
        page = 1
        while True:
            entries = self.request('GET', f'/releases?per_page=100&page={page}') or []
            yield from entries
            if len(entries) < 100:
                return
            page += 1

    def verify_ref(self, tag, commit):
        ref = self.request('GET', '/git/ref/tags/'+quote(tag,safe=''))
        if not ref:
            raise ReleaseError('Tag remoto non trovato.')
        obj = ref['object']
        for _ in range(8):
            if obj['type'] != 'tag':
                break
            obj = self.request('GET','/git/tags/'+obj['sha'])['object']
        if obj['type'] != 'commit' or obj['sha'] != commit:
            raise ReleaseError('Il tag remoto non punta più al commit verificato. Pubblicazione rifiutata.')


def require_new_release(release, entries):
    for existing in entries:
        tag = existing.get('tag_name','')
        if tag == release.tag:
            raise ReleaseError('Release già esistente, anche se draft: nessuna sovrascrittura consentita.')
        try:
            prior = parse_tag(tag if tag.startswith('v') else 'v'+tag)
        except ReleaseError:
            continue
        if Version(prior.python) == Version(release.python):
            raise ReleaseError('Versione già presente con un altro tag.')
        if not release.prerelease and not prior.prerelease and not existing.get('draft') and Version(release.python) < Version(prior.python):
            raise ReleaseError('Release stabile più vecchia di una già pubblicata: evita di retrocedere latest. Usa una nuova versione crescente.')


def output(values):
    target = os.environ.get('GITHUB_OUTPUT')
    if target:
        with open(target,'a',encoding='utf-8') as stream:
            for key,value in values.items():
                if '\n' in str(value):
                    raise ReleaseError('Output workflow non valido.')
                stream.write(f'{key}={value}\n')


def validate_remote():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    release = validate_event(event,os.environ['GITHUB_REF'],os.environ['GITHUB_EVENT_NAME'])
    release = validate_versions(release.tag)
    commit = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    api = GitHub()
    api.verify_ref(release.tag,commit)
    require_new_release(release,api.releases())
    output({'tag':release.tag,'version':release.version,'python_version':release.python,'docker_version':release.docker,
            'minor':release.minor,'prerelease':str(release.prerelease).lower(),'commit':commit,
            'image':'ghcr.io/'+api.repository.lower(), 'codex_version':(ROOT/'deploy/codex-version.txt').read_text().strip()})
    print('Nuovo tag, versioni e commit verificati: '+release.tag)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def assert_safe_members(names):
    for name in names:
        parts = Path(name.replace('\\','/')).parts
        if name.startswith(('/', '\\')) or '..' in parts or any(':' in p or p.casefold() in FORBIDDEN or p.casefold().startswith('.env') or p.casefold() in {'.venv','node_modules','outputs','.codex','__pycache__'} for p in parts):
            raise ReleaseError('File non ammesso nella distribuzione: '+name)


def archive(executable, target, tag, destination):
    release = validate_versions(tag)
    if target not in PLATFORMS:
        raise ReleaseError('Piattaforma standalone non prevista.')
    executable = Path(executable)
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    name = f'AlterEcho-{release.version}-{target}'
    suffix = '.zip' if target.startswith('windows') else '.tar.gz'
    path = destination/(name+suffix)
    if path.exists():
        raise ReleaseError('Archivio già esistente; usa una directory di output vuota.')
    readme = f'''AlterEcho {release.version} / {target}

Estrai in una cartella e avvia il binario alterecho (alterecho.exe su Windows).
  alterecho serve                 server headless in background
  alterecho                      client CLI
  alterecho web                  browser: http://127.0.0.1:8765
  alterecho down                 arresto locale controllato
  alterecho serve --foreground    diagnostica e supervisori

Il token locale si trova nella configurazione del server (server-token).
Codex e Ollama sono esterni all'eseguibile. Nessun modello o credenziale incluso.
macOS: eseguibile non firmato/notarizzato; Gatekeeper può bloccarlo.
Linux: build su Ubuntu 22.04, glibc 2.35 o successiva; altre distro da verificare.
Guida: https://github.com/giovannirob/AlterEcho/blob/{release.tag}/docs/GUIDA.md
'''
    if suffix == '.zip':
        with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.write(executable,executable.name)
            zipped.writestr('README.txt',readme)
    else:
        import io
        with tarfile.open(path,'w:gz') as tar:
            tar.add(executable,arcname=executable.name,recursive=False)
            data=readme.encode();info=tarfile.TarInfo('README.txt');info.size=len(data);info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
    print(path)


def expected_assets(release):
    return {f'alterecho-{release.python}-py3-none-any.whl', f'alterecho-{release.python}.tar.gz',
            *(f'AlterEcho-{release.version}-{p}'+('.zip' if p.startswith('windows') else '.tar.gz') for p in PLATFORMS)}


def bundle(tag, directory, commit, digest):
    release = validate_versions(tag)
    directory = Path(directory)
    files = {p.name:p for p in directory.iterdir() if p.is_file()}
    if set(files) != expected_assets(release):
        raise ReleaseError('Allegati mancanti o inattesi: '+str(sorted(set(files)^expected_assets(release))))
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
        raise ReleaseError('Digest Docker mancante o non valido.')
    hashes = {name:sha256(path) for name,path in sorted(files.items())}
    manifest = {'tag':tag,'version':release.version,'commit':commit,'platforms':list(PLATFORMS),'files':hashes,
                'docker':{'image':'ghcr.io/'+os.environ.get('GITHUB_REPOSITORY','giovannirob/AlterEcho').lower(),'digest':digest,'tag':release.docker}}
    path = directory/'release-manifest.json'
    path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    hashes[path.name] = sha256(path)
    (directory/'SHA256SUMS.txt').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(hashes.items())),encoding='utf-8')
    return manifest


class Registry:
    """Read-only GHCR existence check. Write operations use logged-in Docker CLI."""
    def __init__(self, image, token=None):
        if not re.fullmatch(r'ghcr.io/[a-z0-9_.-]+/[a-z0-9_.-]+',image):
            raise ReleaseError('Nome immagine GHCR non valido.')
        self.path=image.removeprefix('ghcr.io/')
        self.token=token or os.environ['GITHUB_TOKEN']

    def exists(self, tag):
        basic=base64.b64encode((os.environ.get('GITHUB_ACTOR','github-actions')+':'+self.token).encode()).decode()
        url='https://ghcr.io/token?'+urlencode({'service':'ghcr.io','scope':f'repository:{self.path}:pull,push'})
        try:
            with build_opener(NoRedirect()).open(Request(url,headers={'Authorization':'Basic '+basic}),timeout=30) as response:
                bearer=json.load(response)['token']
            request=Request(f'https://ghcr.io/v2/{self.path}/manifests/{quote(tag,safe="")}',method='HEAD',headers={
                'Authorization':'Bearer '+bearer,'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'})
            with build_opener(NoRedirect()).open(request,timeout=30):
                return True
        except HTTPError as error:
            # A package may not exist yet on its first publication. Denied
            # credentials are NEVER interpreted as permission to overwrite.
            if error.code == 404:
                return False
            raise ReleaseError(f'Controllo GHCR fallito (HTTP {error.code}); pubblicazione rifiutata.') from None


def publish_docker(tag, image, directory, commit):
    release=validate_versions(tag)
    GitHub().verify_ref(tag,commit)
    if Registry(image).exists(release.docker):
        raise ReleaseError('Tag immagine già presente su GHCR; nessuna sovrascrittura della versione.')
    verified=[]
    for arch in ('amd64','arm64'):
        folder=Path(directory)/arch
        checked=json.loads((folder/'verified.json').read_text())
        tar=folder/'image.tar'
        if checked!={'architecture':arch,'commit':commit,'version':release.version,'sha256':sha256(tar)}:
            raise ReleaseError('Immagine Docker non verificata o artifact modificato.')
        verified.append((arch,tar))
    sources=[]
    for arch,tar in verified:
        subprocess.run(['docker','load','--input',str(tar)],check=True)
        local='alterecho:release-'+arch
        staged=f'{image}:build-{os.environ["GITHUB_RUN_ID"]}-{os.environ["GITHUB_RUN_ATTEMPT"]}-{arch}'
        subprocess.run(['docker','tag',local,staged],check=True)
        subprocess.run(['docker','push',staged],check=True)
        inspected=json.loads(subprocess.check_output(['docker','buildx','imagetools','inspect',staged,'--format','{{json .Manifest}}'],text=True))
        sources.append(image+'@'+inspected['digest'])
    tags=docker_tags(release)
    subprocess.run(['docker','buildx','imagetools','create',*(arg for tag in tags for arg in ('--tag',image+':'+tag)),*sources],check=True)
    result=json.loads(subprocess.check_output(['docker','buildx','imagetools','inspect',image+':'+release.docker,'--format','{{json .Manifest}}'],text=True))
    platforms={m['platform']['architecture'] for m in result.get('manifests',[]) if m['platform'].get('os')=='linux'}
    if platforms!={'amd64','arm64'}:
        raise ReleaseError('Manifest GHCR inatteso: piattaforme incomplete.')
    output({'digest':result['digest']})


def docker_tags(release):
    return [release.docker] if release.prerelease else [release.docker,release.minor,'latest']


def publish_release(tag, directory, commit, api=None):
    release=validate_versions(tag)
    api=api or GitHub()
    api.verify_ref(tag,commit)
    directory=Path(directory)
    manifest=json.loads((directory/'release-manifest.json').read_text())
    if manifest['tag']!=tag or manifest['commit']!=commit or set(manifest['files'])!=expected_assets(release):
        raise ReleaseError('Manifest degli allegati incoerente.')
    names=expected_assets(release)|{'release-manifest.json','SHA256SUMS.txt'}
    if {p.name for p in directory.iterdir()}!=names:
        raise ReleaseError('Directory allegati incompleta o contenente file inattesi.')
    for name,digest in manifest['files'].items():
        if sha256(directory/name)!=digest:
            raise ReleaseError('Checksum allegato non valido: '+name)
    expected=''.join(f'{sha256(directory/name)}  {name}\n' for name in sorted(names-{'SHA256SUMS.txt'}))
    if (directory/'SHA256SUMS.txt').read_text()!=expected:
        raise ReleaseError('File checksum non valido.')
    marker=f'<!-- alterecho-release run={os.environ["GITHUB_RUN_ID"]} commit={commit} -->'
    existing=api.request('GET','/releases/tags/'+quote(tag,safe=''))
    if existing and (not existing['draft'] or marker not in existing.get('body','')):
        raise ReleaseError('Release già pubblicata o draft non appartenente a questa esecuzione.')
    if not existing:
        generated=api.request('POST','/releases/generate-notes',{'tag_name':tag,'target_commitish':commit})
        date=datetime.now(timezone.utc).date().isoformat()
        notes=f'AlterEcho {release.version} · {date}\n\n'+generated['body']
        notes+='\n\nDistribuzioni costruite e verificate:\n'+''.join('- '+name+'\n' for name in sorted(manifest['files']))
        notes+=f'\nDocker: `{manifest["docker"]["image"]}:{release.docker}` (linux/amd64 e linux/arm64).\nDigest verificato: `{manifest["docker"]["digest"]}`.\n'
        notes+='\nPacchetto privato: autenticarsi a GHCR prima del pull. macOS non firmato/notarizzato; Linux richiede glibc 2.35+. Verifica SHA256SUMS.txt prima dell’installazione.\n\n'+marker
        existing=api.request('POST','/releases',{'tag_name':tag,'target_commitish':commit,'name':'AlterEcho '+release.version,
            'body':notes,'draft':True,'prerelease':release.prerelease})
    assets={asset['name']:asset for asset in api.request('GET',f'/releases/{existing["id"]}/assets?per_page=100')}
    if set(assets)-names:
        raise ReleaseError('Il draft contiene allegati inattesi: nessun file sostituito.')
    for name in sorted(names):
        digest=sha256(directory/name)
        if name not in assets:
            url=existing['upload_url'].split('{')[0]+'?'+urlencode({'name':name})
            assets[name]=api.request('POST',url,binary=(directory/name).read_bytes())
        if assets[name].get('digest')!='sha256:'+digest or assets[name]['size']!=(directory/name).stat().st_size:
            raise ReleaseError('Allegato remoto differente; draft non pubblicato e nessuna sovrascrittura: '+name)
    # Publish only after EVERY upload has been checked, even on a resumed job.
    api.verify_ref(tag,commit)
    api.request('PATCH',f'/releases/{existing["id"]}',{'draft':False,'make_latest':'false' if release.prerelease else 'true'})
    print('GitHub Release pubblicata: '+tag)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('validate')
    archive_parser=sub.add_parser('archive')
    archive_parser.add_argument('--executable',required=True);archive_parser.add_argument('--target',required=True)
    for name in ('archive','bundle','publish-docker','publish-release'):
        command=archive_parser if name=='archive' else sub.add_parser(name)
        command.add_argument('--tag',required=True);command.add_argument('--directory',required=True)
        if name!='archive':command.add_argument('--commit',required=True)
        if name=='bundle':command.add_argument('--digest',required=True)
        if name=='publish-docker':command.add_argument('--image',required=True)
    args=parser.parse_args()
    try:
        if args.action=='validate':validate_remote()
        elif args.action=='archive':archive(args.executable,args.target,args.tag,args.directory)
        elif args.action=='bundle':bundle(args.tag,args.directory,args.commit,args.digest)
        elif args.action=='publish-docker':publish_docker(args.tag,args.image,args.directory,args.commit)
        else:publish_release(args.tag,args.directory,args.commit)
    except (ReleaseError,InvalidVersion) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
