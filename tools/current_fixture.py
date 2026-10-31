"""Loopback fictional current-year and grade-status drafts; no applicant endpoints."""
import json
from http.server import HTTPServer

from bc_application.common_current import CONTRACT
from bc_application.common_factual import CONTRACTS
from tools.synthetic_server import Handler


def build():
    script=r'''
const spec=SPEC,storage='bc-synthetic-current-v25';
const saved=JSON.parse(localStorage.getItem(storage)||'null');
let draft=structuredClone(saved||{count:'1',schedule:'Semester',rows:[{subject:'',name:'',level:'',terms:[]}]});
const node=(tag,attrs={},text='')=>{const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);e.textContent=text;return e;};
const button=(text,fn,attrs={})=>{const e=node('button',{type:'button',...attrs},text);e.onclick=fn;return e;};
function select(parent,id,label,options,value,onchange,multiple=false){
 const title=node('label',{id:'title_ques_'+id,for:'text_ques_'+id},label),owner=node('ng-select',{class:multiple?'ng-select-multiple':''}),box=node('div',multiple?{role:'listbox','aria-labelledby':title.id}:{});
 const input=node('input',{id:'text_ques_'+id,type:'text',role:'combobox','aria-haspopup':'listbox','aria-expanded':'false',required:'','aria-label':label,...(multiple?{'aria-invalid':String(!value.length)}:{})});
 if(multiple){for(const s of value)box.append(node('span',{role:'option','aria-selected':'true'},s));}else input.value=value;
 box.append(input);owner.append(box);parent.append(title,owner);
 function close(){document.getElementById('synthetic-options-'+id)?.remove();input.removeAttribute('aria-controls');input.setAttribute('aria-expanded','false');}
 input.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();close();}};
 input.onclick=()=>{close();const panel=node('div',{role:'listbox','aria-label':'Options',id:'synthetic-options-'+id,class:multiple?'ng-select-multiple':''});
 input.setAttribute('aria-controls',panel.id);input.setAttribute('aria-expanded','true');
 for(const option of options){const e=node('div',{role:'option',tabindex:'0',...(multiple&&value.includes(option)?{'aria-selected':'true'}:{})},option);
 e.onclick=()=>{close();onchange(multiple?(value.includes(option)?value.filter(v=>v!==option):[...value,option]):option);render();};panel.append(e);}owner.append(panel);};
}
function nav(){const n=document.querySelector('nav');n.replaceChildren();for(const[id,status]of [['secondaryNavItem4',saved?'complete':'in progress'],['tertiaryNavItem4_24',saved?'complete':'incomplete'],['secondaryNavItem7','in progress']]){
 const item=node('a',{id}),s=node('span',{class:'nav-item__status'});s.append(node('forge-screen-reader-text',{},status));item.append(s);n.append(item);}}
function render(){nav();const main=document.querySelector('main');main.replaceChildren(node('p',{},'Complete your Common Application'),node('h1',{id:'pageTitle'},spec.heading),node('div',{id:'pageHeaderStatus'},saved?'Complete Complete':'Incomplete Incomplete'),button('Preview Education Section, Opens dialog',()=>{}));
 main.append(node('p',{},spec.content_base.split('Opens dialog ')[1].split(' How many')[0]));
 select(main,307,'How many courses would you like to report?',Array.from({length:15},(_,i)=>String(i+1)),draft.count,v=>{draft.count=v;draft.rows=Array.from({length:Number(v)},(_,i)=>draft.rows[i]||{subject:'',name:'',level:'',terms:[]});});
 // The live count's public label combines instruction text and the count question.
 main.querySelector('#text_ques_307').setAttribute('aria-label',spec.count_label);
 const field=node('fieldset');field.append(node('legend',{},spec.scheduling_label));
 for(const[index,v]of ['Semester','Trimester','Quarter','Yearly'].entries()){
 const id='option_ques_1803_'+(index+1)+'-input',e=node('input',{id,type:'radio',name:'mat-radio-group-1',value:v,required:''});e.checked=draft.schedule===v;e.onchange=()=>{draft.schedule=v;render();};field.append(e,node('label',{for:id},v));}main.append(field);
 draft.rows.forEach((r,i)=>{const n=i+1,base=5000+n*4;
 select(main,base,'Course '+n+' subject',['Other/Elective','Computer Science','History/Social Science'],r.subject,v=>r.subject=v);
 const label='Course '+n+' name',id='text_ques_'+(base+1),e=node('textarea',{id,required:'','aria-label':label});e.value=r.name;e.oninput=()=>r.name=e.value;main.append(node('label',{for:id},label),e);
 select(main,base+2,'Course '+n+' level',['Regular/Standard','Honors'],r.level,v=>r.level=v);
 select(main,base+3,'Course '+n+' schedule',['Full Year','First Semester','Second Semester'],r.terms,v=>r.terms=v,true);});
 main.append(button('Continue to next section',()=>{localStorage.setItem(storage,JSON.stringify(draft));location.href='/common/4/next';},{id:'sectionContinue24'}));
}
render();
'''.replace('SPEC',json.dumps(CONTRACT))
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>'+CONTRACT['title']+'</title><style>body{font:17px system-ui;max-width:800px;margin:auto}label,textarea,ng-select{display:block;margin:8px 0}input,textarea,button{font:inherit}ng-dropdown-panel,[role=listbox][aria-label=Options]{border:2px solid #778;padding:10px} [role=option]{padding:4px}nav{padding:10px;background:#def}</style><nav></nav><main></main><script>'+script+'</script></html>').encode()


def grade_status():
    spec=next(s for s in CONTRACTS if s['kind']=='grade12_status')
    label=spec['fields'][0]['label']
    script='''<script>const storage='bc-synthetic-grade-status-v25',saved=localStorage.getItem(storage);if(saved)document.querySelector('input[value="'+saved+'"]').checked=true;
document.getElementById('pageHeaderStatus').textContent=saved?'Complete Complete':'Incomplete Incomplete';
for(const e of document.querySelectorAll('nav forge-screen-reader-text'))if(e.id!=='unrelated')e.textContent=saved?'complete':'incomplete';
document.getElementById('sectionContinue58').onclick=()=>{const value=document.querySelector('input:checked')?.value;if(value){localStorage.setItem(storage,value);location.href='/common/4/next';}};</script>'''
    return ('<!doctype html><meta charset="utf-8"><title>'+spec['title']+'</title><nav><a id="secondaryNavItem13"><span class="nav-item__status"><forge-screen-reader-text>incomplete</forge-screen-reader-text></span></a><a id="tertiaryNavItem13_58"><span class="nav-item__status"><forge-screen-reader-text>incomplete</forge-screen-reader-text></span></a><a id="secondaryNavItem7"><span class="nav-item__status"><forge-screen-reader-text id="unrelated">in progress</forge-screen-reader-text></span></a></nav>'
        '<main><p>Complete your Common Application</p><h1 id="pageTitle">12th Grade</h1><div id="pageHeaderStatus"></div><button>Preview Courses &amp; Grades Section, Opens dialog</button><fieldset><legend>'+label+'</legend>'
        '<input type="radio" required name="mat-radio-group-0" id="option_ques_1927_2371-input" value="0"><label for="option_ques_1927_2371-input">Yes</label> <input type="radio" required name="mat-radio-group-0" id="option_ques_1927_2372-input" value="1"><label for="option_ques_1927_2372-input">No</label></fieldset>'
        '<button id="sectionContinue58">Continue to next section</button></main>'+script).encode()


if __name__=='__main__':
    Handler.pages={'/common/4/24':build(),'/common/13/58':grade_status(),'/common/4/next':b'<!doctype html><h1>Invented draft saved</h1>'}
    print('Invented current-year UI on loopback port 8765',flush=True)
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
