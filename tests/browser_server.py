"""Isolated real HTTP/SSE browser-test backend. Never contacts AI providers."""
import asyncio
from dataclasses import asdict
import os
from pathlib import Path
import tempfile

import uvicorn

from alterecho.adapters.base import Reply
from alterecho.config import Config
from alterecho.history import Conversation, Message
from alterecho.integrations import new_profile
from alterecho.preferences import UserSettings
from alterecho.server import create_app
from alterecho.server_settings import ServerSettings
from alterecho.sessions import SessionManager
from alterecho.storage import Store
from unittest.mock import patch


TOKEN = 'browser-fixture-only-token-' + 'x'*32
TEXT = ("Il dialogo prende forma, una prospettiva alla volta. **Idee e domande** si incontrano.\n\n"*28
        + "| Aspetto | Prospettiva |\n|---|---|\n| Metodo | Confronto |\n\n```python\nprint('AlterEcho')\n" + "# codice leggibile\n"*15 + "```\n\nConclusione del turno.")


class ControlledAdapter:
    def __init__(self, cfg, side):self.cfg,self.side=cfg,side
    async def start(self):return [{'model':'fixture-codex','supportedReasoningEfforts':[{'reasoningEffort':'medium'},{'reasoningEffort':'high'}]}]
    async def models(self):return ['fixture-'+self.cfg.adapter_pair[self.side]['provider']]
    async def attach(self,c,checkpoint):pass
    async def prepare(self):pass
    async def close(self):pass
    async def generate(self,c,checkpoint):
        model=self.cfg.adapter_pair[self.side]['model']
        c.partial={'speaker':self.side,'model':model,'text':''}
        for i in range(0,len(TEXT),65):
            chunk=TEXT[i:i+65];c.partial['text']+=chunk
            checkpoint();checkpoint.delta(self.side,model,chunk)
            await asyncio.sleep(.045)
        return Reply(TEXT,model,{'input_tokens':30,'output_tokens':650})


def main():
    with tempfile.TemporaryDirectory(prefix='alterecho-browser-') as directory:
        os.environ['ALTERECHO_HOME']=directory
        os.environ['OPENAI_API_KEY']=os.environ['OPENROUTER_API_KEY']=''
        settings=ServerSettings(port=18876,token=TOKEN,origins=['http://127.0.0.1:18876','http://127.0.0.1:18878'])
        settings.prepare()
        profiles=[]
        for provider in ['codex','ollama','openai','openrouter']:
            p=new_profile(provider,provider.title());p['id']=provider;p['model']='fixture-'+provider;profiles.append(p)
        cfg=Config(max_turns=4,codex_effort='medium',codex_model='fixture-codex',ollama_model='fixture-ollama',adapter_pair={'codex':profiles[0],'ollama':profiles[1]})
        preferences=UserSettings();preferences.save(cfg)
        manager=SessionManager(settings);manager.catalog.save(profiles)
        async def diagnose():
            result=[]
            for p in profiles:
                models=[{'model':p['model'],'supportedReasoningEfforts':[{'reasoningEffort':'medium'},{'reasoningEffort':'high'}]}] if p['provider']=='codex' else [p['model']]
                result.append({'profile_id':p['id'],'name':p['name'],'provider':p['provider'],'available':True,'models':models})
            manager.provider_status={p['profile_id']:p for p in result}
            return result
        manager.diagnose=diagnose
        for count in [50,100]:
            history=Conversation(cfg.to_dict(),id=f'history-{count}',status='completed',messages=[Message('codex' if i%2==0 else 'ollama','fixture','Messaggio '+str(i+1)+'\n\n'+TEXT,.1) for i in range(count)])
            Store(Path(cfg.output_dir)/f'{history.id}.json').save(history)
        preview_texts=[
            "Un dialogo è utile quando **mette in discussione le ipotesi**. Non basta alternare risposte: serve una domanda che lasci spazio a prospettive diverse.\n\nProporrei tre criteri:\n- ascoltare l’argomento dell’altro;\n- distinguere fatti e interpretazioni;\n- spiegare che cosa farebbe cambiare idea.",
            "Aggiungerei un criterio: **lasciare una traccia del percorso**. Una conclusione condivisa può essere utile, ma anche capire dove rimane il disaccordo.\n\nPer esempio, possiamo concordare sul valore del confronto e avere priorità diverse: tu cerchi ipotesi più solide, io domande migliori.",
            "Allora il risultato non deve essere per forza un vincitore. Può essere una mappa più chiara del problema.\n\n> Una buona conversazione rende più preciso ciò che sappiamo e più visibile ciò che dobbiamo ancora capire.\n\nPartirei da qui per il prossimo scambio."]
        preview=Conversation(dict(cfg.to_dict(),max_turns=3),id='chat-preview',status='completed',messages=[Message('codex' if i%2==0 else 'ollama','fixture-codex' if i%2==0 else 'fixture-ollama',text,.1) for i,text in enumerate(preview_texts)])
        Store(Path(cfg.output_dir)/'chat-preview.json').save(preview)
        with patch('alterecho.profile_runtime.build_adapters',side_effect=lambda cfg:{s:ControlledAdapter(cfg,s) for s in ('codex','ollama')}):
            uvicorn.run(create_app(settings,manager),host='127.0.0.1',port=18876,log_level='warning',access_log=False)


if __name__=='__main__':main()
