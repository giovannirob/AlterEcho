import {test,expect} from '@playwright/test';
const token='browser-fixture-only-token-'+'x'.repeat(32);
test.use({locale:'en-US'});

test('language detection, explicit preference and persistence work before login',async({page,browser})=>{
  await page.goto('/');await expect(page.getByLabel('Service token')).toBeVisible();
  await page.getByLabel('Language',{exact:true}).selectOption('it');
  await expect(page.getByLabel('Token del servizio')).toBeVisible();
  await page.reload();await expect(page.getByLabel('Token del servizio')).toBeVisible();
  const other=await browser.newContext({locale:'de-DE'});
  try{const tab=await other.newPage();await tab.goto('/');await expect(tab.getByLabel('Service token')).toBeVisible();}finally{await other.close();}
  await expect(page.getByLabel('Token del servizio')).toBeVisible();
  await page.getByLabel('Lingua',{exact:true}).selectOption('auto');
  await expect(page.getByLabel('Service token')).toBeVisible();
});

test('language switching preserves a draft, an open modal and live SSE content',async({page},info)=>{
  let streams=0;page.on('request',request=>{if(request.url().endsWith('/events'))streams++;});
  await page.goto('/');await page.getByLabel('Service token').fill(token);await page.getByRole('button',{name:'Connect to server'}).click();
  await page.getByRole('navigation').getByRole('button',{name:'New conversation'}).click();
  const topic='Argomento originale / original topic 日本語';await page.getByLabel('Topic',{exact:true}).fill(topic);
  await page.getByRole('button',{name:'Start conversation',exact:false}).click();
  const modal=page.getByRole('dialog');await modal.getByLabel('Language',{exact:true}).selectOption('it');
  await expect(modal.getByRole('heading')).toHaveText('Avvia conversazione');await expect(modal).toContainText(topic);
  await modal.getByRole('button',{name:'Annulla',exact:true}).click();await expect(page.getByLabel('Argomento',{exact:true})).toHaveValue(topic);
  await page.getByRole('button',{name:'Avvia conversazione',exact:false}).click();await modal.getByRole('button',{name:'Avvia conversazione',exact:true}).click();
  await expect(page.locator('.generating')).toBeVisible();await expect.poll(()=>page.locator('.markdown').first().textContent()).not.toBe('');
  const scroller=page.locator('.chat-scroll');
  await expect.poll(()=>scroller.evaluate(element=>element.scrollHeight-element.clientHeight)).toBeGreaterThan(400);
  await scroller.hover();const followingTop=await scroller.evaluate(element=>element.scrollTop);await page.mouse.wheel(0,-350);
  await expect.poll(()=>scroller.evaluate(element=>element.scrollTop)).toBeLessThan(followingTop-100);
  await scroller.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const readingTop=await scroller.evaluate(element=>element.scrollTop);
  const id=new URLSearchParams(new URL(page.url()).hash.slice(1)).get('conversation');
  const snapshot=await (await page.request.get(`/api/v1/conversations/${id}`,{headers:{Authorization:'Bearer '+token}})).json();const count=streams;
  await page.locator('.client-language select').selectOption('en');
  await expect(page.locator('.generating')).toContainText('Generating response');
  await expect(page.locator('.chat-title h1')).toHaveText(topic);expect(streams).toBe(count);
  expect(await scroller.evaluate(element=>element.scrollTop)).toBeCloseTo(readingTop,0);
  const after=await (await page.request.get(`/api/v1/conversations/${id}`,{headers:{Authorization:'Bearer '+token}})).json();
  expect(after.config.topic).toBe(snapshot.config.topic);
  expect(after.messages.slice(0,snapshot.messages.length)).toEqual(snapshot.messages);
  if(snapshot.partial)expect(after.messages[snapshot.messages.length]?.text??after.partial?.text).toContain(snapshot.partial.text);
  await expect(page.locator('.markdown').first()).toContainText('Il dialogo prende forma');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:`test-results/i18n-english-${info.project.name}.png`});
  await page.getByRole('button',{name:'Stop',exact:true}).click();
});
