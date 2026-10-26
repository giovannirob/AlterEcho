<script lang="ts">
  import {t} from './i18n';
  import type {Configuration, Profile, Provider, Side} from './api';
  import ModelSelector from './ModelSelector.svelte';
  import {efforts} from './catalog';
  export let value:Configuration;
  export let profiles:Profile[]=[];
  export let catalogs:Provider[]=[];
  export let compact=false;
  export let loading=false;
  export let refresh:()=>void=()=>{};
  $: supported=efforts(value,catalogs);
  let optionsError='';
  function selectProfile(side:Side) {const p=profiles.find(p=>p.id===value.participants[side].profile_id); if(p)value.participants[side]={profile_id:p.id,model:value.participants[side].model};}
  function options(event:Event) {try {const parsed=JSON.parse((event.target as HTMLTextAreaElement).value);if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw Error();value.ollama_options=parsed;optionsError='';}catch {optionsError='web.enter_a_valid_json_object';}}
</script>

<div class="form-grid">
  {#each ['A','B'] as letter}
    {@const side=letter as Side}
    <fieldset class="participant"><legend><span class:side-b={side==='B'} class="side">{side}</span>{$t('web.participant_name',{side})}</legend>
      <label>{$t('web.profile_label')}<select bind:value={value.participants[side].profile_id} on:change={()=>selectProfile(side)}>{#each profiles.filter(p=>side==='A'||p.provider!=='codex') as p}<option value={p.id}>{p.name} · {p.provider}{p.billable?$t('web.metered'):''}</option>{/each}</select></label>
      <ModelSelector label={$t('web.model_name',{side})} bind:value={value.participants[side].model} profileId={value.participants[side].profile_id} {catalogs} {loading} {refresh}/>
    </fieldset>
  {/each}
  <label class="wide">{$t('web.topic')}<textarea required rows="3" bind:value={value.topic}></textarea></label>
  <label>{$t('web.mode')}<select bind:value={value.mode}><option value="free">{$t('web.free_dialogue')}</option><option value="debate">{$t('web.debate')}</option><option value="blind">{$t('web.blind_experiment')}</option></select></label>
  <label>{$t('web.first_participant')}<select bind:value={value.first}><option>A</option><option>B</option></select></label>
  <label>{$t('web.total_messages')}<input required type="number" min="1" max="10000" bind:value={value.max_turns}/><small>{$t('web.10_messages_5_responses_each')}</small></label>
  <label>{$t('web.delay_between_turns_s')}<input type="number" min="0" max="3600" step="0.1" bind:value={value.delay}/></label>
</div>
{#if supported.length&&!supported.includes(value.codex_effort)}<p role="alert" class="error-text">{$t('web.unsupported_reasoning',{level:value.codex_effort})}</p>{/if}
<details open={compact}><summary>{$t('web.personalities_reasoning_and_advanced_options')}</summary><div class="form-grid advanced">
  {#each ['A','B'] as letter}{@const side=letter as Side}
    <label>{$t('web.personality_name',{side})}<textarea rows="2" bind:value={value.roles[side]}></textarea></label>
    <label>{$t('web.position_name',{side})}<textarea rows="2" bind:value={value.positions[side]}></textarea></label>
  {/each}
  {#if supported.length}<label>{$t('web.codex_reasoning')}<select aria-label="{$t('web.codex_reasoning')}" bind:value={value.codex_effort} required>{#if !supported.includes(value.codex_effort)}<option value={value.codex_effort} disabled>{value.codex_effort}{$t('web.unsupported')}</option>{/if}{#each supported as effort}<option>{effort}</option>{/each}</select><small>{$t('web.levels_returned_by_the_selected_model_catalog')}</small></label>{:else}<div><small>{$t('web.the_catalog_does_not_declare_reasoning_levels_the_server_will_verify_the_existing_configuration')}</small></div>{/if}
  <label>{$t('web.turn_timeout_s')}<input type="number" min="1" max="3600" bind:value={value.timeout}/></label>
  <label>{$t('web.ollama_context')}<input type="number" min="512" bind:value={value.num_ctx}/></label>
  <label>{$t('web.ollama_response_tokens')}<input type="number" min="1" bind:value={value.num_predict}/></label>
  <label>{$t('web.ollama_temperature')}<input type="number" min="0" max="2" step="0.05" bind:value={value.temperature}/></label>
  <label>{$t('web.api_response_tokens')}<input type="number" min="1" bind:value={value.api_max_output_tokens}/></label>
  <label>{$t('web.ollama_memory')}<select bind:value={value.ollama_keep_alive}><option value={-1}>{$t('web.never_expire_1')}</option><option value="10m">{$t('web.10_minutes')}</option><option value="5m">{$t('web.5_minutes')}</option><option value={0}>{$t('web.unload_after_each_response_0')}</option></select></label>
  <label class="check"><input type="checkbox" bind:checked={value.ollama_unload_on_exit}/>{$t('web.request_final_unload_only_if_safe')}</label>
  <label class="wide">{$t('web.other_ollama_options_json')}<textarea rows="2" value={JSON.stringify(value.ollama_options,null,2)} on:change={options}></textarea>{#if optionsError}<small class="error-text">{$t(optionsError)}</small>{/if}</label>
</div></details>
