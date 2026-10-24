<script lang="ts">
  import type {Configuration, Profile, Provider, Side} from './api';
  export let value:Configuration;
  export let profiles:Profile[]=[];
  export let catalogs:Provider[]=[];
  export let compact=false;
  let optionsError='';
  function selectProfile(side:Side) {const p=profiles.find(p=>p.id===value.participants[side].profile_id); if(p)value.participants[side]={profile_id:p.id,model:p.model};}
  function options(event:Event) {try {const parsed=JSON.parse((event.target as HTMLTextAreaElement).value);if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw Error();value.ollama_options=parsed;optionsError='';}catch {optionsError='Inserisci un oggetto JSON valido.';}}
</script>

<div class="form-grid">
  {#each ['A','B'] as letter}
    {@const side=letter as Side}
    <fieldset class="participant"><legend><span class:side-b={side==='B'} class="side">{side}</span> Interlocutore {side}</legend>
      <label>Profilo<select bind:value={value.participants[side].profile_id} on:change={()=>selectProfile(side)}>{#each profiles.filter(p=>side==='A'||p.provider!=='codex') as p}<option value={p.id}>{p.name} · {p.provider}{p.billable?' · a consumo':''}</option>{/each}</select></label>
      <label>Modello<input required bind:value={value.participants[side].model} list={'models-'+side} placeholder="Scegli dal catalogo o inserisci l'ID" /></label>
      <datalist id={'models-'+side}>{#each catalogs.find(c=>c.profile_id===value.participants[side].profile_id)?.models||[] as m}<option value={typeof m==='string'?m:m.model}></option>{/each}</datalist>
    </fieldset>
  {/each}
  <label class="wide">Argomento<textarea required rows="3" bind:value={value.topic}></textarea></label>
  <label>Modalità<select bind:value={value.mode}><option value="free">Dialogo libero</option><option value="debate">Dibattito</option><option value="blind">Esperimento cieco</option></select></label>
  <label>Primo interlocutore<select bind:value={value.first}><option>A</option><option>B</option></select></label>
  <label>Messaggi totali<input required type="number" min="1" max="10000" bind:value={value.max_turns}/><small>10 messaggi = 5 risposte ciascuno</small></label>
  <label>Ritardo tra i turni (s)<input type="number" min="0" max="3600" step="0.1" bind:value={value.delay}/></label>
</div>
<details open={compact}><summary>Personalità, ragionamento e opzioni avanzate</summary><div class="form-grid advanced">
  {#each ['A','B'] as letter}{@const side=letter as Side}
    <label>Personalità {side}<textarea rows="2" bind:value={value.roles[side]}></textarea></label>
    <label>Posizione iniziale {side}<textarea rows="2" bind:value={value.positions[side]}></textarea></label>
  {/each}
  <label>Ragionamento Codex<select bind:value={value.codex_effort}>{#each ['none','minimal','low','medium','high','xhigh','max','ultra'] as effort}<option>{effort}</option>{/each}</select><small>Deve essere supportato dal modello scelto.</small></label>
  <label>Timeout del turno (s)<input type="number" min="1" max="3600" bind:value={value.timeout}/></label>
  <label>Contesto Ollama<input type="number" min="512" bind:value={value.num_ctx}/></label>
  <label>Token risposta Ollama<input type="number" min="1" bind:value={value.num_predict}/></label>
  <label>Temperature Ollama<input type="number" min="0" max="2" step="0.05" bind:value={value.temperature}/></label>
  <label>Token risposta API<input type="number" min="1" bind:value={value.api_max_output_tokens}/></label>
  <label>Memoria Ollama<select bind:value={value.ollama_keep_alive}><option value={-1}>Senza scadenza (-1)</option><option value="10m">10 minuti</option><option value="5m">5 minuti</option><option value={0}>Scarica dopo ogni risposta (0)</option></select></label>
  <label class="check"><input type="checkbox" bind:checked={value.ollama_unload_on_exit}/>Richiedi scaricamento finale solo se sicuro</label>
  <label class="wide">Altre opzioni Ollama (JSON)<textarea rows="2" value={JSON.stringify(value.ollama_options,null,2)} on:change={options}></textarea>{#if optionsError}<small class="error-text">{optionsError}</small>{/if}</label>
</div></details>
