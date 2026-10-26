"""Explicit, copy-only migration plans. Source files are never modified."""
from .i18n import t
from hashlib import sha256
import json
from pathlib import Path
import shutil

from .config import BridgeError
from .history import Conversation
from .storage import atomic_write


def digest(path):
    h=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def migrate(source, destination, apply=False):
    source, destination=Path(source).expanduser().resolve(),Path(destination).expanduser().resolve()
    if not source.is_dir() or source==destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise BridgeError(t('migration.use_separate_source_and_destination_directories_without_nesting'))
    if destination.exists() and any(destination.iterdir()):
        raise BridgeError(t('migration.destination_must_be_new_or_empty_no_files_are_overwritten'))
    files=[]
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise BridgeError(t('migration.migration_stopped_review_the_symbolic_link_manually'))
        if not path.is_file() or path.suffix in {'.tmp','.lock'}:
            continue
        if path.suffix.lower() not in {'.json','.md','.txt','.html','.toml','.jsonl','.bak'}:
            continue
        if path.name in {'auth.json','client.json'} or 'secrets' in path.parts:
            continue
        if path.suffix=='.json' and path.name not in {'config.json','adapters.json'}:
            # Canonical conversations are validated before copying; unknown JSON
            # must be reviewed instead of accidentally importing credentials.
            try:
                Conversation.from_dict(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError,TypeError,KeyError,BridgeError) as e:
                raise BridgeError(t('migration.review_json_before_migration' ,p0=path.name)) from e
        files.append({'path':path.relative_to(source).as_posix(),'sha256':digest(path),'bytes':path.stat().st_size})
    plan={'source':str(source),'destination':str(destination),'files':files,'applied':False,
          'note':t('migration.copy_verified_internal_paths_and_codex_credentials_require_separate_review_histories_were_not_r')}
    if apply:
        destination.mkdir(parents=True,exist_ok=True)
        for item in files:
            original=source/item['path'];target=destination/item['path']
            if digest(original)!=item['sha256'] or target.exists():
                raise BridgeError(t('migration.source_changed_or_destination_not_empty_migration_stopped_source_intact'))
            target.parent.mkdir(parents=True,exist_ok=True)
            with original.open('rb') as src,target.open('xb') as dst:
                shutil.copyfileobj(src,dst)
            if digest(target)!=item['sha256']:
                raise BridgeError(t('migration.copy_sha_256_verification_failed_source_intact'))
        plan['applied']=True
        atomic_write(destination/'migration-manifest.json',json.dumps(plan,ensure_ascii=False,indent=2))
    return plan
