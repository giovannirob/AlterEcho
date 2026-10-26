<script lang="ts">
  import type {Provider} from './api';
  import {modelId,validSelection} from './catalog';
  export let value='';
  export let profileId='';
  export let catalogs:Provider[]=[];
  export let loading=false;
  export let label='Modello';
  export let optional=false;
  export let enabled=true;
  export let refresh:()=>void=()=>{};
  let search='';
  $: catalog=catalogs.find(c=>c.profile_id===profileId);
  $: models=catalog?.models.map(modelId)||[];
  $: valid=validSelection(profileId,value,catalogs);
</script>
<div class="model-selector">
  {#if models.length>30}<label class="model-search">Filtra catalogo<input type="search" bind:value={search} placeholder="Cerca un modello…"/></label>{/if}
  <label>{label}<select bind:value aria-label={label} required={!optional} disabled={loading||!catalog?.available||!enabled} aria-invalid={!!value&&!valid}>
    <option value="">{loading?'Caricamento catalogo…':optional?'Nessuna preferenza':'Seleziona un modello'}</option>
    {#if value&&!valid}<option value={value} disabled>{value} · non disponibile</option>{/if}
    {#each models.filter(m=>m===value||m.toLowerCase().includes(search.toLowerCase())) as model}<option value={model}>{model}</option>{/each}
  </select></label>
  <div class="catalog-help"><small class:error-text={!loading&&(!catalog?.available||!!value&&!valid)}>
    {#if loading}Verifica senza inferenze…{:else if !enabled}Salva il profilo prima di verificarne il catalogo.{:else if !catalog}Catalogo da verificare.{:else if !catalog.available}{catalog.error||'Provider non disponibile.'}{:else if !models.length}Nessun modello disponibile.{:else if value&&!valid}Il modello salvato non è nel catalogo. Scegli esplicitamente un modello disponibile.{:else}{models.length} modelli disponibili{/if}
  </small><button type="button" disabled={loading||!enabled} on:click={refresh} aria-label={'Aggiorna catalogo '+label}>↻</button></div>
</div>
<style>
  .model-selector{min-width:0}.catalog-help{display:flex;align-items:start;gap:8px;margin-top:6px}.catalog-help small{flex:1;line-height:1.5}.catalog-help button{padding:2px 8px;font-size:14px}.model-search{margin-bottom:8px}.model-search input{padding:7px}
</style>
