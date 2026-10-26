<script lang="ts">
  import {t,preference,languages,setPreference} from './i18n';
</script>
<label class="language-selector">{$t('language.label')}
  <select aria-label={$t('language.label')} value={$preference} on:change={event=>setPreference(event.currentTarget.value)}>
    <option value="auto">{$t('language.automatic')}</option>
    {#each languages as item}<option value={item.code}>{item.name}</option>{/each}
  </select>
</label>
<style>.language-selector{font-size:11px;display:block;margin:10px 0}.language-selector select{margin-top:5px;max-width:100%}</style>
