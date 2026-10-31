"""Loopback academic UI fixture with invented schools; no applicant file access."""
import json
from http.server import HTTPServer
from tools.synthetic_server import Handler


def build(*,school_registry=None,storage='bc-synthetic-academic-v22'):
    from bc_application.common_academic import CONTRACT
    script=r'''
const spec=SPEC,storage=STORAGE,schoolRegistry=REGISTRY;
let saved=JSON.parse(localStorage.getItem(storage)||'null'),draft=null;
const blankRow=()=>({subject:'Select',name:'',level:'Select',grades:{},credits:{},na:false});
const blankTranscript=()=>({headers:{school_name:'Select',school_year:'Select',grading_scale:'Select',schedule:'Select'},rows:[blankRow(),blankRow()]});
const node=(tag,attrs={},text='')=>{const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);e.textContent=text;return e;};
const button=(text,fn,attrs={})=>{const e=node('button',{type:'button',...attrs},text);e.onclick=fn;return e;};
function material(parent,id,label,value,options,onchange){
 const e=node('mat-select',{id,role:'combobox','aria-label':label,'aria-required':'true','aria-expanded':'false'},value);e.tabIndex=0;
 e.onclick=()=>{e.setAttribute('aria-expanded','true');const panel=node('div',{role:'listbox','aria-label':label});
  panel.tabIndex=0;panel.onkeydown=event=>{if(event.key==='Escape'){panel.remove();e.setAttribute('aria-expanded','false');}};
  options.forEach(text=>panel.append(button(text,()=>{panel.remove();e.setAttribute('aria-expanded','false');onchange(text);renderDialog();},{role:'option','aria-disabled':'false'})));
  document.body.append(panel);panel.focus();};parent.append(e);
}
function input(parent,id,label,value,onchange,readonly=false){const e=node('input',{id,'aria-label':label});e.value=value;e.required=id.startsWith('courseName');e.readOnly=readonly;e.oninput=()=>onchange(e.value);parent.append(e);}
function parent(){
 document.querySelectorAll('[role=dialog],[role=listbox]').forEach(e=>e.remove());draft=null;
 const main=document.querySelector('main');main.replaceChildren(node('h1',{id:'pageTitle'},'9th Grade'),node('p',{},'Synthetic development fixture — all schools and records invented.'));
 if(schoolRegistry){const registry=JSON.parse(localStorage.getItem(schoolRegistry)||'{}'),nav=document.querySelector('nav');nav.replaceChildren();
  for(const [id,label,status,path]of [['secondaryNavItem4','Education',registry.current&&registry.other?'complete':'in progress',''],
   ['tertiaryNavItem4_18','Current school',registry.current?'complete':'incomplete','/common/4/18'],
   ['tertiaryNavItem4_19','Other schools',registry.other?'complete':'not started','/common/4/19'],
   ['secondaryNavItem13','Courses & Grades',saved?'in progress':'not started',''],
   ['tertiaryNavItem13_55','9th Grade','incomplete','/common/13/55'],['secondaryNavItem3','Profile','complete','']]){
   const a=node('a',{id,...(path?{href:path}:{})},label+' '),span=node('span',{class:'nav-item__status'});span.append(node('forge-screen-reader-text',{},status));a.append(span);nav.append(a);}}
 if(saved)for(const t of saved)main.append(node('p',{},`Completed courses & grades entered: ${t.rows.length} Incomplete courses & grades entered: 0`));
 const check=node('input',{id:'completion',type:'checkbox','aria-label':'I have reported all of my courses for this grade'});main.append(check);
 main.append(button(saved?'Edit 9th grade':'Enter 9th grade',()=>{draft=structuredClone(saved||[blankTranscript()]);renderDialog();},{id:'addCG'}));
}
function renderDialog(){
 document.querySelector('[role=dialog]')?.remove();
 const d=node('section',{role:'dialog','aria-modal':'true','aria-labelledby':'dialogName'});
 d.append(node('span',{id:'dialogName'},'Courses & Grades'),node('h3',{},'Courses & Grades – 9th grade'));
 for(const text of spec.instructions)d.append(node('p',{},text));
 draft.forEach((t,ti)=>{const n=ti+1,owner=node('ca-cng-transcript');
  for(const [key,label] of Object.entries(spec.headers)){
   const prefix={school_name:'schoolName',school_year:'schoolYear',grading_scale:'gradingScale',schedule:'schedule'}[key];
   const registered=schoolRegistry?Object.values(JSON.parse(localStorage.getItem(schoolRegistry)||'{}')).flatMap(p=>Object.values(p?.schools||{})).map(s=>s.name):['Fictional Secondary 1','Fictional Secondary 2'];
   const options={school_name:registered,school_year:['2023-24'],grading_scale:['Other','1-100'],schedule:['Semesters','Yearly']}[key];
   material(owner,`${prefix}Control${n}`,`Transcript ${n} ${label}`,t.headers[key],options,v=>t.headers[key]=v);
  }
  t.rows.forEach((r,ri)=>{const i=ri+1,row=node('ca-cng-course'),suffix=`T${n}C${i}`,label=`Transcript ${n}, Course ${i}, `;
   material(row,`subjectControl_${suffix}`,label+'Subject',r.subject,['Other/Elective','Science'],v=>r.subject=v);
   input(row,`courseNameControl_${suffix}`,label+'Course Nameundefined',r.name,v=>r.name=v);
   material(row,`levelControl_${suffix}`,label+'Course Level',r.level,['Regular/Standard','Honors'],v=>r.level=v);
   const terms=t.headers.grading_scale!=='Select'&&spec.schedules[t.headers.schedule];
   if(terms){
    for(const term of terms){const tl=spec.terms[term],other=t.headers.grading_scale==='Other',part={semester_1:'1',semester_2:'2',final:'Final'}[term];
     if(other)input(row,`gradeControl_${suffix}`,label+tl+'undefined',r.grades[term]||'',v=>r.grades[term]=v);
     else material(row,`grade${part}Control_${suffix}`,label+tl+' Grade',r.grades[term]||'',['','84','78','92'],v=>r.grades[term]=v);
    }
    for(const term of terms){const part={semester_1:'1',semester_2:'2',final:'Final'}[term];input(row,`credit${part}Control_${suffix}`,label+spec.terms[term]+(term==='final'?' Credits':' Credit'),r.credits[term]||'',v=>r.credits[term]=v,r.na);}
    const na=node('input',{type:'checkbox',id:`creditNA_${suffix}-input`,'aria-label':label+'Credits not applicable'});na.checked=r.na;
    na.onchange=()=>{r.na=na.checked;renderDialog();};row.append(na);
   }
   if(i>1)row.append(button('Remove',()=>{
    d.style.display='none';const confirm=node('section',{role:'dialog','aria-label':`Remove course ${i} of ${t.rows.length}`});
    confirm.append(node('h2',{},`Remove course ${i} of ${t.rows.length}`),node('p',{},'Are you sure you want to permanently remove this course?'));
    confirm.append(button('Cancel',()=>{confirm.remove();d.style.display='';},{id:'alert_rc_c'}),button('Remove',()=>{t.rows.splice(ri,1);confirm.remove();renderDialog();},{id:'alert_rc_r'}));document.body.append(confirm);
   },{'aria-label':`Remove transcript ${n}, course ${i} of ${t.rows.length}, Opens dialog`}));
   owner.append(row);
  });
  owner.append(button('Add another course',()=>{t.rows.push(blankRow());renderDialog();}));d.append(owner);
 });
 d.append(button(spec.add_transcript,()=>{draft.push(blankTranscript());renderDialog();}));
 d.append(button('Close dialog',()=>parent(),{id:'changePreferencesClose'}));
 d.append(button(spec.save,()=>{saved=structuredClone(draft);localStorage.setItem(storage,JSON.stringify(saved));parent();}));document.body.append(d);
}
parent();
'''.replace('SPEC',json.dumps(CONTRACT,ensure_ascii=False)).replace('STORAGE',json.dumps(storage)).replace('REGISTRY',json.dumps(school_registry))
    return ('''<!doctype html><meta charset="utf-8"><title>My Common Application | Common App</title>
<style>body{font:16px system-ui;max-width:1000px;margin:20px auto}ca-cng-transcript,ca-cng-course{display:block;border:1px solid #bbc;padding:10px;margin:10px}mat-select{display:inline-block;border:1px solid #789;padding:6px;margin:4px;cursor:pointer}input{margin:4px}button{margin:4px;padding:6px}[role=listbox]{position:fixed;inset:10% 20%;background:white;border:3px solid #456;z-index:5;overflow:auto}[role=dialog]{background:#f8faff;padding:16px}</style>
<nav><a id="secondaryNavItem13"><span class="nav-item__status"><forge-screen-reader-text>Incomplete</forge-screen-reader-text></span></a><a id="tertiaryNavItem13_55"><span class="nav-item__status"><forge-screen-reader-text>Incomplete</forge-screen-reader-text></span></a></nav><main></main><script>'''+script+'</script>').encode('utf-8')


if __name__=='__main__':
    Handler.pages={'/common/13/55':build()}
    print('Invented academic creation UI at loopback port 8765',flush=True)
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
