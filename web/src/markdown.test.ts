// @vitest-environment jsdom
import {describe,it,expect} from 'vitest';
import {markdown} from './markdown';
describe('safe conversation Markdown',()=>{
  it('keeps formatting and code',()=>{const html=markdown('**test**\n\n```js\nconst a=1;\n```');expect(html).toContain('<strong>test</strong>');expect(html).toContain('<pre>');});
  it('never embeds scripts, images or active links',()=>{const html=markdown('<script>alert(1)</script> ![x](https://evil.example/x) [x](javascript:alert(1))');expect(html).not.toContain('<script');expect(html).not.toContain('<img');expect(html).not.toContain('href="javascript:');});
  it('blocks file and relative links',()=>{expect(markdown('[x](file:///private) [y](/api/v1/settings)')).not.toContain('href="/api');});
});
