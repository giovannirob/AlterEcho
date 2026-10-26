<script lang="ts">
  import {t} from './i18n';
  import {onMount} from 'svelte';
  import LanguageSelector from './LanguageSelector.svelte';
  export let title:string;
  export let confirmLabel='';
  export let danger=false;
  export let disabled=false;
  export let confirm:()=>void;
  export let cancel:()=>void;
  let dialog:HTMLDialogElement;
  onMount(()=>{
    const previous=document.activeElement as HTMLElement;
    const overflow=document.body.style.overflow;
    document.body.style.overflow='hidden';
    dialog.showModal();
    dialog.querySelector<HTMLButtonElement>('[data-cancel]')?.focus();
    return()=>{dialog.close();document.body.style.overflow=overflow;previous?.focus();};
  });
</script>
<dialog bind:this={dialog} aria-labelledby="confirm-title" on:cancel|preventDefault={cancel} class:danger>
  <div class="dialog-heading"><span aria-hidden="true">{danger?'!':'↔'}</span><h2 id="confirm-title">{title}</h2></div>
  <div class="dialog-content"><slot/></div>
  <LanguageSelector/>
  <div class="dialog-actions"><button type="button" data-cancel on:click={cancel}>{$t('web.cancel')}</button><button type="button" class={danger?'danger':'primary'} {disabled} on:click={confirm}>{confirmLabel||$t('web.confirm')}</button></div>
</dialog>
<style>
  dialog{width:min(540px,calc(100vw - 28px));max-height:calc(100dvh - 32px);overflow:auto;margin:auto;padding:26px;border:1px solid var(--line);border-radius:18px;background:var(--panel);color:var(--text);box-shadow:0 24px 90px #0006;animation:appear .15s ease}dialog::backdrop{background:#070b14b3;backdrop-filter:blur(3px)}.dialog-heading{display:flex;align-items:center;gap:12px}.dialog-heading span{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;color:var(--accent);background:var(--bg)}.danger .dialog-heading span{color:var(--danger)}h2{font-size:20px;margin:0}.dialog-content{margin:22px 0;line-height:1.7;font-size:14px}.dialog-actions{display:flex;justify-content:flex-end;gap:10px;padding-top:18px;border-top:1px solid var(--line)}@keyframes appear{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}@media(prefers-reduced-motion:reduce){dialog{animation:none}}@media(max-width:500px){dialog{padding:20px}.dialog-actions button{flex:1}}
</style>
