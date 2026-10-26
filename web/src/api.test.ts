import {afterEach,describe,it,expect,vi} from 'vitest';
import {api,cleanConfiguration,setToken,stream,type Configuration} from './api';
import {errorText,LocalizedError} from './i18n';
afterEach(()=>vi.unstubAllGlobals());
describe('shared HTTP client',()=>{
  it('keeps legacy detail and exposes structured errors for either client language',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({detail:'legacy provider diagnostic'}),{status:400})).mockResolvedValueOnce(new Response(JSON.stringify({detail:'Conversation not found.',code:'server.conversation_not_found',params:{}}),{status:404})));
    await expect(api('/legacy')).rejects.toThrow('legacy provider diagnostic');
    try{await api('/missing');throw Error('Request unexpectedly succeeded');}catch(error){expect(error).toBeInstanceOf(LocalizedError);expect(errorText(error,'it')).toBe('Conversazione non trovata.');}
  });
  it('transmits only the service bearer credential',async()=>{const fetch=vi.fn().mockResolvedValue(new Response('{"ok":true}'));vi.stubGlobal('fetch',fetch);setToken('fixture-service');await api('/status');const [,options]=fetch.mock.calls[0];expect(options.headers.Authorization).toBe('Bearer fixture-service');expect(options.credentials).toBe('omit');expect(options.redirect).toBe('error');});
  it('removes provider metadata from generation requests',()=>{const c={participants:{A:{profile_id:'p',model:'m',provider:'openai',name:'A',billable:true},B:{profile_id:'b',model:'n'}}} as Configuration;expect(cleanConfiguration(c).participants.A).toEqual({profile_id:'p',model:'m'});});
  it('parses real fragmented SSE without splitting a completed reply',async()=>{const event={id:'epoch:1',type:'message.delta',conversation_id:'c',data:{delta:'è'}};const bytes=new TextEncoder().encode(`id: epoch:1\ndata: ${JSON.stringify(event)}\n\n`);const body=new ReadableStream({start(c){c.enqueue(bytes.slice(0,37));c.enqueue(bytes.slice(37));c.close();}});const fetch=vi.fn().mockResolvedValueOnce(new Response(body)).mockResolvedValueOnce(new Response(JSON.stringify({active:false,messages:[]})));vi.stubGlobal('fetch',fetch);const events:any[]=[];await stream('c',e=>events.push(e),new AbortController().signal,()=>{});expect(events[0]).toEqual(event);expect(events[1].type).toBe('state.snapshot');});
});

describe('SSE recovery boundaries',()=>{
  it('handles UTF-8 and CRLF split at every byte and ignores repeated event IDs',async()=>{
    const event={id:'e:1',type:'message.delta',conversation_id:'c',data:{delta:'è 日本語'}};
    const bytes=new TextEncoder().encode(`data: ${JSON.stringify(event)}\r\n\r\ndata: ${JSON.stringify(event)}\r\n\r\n`);
    const body=new ReadableStream({start(c){for(const byte of bytes)c.enqueue(new Uint8Array([byte]));c.close();}});
    vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(new Response(body)).mockResolvedValueOnce(new Response('{"active":false}')));
    const events:any[]=[];await stream('c',e=>events.push(e),new AbortController().signal,()=>{});
    expect(events.filter(e=>e.type==='message.delta')).toEqual([event]);
  });
  it('never applies an active GET snapshot before cursor replay',async()=>{
    const delta=(id:string,text:string)=>({id,type:'message.delta',conversation_id:'c',data:{index:1,speaker:'A',model:'m',delta:text}});
    const body=(e:any)=>new Response(`data: ${JSON.stringify(e)}\n\n`);
    const fetch=vi.fn().mockResolvedValueOnce(body(delta('e:1','ab'))).mockResolvedValueOnce(new Response('{"active":true,"partial":{"text":"abcd"}}'))
      .mockResolvedValueOnce(body(delta('e:2','cd'))).mockResolvedValueOnce(new Response('{"active":false,"messages":[]}'));
    vi.stubGlobal('fetch',fetch);const events:any[]=[];
    await stream('c',e=>events.push(e),new AbortController().signal,()=>{});
    expect(events.filter(e=>e.type==='message.delta').map(e=>e.data.delta).join('')).toBe('abcd');
    expect(events.filter(e=>e.type==='state.snapshot')).toHaveLength(1);
    expect(fetch.mock.calls[2][1].headers['Last-Event-ID']).toBe('e:1');
  });
});
