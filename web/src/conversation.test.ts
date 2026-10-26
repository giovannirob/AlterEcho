import {describe,it,expect} from 'vitest';
import {applyEvent} from './conversation';
import {configurationValid,efforts} from './catalog';
import type {Configuration,Conversation,Provider,ServerEvent} from './api';
const config={participants:{A:{profile_id:'a',model:'a-model'},B:{profile_id:'b',model:'b-model'}},codex_effort:'medium'} as Configuration;
const catalogs:Provider[]=[{profile_id:'a',name:'A',provider:'codex',available:true,models:[{model:'a-model',supportedReasoningEfforts:[{reasoningEffort:'medium'},{reasoningEffort:'high'}]}]},{profile_id:'b',name:'B',provider:'ollama',available:true,models:['b-model']}];
const event=(type:string,data:any):ServerEvent=>({id:'e:1',conversation_id:'c',type,data});
describe('indexed chat and verified catalogs',()=>{
  it('keeps one bubble from turn start through native deltas and completion',()=>{
    let c={id:'c',config,messages:[],active:true} as unknown as Conversation;
    c=applyEvent(c,event('turn.started',{index:1,speaker:'A'}));expect(c.partial?.text).toBe('');
    c=applyEvent(c,event('message.delta',{index:1,speaker:'A',model:'a-model',delta:'uno'}));
    c=applyEvent(c,event('message.delta',{index:1,speaker:'A',model:'a-model',delta:' due'}));expect(c.partial?.text).toBe('uno due');
    const completed=event('message.completed',{index:1,message:{speaker:'A',text:'uno due'}});
    c=applyEvent(c,completed);expect(c.messages).toHaveLength(1);expect(c.partial).toBeUndefined();
    expect(applyEvent(c,completed)).toBe(c);expect(applyEvent(c,event('message.delta',{index:1,delta:'duplicate'}))).toBe(c);
  });
  it('replaces partial with authoritative snapshot, preserves old history models',()=>{
    const snapshot={messages:[{model:'retired-model'}],partial:{text:'current'}} as Conversation;
    expect(applyEvent({} as Conversation,event('state.snapshot',snapshot))).toBe(snapshot);
  });
  it('rejects offline, empty, removed models and unsupported reasoning without substitution',()=>{
    expect(configurationValid(config,catalogs)).toBe(true);
    expect(configurationValid(config,[])).toBe(false);
    expect(configurationValid(config,catalogs.map(c=>({...c,models:[]})))).toBe(false);
    expect(configurationValid(config,catalogs.map(c=>({...c,available:false})))).toBe(false);
    expect(configurationValid({...config,codex_effort:'ultra'},catalogs)).toBe(false);
    expect(efforts(config,catalogs)).toEqual(['medium','high']);
    expect(config.participants.A.model).toBe('a-model');
  });
});
