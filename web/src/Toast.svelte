<script lang="ts">
  import {t} from './i18n';
  import {onDestroy} from 'svelte';
  export let message:string;
  export let dismiss:()=>void;
  let timer:ReturnType<typeof setTimeout>;
  $: if(message){clearTimeout(timer);timer=setTimeout(dismiss,5500);}
  onDestroy(()=>clearTimeout(timer));
</script>
<div class="toast" role="status"><span>{message}</span><button aria-label="{$t('web.dismiss_notification')}" on:click={dismiss}>×</button></div>
<style>.toast{position:fixed;right:22px;bottom:max(58px,env(safe-area-inset-bottom));z-index:20;display:flex;align-items:center;gap:16px;max-width:min(430px,calc(100vw - 32px));padding:12px 16px;background:var(--panel);color:var(--text);border:1px solid color-mix(in srgb,var(--accent) 40%,var(--line));border-radius:12px;box-shadow:0 5px 25px #0003;font-size:12px;line-height:1.6}.toast button{border:0;background:transparent;padding:0 4px;font-size:18px}</style>
