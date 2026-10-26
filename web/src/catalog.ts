import type {CatalogModel, Configuration, Profile, Provider} from './api';
export const modelId=(model:CatalogModel)=>typeof model==='string'?model:model.model;
export function validSelection(id:string,model:string,catalogs:Provider[]) {
  const catalog=catalogs.find(c=>c.profile_id===id);
  return !!catalog?.available&&catalog.models.some(m=>modelId(m)===model);
}
export function configurationValid(value:Configuration, catalogs:Provider[]) {
  return Object.values(value.participants).every(p=>validSelection(p.profile_id,p.model,catalogs))&&reasoningValid(value,catalogs);
}
export function efforts(value:Configuration,catalogs:Provider[]) {
  const p=value.participants.A,c=catalogs.find(c=>c.profile_id===p.profile_id);
  if(c?.provider!=='codex')return [];
  const model=c.models.find(m=>modelId(m)===p.model);
  return typeof model==='object'?(model.supportedReasoningEfforts||[]).map(e=>typeof e==='string'?e:e.reasoningEffort):[];
}
export function reasoningValid(value:Configuration,catalogs:Provider[]) {
  const supported=efforts(value,catalogs);
  return !supported.length||supported.includes(value.codex_effort);
}
export function profileSignature(p:Profile) {return [p.id,p.provider,p.url,p.api_key_env].join('|');}
