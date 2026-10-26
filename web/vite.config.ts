import {defineConfig} from 'vite';
import {svelte} from '@sveltejs/vite-plugin-svelte';
import {readFileSync} from 'node:fs';
const version=JSON.parse(readFileSync(new URL('./package.json',import.meta.url),'utf-8')).version;
export default defineConfig({plugins:[svelte()], define:{__ALTERECHO_VERSION__:JSON.stringify(version)}, build:{outDir:'../alterecho/static', emptyOutDir:true}, server:{proxy:{'/api':process.env.ALTERECHO_DEV_API||'http://127.0.0.1:8765'}}});
