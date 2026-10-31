import test from 'node:test';
import assert from 'node:assert/strict';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {contracts,createCommonFactual} from '../skills/bc-application/scripts/common_factual.mjs';
import {createCommonLanguage} from '../skills/bc-application/scripts/common_language.mjs';

const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
function setup(kind='language',{n=2,blankGrade=false}={}) {
  const spec=contracts.find(s=>s.kind===kind),calls=[],options={},fields=[];
  let generation=0,opened=null,url='https://apply.commonapp.org'+spec.path,drift=false,association='options-popup';
  const state={schema:'observed-state/1',coverage:'common_app_visible_navigation',current_page_key:spec.current_key,
    items:[{key:spec.current_key,status:'complete'},{key:spec.parent_key,status:'complete'},{key:'secondaryNavItem7',status:'in progress'}]};
  function radio(wanted,index) {
    const q=wanted.key.split('_').at(-1),labels=q==='223'?['1','2','3','4','5']:q==='364'?['Married','Separated']:q==='366'?['Both Parents','Parent 1']:['Yes','No'];
    fields.push({...wanted,name:'mat-radio-group-'+index,selector:`[id="option_ques_${q}_0-input"]`,value:q==='223'?(n?String(n-1):''):q==='1927'?(blankGrade?'':'1'):'0',
      options:labels.map((label,i)=>({label,value:String(i),disabled:false,selector:`[id="option_ques_${q}_${i}-input"]`})),invalid:false,disabled:false,readonly:false});
  }
  const rows=[];
  function addRows(count) {
    rows.splice(0);fields.splice(1);
    for(let i=0;i<count;i++) {
      const language_key='i:text_ques_'+(4000+i*2),proficiency_id=String(4001+i*2);rows.push({language_key,proficiency_id});
      fields.push({key:language_key,name:language_key.slice(2),label:spec.language_label,group:'',control:'choice_input',required:true,
        selector:`[id="${language_key.slice(2)}"]`,value:'English',invalid:false,disabled:false,readonly:false,options:[]});
      options[language_key]=['English','French','Spanish','German','Mandarin'].map((label,index)=>({label,value:label,disabled:false,index}));
      for(const p of spec.proficiencies)fields.push({key:`g:${proficiency_id}:${p.part}`,label:p.label,group:spec.proficiency_label,control:'checkbox',
        required:false,selector:`fieldset:has([id="title_ques_${proficiency_id}"]) input[type="checkbox"][value="${p.value}"]`,
        value:p.part==='speak',options:[],invalid:false,disabled:false,readonly:false});
    }
  }
  if(kind!=='language')spec.fields.forEach(radio);
  else {
    radio(spec.count_field,0);addRows(n);
  }
  let saved=structuredClone(fields),savedRows=structuredClone(rows);
  function restoreSaved(){fields.splice(0,fields.length,...structuredClone(saved));rows.splice(0,rows.length,...structuredClone(savedRows));}
  function rawAndNative() {
    const raw={schema:'observed-page/1',url:'https://apply.commonapp.org'+spec.path,title:spec.title,frames_present:false,
      fields:structuredClone(fields),actions:[{key:'i:sectionContinue'+spec.path.split('/').at(-1),label:'Continue to next section',
        selector:`[id="sectionContinue${spec.path.split('/').at(-1)}"]`,disabled:false}],state_metadata:structuredClone(state)};
    const native={schema:'common-factual-native/1',heading:spec.heading,content:'Synthetic '+kind+' public content',controls:[],rows:[],auxiliary:[]};
    for(const [i,f] of raw.fields.entries()) {
      if(f.control==='radio'){f.name='mat-radio-group-'+(generation*50+i);f.key='n:'+f.name;}
      if(f.control==='choice_input') {
        f.control='unsupported';native.controls.push({key:f.key,tag:'INPUT',type:'text',role:'combobox',popup:'listbox',expanded:'false',wrapper:'NG-SELECT'});
        if(f.value){const index=raw.actions.length;native.auxiliary.push({index,field_key:f.key});raw.actions.push({key:'a:'+index,label:'',selector:null,disabled:false});}
      }
    }
    if(kind==='language')for(const [index,row] of rows.entries()) {
      const proficiency=spec.proficiencies.map(p=>{
        const f=raw.fields.find(f=>f.key===`g:${row.proficiency_id}:${p.part}`),id=`checkbox-${generation}-${index}-${p.part}`;
        f.key='i:'+id;f.name='generated-group-'+generation;f.selector=`[id="${id}"]`;
        return {raw_key:f.key,label:p.label,value:p.value,selector_count:1};
      });native.rows.push({...row,proficiency});
    }
    if(drift)raw.fields.push({...raw.fields[0],key:'i:new',control:'text',label:'Unexpected required answer'});
    raw.actions.push({key:'a:'+raw.actions.length,label:'Help',selector:null,disabled:false});
    return {raw,native};
  }
  const locator=selector=>{
    const field=fields.find(f=>f.selector===selector),radioField=fields.find(f=>f.options.some(o=>o.selector===selector));
    return {count:async()=>1,nth:index=>({waitFor:async({state})=>{
      if(selector==='main input[role="combobox"]') {
        if(state==='visible')assert.ok(index<rows.length);
        else if(state==='hidden')assert.ok(index>=rows.length);
        else throw Error('Unused language rows remain mounted but hidden');
        calls.push('row-wait:'+index+':'+state);
      }
    }}),evaluate:async()=>({tag:'INPUT',type:'text',role:'combobox',popup:'listbox',expanded:opened?'true':'false'}),
      getAttribute:async()=>association,waitFor:async()=>{},click:async()=>{
        if(selector.startsWith('[id="sectionContinue')){calls.push('save');saved=structuredClone(fields);savedRows=structuredClone(rows);url='https://apply.commonapp.org/common/next';}
        else {opened=field.key;calls.push('open');}
      },press:async key=>{assert.equal(key,'Escape');opened=null;calls.push('close');},
      check:async()=>{const option=radioField.options.find(o=>o.selector===selector);radioField.value=option.value;
        if(radioField.key===spec.count_field?.key&&rows.length!==Number(option.label))addRows(Number(option.label));calls.push('radio');},
      setChecked:async v=>{field.value=v;calls.push('checkbox');}};
  };
  const panel={count:async()=>Number(!!opened),isVisible:async()=>!!opened,getAttribute:async()=> 'options-popup',waitFor:async()=>{},
    evaluate:async()=>options[opened].map(({label,disabled,index})=>({label,disabled,index})),getByRole:()=>({count:async()=>options[opened].length,nth:i=>({click:async()=>{
      const key=opened;fields.find(f=>f.key===key).value=options[key][i].label;
      const row=rows.find(r=>r.language_key===key);for(const f of fields.filter(f=>f.key.startsWith('g:'+row.proficiency_id+':')))f.value=false;
      calls.push('choose');opened=null;
    }})})};
  const tab={url:async()=>url,goto:async dest=>{url=dest;restoreSaved();generation++;calls.push('revisit');},
    reload:async()=>{restoreSaved();generation++;calls.push('cancel');},
    playwright:{locator,getByRole:role=>role==='listbox'?panel:{waitFor:async()=>{}},domSnapshot:async()=>'',evaluate:async()=>rawAndNative().native}};
  const hostAdapter={...host,observe:async()=>rawAndNative().raw,digest:v=>v==='Synthetic '+kind+' public content'?
    (kind==='language'&&!rows.length?spec.empty_content_sha256:spec.content_sha256):host.digest(v)},api=createCommonFactual(hostAdapter,kind);
  const {raw,native}=rawAndNative(),choices=Object.fromEntries(Object.entries(options).map(([k,v])=>[k,v.map(({label,value,disabled})=>({label,value,disabled}))]));
  const observed=api.decorate(raw,native,choices),desired=vals(observed);
  if(kind==='language'&&rows.length)desired[rows[0].language_key]='French';else if(kind==='household')desired['r:ques_366']='1';
  else if(kind==='grade12_status')desired['r:ques_1927']='1';
  const writes=Object.entries(desired).filter(([k,v])=>vals(observed)[k]!==v).map(([field_key,value])=>({field_key,value}));
  if(kind==='language'&&rows.length)for(const f of observed.fields.filter(f=>f.key.startsWith('g:'+rows[0].proficiency_id+':')))writes.push({field_key:f.key,value:f.value});
  const plan={system:'common_app',ready:true,page_url:raw.url,common_factual:observed.common_factual,choice_observations:choices,
    observation_sha256:host.digest(observed),structure_sha256:host.digest(host.structure(observed)),expected_values_sha256:host.digest(desired),writes,save_action:observed.actions[0]};
  const context={browser_family:'edge',transport:'extension',origin:'https://apply.commonapp.org',access_verified:true,journal_persisted:true};
  return {api,languageApi:kind==='language'?createCommonLanguage(hostAdapter):null,tab,fields,plan,context,calls,observed,rows,options,rawAndNative,setDrift:v=>{drift=v;},setAssociation:v=>{association=v;}};
}

for(const kind of ['household','language','grade12_status'])test(`${kind} whole-page draft save survives regenerated native identities`,async()=>{
  const s=setup(kind),original=vals(s.observed);await s.api.apply(s.tab,s.plan,s.context);const saved=await s.api.saveAndRead(s.tab,s.plan,s.context);
  assert.equal(host.digest(vals(saved.page)),s.plan.expected_values_sha256);assert.equal(host.digest(host.structure(saved.page)),s.plan.structure_sha256);
  const writes=Object.entries(original).filter(([k,v])=>vals(saved.page)[k]!==v).map(([field_key,value])=>({field_key,value}));
  if(kind==='language')for(const f of saved.page.fields.filter(f=>f.key.startsWith('g:'+s.rows[0].proficiency_id+':')))writes.push({field_key:f.key,value:original[f.key]});
  const restored=await s.api.restore(s.tab,{plan:s.plan,context:s.context,writes,original_invalid_fields:[],original_values_sha256:host.digest(original)});
  assert.deepEqual(vals(restored.page),original);assert.equal(s.calls.filter(c=>c==='save').length,2);
});

test('blank grade-12 status can fill only the observed No answer',async()=>{
  const s=setup('grade12_status',{blankGrade:true});await s.api.apply(s.tab,s.plan,s.context);
  const result=await s.api.saveAndRead(s.tab,s.plan,s.context);assert.equal(result.page.fields[0].value,'1');
});

test('grade-12 Yes and unknown grade records never use the No-page port',()=>{
  const s=setup('grade12_status'),{raw,native}=s.rawAndNative();raw.fields[0].value='0';
  assert.throws(()=>s.api.decorate(raw,native),/grade12_official_grade_layout/);
  raw.fields[0].value='1';raw.fields.push({...raw.fields[0],key:'i:extra-grade',control:'text',label:'Course grade'});
  assert.throws(()=>s.api.decorate(raw,native));assert.equal(s.calls.length,0);
});

for(const n of [1,3,5])test(`semantic language associations handle ${n} existing rows`,async()=>{
  const s=setup('language',{n}),page=await s.api.inspect(s.tab);assert.equal(page.fields.length,1+6*n);assert.equal(Object.keys(page.choice_observations).length,n);
});

for(const change of ['new_field','wrong_group','bad_pair','cross_question','checkbox_label','checkbox_value','ambiguous_checkbox','widget','content'])test(`${change} blocks an unrecognized factual shape`,async()=>{
  const s=setup(),{raw,native}=s.rawAndNative();
  if(change==='new_field')raw.fields.push({...raw.fields[1],key:'i:new'});
  if(change==='wrong_group')raw.fields[2].group='A different question';
  if(change==='bad_pair')native.rows[1].proficiency_id=native.rows[0].proficiency_id;
  if(change==='cross_question')native.rows[0].proficiency_id='4000';
  if(change==='checkbox_label')native.rows[0].proficiency[0].label='Different';
  if(change==='checkbox_value')native.rows[0].proficiency[0].value='999';
  if(change==='ambiguous_checkbox')native.rows[0].proficiency[0].selector_count=2;
  if(change==='widget')native.controls[0].wrapper='UNKNOWN';
  if(change==='content')native.content='New consent or unknown question';
  assert.throws(()=>s.api.decorate(raw,native,s.plan.choice_observations));assert.deepEqual(s.calls,[]);
});

for(const change of ['journal','stale','choice_drift','association'])test(`${change} cannot enable input or a save`,async()=>{
  const s=setup();
  if(change==='journal')s.context.journal_persisted=false;
  if(change==='stale')s.plan.observation_sha256='0'.repeat(64);
  if(change==='choice_drift')s.options[s.rows[0].language_key][1].disabled=true;
  if(change==='association')s.setAssociation('another-menu');
  await assert.rejects(s.api.apply(s.tab,s.plan,s.context));assert.ok(!s.calls.some(c=>['choose','checkbox','save'].includes(c)));
});

test('new conditional questions after selection stop before saving',async()=>{
  const s=setup(),choose=s.tab.playwright.getByRole;
  s.tab.playwright.getByRole=(role,...args)=>{const result=choose(role,...args);if(role!=='listbox')return result;
    const options=result.getByRole;return {...result,getByRole:(...a)=>{const list=options(...a);return {...list,nth:i=>{
      const option=list.nth(i);return {click:async()=>{await option.click();s.setDrift(true);}};}};}};};
  await assert.rejects(s.api.apply(s.tab,s.plan,s.context));assert.ok(!s.calls.includes('save'));
});

test('unsaved edits cancel without saving and preserve original flags',async()=>{
  const s=setup(),original=vals(s.observed);await s.api.apply(s.tab,s.plan,s.context);
  const canceled=await s.api.restore(s.tab,{plan:s.plan,context:s.context},{unsaved:true});
  assert.deepEqual(vals(canceled.page),original);assert.equal(canceled.restore_save_performed,false);assert.ok(!s.calls.includes('save'));
});

for(const kind of ['language','household'])test(`generic ${kind} filling cannot bypass the dedicated semantic observer`,async()=>{
  const s=setup(kind),tab={...s.tab,playwright:{...s.tab.playwright,evaluate:async()=>structuredClone(s.observed)}};
  await assert.rejects(host.applyWrites(tab,{...s.plan,allowed_origin:s.context.origin},s.context),/dedicated_common_page_port_required/);
  await assert.rejects(host.saveAndRead(tab,{...s.plan,allowed_origin:s.context.origin},s.context),/dedicated_common_page_port_required/);
  assert.deepEqual(s.calls,[]);
});

async function countPlan(s,n) {
  const before=await s.languageApi.inspect(s.tab),count=before.fields[0],value=count.options.find(o=>o.label===String(n)).value;
  return {schema:'common-language-count-plan/1',system:'common_app',ready:true,checkpoint_id:'checkpoint:synthetic',
    page_url:before.url,desired_count:n,observation_sha256:host.digest(before),common_factual:before.common_factual,
    writes:count.value===value?[]:[{field_key:count.key,value}],choice_observations:before.choice_observations};
}

function rowPlan(page) {
  const desired=vals(page),writes=[];
  for(const [index,row] of page.common_factual.rows.entries()) {
    const label=['French','Spanish','German','Mandarin','English'][index];
    desired[row.language_key]=label;writes.push({field_key:row.language_key,value:label});
    for(const part of contracts[1].proficiencies){const field_key=`g:${row.proficiency_id}:${part.part}`,value=part.part==='speak'||index===0&&part.part==='first_language';
      desired[field_key]=value;writes.push({field_key,value});}
  }
  return {schema:'page-plan/1',system:'common_app',ready:true,page_url:page.url,common_factual:page.common_factual,
    observation_sha256:host.digest(page),structure_sha256:host.digest(host.structure(page)),expected_values_sha256:host.digest(desired),
    writes,choice_observations:page.choice_observations,save_action:page.actions[0]};
}

for(const [before,after] of [[0,1],[0,5],[1,3],[5,2],[2,2]])test(`staged language ${before} to ${after} uses only freshly observed rows`,async()=>{
  const s=setup('language',{n:before}),plan=await countPlan(s,after),staged=await s.languageApi.changeCount(s.tab,plan,s.context);
  assert.equal(staged.page.common_factual.rows.length,after);assert.equal(staged.saved,false);assert.equal(staged.requires_fresh_fields_plan,true);
  assert.ok(s.calls.includes('row-wait:'+after+':hidden'));
  assert.equal(s.calls.filter(c=>c==='save').length,0);
  await assert.rejects(s.languageApi.apply(s.tab,plan,s.context)); // Count authorization is not a whole-page save plan.
  const fields=rowPlan(staged.page);await s.languageApi.apply(s.tab,fields,s.context);
  const saved=await s.languageApi.saveAndRead(s.tab,fields,s.context);
  assert.equal(host.digest(vals(saved.page)),fields.expected_values_sha256);assert.equal(s.calls.filter(c=>c==='save').length,1);
});

for(const change of ['journal','stale','test','restore_test','extra_write','wrong_count','new_field'])test(`staged language ${change} blocks before count input`,async()=>{
  const s=setup('language',{n:1}),plan=await countPlan(s,3);
  if(change==='journal')s.context.journal_persisted=false;
  if(change==='stale')plan.observation_sha256='0'.repeat(64);
  if(change==='test')s.context.real_account_test=true;
  if(change==='restore_test')s.context.restore_after_test=true;
  if(change==='extra_write')plan.writes.push({field_key:s.rows[0].language_key,value:'French'});
  if(change==='wrong_count')plan.desired_count=0;
  if(change==='new_field')s.setDrift(true);
  await assert.rejects(s.languageApi.changeCount(s.tab,plan,s.context));
  assert.ok(!s.calls.some(c=>['radio','choose','checkbox','save'].includes(c)));
});

for(const before of [0,2])test(`unsaved language row creation cancels back to ${before} rows without a draft save`,async()=>{
  const s=setup('language',{n:before}),original=vals(s.observed),plan=await countPlan(s,4);
  await s.languageApi.changeCount(s.tab,plan,s.context);
  const canceled=await s.languageApi.cancelUnsaved(s.tab,s.context);
  assert.deepEqual(vals(canceled.page),original);assert.equal(canceled.page.common_factual.rows.length,before);
  assert.equal(canceled.restore_save_performed,false);assert.ok(!s.calls.includes('save'));
});
