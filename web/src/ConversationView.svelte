<script lang="ts">
  import {afterUpdate,onMount,onDestroy,tick} from 'svelte';
  import type {Conversation,Side} from './api';
  import MessageBubble from './MessageBubble.svelte';
  import {positions} from './conversation';
  export let conversation:Conversation;
  export let busy=false;
  export let copy:(text:string)=>void;
  export let control:(action:string)=>void;
  export let resume:()=>void;
  export let remove:()=>void;
  export let download:(format:string)=>void;
  let scroller:HTMLDivElement,content:HTMLDivElement;
  let follow=true,frame=0,query='',touchY=0,lastTop=0;
  const labels:Record<string,string>={completed:'Completata',running:'In corso',starting:'In avvio',paused:'In pausa',interrupted:'Interrotta',failed:'Errore',stopped:'Arrestata'};
  $: rows=[...conversation.messages,...(conversation.partial?[conversation.partial]:[])];
  function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;if(follow&&scroller){scroller.scrollTop=scroller.scrollHeight;lastTop=scroller.scrollTop;}});}
  function scroll(){if(!scroller.isConnected)return;const top=scroller.scrollTop,distance=scroller.scrollHeight-scroller.clientHeight-top;if(top<lastTop-1)follow=false;else if(distance<20)follow=true;lastTop=top;positions.set(conversation.id,{top:lastTop,follow});}
  function bottom(){follow=true;scroller.scrollTo({top:scroller.scrollHeight,behavior:'instant'});lastTop=scroller.scrollTop;schedule();}
  function wheel(e:WheelEvent){if(e.deltaY<0)follow=false;}
  function key(e:KeyboardEvent){
    if(e.target!==scroller||e.altKey||e.ctrlKey||e.metaKey)return;
    const steps:Record<string,number>={ArrowUp:-40,ArrowDown:40,PageUp:-scroller.clientHeight*.85,PageDown:scroller.clientHeight*.85};
    if(e.key==='End'){e.preventDefault();bottom();}
    else if(e.key==='Home'||e.key in steps){e.preventDefault();if(e.key==='Home'||steps[e.key]<0)follow=false;scroller.scrollTo({top:e.key==='Home'?0:scroller.scrollTop+steps[e.key],behavior:'instant'});}
  }
  onMount(()=>{
    const saved=positions.get(conversation.id);follow=saved?.follow??true;
    tick().then(()=>{if(saved&&!saved.follow){scroller.scrollTop=saved.top;lastTop=scroller.scrollTop;}else schedule();});
    const observer=new ResizeObserver(schedule);observer.observe(content);observer.observe(scroller);
    return()=>observer.disconnect();
  });
  afterUpdate(schedule);
  onDestroy(()=>{positions.set(conversation.id,{top:lastTop,follow});cancelAnimationFrame(frame);});
</script>
<section class="chat-view" aria-label="Conversazione">
  <div class="chat-header"><div class="chat-title"><div class="title-line"><span class="badge" class:running={conversation.active}>{labels[conversation.status]||conversation.status}</span><small>{conversation.messages.length} / {conversation.config.max_turns} messaggi</small></div><h1>{conversation.config.topic}</h1><div class="identities">{#each ['A','B'] as s}{@const side=s as Side}<span class:b={side==='B'}><b>{side}</b> {conversation.config.participants[side].name}<small>{conversation.config.participants[side].model}</small></span>{/each}</div></div><div class="controls">{#if conversation.active}<button disabled={busy||conversation.pause_requested} on:click={()=>control('pause')}>{conversation.pause_requested?'Pausa richiesta':'Pausa'}</button><button class="danger" disabled={busy} on:click={()=>control('stop')}>Arresta</button>{:else if !conversation.demo}<button disabled={busy} on:click={resume}>Riprendi</button>{/if}<details class="info"><summary aria-label="Informazioni e strumenti">•••</summary><div class="info-panel"><small>ID conversazione</small><code>{conversation.id}</code><button on:click={()=>copy(conversation.id)}>Copia ID</button><label>Cerca nei messaggi<input type="search" bind:value={query}/></label><div class="export-buttons">{#each ['html','md','txt','json'] as fmt}<button on:click={()=>download(fmt)}>{fmt.toUpperCase()}</button>{/each}</div><button class="danger" disabled={busy||conversation.active} on:click={remove}>Elimina conversazione</button></div></details></div></div>
  {#if conversation.error}<div role="alert" class="alert error">{conversation.error}</div>{/if}
  <div class="chat-area">
  <!-- svelte-ignore a11y_no_noninteractive_tabindex a11y_no_noninteractive_element_interactions (A keyboard-focusable scroll region supports reading with PageUp/Down.) -->
  <div class="chat-scroll" bind:this={scroller} on:scroll={scroll} on:wheel|passive={wheel} on:keydown={key} on:touchstart|passive={(e)=>touchY=e.touches[0].clientY} on:touchmove|passive={(e)=>{if(e.touches[0].clientY>touchY+2)follow=false;touchY=e.touches[0].clientY;}} tabindex="0" role="region" aria-label="Messaggi della conversazione"><div class="chat-column" bind:this={content}>
    {#each rows as message,index (index)}{#if !query||message.text.toLowerCase().includes(query.toLowerCase())}<MessageBubble {message} participant={conversation.config.participants[message.speaker]} index={index+1} pending={index>=conversation.messages.length} active={conversation.active} {copy}/>{/if}{/each}
    {#if !rows.length}<div class="empty"><span>↔</span><p>Il dialogo sta per iniziare.</p></div>{/if}
  </div></div>{#if !follow}<button class="jump-bottom" aria-label="Vai all'ultimo messaggio" title="Vai all'ultimo messaggio" on:click={bottom}>↓</button>{/if}</div>
  <div class="chat-bottom"><span>{conversation.active?'Il dialogo prosegue sul server.':'Dialogo salvato sul server.'}</span><details><summary>{conversation.stats.seconds.toFixed(1)} s · Token e statistiche</summary><div class="stats-popover">{#each Object.entries(conversation.stats.speakers) as [side,stats]}<p><b>{side}</b> · {stats.input_tokens} input / {stats.output_tokens} output token misurati</p>{/each}<small>{conversation.messages.length} messaggi completati · {labels[conversation.status]||conversation.status}</small></div></details></div>
</section>
<style>
  .controls{display:flex;align-items:center;gap:8px;flex-shrink:0}
  .chat-view{display:flex;flex-direction:column;flex:1;min-height:0;height:100%;position:relative}.chat-header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line);padding:20px 28px;background:var(--bg);z-index:3}.chat-title{min-width:0}.title-line{display:flex;gap:12px;align-items:center}.title-line small{font-size:10px}h1{font-size:20px;line-height:1.4;letter-spacing:-.4px;margin:8px 0;display:-webkit-box;-webkit-line-clamp:2;line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.identities{display:flex;gap:16px;flex-wrap:wrap}.identities>span{color:var(--accent);font-size:11px}.identities>span.b{color:var(--b)}.identities b{margin-right:5px}.identities small{margin-left:6px;color:var(--muted);font-size:10px}.controls{flex-shrink:0}.info{position:relative;margin:0;padding:0;border:0}.info>summary{list-style:none;padding:8px 10px;border:1px solid var(--line);border-radius:8px}.info-panel{position:absolute;right:0;top:36px;width:300px;padding:18px;display:flex;flex-direction:column;gap:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:0 12px 40px #0004}.info-panel code{overflow-wrap:anywhere;font-size:11px}.info-panel label{font-size:11px}.chat-area{flex:1;min-height:0;position:relative}.chat-scroll{height:100%;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;overflow-anchor:none;outline-offset:-3px}.chat-column{width:min(100%,990px);padding:32px 32px 28px;margin:auto}.jump-bottom{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);width:44px;height:44px;padding:0;border-radius:50%;background:var(--panel);color:var(--text);border:1px solid var(--line);box-shadow:0 4px 20px #0003;font-size:24px;animation:appear .15s ease}.chat-bottom{flex-shrink:0;display:flex;justify-content:space-between;gap:12px;padding:12px 26px max(12px,env(safe-area-inset-bottom));border-top:1px solid var(--line);font-size:10px;color:var(--muted);background:var(--bg)}.chat-bottom details{margin:0;padding:0;border:0;position:relative}.chat-bottom summary{font-size:10px}.stats-popover{position:absolute;right:0;bottom:26px;width:300px;max-width:80vw;padding:15px;background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:0 6px 25px #0004}.chat-view>.alert{margin:8px 20px}.chat-scroll:focus-visible{outline:2px solid var(--accent)}@keyframes appear{from{opacity:0}to{opacity:1}}@media(prefers-reduced-motion:reduce){.jump-bottom{animation:none}}@media(max-width:700px){.chat-header{padding:12px;gap:8px}h1{font-size:16px}.controls{gap:5px}.controls button{font-size:10px;padding:7px}.identities{gap:6px;display:block}.identities>span{display:block;font-size:10px;line-height:1.8}.identities small{font-size:9px}.chat-column{padding:22px 10px}.chat-bottom{padding:10px 12px max(10px,env(safe-area-inset-bottom));font-size:9px}.chat-bottom summary{font-size:9px}.chat-bottom>span{max-width:40%}.info-panel{width:min(290px,calc(100vw - 24px))}.title-line .badge{font-size:8px}.title-line small{font-size:9px}}
</style>
