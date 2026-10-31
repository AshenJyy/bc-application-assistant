import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createGradeEditor} from '../skills/bc-application/scripts/grade_editor.mjs';
import {digest,structure,guard} from '../skills/bc-application/scripts/host_browser.mjs';

const fixture=JSON.parse(await readFile(new URL('./fixtures/grade_dialog_page.json',import.meta.url),'utf8'));
function setup({delayedSelection=false}={}) {
  const page=structuredClone(fixture),calls=[];
  const key='i:grades1_T2C1',f=page.fields.find(f=>f.key===key);
  let opened=false,selectionPending=false,options=page.choice_observations[key].map((o,index)=>({...o,index}));
  const combo={count:async()=>1,evaluate:async()=>({tag:'MAT-SELECT',role:'combobox',expanded:'false'}),
    click:async()=>{opened=true;calls.push('open');},press:async(k)=>{assert.equal(k,'Escape');opened=false;calls.push('escape');}};
  const panel={count:async()=>opened?1:0,isVisible:async()=>opened,
    press:async key=>{assert.equal(key,'Escape');assert.equal(selectionPending,false,'Never send Escape during a successful selection transition');opened=false;calls.push('dismiss-overlay');},
    waitFor:async({state})=>{if(state==='hidden'||state==='detached'){if(selectionPending){opened=false;selectionPending=false;calls.push('selection-closed');}assert.equal(opened,false);}},
    evaluate:async()=>structuredClone(options),getByRole:()=>({count:async()=>options.length,
      nth:i=>({click:async()=>{calls.push(`choose:${options[i].label}`);f.value=options[i].label;selectionPending=delayedSelection;opened=delayedSelection;}})})};
  const tab={playwright:{domSnapshot:async()=>'',locator:()=>combo,getByRole:(role)=>{
    if(role==='listbox')return panel;
    if(role==='dialog')return {getByRole:()=>({click:async()=>{opened=false;calls.push('dismiss-overlay');}})};
    throw Error('unexpected UI surface: '+role);
  }}};
  const api=createGradeEditor({digest,structure,guard,observe:async()=>structuredClone(page),
    writeObserved:async(_tab,_page,writes)=>{for(const w of writes){calls.push('native:'+w.field_key);page.fields.find(f=>f.key===w.field_key).value=w.value;}}});
  const context={browser_family:'edge',transport:'extension',access_verified:true,origin:'http://127.0.0.1:8765',synthetic_test:true,journal_persisted:true};
  const plan={ready:true,allowed_origin:'https://apply.commonapp.org',page_url:page.url,
    editor_state:page.editor_state,choice_observations:page.choice_observations,
    observation_sha256:digest(page),structure_sha256:digest(structure(page)),
    expected_values_sha256:digest(Object.fromEntries(page.fields.map(f=>[f.key,f.key===key?'94':f.value]))),
    writes:[{field_key:key,value:'94'}],save_action:page.actions[0]};
  return {api,tab,page,calls,plan,context,setOptions:v=>{options=v;},f};
}

test('actual option labels are discovered and inspection closes the listbox without writes',async()=>{
  const s=setup();const before=digest(s.page);
  assert.deepEqual(await s.api.inspectGradeOptions(s.tab,s.page.editor_state,s.f.key),s.page.choice_observations[s.f.key]);
  assert.deepEqual(s.calls,['open','dismiss-overlay']);assert.equal(digest(s.page),before);
});

test('Material writing uses an exact fresh option and checks the complete editor afterward',async()=>{
  const s=setup();const result=await s.api.applyGradeWrites(s.tab,s.plan,s.context);
  assert.equal(result.fields.find(f=>f.key===s.f.key).value,'94');
  assert.deepEqual(s.calls,['open','choose:94']);
});

test('successful asynchronous selection waits for closure without sending Escape to its parent',async()=>{
  const s=setup({delayedSelection:true});await s.api.applyGradeWrites(s.tab,s.plan,s.context);
  assert.deepEqual(s.calls,['open','choose:94','selection-closed']);
});

for(const change of ['disabled','label','order'])test(`changed ${change} options stop before selection`,async()=>{
  const s=setup(),opts=s.page.choice_observations[s.f.key].map((o,index)=>({...o,index}));
  if(change==='disabled')opts[1].disabled=true;
  if(change==='label')opts[1].label='Unexpected';
  if(change==='order')opts.reverse();
  s.setOptions(opts);
  await assert.rejects(s.api.applyGradeWrites(s.tab,s.plan,s.context),/material_choices_changed/);
  assert.deepEqual(s.calls,['open','dismiss-overlay']);assert.equal(s.f.value,'84');
});

test('stale full observation stops before opening any option panel',async()=>{
  const s=setup();s.page.fields.find(f=>f.control==='text').value='Changed outside prepared plan';
  await assert.rejects(s.api.applyGradeWrites(s.tab,s.plan,s.context),/page_changed_since_preparation/);
  assert.deepEqual(s.calls,[]);
});

test('outer reporting attestation is never included in grade writes',async()=>{
  const s=setup();s.page.fields.push({key:'attestation',control:'checkbox',label:'I have reported all of my courses for this grade',group:'',value:true});
  s.plan.observation_sha256=digest(s.page);
  await assert.rejects(s.api.applyGradeWrites(s.tab,s.plan,s.context),/factual_grade_scope_required/);
  assert.deepEqual(s.calls,[]);
});

test('header reconfiguration and clearing a Material value remain handoff-only',async()=>{
  for(const fieldKey of ['i:schoolYearControl1','i:grades1_T2C1']) {
    const s=setup();s.plan.writes=[{field_key:fieldKey,value:''}];
    await assert.rejects(s.api.applyGradeWrites(s.tab,s.plan,s.context),/grade_header_reconfiguration_excluded|material_clear_recovery_handoff_required/);
    assert.deepEqual(s.calls,[]);
  }
});

test('unverified restoration permission cannot be replaced by a matching plan',async()=>{
  const s=setup();s.context.real_account_test=true;
  await assert.rejects(s.api.applyGradeWrites(s.tab,s.plan,s.context),/real_test_restoration_not_established/);
  assert.deepEqual(s.calls,[]);
});

test('unrecognized narrative control blocks saving even when a fabricated plan matches',async()=>{
  const s=setup();s.page.fields.push({key:'unknown',control:'text',label:'Describe your goals',group:'',value:'Existing narrative'});
  await assert.rejects(s.api.saveGradeAndRead(s.tab,s.plan,s.context),/known_factual_grade_controls_required/);
  assert.deepEqual(s.calls,[]);
});

async function saveHarness({slowClose=false,stuck=false}={}) {
  const p=structuredClone(fixture),calls=[];delete p.editor_state;delete p.choice_observations;
  const closed={...p,fields:[{key:'outer',label:'I have reported all of my courses for this grade',
    control:'checkbox',value:true,required:false,disabled:false,readonly:false}],
    actions:[{key:'i:addCG',label:'Edit 9th grade',selector:'[id="addCG"]',disabled:false},
      {key:'i:sectionContinue55',label:'Continue to next section',disabled:false}]};
  let opened=false;
  const modal={count:async()=>opened?1:0,isVisible:async()=>opened,
    waitFor:async({state})=>{
      if(state==='visible')assert.equal(opened,true);
      else {if(slowClose)opened=false;throw Error('delayed overlay status');}
    },
    getByRole:role=>role==='button'?{count:async()=>1,press:async key=>{assert.equal(key,'Enter');calls.push('modal-draft-save');if(!slowClose&&!stuck)opened=false;}}:
      {waitFor:async()=>assert.equal(opened,true)}};
  const tab={url:async()=>p.url,reload:async()=>{calls.push('reload');opened=false;},playwright:{
    evaluate:async()=>({heading:'9th Grade',text:'Invented parent summary'}),domSnapshot:async()=>'',
    getByRole:role=>role==='dialog'?modal:{waitFor:async()=>{}},
    locator:selector=>selector==='[id="addCG"]'?{count:async()=>1,click:async()=>{opened=true;calls.push('reopen-editor');}}:
      {waitFor:async()=>{calls.push('status-ready');}}}};
  const api=createGradeEditor({digest,structure,guard,writeObserved:async()=>{},
    observe:async(_tab,options)=>structuredClone(options?.grade_dialog?p:closed)});
  const parent=await api.captureParent(tab);opened=true;
  const observed=await api.observeGradeEditor(tab,parent);
  const plan={ready:true,editor_state:parent,choice_observations:{},save_action:p.actions[0],
    structure_sha256:digest(structure(observed)),expected_values_sha256:digest(Object.fromEntries(p.fields.map(f=>[f.key,f.value])))};
  const context={browser_family:'edge',transport:'extension',origin:'http://127.0.0.1:8765',
    access_verified:true,synthetic_test:true,journal_persisted:true};
  return {api,tab,plan,context,calls};
}

test('a delayed modal closure is re-observed, then one save reloads/reopens the whole editor',async()=>{
  const s=await saveHarness({slowClose:true});const result=await s.api.saveGradeAndRead(s.tab,s.plan,s.context);
  assert.equal(result.revisited_after_save,true);
  assert.deepEqual(result.page.editor_state,s.plan.editor_state);
  assert.equal(s.calls.filter(c=>c==='modal-draft-save').length,1);
  assert.equal(s.calls.filter(c=>c==='reload').length,1);
  assert.equal(s.calls.filter(c=>c==='reopen-editor').length,1);
  assert.equal(s.calls.filter(c=>c==='status-ready').length,2);
});

test('an open failed modal stops without another save or reload; caller recovery remains necessary',async()=>{
  const s=await saveHarness({stuck:true});
  await assert.rejects(s.api.saveGradeAndRead(s.tab,s.plan,s.context),/delayed overlay status/);
  assert.deepEqual(s.calls,['modal-draft-save']);
});
