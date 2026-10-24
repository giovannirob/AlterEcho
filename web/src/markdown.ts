import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
const md=new MarkdownIt({html:false,linkify:false}).disable('image');
const original=md.renderer.rules.link_open;
md.renderer.rules.link_open=(tokens,index,options,env,self)=>{
  const href=tokens[index].attrGet('href')||'';
  if(!/^(https?:|mailto:)/i.test(href))tokens[index].attrSet('href','#');
  tokens[index].attrSet('rel','noopener noreferrer');
  return original?original(tokens,index,options,env,self):self.renderToken(tokens,index,options);
};
export function markdown(text:string) {return DOMPurify.sanitize(md.render(text),{FORBID_TAGS:['img','style','iframe','form','input','svg','math'],FORBID_ATTR:['style']});}
