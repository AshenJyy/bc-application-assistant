import test from 'node:test';
import assert from 'node:assert/strict';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createCommonCurrent,currentContract as spec,currentContent,currentStructure} from '../skills/bc-application/scripts/common_current.mjs';

const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
function setup(){
  const calls=[];let fields=[],opened=null,generation=0,drift=false,association=true,url=spec.origin+spec.path;
  const choices={};const opts=labels=>labels.map(label=>({value:label,label,disabled:false}));
  function add(key,label,control,value,options=[]){fields.push({key,label,group:control==='radio'?label:'',control,value,options,required:true,
    disabled:false,readonly:false,invalid:false,selector:`[id="${key.slice(2)}"]`,selector_count:1,selector_index:0});}
  add('i:text_ques_307',spec.count_label,'choice_input','2');choices['i:text_ques_307']=opts(['1','2','3']);
  const options=['Semester','Trimester','Quarter','Yearly'].map((label,i)=>({value:label,label,disabled:false,selector:`[id="option_ques_1803_${i}-input"]`,selector_count:1,selector_index:0}));
  add('r:ques_1803',spec.scheduling_label,'radio','Semester',options);fields[1].selector=options[0].selector;
  for(let i=1;i<=2;i++)for(const [j,part]of ['subject','name','level','schedule'].entries()){
    const key='i:text_ques_'+(5000+i*4+j),control=part==='name'?'course_name':part==='schedule'?'term_choices':'choice_input';
    add(key,`Course ${i} ${part}`,control,part==='name'?'Original course '+i:part==='schedule'?['First Semester']:part==='subject'?'Other/Elective':'Regular/Standard');
    if(part!=='name')choices[key]=opts(part==='schedule'?['Full Year','First Semester','Second Semester']:part==='subject'?['Other/Elective','Computer Science']:['Regular/Standard','Honors']);
  }
  let saved=structuredClone(fields);
  const state={schema:'observed-state/1',coverage:'common_app_visible_navigation',current_page_key:'tertiaryNavItem4_24',items:[
    {key:'secondaryNavItem4',status:'complete'},{key:'tertiaryNavItem4_24',status:'complete'},{key:'secondaryNavItem7',status:'in progress'}]};
  function rawAndNative(){const raw={schema:'observed-page/1',url,title:spec.title,frames_present:false,fields:structuredClone(fields),
    actions:[{key:'i:sectionContinue24',label:'Continue to next section',selector:'[id="sectionContinue24"]',disabled:false}],state_metadata:structuredClone(state)};
    const widgets=[];let content=spec.content_base+' '+spec.scheduling_label+' Semester Trimester Quarter Yearly';
    for(const f of raw.fields){if(f.control==='radio'){f.key='n:mat-radio-group-'+generation;f.name='mat-radio-group-'+generation;}
      else if(f.control==='course_name')f.control='textarea';
      else {widgets.push({key:f.key,multiple:f.control==='term_choices',selected:f.control==='term_choices'?f.value:[],selection_text:f.control==='term_choices'?f.value.join(' '):'',semantic_invalid:false});if(f.control==='term_choices')f.value='';f.control='unsupported';}}
    for(let i=1;i<=2;i++){const schedule=fields.find(f=>f.label===`Course ${i} schedule`).value;
      content+=' '+['subject','name','level','schedule'].map(p=>`Course ${i} ${p}`).join(' ')+(schedule.length?' '+schedule.join(' '):'');}
    content+=' '+spec.content_end;
    if(drift)raw.fields.push({...raw.fields[2],key:'i:unexpected'});
    return {raw,native:{heading:spec.heading,content,widgets}};
  }
  const fieldFor=selector=>fields.find(f=>f.selector===selector);
  const locator=selector=>({count:async()=>1,getAttribute:async name=>name==='aria-controls'?(association?'panel':'wrong'):null,
    evaluate:async()=>({tag:'INPUT',type:'text',role:'combobox',popup:'listbox',expanded:opened?'true':'false'}),
    click:async()=>{if(selector==='[id="sectionContinue24"]'){saved=structuredClone(fields);url=spec.origin+'/common/4/next';calls.push('save');}
      else {opened=fieldFor(selector).key;calls.push('open');}},press:async k=>{if(k==='Escape'){opened=null;calls.push('close');}else assert.equal(k,'Tab');},
    fill:async v=>{fieldFor(selector).value=v;calls.push('name');},check:async()=>{const f=fields[1],o=f.options.find(o=>o.selector===selector);f.value=o.value;calls.push('radio');},waitFor:async()=>{}});
  const panel={count:async()=>opened?1:0,isVisible:async()=>!!opened,getAttribute:async()=> 'panel',waitFor:async()=>{},
    evaluate:async()=>choices[opened].map((o,index)=>({...o,index,selected:fields.find(f=>f.key===opened).value.includes(o.label)})),
    getByRole:(role,query)=>({count:async()=>query?choices[opened].filter(o=>o.label===query.name).length:choices[opened].length,
      click:async()=>{const f=fields.find(f=>f.key===opened),v=query.name;
        f.value=f.value.includes(v)?f.value.filter(x=>x!==v):[...f.value,v].sort();opened=null;calls.push('term');},
      nth:i=>({click:async()=>{fields.find(f=>f.key===opened).value=choices[opened][i].label;opened=null;calls.push('choice');}})})};
  const tab={url:async()=>url,goto:async u=>{url=u;fields=structuredClone(saved);generation++;calls.push('revisit');},reload:async()=>{fields=structuredClone(saved);generation++;calls.push('cancel');},
    playwright:{locator,getByRole:(role)=>role==='listbox'?panel:{waitFor:async()=>{}},domSnapshot:async()=>'',evaluate:async()=>rawAndNative().native}};
  const adapter={...host,observe:async()=>rawAndNative().raw},api=createCommonCurrent(adapter),n=rawAndNative();
  const page=api.decorate(n.raw,n.native,choices),desired=vals(page);
  desired['i:text_ques_5005']='Source-backed name';desired['i:text_ques_5004']='Computer Science';desired['i:text_ques_5007']=['First Semester','Second Semester'];
  const plan={schema:'common-current-plan/1',system:'common_app',ready:true,page_url:page.url,stage:'fields',observation_sha256:host.digest(page),
    choice_observations:choices,structure_sha256:host.digest(currentStructure(page)),expected_values_sha256:host.digest(desired),
    writes:Object.entries(desired).filter(([k,v])=>host.digest(v)!==host.digest(vals(page)[k])).map(([field_key,value])=>({field_key,value}))};
  const context={browser_family:'edge',transport:'extension',origin:spec.origin,access_verified:true,journal_persisted:true};
  return {api,page,plan,context,tab,calls,rawAndNative,setDrift:v=>drift=v,setAssociation:v=>association=v,choices,fields};
}

test('whole current-year page writes exact single/multiple choices, saves and restores original values',async()=>{
  const s=setup(),original=vals(s.page);await s.api.apply(s.tab,s.plan,s.context);const result=await s.api.saveAndRead(s.tab,s.plan,s.context);
  assert.equal(host.digest(vals(result.page)),s.plan.expected_values_sha256);assert.equal(s.calls.filter(c=>c==='term').length,1);
  const plan={...s.plan,restoration:true,observation_sha256:host.digest(result.page),expected_values_sha256:host.digest(original),
    writes:Object.entries(original).filter(([k,v])=>host.digest(v)!==host.digest(vals(result.page)[k])).map(([field_key,value])=>({field_key,value}))};
  await s.api.apply(s.tab,plan,s.context);const restored=await s.api.saveAndRead(s.tab,plan,s.context);
  assert.deepEqual(vals(restored.page),original);assert.equal(s.calls.filter(c=>c==='save').length,2);
});

test('inspection reads selected chips without changing any page values or saving',async()=>{
  const s=setup(),page=await s.api.inspect(s.tab);assert.deepEqual(vals(page),vals(s.page));assert.equal(s.calls.filter(c=>['name','choice','term','save'].includes(c)).length,0);
});

test('empty search-input validity is normalized only for the observed selected-chip widget',()=>{
  const s=setup(),{raw,native}=s.rawAndNative(),field=raw.fields.find(f=>f.label==='Course 1 schedule');field.invalid=true;
  assert.equal(s.api.decorate(raw,native,s.choices).fields.find(f=>f.label===field.label).invalid,false);
  native.widgets.find(w=>w.key===field.key).semantic_invalid=true;
  assert.equal(s.api.decorate(raw,native,s.choices).fields.find(f=>f.label===field.label).invalid,true);
});

test('normalizing selected chips cannot swallow another instruction inside their owner',()=>{
  const s=setup(),{raw,native}=s.rawAndNative();native.widgets.find(w=>w.multiple).selection_text+=' I agree to a declaration';
  assert.throws(()=>s.api.decorate(raw,native,s.choices));assert.deepEqual(s.calls,[]);
});

for(const change of ['instructions','unknown','multiple_owner','missing_row_part','duplicate_widget','ambiguous_selector','non_required','new_action'])test(`${change} stops an unknown current-year contract`,()=>{
  const s=setup(),{raw,native}=s.rawAndNative();
  if(change==='instructions')native.content+=' Consent to something new';
  if(change==='unknown')raw.fields.push({...raw.fields[2],key:'i:new'});
  if(change==='multiple_owner')native.widgets.find(w=>w.multiple).multiple=false;
  if(change==='missing_row_part')raw.fields.splice(3,1);
  if(change==='duplicate_widget')native.widgets.push(native.widgets[0]);
  if(change==='ambiguous_selector')raw.fields[2].selector_count=2;
  if(change==='non_required')raw.fields[2].required=false;
  if(change==='new_action')raw.actions[0].label='Submit application';
  assert.throws(()=>s.api.decorate(raw,native,s.choices));assert.deepEqual(s.calls,[]);
});

for(const change of ['journal','stale','association','changed_options','unknown_term'])test(`${change} cannot silently fill or save`,async()=>{
  const s=setup();if(change==='journal')s.context.journal_persisted=false;
  if(change==='stale')s.setDrift(true);
  if(change==='association')s.setAssociation(false);
  if(change==='changed_options')s.choices['i:text_ques_5004'].reverse();
  if(change==='unknown_term'){s.plan.writes=s.plan.writes.filter(w=>w.field_key==='i:text_ques_5007');s.plan.writes[0].value=['Unobserved term'];}
  await assert.rejects(()=>s.api.apply(s.tab,s.plan,s.context));assert.equal(s.calls.includes('save'),false);
});

test('generic browser writer cannot treat course-name textareas as essays or bypass the dedicated port',async()=>{
  const s=setup();await assert.rejects(()=>host.writeObserved(s.tab,s.page,[{field_key:'i:text_ques_5005',value:'Essay'}]));assert.equal(s.calls.includes('name'),false);
});
