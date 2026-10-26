import {test,expect, type Page} from '@playwright/test';
const token='browser-fixture-only-token-'+'x'.repeat(32);
test('chat overview remains readable with three distinct messages and themes',async({page},info)=>{
  await login(page,'chat-preview');await expect(page.locator('.chat-message')).toHaveCount(3);
  await expect(page.locator('.generating')).toHaveCount(0);
  if(info.project.name==='mobile')await page.getByRole('button',{name:'Chiaro',exact:false}).click();
  await page.screenshot({path:`test-results/overview-${info.project.name}.png`});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
async function login(page:Page,history='') {
  await page.goto('/'+(history?'#conversation='+history:''));
  await page.getByLabel('Token del servizio').fill(token);
  await page.getByRole('button',{name:'Collega al server'}).click();
  await expect(page.locator('.shell')).toBeVisible();
}
async function bottomDistance(page:Page){return page.locator('.chat-scroll').evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop);}
async function newChat(page:Page){
  await page.getByRole('navigation').getByRole('button',{name:'Nuova conversazione'}).click();
  await expect(page.getByRole('combobox',{name:'Modello A',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Avvia conversazione'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button',{name:'Avvia conversazione',exact:true}).click();
  await expect(page.locator('.chat-scroll')).toBeVisible();
}
test('streaming follows bottom, respects reading, reconnects, restores and never duplicates',async({page},info)=>{
  await login(page);await newChat(page);
  const scroller=page.locator('.chat-scroll');
  await expect(page.locator('.chat-message')).toHaveCount(1);
  await expect.poll(()=>scroller.evaluate(e=>e.scrollHeight>e.clientHeight+300)).toBeTruthy();
  await expect.poll(()=>bottomDistance(page)).toBeLessThan(24);
  const first=await page.locator('[data-turn="1"]').elementHandle();
  await scroller.hover();await page.mouse.wheel(0,-600);
  const jump=page.getByRole('button',{name:"Vai all'ultimo messaggio"});await expect(jump).toBeVisible();
  const readingTop=await scroller.evaluate(e=>e.scrollTop);
  await page.waitForTimeout(450);
  expect(await scroller.evaluate(e=>e.scrollTop)).toBeCloseTo(readingTop,0);
  // Force the real HTTP SSE transport to disconnect, then recover by cursor.
  await page.context().setOffline(true);await page.waitForTimeout(150);await page.context().setOffline(false);
  await page.waitForTimeout(1400);
  expect(await scroller.evaluate(e=>e.scrollTop)).toBeCloseTo(readingTop,0);
  await jump.click();await expect(jump).toBeHidden();await expect.poll(()=>bottomDistance(page)).toBeLessThan(24);
  await expect(page.locator('[data-turn="2"]')).toBeVisible({timeout:20000});
  await page.screenshot({path:`test-results/chat-${info.project.name}-stream.png`});
  expect(await first?.evaluate(e=>e.isConnected)).toBeTruthy();
  await expect(page.locator('[data-turn="1"]')).toHaveCount(1);
  await expect(page.locator('[data-turn="1"] .generating')).toHaveCount(0);
  await expect.poll(()=>bottomDistance(page)).toBeLessThan(24);
  await scroller.focus();await page.keyboard.press('Home');await expect(jump).toBeVisible();
  await expect.poll(()=>scroller.evaluate(e=>e.scrollTop)).toBe(0);
  await scroller.evaluate(e=>e.scrollTop=600);await page.waitForTimeout(100);
  const position=await scroller.evaluate(e=>e.scrollTop);
  await page.getByRole('navigation').getByRole('button',{name:'Cronologia'}).click();
  await page.locator('.history-main').first().click();
  await expect.poll(()=>scroller.evaluate(e=>e.scrollTop)).toBeCloseTo(position,0);
  await page.screenshot({path:`test-results/chat-${info.project.name}-dark.png`});
  await page.getByRole('button',{name:'Chiaro',exact:false}).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.screenshot({path:`test-results/chat-${info.project.name}-light.png`});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.getByRole('button',{name:'Arresta',exact:true}).click();
});
for(const count of [50,100])test(`${count}-message history opens at end, keyboard/touch scrolling and stable components`,async({page},info)=>{
  await login(page,'history-'+count);await expect(page.locator('.chat-message')).toHaveCount(count);
  await expect.poll(()=>bottomDistance(page)).toBeLessThan(24);
  const scroller=page.locator('.chat-scroll');await scroller.focus();await page.keyboard.press('PageUp');
  const jump=page.getByRole('button',{name:"Vai all'ultimo messaggio"});await expect(jump).toBeVisible();
  if(info.project.name==='mobile'){
    await scroller.dispatchEvent('touchstart',{touches:[{identifier:1,clientX:200,clientY:300}]});
    await scroller.dispatchEvent('touchmove',{touches:[{identifier:1,clientX:200,clientY:500}]});
    await expect(jump).toBeVisible();
    await page.setViewportSize({width:851,height:393});
  }
  await jump.click();await expect(jump).toBeHidden();await expect.poll(()=>bottomDistance(page)).toBeLessThan(24);
  await expect(page.locator('.markdown table')).toHaveCount(count);
  await expect(page.locator('.markdown pre')).toHaveCount(count);
  await page.screenshot({path:`test-results/history-${count}-${info.project.name}.png`});
});
test('catalog selects only verified models, modal focus, explicit paid consent, empty/error states',async({page},info)=>{
  let nativeDialogs=0;page.on('dialog',dialog=>{nativeDialogs++;void dialog.dismiss();});
  await login(page);await page.screenshot({path:`test-results/dashboard-${info.project.name}.png`});
  await page.getByRole('navigation').getByRole('button',{name:'Nuova conversazione'}).click();
  await expect(page.getByRole('combobox',{name:'Modello A',exact:true})).toHaveValue('fixture-codex');
  await page.screenshot({path:`test-results/new-${info.project.name}.png`,fullPage:true});
  await page.getByText('Personalit'+String.fromCharCode(224)+', ragionamento e opzioni avanzate',{exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Ragionamento Codex',exact:true})).toHaveCount(1);
  await expect(page.getByRole('combobox',{name:'Ragionamento Codex',exact:true}).locator('option')).toHaveText(['medium','high']);
  await page.getByRole('combobox',{name:'Profilo',exact:true}).first().selectOption('openai');
  await expect(page.getByRole('button',{name:'Avvia conversazione'})).toBeDisabled();
  await page.getByRole('combobox',{name:'Modello A',exact:true}).selectOption('fixture-openai');
  await expect(page.getByRole('combobox',{name:'Modello A',exact:true})).toHaveValue('fixture-openai');
  await expect(page.getByRole('combobox',{name:'Modello A',exact:true}).locator('option')).toHaveText(['Seleziona un modello','fixture-openai']);
  await page.getByRole('button',{name:'Avvia conversazione'}).click();
  const modal=page.getByRole('dialog');await expect(modal).toBeVisible();
  const start=modal.getByRole('button',{name:'Avvia conversazione',exact:true});await expect(start).toBeDisabled();
  await expect(modal.getByRole('button',{name:'Annulla'})).toBeFocused();
  await page.keyboard.press('Shift+Tab');expect(await modal.evaluate((e)=>e.contains(document.activeElement))).toBeTruthy();
  await page.screenshot({path:`test-results/confirm-${info.project.name}.png`});
  await modal.getByRole('checkbox').check();await expect(start).toBeEnabled();
  await page.keyboard.press('Escape');await expect(modal).toBeHidden();
  await expect(page.getByRole('button',{name:'Avvia conversazione'})).toBeFocused();
  await page.route('**/api/v1/doctor',route=>route.fulfill({json:{providers:[{profile_id:'openai',provider:'openai',available:true,models:[]},{profile_id:'ollama',provider:'ollama',available:false,models:[],error:'Offline simulato'}]}}));
  await page.getByRole('button',{name:'Aggiorna modelli',exact:false}).click();
  await expect(page.getByText('Nessun modello disponibile.',{exact:true})).toBeVisible();
  await expect(page.getByText('Offline simulato',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Avvia conversazione'})).toBeDisabled();
  expect(nativeDialogs).toBe(0);
});
test('paid start and resume require fresh consent; delete is deliberate and has no native popup',async({page})=>{
  await login(page);await page.getByRole('navigation').getByRole('button',{name:'Nuova conversazione'}).click();
  await page.getByRole('combobox',{name:'Profilo',exact:true}).first().selectOption('openai');
  await page.getByRole('combobox',{name:'Modello A',exact:true}).selectOption('fixture-openai');
  await page.getByRole('button',{name:'Avvia conversazione'}).click();
  let modal=page.getByRole('dialog');await modal.getByRole('checkbox').check();
  const started=page.waitForRequest(r=>r.method()==='POST'&&r.url().endsWith('/api/v1/conversations'));
  await modal.getByRole('button',{name:'Avvia conversazione',exact:true}).click();
  expect((await started).postDataJSON().confirm_paid).toBe(true);
  await expect(page.locator('.generating')).toBeVisible();
  await page.getByRole('button',{name:'Arresta',exact:true}).click();
  await expect(page.getByRole('button',{name:'Riprendi',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Riprendi',exact:true}).click();
  modal=page.getByRole('dialog');const resume=modal.getByRole('button',{name:'Verifica e riprendi'});
  await expect(resume).toBeDisabled();await modal.getByRole('checkbox').check();await expect(resume).toBeEnabled();
  await page.keyboard.press('Escape');
  await page.getByLabel('Informazioni e strumenti').click();await page.getByRole('button',{name:'Elimina conversazione',exact:true}).click();
  modal=page.getByRole('dialog');await expect(modal).toBeVisible();await page.keyboard.press('Enter');await expect(modal).toBeHidden();
  await expect(page.locator('.chat-view')).toBeVisible();
  await page.getByRole('button',{name:'Elimina conversazione',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Elimina definitivamente'}).click();
  await expect(page.locator('.chat-view')).toHaveCount(0);
});
