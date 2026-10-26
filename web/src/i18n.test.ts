// @vitest-environment jsdom
import {afterEach,describe,it,expect} from 'vitest';
import {get} from 'svelte/store';
import {catalogs,detect,normalize,language,preference,setPreference,storageKey,translate,LocalizedError,errorText} from './i18n';
import {parse} from 'svelte/compiler';

afterEach(()=>{setPreference('auto');localStorage.removeItem(storageKey);});
describe('client-local language catalogs',()=>{
  it('keeps human-facing component text in catalogs and every referenced key in English',()=>{
    const technical=new Set(['AlterEcho ·','ALTERECHO /','AlterEcho','a','e','A','B','s','codex','ollama','openai','openrouter','×']);
    const components=import.meta.glob('./*.svelte',{eager:true,query:'?raw',import:'default'}) as Record<string,string>;
    for(const [file,source] of Object.entries(components)){
      const walk=(node:any)=>{
        if(!node||typeof node!=='object')return;
        if(node.type==='Text'&&/[A-Za-zÀ-ÿ]/.test(node.data))expect(technical.has(node.data.trim()),`${file}: ${node.data}`).toBe(true);
        for(const [key,value]of Object.entries(node)){
          if(['attributes','css','instance','module','expression'].includes(key))continue;
          if(Array.isArray(value))value.forEach(walk);else if(value&&typeof value==='object')walk(value);
        }
      };
      walk(parse(source).html);
      for(const match of source.matchAll(/\$t\(['"]([^'"]+)['"]/g))expect(catalogs.en[match[1]],file+': '+match[1]).toBeDefined();
    }
  });
  it('selects the first supported browser preference and falls back to English',()=>{
    expect(detect(['it-IT'])).toBe('it');expect(detect(['en-US'])).toBe('en');
    expect(detect(['de-DE','it-CH','en-GB'])).toBe('it');expect(detect(['de','fr'])).toBe('en');
    expect(normalize('it_IT')).toBe('it');
  });
  it('stores only the local preference and updates immediately',()=>{
    setPreference('it');expect(get(language)).toBe('it');expect(localStorage.getItem(storageKey)).toBe('it');
    setPreference('en');expect(get(language)).toBe('en');expect(document.documentElement.lang).toBe('en');
    setPreference('auto');expect(get(preference)).toBe('auto');
  });
  it('keeps catalog keys and interpolation parameters aligned',()=>{
    expect(Object.keys(catalogs.en).sort()).toEqual(Object.keys(catalogs.it).sort());
    for(const key of Object.keys(catalogs.en).filter(k=>k!=='_meta')){
      const fields=(value:unknown)=>[...new Set(JSON.stringify(value).match(/\{\w+\}/g)||[])].sort();
      expect(fields(catalogs.en[key]),key).toEqual(fields(catalogs.it[key]));
    }
  });
  it('handles missing translations, plurals and parameters as plain text',()=>{
    const saved=catalogs.it['web.history'];delete catalogs.it['web.history'];
    try{expect(translate('it','web.history')).toBe('History');}finally{catalogs.it['web.history']=saved;}
    expect(translate('en','web.messages',{},1)).toBe('1 message');expect(translate('it','web.messages',{},2)).toBe('2 messaggi');
    expect(translate('en','web.delete_topic',{topic:'<script>original</script>'})).toContain('<script>original</script>');
  });
  it('can re-render the same error in either language without changing diagnostics',()=>{
    const error=new LocalizedError('server.conversation_not_found');
    expect(errorText(error,'it')).toBe('Conversazione non trovata.');expect(errorText(error,'en')).toBe('Conversation not found.');
    expect(errorText(new Error('external 日本語'),'it')).toBe('external 日本語');
  });
});
