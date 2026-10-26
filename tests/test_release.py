"""Release acceptance gates with fake HTTP/registry clients; zero publications."""
import copy
import contextlib
import hashlib
import json
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit

import yaml

from deploy import release


ROOT=Path(__file__).resolve().parents[1]


class FakeGitHub:
    def __init__(self):
        self.existing=None;self.assets={};self.calls=[];self.fail_upload=False;self.fail_after=0
    def verify_ref(self,*args):self.calls.append(('verify',args))
    def request(self,method,path,body=None,binary=None):
        self.calls.append((method,path,body))
        if method=='GET' and path.startswith('/releases/tags/'):return self.existing
        if path=='/releases/generate-notes':return {'body':'### Modifiche\n* Avvio headless e chat aggiornati.'}
        if path=='/releases' and method=='POST':
            self.existing=dict(body,id=10,upload_url='https://uploads.github.com/repos/test/test/releases/10/assets{?name,label}')
            return self.existing
        if method=='GET' and '/assets?' in path:return list(self.assets.values())
        if binary is not None:
            if self.fail_upload and len(self.assets)>=self.fail_after:raise release.ReleaseError('Fixture upload failure')
            name=parse_qs(urlsplit(path).query)['name'][0]
            self.assets[name]={'name':name,'size':len(binary),'digest':'sha256:'+hashlib.sha256(binary).hexdigest()}
            return self.assets[name]
        if method=='PATCH':self.existing.update(body);return self.existing
        raise AssertionError((method,path))


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.env=patch.dict(os.environ,{'GITHUB_RUN_ID':'1234','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'giovannirob/AlterEcho'})
        self.env.start();self.addCleanup(self.env.stop)
        # Publication-unit fixtures deliberately use a fixed example version;
        # the separate version tests exercise the real validator on temp files.
        self.real_validate=release.validate_versions
        versions=patch.object(release,'validate_versions',side_effect=release.parse_tag)
        versions.start();self.addCleanup(versions.stop)

    def fixture_versions(self,python='1.1.0',web='1.1.0',runtime=None):
        (self.root/'alterecho').mkdir(exist_ok=True);(self.root/'web').mkdir(exist_ok=True)
        (self.root/'pyproject.toml').write_text('[project]\nversion='+json.dumps(python),encoding='utf-8')
        (self.root/'alterecho/__init__.py').write_text('__version__='+json.dumps(runtime or python),encoding='utf-8')
        (self.root/'web/package.json').write_text(json.dumps({'version':web}),encoding='utf-8')
        (self.root/'web/package-lock.json').write_text(json.dumps({'version':web,'packages':{'':{'version':web}}}),encoding='utf-8')

    def assets(self):
        info=release.parse_tag('v1.1.0')
        for name in release.expected_assets(info):(self.root/name).write_bytes(b'fixture package only: '+name.encode())
        release.bundle(info.tag,self.root,'a'*40,'sha256:'+'b'*64)

    def test_semver_and_python_prerelease_mapping(self):
        for tag,python in [('v1.1.0','1.1.0'),('v2.0.0-rc.1','2.0.0rc1'),('v2.0.0-alpha.0','2.0.0a0'),('v2.0.0-beta.2','2.0.0b2'),('v2.0.0-dev.3','2.0.0.dev3'),('v1.2.0+build.4','1.2.0+build.4')]:
            with self.subTest(tag=tag):self.assertEqual(release.parse_tag(tag).python,python)
        for invalid in ['1.1.0','v01.1.0','v1.01.0','v1.1','v1.1.0-rc.01','v1.1.0-','v1.1.0\n','v1.1.0;echo secret','v１.1.0','docs-update','v1.2.0-preview.1']:
            with self.subTest(tag=invalid),self.assertRaises(release.ReleaseError):release.parse_tag(invalid)

    def test_versions_must_match_without_mutating_files(self):
        self.fixture_versions();self.assertEqual(self.real_validate('v1.1.0',self.root).version,'1.1.0')
        original=(self.root/'pyproject.toml').read_bytes()
        with self.assertRaises(release.ReleaseError):self.real_validate('v1.2.0',self.root)
        self.assertEqual((self.root/'pyproject.toml').read_bytes(),original)
        self.fixture_versions('2.0.0rc1','2.0.0-rc.1')
        self.assertTrue(self.real_validate('v2.0.0-rc.1',self.root).prerelease)
        self.fixture_versions(runtime='1.0.0')
        with self.assertRaises(release.ReleaseError):self.real_validate('v1.1.0',self.root)
        self.fixture_versions('1.1','1.1.0')
        with self.assertRaises(release.ReleaseError):self.real_validate('v1.1.0',self.root)

    def test_only_new_version_tag_pushes_are_allowed(self):
        event={'created':True,'deleted':False,'forced':False}
        self.assertEqual(release.validate_event(event,'refs/tags/v1.1.0','push').version,'1.1.0')
        for name,ref,patcher in [('push','refs/heads/main',{}),('pull_request','refs/tags/v1.1.0',{}),('workflow_dispatch','refs/tags/v1.1.0',{}),('push','refs/tags/docs',{}),('push','refs/tags/v1.1.0',{'forced':True}),('push','refs/tags/v1.1.0',{'created':False}),('push','refs/tags/v1.1.0',{'deleted':True})]:
            with self.subTest(event=name,ref=ref,patch=patcher),self.assertRaises(release.ReleaseError):release.validate_event(event|patcher,ref,name)

    def test_duplicates_drafts_aliases_and_stable_downgrades_are_rejected(self):
        current=release.parse_tag('v1.1.0')
        for prior in [{'tag_name':'v1.1.0'},{'tag_name':'v1.1.0','draft':True},{'tag_name':'1.1.0'},{'tag_name':'v2.0.0','draft':False}]:
            with self.subTest(prior=prior),self.assertRaises(release.ReleaseError):release.require_new_release(current,[prior])
        release.require_new_release(current,[{'tag_name':'1.0.0'}])
        self.assertEqual(release.docker_tags(current),['1.1.0','1.1','latest'])
        self.assertEqual(release.docker_tags(release.parse_tag('v2.0.0-rc.1')),['2.0.0-rc.1'])

    def test_remote_ref_movement_blocks_publication(self):
        api=release.GitHub('owner/repo','fixture-token')
        with patch.object(api,'request',return_value={'object':{'type':'commit','sha':'wrong'}}):
            with self.assertRaises(release.ReleaseError):api.verify_ref('v1.1.0','a'*40)
        with patch.object(api,'request',side_effect=[{'object':{'type':'tag','sha':'tag-object'}},{'object':{'type':'commit','sha':'a'*40}}]):
            api.verify_ref('v1.1.0','a'*40)

    def test_exact_artifacts_and_checksums_precede_publication(self):
        with self.assertRaises(release.ReleaseError):release.bundle('v1.1.0',self.root,'a'*40,'sha256:'+'b'*64)
        self.assets();api=FakeGitHub()
        release.publish_release('v1.1.0',self.root,'a'*40,api)
        self.assertFalse(api.existing['draft']);self.assertEqual(api.existing['make_latest'],'true')
        self.assertEqual(set(api.assets),release.expected_assets(release.parse_tag('v1.1.0'))|{'SHA256SUMS.txt','release-manifest.json'})
        self.assertTrue(api.calls[-1][0]=='PATCH')
        self.assertIn('linux-arm64',api.existing['body'])
        prerelease=release.parse_tag('v2.0.0-rc.1');folder=self.root/'pre';folder.mkdir()
        for name in release.expected_assets(prerelease):(folder/name).write_bytes(b'prerelease fixture only')
        release.bundle(prerelease.tag,folder,'a'*40,'sha256:'+'b'*64)
        preview=FakeGitHub();release.publish_release(prerelease.tag,folder,'a'*40,preview)
        self.assertTrue(preview.existing['prerelease']);self.assertEqual(preview.existing['make_latest'],'false')

    def test_failed_upload_keeps_draft_and_rerun_resumes_without_overwriting(self):
        self.assets();api=FakeGitHub();api.fail_upload=True;api.fail_after=2
        with self.assertRaises(release.ReleaseError):release.publish_release('v1.1.0',self.root,'a'*40,api)
        self.assertTrue(api.existing['draft']);self.assertFalse(any(c[0]=='PATCH' for c in api.calls))
        self.assertEqual(len(api.assets),2)
        api.fail_upload=False;release.publish_release('v1.1.0',self.root,'a'*40,api)
        self.assertFalse(api.existing['draft'])
        before=len(api.calls)
        with self.assertRaises(release.ReleaseError):release.publish_release('v1.1.0',self.root,'a'*40,api)
        self.assertFalse(any(c[0] in {'PATCH','POST'} for c in api.calls[before:]))

    def test_tampered_asset_or_foreign_draft_is_not_published(self):
        self.assets();api=FakeGitHub()
        name=next(iter(release.expected_assets(release.parse_tag('v1.1.0'))))
        (self.root/name).write_bytes(b'tampered')
        with self.assertRaises(release.ReleaseError):release.publish_release('v1.1.0',self.root,'a'*40,api)
        self.assertFalse(any(c[0] in {'POST','PATCH'} for c in api.calls))
        api.existing={'draft':True,'body':'someone else'}
        # Restore the hash set, then verify the independent draft guard.
        (self.root/name).write_bytes(b'fixture package only: '+name.encode())
        with self.assertRaises(release.ReleaseError):release.publish_release('v1.1.0',self.root,'a'*40,api)

    def test_no_docker_writes_for_existing_version_or_unverified_architecture(self):
        with patch.object(release,'GitHub') as github,patch.object(release,'Registry') as registry,patch.object(release.subprocess,'run') as run:
            registry.return_value.exists.return_value=True
            with self.assertRaises(release.ReleaseError):release.publish_docker('v1.1.0','ghcr.io/giovannirob/alterecho',self.root,'a'*40)
            run.assert_not_called()
            registry.return_value.exists.return_value=False
            for arch in ('amd64','arm64'):
                folder=self.root/arch;folder.mkdir();tar=folder/'image.tar';tar.write_bytes(b'fixture')
                (folder/'verified.json').write_text(json.dumps({'architecture':arch,'version':'1.1.0','commit':'a'*40,'sha256':release.sha256(tar) if arch=='amd64' else 'wrong'}))
            with self.assertRaises(release.ReleaseError):release.publish_docker('v1.1.0','ghcr.io/giovannirob/alterecho',self.root,'a'*40)
            run.assert_not_called()

    def test_archive_and_credential_filename_restrictions(self):
        executable=self.root/'alterecho';executable.write_bytes(b'fixture, not a compiled platform')
        release.archive(executable,'linux-x64','v1.1.0',self.root/'archives')
        path=self.root/'archives/AlterEcho-1.1.0-linux-x64.tar.gz'
        with tarfile.open(path) as tar:self.assertEqual(tar.getnames(),['alterecho','README.txt'])
        with self.assertRaises(release.ReleaseError):release.archive(executable,'linux-x64','v1.1.0',self.root/'archives')
        for name in ['auth.json','AUTH.JSON','secret/.env','user/.codex/auth.json','../outside','/root/file','C:/private/file','user/managed-server.json']:
            with self.subTest(name=name),self.assertRaises(release.ReleaseError):release.assert_safe_members([name])

    def test_mock_registry_publication_tags_and_verified_multiarch_digest(self):
        for tag in ('v1.1.0','v2.0.0-rc.1'):
            info=release.parse_tag(tag)
            for arch in ('amd64','arm64'):
                folder=self.root/arch;folder.mkdir(exist_ok=True);tar=folder/'image.tar';tar.write_bytes(b'fixture')
                (folder/'verified.json').write_text(json.dumps({'architecture':arch,'version':info.version,'commit':'a'*40,'sha256':release.sha256(tar)}))
            manifests=[{'digest':'sha256:'+'1'*64},{'digest':'sha256:'+'2'*64},
                {'digest':'sha256:'+'3'*64,'manifests':[{'platform':{'os':'linux','architecture':a}} for a in ('amd64','arm64')]}]
            with patch.object(release,'GitHub'),patch.object(release,'Registry') as registry,patch.object(release.subprocess,'run') as run,patch.object(release.subprocess,'check_output',side_effect=[json.dumps(m) for m in manifests]),patch.object(release,'output') as output:
                registry.return_value.exists.return_value=False
                release.publish_docker(tag,'ghcr.io/giovannirob/alterecho',self.root,'a'*40)
                create=run.call_args_list[-1].args[0]
                self.assertEqual(create[:4],['docker','buildx','imagetools','create'])
                self.assertEqual('ghcr.io/giovannirob/alterecho:latest' in create,not info.prerelease)
                output.assert_called_once_with({'digest':'sha256:'+'3'*64})


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.ci=yaml.load((ROOT/'.github/workflows/test.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
        self.release=yaml.load((ROOT/'.github/workflows/release.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)

    def ancestors(self,name):
        needs=self.release['jobs'][name].get('needs',[])
        if isinstance(needs,str):needs=[needs]
        return set(needs)|set().union(*(self.ancestors(n) for n in needs))

    def test_ci_has_no_distribution_builds_or_publication(self):
        self.assertEqual(self.ci['on']['push'],{'branches':['**']})
        self.assertIn('pull_request',self.ci['on']);self.assertIn('workflow_call',self.ci['on'])
        text=json.dumps(self.ci)
        for forbidden in ['python -m build','PyInstaller','docker build','packages: write','upload-artifact','npm run build','publish-release','publish-docker']:
            self.assertNotIn(forbidden,text)

    def test_only_version_tags_trigger_release_and_every_write_depends_on_checks(self):
        self.assertEqual(set(self.release['on']),{'push'})
        self.assertEqual(set(self.release['on']['push']),{'tags'})
        self.assertEqual(self.release['concurrency']['cancel-in-progress'],'false')
        for job in ['frontend','python','standalone','docker-build','docker-publish','publish']:
            self.assertTrue({'validate','tests'}<=self.ancestors(job),job)
        self.assertIn('standalone',self.ancestors('docker-publish'))
        self.assertIn('docker-build',self.ancestors('publish'))
        self.assertEqual(self.release['jobs']['docker-publish']['permissions'],{'contents':'read','packages':'write'})
        self.assertEqual(self.release['jobs']['publish']['permissions'],{'contents':'write'})
        self.assertEqual(self.release['permissions'],{'contents':'read'})

    def test_native_matrices_and_all_external_actions_are_pinned(self):
        matrix=self.release['jobs']['standalone']['strategy']['matrix']['include']
        self.assertEqual({p['target'] for p in matrix},set(release.PLATFORMS))
        self.assertEqual({p['arch'] for p in self.release['jobs']['docker-build']['strategy']['matrix']['include']},{'amd64','arm64'})
        for workflow in (self.ci,self.release):
            for job in workflow['jobs'].values():
                for step in job.get('steps',[]):
                    if 'uses' in step:self.assertRegex(step['uses'],r'^(actions|docker)/[a-z-]+@[0-9a-f]{40}$')
