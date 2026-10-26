export type Side = 'A' | 'B';
export type Profile = {id:string; name:string; provider:string; model:string; url:string; api_key_env:string; billable?:boolean};
export type Selection = {profile_id:string; model:string; name?:string; provider?:string; billable?:boolean};
export type Configuration = {topic:string; mode:string; first:Side; max_turns:number; delay:number; timeout:number; participants:Record<Side,Selection>; roles:Record<Side,string>; positions:Record<Side,string>; codex_effort:string; ollama_keep_alive:number|string; ollama_unload_on_exit:boolean; num_ctx:number; num_predict:number; api_max_output_tokens:number; temperature:number; ollama_options:Record<string,unknown>};
export type Message = {speaker:Side; model:string; text:string; timestamp:string; seconds:number; usage:Record<string,number>};
export type Stats = {messages:number; seconds:number; speakers:Record<string,{input_tokens:number;output_tokens:number}>};
export type Conversation = {id:string; created_at:string; status:string; active:boolean; config:Configuration; error?:string; message_count?:number; messages:Message[]; partial?:{speaker:Side;model:string;text:string}; stats:Stats; demo?:boolean; pause_requested?:boolean};
export type CatalogModel = string|{model:string;defaultReasoningEffort?:string;supportedReasoningEfforts?:({reasoningEffort:string;description?:string}|string)[]};
export type Provider = {profile_id:string; name:string; provider:string; available:boolean; models:CatalogModel[]; error?:string};
export type ServerEvent = {id:string; type:string; conversation_id:string; data:any};

let token = '';
export function setToken(value:string) {token=value;}
export async function request(path:string, method='GET', body?:unknown):Promise<Response> {
  const response=await fetch('/api/v1'+path,{method,headers:{Authorization:'Bearer '+token,...(body!==undefined?{'Content-Type':'application/json'}:{})},body:body!==undefined?JSON.stringify(body):undefined,credentials:'omit',redirect:'error'});
  if(!response.ok) {const data=await response.json().catch(()=>({detail:'Server non raggiungibile'})); throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return response;
}
export async function api<T=any>(path:string, method='GET',body?:unknown):Promise<T> {return (await request(path,method,body)).json();}
export function cleanConfiguration(c:Configuration) {
  return {...c,participants:Object.fromEntries(Object.entries(c.participants).map(([s,p])=>[s,{profile_id:p.profile_id,model:p.model}]))};
}
export async function download(id:string, format:string) {
  const response=await request(`/conversations/${id}/export/${format}`);
  const url=URL.createObjectURL(await response.blob()); const a=document.createElement('a'); a.href=url; a.download=`${id}.${format}`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export async function stream(id:string, onEvent:(event:ServerEvent)=>void, signal:AbortSignal, onRetry:()=>void) {
  let cursor='', retries=0;
  const delivered=new Map<string,number>();
  while(!signal.aborted) {
    try {
      const response=await fetch(`/api/v1/conversations/${id}/events`,{headers:{Authorization:'Bearer '+token,...(cursor?{'Last-Event-ID':cursor}:{})},signal,credentials:'omit',redirect:'error'});
      if(!response.ok||!response.body) throw new Error(`Stream HTTP ${response.status}`);
      const reader=response.body.getReader(),decoder=new TextDecoder(); let buffer='';
      try {
        while(true) {
          const chunk=await reader.read(); if(chunk.done) break;
          buffer+=decoder.decode(chunk.value,{stream:true});
          let boundary:RegExpExecArray|null;
          while((boundary=/\r?\n\r?\n/.exec(buffer))) {
            const frame=buffer.slice(0,boundary.index); buffer=buffer.slice(boundary.index+boundary[0].length);
            const data=frame.split(/\r?\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');
            if(data) {const event:ServerEvent=JSON.parse(data); const split=event.id.lastIndexOf(':'),epoch=event.id.slice(0,split),sequence=Number(event.id.slice(split+1));
              if(event.type==='state.snapshot'||sequence>(delivered.get(epoch)??-1)) {cursor=event.id;delivered.set(epoch,sequence);if(!signal.aborted)onEvent(event);}retries=0;}
          }
        }
      } finally {reader.releaseLock();}
      const state=await api<Conversation>(`/conversations/${id}`);
      if(signal.aborted)return;
      // An active GET has no atomic SSE cursor: applying it before replay would
      // double deltas already present in its partial. Recover via SSE instead.
      if(!state.active) {onEvent({id:cursor,type:'state.snapshot',conversation_id:id,data:state});return;}
    } catch(e) {if(signal.aborted)return; onRetry(); if(++retries>10)throw e;}
    await new Promise<void>(resolve=>{const done=()=>{clearTimeout(timer);signal.removeEventListener('abort',done);resolve();};const timer=setTimeout(done,Math.min(1000*(retries+1),5000)); signal.addEventListener('abort',done,{once:true});});
  }
}
