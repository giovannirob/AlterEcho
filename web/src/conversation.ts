import type {Conversation,ServerEvent} from './api';
export function applyEvent(c:Conversation,e:ServerEvent):Conversation {
  const d=e.data;
  if(e.type==='state.snapshot')return d;
  if(e.type==='turn.started'&&d.index>c.messages.length)return {...c,status:'running',active:true,partial:{speaker:d.speaker,model:c.config.participants[d.speaker as 'A'|'B'].model,text:''}};
  if(e.type==='message.delta') {
    if(d.index&&d.index<=c.messages.length)return c;
    const partial=c.partial||{speaker:d.speaker,model:d.model,text:''};
    return {...c,partial:{...partial,text:partial.text+d.delta}};
  }
  if(e.type==='message.completed') {
    if(d.index<=c.messages.length)return c;
    return {...c,messages:[...c.messages,d.message],partial:undefined};
  }
  if(e.type==='stats.updated')return {...c,stats:d};
  if(['conversation.completed','conversation.stopped','conversation.failed','conversation.paused'].includes(e.type))return {...c,status:d.status,error:d.error,active:false};
  return c;
}
export const positions=new Map<string,{top:number;follow:boolean}>();
