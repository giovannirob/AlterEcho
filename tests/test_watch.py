import asyncio
from copy import deepcopy
import io
import unittest
from unittest.mock import patch

from rich.console import Console

from alterecho.config import BridgeError
from alterecho.ui import Terminal
from alterecho.watching import watch, WatchRenderer


def state(active=True, messages=None, partial=None):
    return {'id':'c','active':active,'status':'running' if active else 'completed',
        'config':{'max_turns':2,'participants':{'A':{'model':'model-a'},'B':{'model':'model-b'}}},
        'messages':messages or [],'partial':partial,'stats':{'seconds':1.2}}


def message(text='unica risposta'):
    return {'speaker':'A','model':'model-a','text':text,'seconds':1.2,'usage':{}}


class WatchTests(unittest.IsolatedAsyncioTestCase):
    def ui(self, tty=False):
        ui=Terminal();ui.console=Console(file=io.StringIO(),force_terminal=tty,width=42,color_system=None)
        return ui

    async def test_completed_watch_never_opens_stream(self):
        class Client:
            def get(self,path):return state(False,[message()])
            def events(self,*a):raise AssertionError('Finished history must not stream')
        ui=self.ui();self.assertEqual(await watch(Client(),'c',ui),0)
        self.assertEqual(ui.console.file.getvalue().count('unica risposta'),1)

    async def test_replay_partial_snapshot_repeated_frames_complete_once(self):
        ui=self.ui()
        events=[{'id':'e:1','type':'state.snapshot','data':state(partial={'speaker':'A','model':'model-a','text':'unica '})},
                {'id':'e:2','type':'message.delta','data':{'index':1,'speaker':'A','model':'model-a','delta':'risposta'}},
                {'id':'e:3','type':'message.completed','data':{'index':1,'message':message()}}]
        class Client:
            calls=0
            def get(self,path):return state(self.calls<2,[] if self.calls<2 else [message()])
            def events(self,cid,cursor):
                self.calls+=1
                if self.calls==1:
                    yield events[0];yield events[1];raise BridgeError('connection lost')
                self.cursor=cursor
                yield events[1];yield events[2];yield events[2]
        client=Client()
        with patch('alterecho.watching.asyncio.sleep',new=self.no_sleep):
            self.assertEqual(await watch(client,'c',ui),0)
        output=ui.console.file.getvalue()
        self.assertEqual(output.count('unica risposta'),1)
        self.assertEqual(client.cursor,'e:2')
        self.assertNotIn('\x1b',output)

    async def no_sleep(self,*a):pass

    async def test_expired_cursor_snapshot_is_authoritative(self):
        ui=self.ui();r=WatchRenderer(ui)
        r.event({'id':'old:2','type':'state.snapshot','data':state(partial={'speaker':'A','model':'m','text':'ab'})})
        r.event({'id':'new:0','type':'state.snapshot','data':state(partial={'speaker':'A','model':'m','text':'abcd'})})
        r.event({'id':'new:1','type':'message.delta','data':{'index':1,'speaker':'A','model':'m','delta':'ef'}})
        self.assertEqual(r.partial['text'],'abcdef')

    async def test_rich_updates_current_panel_then_commits_once(self):
        ui=self.ui(True);r=WatchRenderer(ui);r.snapshot(state())
        r.event({'id':'e:1','type':'turn.started','data':{'index':1,'speaker':'A'}})
        live=r.live
        r.event({'id':'e:2','type':'message.delta','data':{'index':1,'speaker':'A','model':'model-a','delta':'Unicode è 日本語\x1b[31m'}})
        self.assertIs(r.live,live)
        with patch.object(ui,'message',wraps=ui.message) as render:
            r.event({'id':'e:3','type':'message.completed','data':{'index':1,'message':message()}})
            r.event({'id':'e:4','type':'message.completed','data':{'index':1,'message':message()}})
            self.assertEqual(render.call_count,1)
        self.assertIsNone(r.live)
        r.event({'id':'e:5','type':'turn.started','data':{'index':2,'speaker':'B'}})
        r.event({'id':'e:6','type':'message.delta','data':{'index':2,'speaker':'B','model':'model-b','delta':'seconda risposta'}})
        current=r.live
        r.event({'id':'e:7','type':'message.completed','data':{'index':1,'message':message()}})
        self.assertIs(r.live,current)
        self.assertEqual(r.partial['text'],'seconda risposta')
        r.close()

    async def test_ctrl_c_closes_live_without_stop_request(self):
        class Client:
            def get(self,path):return state()
            def events(self,*a):
                yield {'id':'e:0','type':'state.snapshot','data':state(partial={'speaker':'A','model':'m','text':'partial'})}
                raise KeyboardInterrupt()
        with patch('alterecho.watching.WatchRenderer.close',autospec=True) as close:
            with self.assertRaises(KeyboardInterrupt):await watch(Client(),'c',self.ui(True))
            self.assertTrue(close.called)

    async def test_missing_id_fails_immediately(self):
        class Client:
            def get(self,path):raise BridgeError('Conversazione non trovata')
        with self.assertRaisesRegex(BridgeError,'non trovata'):await watch(Client(),'missing',self.ui())
