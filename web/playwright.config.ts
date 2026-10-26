import {defineConfig,devices} from '@playwright/test';
import {existsSync} from 'node:fs';
const python=process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python';
const dev=process.env.ALTERECHO_BROWSER_DEV==='1';
const backend={command:`"${existsSync(python)?python.slice(3):'python'}" -m tests.browser_server`,cwd:'..',url:'http://127.0.0.1:18876/api/v1/health',reuseExistingServer:false,timeout:30000};
export default defineConfig({testDir:'./e2e',fullyParallel:false,workers:1,timeout:40000,
  use:{baseURL:dev?'http://127.0.0.1:18878':'http://127.0.0.1:18876',trace:'retain-on-failure'},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome'],viewport:{width:1440,height:960}}},{name:'mobile',use:{...devices['Pixel 7']}}],
  webServer:dev?[backend,{command:'npm run dev -- --port 18878 --strictPort',url:'http://127.0.0.1:18878',reuseExistingServer:false,timeout:30000,env:{ALTERECHO_DEV_API:'http://127.0.0.1:18876'}}]:backend});
