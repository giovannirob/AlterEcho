<script lang="ts">
  import {t} from './i18n';
  import type {Provider} from './api';
  import {modelId,validSelection} from './catalog';
  export let value='';
  export let profileId='';
  export let catalogs:Provider[]=[];
  export let loading=false;
  export let label='';
  $: displayLabel=label||$t('web.model_label');
  export let optional=false;
  export let enabled=true;
  export let refresh:()=>void=()=>{};
  let search='';
  $: catalog=catalogs.find(c=>c.profile_id===profileId);
  $: models=catalog?.models.map(modelId)||[];
  $: valid=validSelection(profileId,value,catalogs);
</script>
<div class="model-selector">
  {#if models.length>30}<label class="model-search">{$t('web.filter_catalog')}<input type="search" bind:value={search} placeholder="{$t('web.search_for_a_model')}"/></label>{/if}
  <label>{displayLabel}<select bind:value aria-label={displayLabel} required={!optional} disabled={loading||!catalog?.available||!enabled} aria-invalid={!!value&&!valid}>
    <option value="">{loading?$t('web.loading_catalog'):optional?$t('web.no_preference'):$t('web.select_a_model')}</option>
    {#if value&&!valid}<option value={value} disabled>{value}{$t('web.unavailable')}</option>{/if}
    {#each models.filter(m=>m===value||m.toLowerCase().includes(search.toLowerCase())) as model}<option value={model}>{model}</option>{/each}
  </select></label>
  <div class="catalog-help"><small class:error-text={!loading&&(!catalog?.available||!!value&&!valid)}>
    {#if loading}{$t('web.checking_without_inference')}{:else if !enabled}{$t('web.save_the_profile_before_checking_its_catalog')}{:else if !catalog}{$t('web.catalog_not_checked')}{:else if !catalog.available}{catalog.error_info?.code?$t(catalog.error_info.code,catalog.error_info.params):catalog.error||$t('web.provider_unavailable')}{:else if !models.length}{$t('web.no_models_available')}{:else if value&&!valid}{$t('web.the_saved_model_is_not_in_the_catalog_explicitly_choose_an_available_model')}{:else}{$t('web.models_available',{},models.length)}{/if}
  </small><button type="button" disabled={loading||!enabled} on:click={refresh} aria-label={$t('web.refresh_catalog',{label:displayLabel})}>↻</button></div>
</div>
<style>
  .model-selector{min-width:0}.catalog-help{display:flex;align-items:start;gap:8px;margin-top:6px}.catalog-help small{flex:1;line-height:1.5}.catalog-help button{padding:2px 8px;font-size:14px}.model-search{margin-bottom:8px}.model-search input{padding:7px}
</style>
