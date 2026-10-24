import asyncio
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
import uvicorn
from rich.console import Console

from alterecho.api_models import RunRequest, ResumeRequest, Configuration
from alterecho.adapters.base import Reply
from alterecho.adapters.chat_api import ChatAPIAdapter
from alterecho.adapters.ollama import OllamaAdapter
from alterecho.client import APIClient, Connection
from alterecho.config import Config, BridgeError
from alterecho.events import EventLog
from alterecho.history import Conversation, Message
from alterecho.integrations import new_profile
from alterecho.preferences import UserSettings
from alterecho.server import create_app
from alterecho.server_settings import ServerSettings, ServerLease
from alterecho.sessions import SessionManager
from alterecho.storage import Store
from alterecho.ui import Terminal
from tests.test_integrations import response_events


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ, {"ALTERECHO_HOME":self.tmp.name,"ALTERECHO_TOKEN":"","ALTERECHO_OLLAMA_HOSTS":""})
        self.env.start();self.addCleanup(self.env.stop)
        self.settings=ServerSettings(token="fixture-server-token-"+"x"*32,allowed_hosts=["testserver","127.0.0.1","localhost"])
        self.headers={"Authorization":"Bearer "+self.settings.token}

    def client(self):
        return TestClient(create_app(self.settings))

    def wait(self, client, cid):
        for _ in range(300):
            c=client.get(f"/api/v1/conversations/{cid}",headers=self.headers).json()
            if not c["active"]:return c
            time.sleep(.01)
        self.fail("Conversation task did not finish")

    def demo(self, client, turns=2):
        r=client.post('/api/v1/conversations',headers=self.headers,json={"demo":True,"configuration":{"max_turns":turns}})
        self.assertEqual(r.status_code,202,r.text)
        return r.json()['id']

    def test_auth_origin_host_and_csrf_protect_all_operations(self):
        with self.client() as c:
            self.assertEqual(c.get('/api/v1/health').status_code,200)
            for path in ('/api/v1/status','/api/v1/history','/api/v1/settings','/api/v1/models','/api/v1/profiles','/api/v1/openapi.json'):
                self.assertEqual(c.get(path).status_code,401)
                self.assertEqual(c.get(path,headers=self.headers).status_code,200)
                self.assertEqual(c.get(path,headers=self.headers|{'Origin':'https://evil.example'}).status_code,403)
            self.assertEqual(c.get('/api/v1/status',headers=self.headers|{'Host':'rebind.example'}).status_code,400)
            self.assertEqual(c.post('/api/v1/conversations',data='demo=true',headers=self.headers).status_code,415)
            self.assertEqual(c.post('/api/v1/conversations',json={'demo':True},headers=self.headers|{'Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_network_binding_requires_explicit_auth_and_trust(self):
        for settings in (ServerSettings(host='0.0.0.0'),ServerSettings(host='0.0.0.0',token='x'*40),ServerSettings(host='0.0.0.0',token='short',origins=['https://ae.example'],allowed_hosts=['ae.example'])):
            with self.assertRaises(BridgeError):settings.prepare()
        settings=ServerSettings(host='0.0.0.0',token='x'*40,origins=['https://ae.example'],allowed_hosts=['ae.example'])
        settings.prepare()

    def test_demo_events_export_delete_and_restart_persist_same_history(self):
        with self.client() as c:
            cid=self.demo(c,4)
            state=self.wait(c,cid)
            self.assertEqual(state['status'],'completed')
            self.assertEqual([m['speaker'] for m in state['messages']],['A','B','A','B'])
            events=c.get(f'/api/v1/conversations/{cid}/events',headers=self.headers).text
            self.assertIn('state.snapshot',events)
            self.assertNotIn('codex_thread_id',events)
            for fmt in ('json','md','txt','html'):
                response=c.get(f'/api/v1/conversations/{cid}/export/{fmt}',headers=self.headers)
                self.assertEqual(response.status_code,200)
                self.assertIn('attachment',response.headers['Content-Disposition'])
            self.assertEqual(c.get(f'/api/v1/conversations/{cid}/export/auth.json',headers=self.headers).status_code,400)
        with self.client() as c:
            state2=c.get(f'/api/v1/conversations/{cid}',headers=self.headers).json()
            self.assertEqual(state2['messages'],state['messages'])
            self.assertEqual(c.delete(f'/api/v1/conversations/{cid}',headers=self.headers).status_code,200)
            self.assertEqual(c.get(f'/api/v1/conversations/{cid}',headers=self.headers).status_code,404)

    def test_paid_apis_require_confirmation_and_both_work_through_server(self):
        a,b=new_profile('openai','API A'),new_profile('openrouter','API B')
        a['model'],b['model']='model-a','model-b'
        UserSettings().save(Config(adapter_pair={'codex':a,'ollama':b},max_turns=2))
        seen=[]
        def factory(cfg):
            result={}
            for slot,p in cfg.adapter_pair.items():
                def handle(r,p=p):
                    seen.append((p['provider'],r.method,r.url.path))
                    return httpx.Response(200,json={'data':[{'id':p['model']}]}) if r.method=='GET' else httpx.Response(200,text=response_events(model=p['model']))
                result[slot]=ChatAPIAdapter(cfg,p,slot,httpx.MockTransport(handle))
            return result
        with patch.dict(os.environ,{'OPENAI_API_KEY':'private-fixture-A','OPENROUTER_API_KEY':'private-fixture-B'}),patch('alterecho.profile_runtime.build_adapters',side_effect=factory),self.client() as c:
            r=c.post('/api/v1/conversations',json={},headers=self.headers)
            self.assertEqual(r.status_code,400)
            self.assertFalse(seen)
            r=c.post('/api/v1/conversations',json={'confirm_paid':True},headers=self.headers)
            self.assertEqual(r.status_code,202,r.text)
            state=self.wait(c,r.json()['id'])
            self.assertEqual(state['status'],'completed')
            self.assertEqual(state['messages'][0]['usage']['input_tokens'],40)
            self.assertIsNone(c.app.state.manager.get(r.json()['id']).codex_turn_id)
            serialized=json.dumps(state)
            self.assertNotIn('private-fixture',serialized)
            log=c.app.state.manager.log(r.json()['id'])
            self.assertEqual([e.data['delta'] for e in log.events if e.type=='message.delta'],['risposta','risposta'])
        self.assertIn(('openai','POST','/v1/chat/completions'),seen)
        self.assertIn(('openrouter','POST','/api/v1/chat/completions'),seen)

    def test_native_codex_stdio_and_ollama_stream_work_through_server(self):
        cfg=Config(codex_model='test-codex',max_turns=2)
        UserSettings().save(cfg)
        payloads=[]
        def handle(r):
            if r.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':cfg.ollama_model}]})
            if r.url.path=='/api/ps':return httpx.Response(200,json={'models':[]})
            if r.url.path=='/api/show':return httpx.Response(200,json={})
            self.assertEqual(r.url.path,'/api/chat')
            payloads.append(json.loads(r.content))
            return httpx.Response(200,text='\n'.join(json.dumps(v) for v in [{'message':{'content':'ol'}},{'message':{'content':'lama'}},{'done':True,'done_reason':'stop'}]))
        command=[sys.executable,str(Path(__file__).with_name('fake_server.py').resolve())]
        with patch('alterecho.adapters.codex.command',return_value=command),patch('alterecho.profile_runtime.OllamaAdapter',side_effect=lambda cfg,speaker:OllamaAdapter(cfg,httpx.MockTransport(handle),speaker)),self.client() as c:
            response=c.post('/api/v1/conversations',json={},headers=self.headers)
            self.assertEqual(response.status_code,202,response.text)
            cid=response.json()['id'];state=self.wait(c,cid)
            self.assertEqual(state['status'],'completed',state)
            self.assertEqual([m['text'] for m in state['messages']],['Risposta persistente 1','ollama'])
            canonical=c.app.state.manager.stores[cid].load()
            self.assertEqual(canonical.codex_thread_id,'thread-test')
            self.assertEqual(canonical.codex_turn_id,'t1')
            deltas=[e.data['delta'] for e in c.app.state.manager.log(cid).events if e.type=='message.delta']
            self.assertEqual(deltas,['Risposta persistente 1','ol','lama'])
            self.assertEqual(payloads[0]['keep_alive'],-1)
            self.assertEqual(payloads[0]['messages'][-1]['content'],'Risposta persistente 1')

    def test_inputs_cannot_set_paths_executables_or_secrets(self):
        with self.client() as c:
            for config in ({'output_dir':'/etc'},{'codex_binary':'cmd.exe'},{'codex_home':'/secrets'},{'api_key':'secret'},{'max_turns':1000000},{'roles':{'A':'x'}}):
                r=c.post('/api/v1/conversations',json={'configuration':config},headers=self.headers)
                self.assertIn(r.status_code,(400,422),r.text)
            p=new_profile('codex','unsafe')
            p['binary']='cmd.exe'
            self.assertEqual(c.put('/api/v1/profiles',json={'profiles':[p]},headers=self.headers).status_code,422)
            self.assertEqual(c.post('/api/v1/conversations',content=b'x'*262145,headers=self.headers|{'Content-Type':'application/json'}).status_code,413)

    def test_rate_limit_and_singleton(self):
        with self.client() as c:
            for _ in range(30):
                self.assertEqual(c.post('/api/v1/conversations',json={'configuration':{'max_turns':0}},headers=self.headers).status_code,422)
            self.assertEqual(c.post('/api/v1/conversations',json={},headers=self.headers).status_code,429)
            lease=ServerLease(self.settings.runtime/'server.lock')
            with self.assertRaises(BridgeError):lease.acquire()
        lease.acquire();lease.release()

    def test_legacy_crash_is_read_only_and_resume_retains_messages_and_backup(self):
        cfg=Config(codex_model='fixture-model')
        # Stateless API in legacy slot A must not inherit native Codex fields.
        a,b=new_profile('openai','A'),new_profile('openrouter','B')
        a['model']=b['model']='fixture-model'
        cfg.adapter_pair={'codex':a,'ollama':b}
        conv=Conversation(cfg.to_dict(),messages=[Message('codex','fixture-model','original',1)],status='running',partial={'speaker':'ollama','model':'fixture-model','text':'partial'})
        path=Path(cfg.output_dir)/'legacy.json';store=Store(path);store.save(conv);original=path.read_bytes()
        class Mock:
            async def models(self):return ['fixture-model']
            async def generate(self,c,checkpoint):return Reply('resumed','fixture-model')
            async def close(self):pass
        with patch('alterecho.profile_runtime.build_adapters',side_effect=lambda cfg:{s:Mock() for s in cfg.adapter_pair}),self.client() as c:
            state=c.get(f'/api/v1/conversations/{conv.id}',headers=self.headers).json()
            self.assertEqual(state['status'],'interrupted');self.assertEqual(path.read_bytes(),original)
            r=c.post(f'/api/v1/conversations/{conv.id}/resume',headers=self.headers,json={'max_turns':2,'confirm_paid':True})
            self.assertEqual(r.status_code,202,r.text)
            state=self.wait(c,conv.id)
            self.assertEqual(len(state['messages']),2)
            self.assertEqual(state['messages'][0]['text'],'original')
            self.assertEqual(next((path.parent/'.backups').iterdir()).read_bytes(),original)

    def test_ollama_remote_endpoint_requires_server_allowlist(self):
        for url in ('http://ollama:11434','http://host.docker.internal:11434','http://192.168.1.2:11434'):
            with self.assertRaises(BridgeError):Config(ollama_url=url).validate()
        with patch.dict(os.environ,{'ALTERECHO_OLLAMA_HOSTS':'ollama,host.docker.internal,192.168.1.2'}):
            Config(ollama_url='http://ollama:11434').validate()
            with self.assertRaises(BridgeError):Config(ollama_url='http://ollama.evil:11434').validate()

    def test_cli_imports_no_engine_and_server_absent_is_actionable(self):
        code="import alterecho.cli,sys; assert 'alterecho.coordinator' not in sys.modules; assert 'alterecho.profile_runtime' not in sys.modules; assert not any(k.startswith('alterecho.adapters.') for k in sys.modules)"
        subprocess.run([sys.executable,'-c',code],check=True,capture_output=True)
        result=subprocess.run([sys.executable,'-m','alterecho','--server','http://127.0.0.1:1','run','--non-interactive'],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,1)
        self.assertIn(b'alterecho serve',result.stdout)
        self.assertFalse(list(self.root.rglob('*.json')))

    def test_event_epoch_order_and_expired_cursor(self):
        log=EventLog(limit=2)
        first=log.append('turn.started','cid')
        second=log.append('message.delta','cid',{'delta':'x'})
        self.assertEqual(log.after(first.id),[second])
        log.append('message.completed','cid')
        self.assertIsNone(log.after(first.id))
        self.assertIsNone(log.after('previous-process:1'))


class LiveStreamingTests(unittest.TestCase):
    setUp = ServerTests.setUp
    def test_clients_disconnect_without_stopping_native_stream_and_replay(self):
        entered,release=threading.Event(),threading.Event()
        class Controlled:
            def __init__(self,cfg):self.config=cfg
            async def start(self):return [{'model':'fixture'}]
            async def attach(self,c,checkpoint):c.codex_thread_id='fixture-thread';checkpoint()
            async def models(self):return ['fixture']
            async def prepare(self):pass
            async def generate(self,c,checkpoint):
                c.partial={'speaker':c.next_speaker(),'model':'fixture','text':'first '}
                checkpoint.delta(c.next_speaker(),'fixture','first ');checkpoint();entered.set()
                while not release.is_set():await asyncio.sleep(.01)
                checkpoint.delta(c.next_speaker(),'fixture','second')
                return Reply('first second','fixture')
            async def close(self):pass
        UserSettings().save(Config(codex_model='fixture',ollama_model='fixture',max_turns=2))
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        app=create_app(self.settings)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
        with patch('alterecho.profile_runtime.build_adapters',side_effect=lambda cfg:{s:Controlled(cfg) for s in ('codex','ollama')}):
            thread.start()
            try:
                for _ in range(300):
                    if server.started:break
                    time.sleep(.01)
                self.assertTrue(server.started)
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers=self.headers,trust_env=False,timeout=5) as cli:
                    cid=cli.post('/api/v1/conversations',json={}).json()['id']
                    self.assertTrue(entered.wait(3))
                    # Browser attaches while the provider is blocked in a real
                    # asynchronous turn, then closes the SSE connection.
                    with cli.stream('GET',f'/api/v1/conversations/{cid}/events') as response:
                        for line in response.iter_lines():
                            if line.startswith('id: '):cursor=line[4:]
                            if line.startswith('data: '):
                                snapshot=json.loads(line[6:]);break
                        self.assertTrue(snapshot['data']['active'])
                        self.assertEqual(snapshot['data']['partial']['text'],'first ')
                    self.assertTrue(cli.get(f'/api/v1/conversations/{cid}').json()['active'])
                # CLI TCP connection closes too. Server task still owns the turn.
                release.set()
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers=self.headers,trust_env=False,timeout=5) as browser:
                    for _ in range(300):
                        state=browser.get(f'/api/v1/conversations/{cid}').json()
                        if not state['active']:break
                        time.sleep(.01)
                    self.assertEqual(state['status'],'completed')
                    self.assertEqual(len(state['messages']),2)
                    replay=browser.get(f'/api/v1/conversations/{cid}/events',headers={'Last-Event-ID':cursor}).text
                    self.assertIn('message.delta',replay)
                    self.assertIn('second',replay)
                    self.assertNotIn('state.snapshot',replay)
            finally:
                release.set();server.should_exit=True;thread.join(10);sock.close()
                self.assertFalse(thread.is_alive())
