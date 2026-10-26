import {derived, get, writable} from 'svelte/store';

type Catalog = Record<string, any>;
const modules = import.meta.glob('../../../alterecho/locales/*.json', {eager:true, import:'default'}) as Record<string,Catalog>;
export const catalogs:Record<string,Catalog> = Object.fromEntries(Object.entries(modules).map(([path,data])=>[path.split('/').pop()!.slice(0,-5),data]));
export const languages = Object.entries(catalogs).map(([code,data])=>({code,name:data._meta.name}));
export const storageKey='alterecho-language';
export function normalize(value:string):string|undefined {
  const candidate=value.replaceAll('_','-').toLowerCase();
  return Object.keys(catalogs).find(code=>code.toLowerCase()===candidate)||Object.keys(catalogs).find(code=>code.toLowerCase()===candidate.split('-')[0]);
}
export function detect(values:readonly string[]):string {return values.map(normalize).find(Boolean)||'en';}
function stored():string {try{return localStorage.getItem(storageKey)||'auto';}catch{return 'auto';}}
export const preference=writable(stored());
const browserLanguages=writable(typeof navigator==='undefined'?[]:navigator.languages);
export const language=derived([preference,browserLanguages],([$preference,$browser])=>$preference==='auto'?detect($browser):normalize($preference)||'en');
export function setPreference(value:string) {
  if(value!=='auto'&&!catalogs[value])return;
  try{localStorage.setItem(storageKey,value);}catch{/* Private browser storage can be unavailable. */}
  preference.set(value);
}
export function translate(code:string,key:string,params:Record<string,unknown>={},count?:number):string {
  let value=catalogs[code]?.[key]??catalogs.en[key];
  if(value===undefined){if(import.meta.env.DEV)console.debug('Missing translation:',key);return 'Message unavailable.';}
  if(count!==undefined)params={...params,count};
  if(typeof value==='object')value=value[new Intl.PluralRules(code).select(count??0)]??value.other;
  return String(value).replace(/\{([A-Za-z_][A-Za-z_0-9]*)\}/g,(_,name)=>String(params[name]??`{${name}}`));
}
export const t=derived(language,code=>(key:string,params:Record<string,unknown>={},count?:number)=>translate(code,key,params,count));
export const formatNumber=derived(language,code=>(value:number,options?:Intl.NumberFormatOptions)=>new Intl.NumberFormat(code,options).format(value));
export const formatDate=derived(language,code=>(value:string)=>new Intl.DateTimeFormat(code,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)));
export function text(key:string,params:Record<string,unknown>={}) {return get(t)(key,params);}
export class LocalizedError extends Error {
  constructor(public code:string,public params:Record<string,unknown>={},public detail='') {super(detail);}
}
export function errorText(error:unknown,code=get(language)):string {
  return error instanceof LocalizedError&&(catalogs.en[error.code]!==undefined)?translate(code,error.code,error.params):error instanceof Error?error.message:String(error);
}
language.subscribe(code=>{if(typeof document!=='undefined')document.documentElement.lang=code;});
if(typeof window!=='undefined')window.addEventListener('languagechange',()=>browserLanguages.set(navigator.languages));
