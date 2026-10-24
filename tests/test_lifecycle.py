import asyncio
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from alterecho.api_models import RunRequest, ResumeRequest
from alterecho.adapters.base import Reply
from alterecho.config import Config, BridgeError
from alterecho.history import Conversation, Message
from alterecho.preferences import UserSettings
from alterecho.server_settings import ServerSettings
from alterecho.sessions import SessionManager, Conflict
from alterecho.storage import Store
from alterecho.migration import migrate


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'ALTERECHO_HOME':self.tmp.name});self.env.start();self.addCleanup(self.env.stop)
        self.cfg=Config(codex_model='fixture',ollama_model='fixture',max_turns=3)
        UserSettings().save(self.cfg)
        self.manager=SessionManager(ServerSettings(token='x'*40))
        self.addAsyncCleanup(self.manager.shutdown)
        self.entered,self.release=asyncio.Event(),asyncio.Event()
        parent=self
        class Controlled:
            async def start(self):return [{'model':'fixture'}]
            async def attach(self,c,checkpoint):c.codex_thread_id='thread-'+c.id;checkpoint()
            async def models(self):return ['fixture']
            async def prepare(self):pass
            async def generate(self,c,checkpoint):
                c.partial={'speaker':c.next_speaker(),'model':'fixture','text':'partial'}
                checkpoint.delta(c.next_speaker(),'fixture','partial');checkpoint()
                parent.entered.set();await parent.release.wait()
                return Reply('complete','fixture')
            async def close(self):pass
        self.factory=patch('alterecho.profile_runtime.build_adapters',side_effect=lambda cfg:{s:Controlled() for s in ('codex','ollama')})
        self.factory.start();self.addCleanup(self.factory.stop)

    async def test_pause_finishes_current_turn_then_resume(self):
        cid=await self.manager.create(RunRequest())
        await self.entered.wait()
        self.manager.pauses.add(cid);self.release.set()
        await self.manager.tasks[cid]
        state=self.manager.snapshot(cid)
        self.assertEqual((state['status'],len(state['messages'])),('paused',1))
        await self.manager.resume(cid,ResumeRequest(max_turns=3))
        await self.manager.tasks[cid]
        self.assertEqual(self.manager.snapshot(cid)['status'],'completed')
        self.assertEqual(len(self.manager.snapshot(cid)['messages']),3)

    async def test_concurrent_resume_delete_and_shutdown_preserve_partial(self):
        cid=await self.manager.create(RunRequest())
        await self.entered.wait()
        with self.assertRaises(Conflict):await self.manager.resume(cid,ResumeRequest(max_turns=5))
        await self.manager.shutdown()
        saved=self.manager.stores[cid].load()
        self.assertEqual(saved.status,'interrupted')
        self.assertEqual(saved.messages,[])
        self.assertEqual(saved.partial['text'],'partial')
        self.assertFalse(self.manager.tasks)
        self.assertTrue(any(e.type=='conversation.stopped' for e in self.manager.log(cid).events))

    async def test_task_cleanup_survives_export_failure(self):
        cid=await self.manager.create(RunRequest())
        await self.entered.wait()
        with patch.object(self.manager.stores[cid],'export',side_effect=OSError('disk full')):
            self.release.set();await self.manager.tasks[cid]
        self.assertFalse(self.manager.tasks)
        self.assertEqual(self.manager.snapshot(cid)['status'],'failed')

    async def test_same_codex_thread_is_reserved_before_task_starts(self):
        ids=[]
        for _ in range(2):
            c=Conversation(self.cfg.to_dict(),messages=[Message('codex','fixture','first',1)],codex_thread_id='same-thread')
            store=Store(Path(self.cfg.output_dir)/f'{c.id}.json');store.save(c)
            self.manager.loaded[c.id],self.manager.stores[c.id]=c,store;ids.append(c.id)
        await self.manager.resume(ids[0],ResumeRequest(max_turns=3))
        with self.assertRaises(Conflict):await self.manager.resume(ids[1],ResumeRequest(max_turns=3))
        self.release.set();await self.manager.tasks[ids[0]]


class MigrationTests(unittest.TestCase):
    def test_delete_removes_only_selected_history_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'chat.json');store.save(Conversation(Config().to_dict()))
            backups=Path(tmp)/'.backups';backups.mkdir()
            owned=backups/'chat.json.123.bak';owned.write_text('private')
            other=backups/'other.json.123.bak';other.write_text('keep')
            removed=store.delete()
            self.assertIn(owned,removed)
            self.assertFalse(owned.exists())
            self.assertEqual(other.read_text(),'keep')

    def test_plan_copy_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,dest=Path(tmp)/'source',Path(tmp)/'dest';source.mkdir()
            c=Conversation(Config().to_dict())
            Store(source/'old.json').save(c)
            (source/'auth.json').write_text('do-not-copy',encoding='utf-8')
            original=(source/'old.json').read_bytes()
            plan=migrate(source,dest)
            self.assertFalse(dest.exists());self.assertEqual(len(plan['files']),1)
            result=migrate(source,dest,apply=True)
            self.assertTrue(result['applied'])
            self.assertEqual((dest/'old.json').read_bytes(),original)
            self.assertEqual((source/'old.json').read_bytes(),original)
            self.assertFalse((dest/'auth.json').exists())
            with self.assertRaises(BridgeError):migrate(source,dest,apply=True)

    def test_unknown_json_and_nested_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();(source/'unknown.json').write_text('{}')
            with self.assertRaises(BridgeError):migrate(source,source/'dest')
            with self.assertRaises(BridgeError):migrate(source,Path(tmp)/'dest')
