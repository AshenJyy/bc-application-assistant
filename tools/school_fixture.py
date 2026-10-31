"""Loopback-only school UI: invented directory, native inputs and persisted drafts."""
import json
from http.server import HTTPServer
from tools.synthetic_server import Handler


def build(*,academic_storage=None,storage='bc-synthetic-schools-v23'):
    from bc_application.common_schools import CONTRACT
    script=r'''
const spec=SPEC,storage=SCHOOLSTORAGE,academicStorage=ACADEMIC,kind=location.pathname.endsWith('/19')?'other':'current',s=spec[kind];
const saved=JSON.parse(localStorage.getItem(storage)||'{"current":null,"other":null}');
let draft=structuredClone(saved[kind]||{schools:{},dates:{},boarding:'',graduate:'',progression:[],note:'',count:''});
const schools=[1,2].map(n=>({name:'Fictional Secondary '+n,city:'Invented City',region:'BC',country:'Canada',ceeb:'12345'+n}));
const node=(tag,attrs={},text='')=>{const e=document.createElement(tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);e.textContent=text;return e;};
const button=(text,fn,attrs={})=>{const e=node('button',{type:'button',...attrs},text);e.onclick=fn;return e;};
function nav(){const n=document.querySelector('nav');n.replaceChildren();
 const entries=[['secondaryNavItem4','Education',saved.current&&saved.other?'complete':'in progress',''],
 ['tertiaryNavItem4_18',spec.current.heading,saved.current?'complete':'incomplete',spec.current.path],
 ['tertiaryNavItem4_19',spec.other.heading,saved.other?'complete':'not started',spec.other.path],['secondaryNavItem3','Profile','complete','']];
 if(academicStorage)entries.push(['secondaryNavItem13','Courses & Grades',localStorage.getItem(academicStorage)?'in progress':'not started',''],['tertiaryNavItem13_55','9th Grade','incomplete','/common/13/55']);
 for(const [id,label,status,path]of entries){
 const a=node('a',{id,...(path?{href:path}:{})},label+' '),span=node('span',{class:'nav-item__status'});
 span.append(node('forge-screen-reader-text',{},status));a.append(span);n.append(a);}}
function radio(parent,item,key,options){const field=node('fieldset'),legend=node('legend',{},item.label);field.append(legend);
 options.forEach((text,index)=>{const id='option_ques_'+item.key.split('_').at(-1)+'_'+(1000+index)+'-input',e=node('input',{id,type:'radio',name:'mat-radio-group-'+key,value:index,required:''});
 e.checked=draft[key]===String(index);e.onchange=()=>{draft[key]=String(index);render();};field.append(e,node('label',{for:id},text));});parent.append(field);}
function date(parent,key,label){const id=key.slice(2),e=node('input',{id,type:'text',required:'','aria-label':label});e.value=draft.dates[key]||'';
 e.oninput=()=>draft.dates[key]=e.value;parent.append(node('label',{for:id},label),e);}
function note(parent){const q=s.statement.question_id,label=node('label',{id:'title_ques_'+q},s.statement.label),e=node('div',{role:'textbox',contenteditable:'true','aria-labelledby':label.id,'aria-required':'true'});
 e.append(node('p',{},draft.note));e.oninput=()=>draft.note=e.innerText.trim();e.onblur=()=>e.replaceChildren(node('p',{},draft.note));parent.append(label,e);}
function school(parent,r){const id=r.question_id,owner=node('ca-lookup',{id:'text_ques_'+id,'aria-labelledby':'title_ques_'+id}),chosen=draft.schools[id];
 parent.append(node('label',{id:'title_ques_'+id},r.label+' *'));if(chosen){owner.append(node('div',{},chosen.name),node('div',{},'1 Invented Street'),node('div',{},chosen.city+', BC'),node('div',{},'CAN'),node('div',{},'Independent'),node('div',{},'CEEB Code : '+chosen.ceeb));
 owner.append(button('Change',()=>lookup(id),{id:'changeSchool'+id}),button('Remove',()=>{delete draft.schools[id];render();},{id:'removeSchool'+id}));}
 else owner.append(button('Find school',()=>lookup(id),{id:'findSchool'+id}));parent.append(owner);date(parent,r.entry_key,r.entry_label);if(r.exit_key)date(parent,r.exit_key,r.exit_label);}
function lookup(q){let query='',selected=null;const d=node('section',{role:'dialog','aria-label':spec.lookup_title,'aria-modal':'true'});
 d.append(node('h2',{},spec.lookup_title),button('Close dialog',()=>d.remove(),{id:'dialogClose'}));
 const by=node('input',{id:'searchByControl'+q,role:'combobox',readonly:'','aria-label':'Search by'});by.value=spec.lookup_search;d.append(by);
 const input=node('input',{id:'searchTermControl'+q,type:'search','aria-label':spec.lookup_search}),list=node('ca-single-selection-list',{id:'selectionListControl'+q,role:'listbox'}),count=node('p');
 function results(){selected=null;const found=schools.filter(s=>s.name.toLowerCase().includes(query.toLowerCase()));count.textContent=found.length+' high schools resulted in your search';list.replaceChildren();
 for(const candidate of found){const opt=node('ca-single-selection-list-option',{id:'selectionListResult100'+candidate.ceeb.at(-1)+'-',role:'option','aria-selected':'false',tabindex:'0'});
 opt.append(node('p',{},candidate.name),node('p',{},candidate.city+', BC, Canada | CEEB: '+candidate.ceeb));opt.onclick=()=>{selected=candidate;list.querySelectorAll('[role=option]').forEach(o=>o.setAttribute('aria-selected',String(o===opt)));};list.append(opt);}
 for(const text of ['Homeschooled',"I don't see my high school in this list"])list.append(node('div',{role:'option',id:'selectionListResult'},text));}
 input.oninput=()=>{query=input.value;results();};d.append(input,count,list,button('Continue , Close dialog',()=>{if(selected){draft.schools[q]=structuredClone(selected);d.remove();render();}},{id:'lookupContinue'+q}));results();document.body.append(d);}
function render(){nav();const main=document.querySelector('main');main.replaceChildren(node('h1',{id:'pageTitle'},s.heading),node('p',{},'Synthetic development fixture — invented schools and applicant.'));
 if(kind==='current'){
 school(main,s.records[0]);radio(main,s.boarding,'boarding',['Yes','No']);radio(main,s.graduate,'graduate',['Yes','No']);
 if(draft.graduate==='0')date(main,s.graduation.key,s.graduation.label);
 const f=node('fieldset'),legend=node('legend');legend.append(node('span',{id:'title_ques_265'},spec.progression_label));f.append(legend);
 for(const p of spec.progression){const e=node('input',{type:'checkbox',id:'progression_'+p.value+'-input',value:p.value});e.checked=draft.progression.includes(p.part);
 e.onchange=()=>{draft.progression=e.checked?[...draft.progression,p.part]:draft.progression.filter(x=>x!==p.part);render();};f.append(e,node('label',{for:e.id},p.label));}main.append(f);
 if(draft.progression.some(p=>p!=='unchanged'))note(main);
 }else{radio(main,s.count,'count',['0','1','2','3']);for(const r of s.records.slice(0,Number(draft.count||0)))school(main,r);if(Number(draft.count||0))note(main);}
 main.append(button('Continue (to next section)',()=>{
  if(Array.from(main.querySelectorAll('input')).some(e=>!e.validity.valid))return;
  if(!Object.values(draft.schools).length&&!(kind==='other'&&draft.count==='0'))return;
  saved[kind]=structuredClone(draft);localStorage.setItem(storage,JSON.stringify(saved));location.assign('/common/4/next');
 },{id:'sectionContinue'+s.path.split('/').at(-1)}));}
render();
'''.replace('SPEC',json.dumps(CONTRACT,ensure_ascii=False)).replace('ACADEMIC',json.dumps(academic_storage)).replace('SCHOOLSTORAGE',json.dumps(storage))
    return ('''<!doctype html><meta charset="utf-8"><title>My Common Application | Common App</title>
<style>body{font:16px system-ui;max-width:950px;margin:20px auto;color:#182b48}nav a{display:block;padding:4px}fieldset,ca-lookup{display:block;border:1px solid #bbc;padding:12px;margin:10px 0}label{margin:6px}input,button{font:inherit;margin:6px;padding:6px}[role=textbox]{min-height:60px;border:1px solid #789;padding:10px}[role=dialog]{position:fixed;inset:5% 12%;background:white;border:3px solid #456;padding:20px;overflow:auto}ca-single-selection-list-option{display:block;cursor:pointer;padding:6px}ca-single-selection-list-option[aria-selected=true]{background:#d0e9ff}p{margin:6px}</style>
<nav></nav><main></main><script>'''+script+'</script>').encode()


if __name__=='__main__':
    Handler.pages={p:build() for p in ('/common/4/18','/common/4/19')}
    Handler.pages['/common/4/next']=b'<!doctype html><title>Fictional draft saved</title><h1>Fictional draft saved</h1><p>Return to the saved school page to verify.</p>'
    print('Invented school UI at loopback port 8765',flush=True)
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
