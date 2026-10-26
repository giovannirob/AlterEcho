<script lang="ts">
  import type {Message,Selection,Side} from './api';
  import {markdown} from './markdown';
  export let message:Message|{speaker:Side;model:string;text:string};
  export let participant:Selection;
  export let index:number;
  export let pending=false;
  export let active=false;
  export let copy:(text:string)=>void;
  let previous='',html='';
  $: if(message.text!==previous){previous=message.text;html=markdown(previous);}
  $: full='usage' in message?message as Message:null;
</script>
<article class="chat-message" class:side-b={message.speaker==='B'} data-turn={index}>
  <div class="avatar" aria-hidden="true">{message.speaker}</div>
  <div class="bubble">
    <div class="bubble-heading"><div><strong>{participant.name||'Interlocutore '+message.speaker}</strong><small>{message.model} <span>· {index}</span></small></div><button type="button" class="text-button" on:click={()=>copy(message.text)} aria-label={'Copia messaggio '+index}>Copia</button></div>
    <div class="markdown">{@html html}</div>
    {#if pending}<div class="generating" role="status"><span class:working={active}></span>{active?'Generazione in corso…':'Risposta parziale · non completata'}</div>{/if}
    {#if full}<details class="message-details"><summary>{full.seconds.toFixed(1)} s{#if full.usage.output_tokens!==undefined} · {full.usage.output_tokens} token output{/if}<span>Dettagli</span></summary><dl><dt>Data</dt><dd>{new Date(full.timestamp).toLocaleString('it-IT')}</dd>{#each Object.entries({input_tokens:'Token input',output_tokens:'Token output',tokens_per_second:'Token/s',load_seconds:'Caricamento (s)',generation_seconds:'Generazione (s)'}) as [key,label]}{#if full.usage[key]!==undefined}<dt>{label}</dt><dd>{full.usage[key]}</dd>{/if}{/each}</dl></details>{/if}
  </div>
</article>
<style>
  .chat-message{color:var(--text);background:transparent}
  .chat-message{display:flex;align-items:flex-start;gap:12px;width:94%;max-width:850px;margin:0 auto 26px 0;--speaker:var(--accent)}.chat-message.side-b{margin-left:auto;margin-right:0;--speaker:var(--b)}.avatar{flex:0 0 30px;height:30px;border-radius:10px;display:grid;place-items:center;color:var(--speaker);background:color-mix(in srgb,var(--speaker) 12%,var(--bg));border:1px solid color-mix(in srgb,var(--speaker) 30%,var(--line));font-size:12px;margin-top:5px}.bubble{min-width:0;flex:1;border:1px solid color-mix(in srgb,var(--speaker) 16%,var(--line));background:color-mix(in srgb,var(--speaker) 3%,var(--panel-soft));border-radius:4px 18px 18px;padding:20px 24px}.side-b .bubble{border-radius:18px 4px 18px 18px}.bubble-heading{display:flex;align-items:center;gap:12px;margin-bottom:15px}.bubble-heading strong{font-size:13px;color:var(--speaker)}.bubble-heading small{display:block;margin-top:4px;font-size:11px;overflow-wrap:anywhere}.bubble-heading button{margin-left:auto;font-size:11px;padding:5px}.generating{font-size:11px;color:var(--muted);display:flex;gap:8px;align-items:center;margin-top:12px}.generating>span{width:6px;height:6px;border-radius:50%;background:var(--speaker)}.working{animation:pulse 1.3s infinite}.message-details{margin:18px 0 0;padding-top:10px;border-top:1px solid var(--line)}.message-details summary{font-size:10px;color:var(--muted)}.message-details summary span{float:right}.message-details dl{display:grid;grid-template-columns:1fr auto;gap:6px;font-size:11px;color:var(--muted)}dd{margin:0} @keyframes pulse{50%{opacity:.3}}@media(prefers-reduced-motion:reduce){.working{animation:none}}@media(max-width:700px){.chat-message{width:100%;gap:8px;margin-bottom:20px}.avatar{flex-basis:24px;height:24px;font-size:10px;border-radius:8px}.bubble{padding:15px 16px}.bubble-heading small{font-size:10px}}
</style>
