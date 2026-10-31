import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createCommonAcademic,contract,reportingControlShape} from '../skills/bc-application/scripts/common_academic.mjs';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.BC_TEST_PYTHON||(process.platform==='win32'?root+'work/.venv/Scripts/python.exe':'python3');
const stages=JSON.parse(execFileSync(python,['-B',root+'tests/academic_host_scenario.py'],{cwd:root,encoding:'utf8',maxBuffer:4e6,
  env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}}));
const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

test('observed outer reporting checkbox uses stable semantics across navigation',()=>{
  const a={key:'i:generated-1',name:'group-1',selector:'[id="generated-1"]',control:'checkbox',label:'I have reported all of my courses for this grade',
    value:true,invalid:false,required:false,disabled:false,readonly:false,selector_count:1,selector_index:0,options:[],group:''};
  const b={...a,key:'i:generated-9',name:'group-9',selector:'[id="generated-9"]'};
  assert.deepEqual(reportingControlShape([a]),reportingControlShape([b]));
  assert.notDeepEqual(reportingControlShape([a]),reportingControlShape([{...b,disabled:true}]));
  assert.throws(()=>reportingControlShape([{...b,label:'I sign this application'}]));
  assert.throws(()=>reportingControlShape([a,b]));
});

function setup(source,{noEffect=false}={}) {
  const s=structuredClone(source),calls=[];let page=s.before,opened=null,confirmation=false,visible=true;
  const move=()=>{if(!noEffect)page=structuredClone(s.after);};
  const locator=selector=>({count:async()=>1,nth:()=>locator(selector),
    evaluate:async()=>({tag:'MAT-SELECT',role:'combobox',expanded:'false'}),
    waitFor:async({state})=>{calls.push('wait:'+state);},
    getByRole:(_role,{name})=>action(name),locator,
    click:async()=>{
      if(selector==='[id="alert_rc_r"]'){calls.push('remove-empty');confirmation=false;move();return;}
      if(selector==='[id="changePreferencesClose"]'){calls.push('cancel');visible=false;return;}
      const f=page.fields.find(f=>f.selector===selector);if(f){opened=f;calls.push('open-options');return;}
      throw Error('unknown selector '+selector);
    }});
  const action=name=>({count:async()=>1,press:async()=>{calls.push('save');visible=false;},click:async()=>{
    if(String(name).startsWith('Remove transcript')){confirmation=true;calls.push('confirm-empty');}
    else {calls.push(name);move();}
  }});
  const panel={count:async()=>opened?1:0,isVisible:async()=>!!opened,waitFor:async()=>{},
    press:async()=>{opened=null;},evaluate:async()=>s.before.choice_observations[opened.key].map((o,index)=>({...o,index})),
    getByRole:()=>({count:async()=>s.before.choice_observations[opened.key].length,nth:i=>({click:async()=>{
      const option=s.before.choice_observations[opened.key][i];calls.push('choose:'+option.label);
      if(!noEffect)page.fields.find(f=>f.key===opened.key).value=option.label;opened=null;
      if(s.plan.stage==='header')move();
    }})})};
  const dialog={count:async()=>visible?1:0,waitFor:async()=>{},locator,getByRole:(_role,{name})=>action(name)};
  const confirm={waitFor:async()=>{},innerText:async()=>`Remove course ${s.plan.row} of ${s.before.academic_layout.transcripts[s.plan.transcript-1].rows.length}\nAre you sure you want to permanently remove this course?\nCancelRemove`,locator};
  const tab={url:async()=>page.url,reload:async()=>{calls.push('revisit');visible=false;},playwright:{locator,domSnapshot:async()=>'',getByText:()=>({waitFor:async()=>{}}),
    getByRole:(role,options)=>role==='listbox'?panel:options?.name==='Courses & Grades'?dialog:confirm,
    evaluate:async()=>structuredClone(page.academic_layout)}};
  const api=createCommonAcademic({...host,observe:async()=>structuredClone(page),
    writeObserved:async(_tab,_page,writes)=>{for(const w of writes){calls.push('write:'+w.field_key);page.fields.find(f=>f.key===w.field_key).value=w.value;}
      if(s.plan.stage==='credit_mode')move();}});
  return {api,tab,calls,context:s.context,plan:s.plan,parent:s.before.editor_state,getPage:()=>page,setPage:p=>{page=p;},s};
}

for(const kind of ['header','add_transcript','add_course','remove_placeholder','credit_mode','fields']) {
  let source=stages.find(s=>s.plan.stage===kind);
  if(kind==='add_course'){
    source=structuredClone(stages.find(s=>s.plan.stage==='remove_placeholder'));
    [source.before,source.after]=[source.after,source.before];
    source.plan={...source.plan,stage:'add_course',row:2,observation_sha256:host.digest(source.before),choice_observations:source.before.choice_observations};
  }
  test(`academic ${kind} acts on current observed owners and checks the result`,async()=>{
    const s=setup(source);const result=await s.api.applyStep(s.tab,s.plan,s.context,s.parent);
    assert.deepEqual(vals(result),vals(source.after));
    assert.ok(!s.calls.includes('save'));
    if(['add_transcript','add_course','remove_placeholder'].includes(kind))assert.ok(s.calls.some(c=>c.startsWith('wait:')));
  });
}

for(const change of ['journal','stale','test','restore_test','wrong_stage','wrong_url'])test(`${change} cannot enable academic input`,async()=>{
  const s=setup(stages[0]);
  if(change==='journal')s.context.journal_persisted=false;
  if(change==='stale')s.plan.observation_sha256='0'.repeat(64);
  if(change==='test')s.context.real_account_test=true;
  if(change==='restore_test')s.context.restore_after_test=true;
  if(change==='wrong_stage')s.plan.stage='attest';
  if(change==='wrong_url')s.plan.page_url='https://example.org/';
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context,s.parent));assert.deepEqual(s.calls,[]);
});

for(const kind of ['add_transcript','header','remove_placeholder'])test(`${kind} with no observed effect stops instead of planning a duplicate`,async()=>{
  const source=stages.find(s=>s.plan.stage===kind),s=setup(source,{noEffect:true});
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context,s.parent),/not_observed/);
  assert.ok(!s.calls.includes('save'));
});

test('only an entirely blank last placeholder is eligible for removal',async()=>{
  const source=structuredClone(stages.find(s=>s.plan.stage==='remove_placeholder'));
  source.before.fields.find(f=>f.key===`i:courseNameControl_T${source.plan.transcript}C${source.plan.row}`).value='Existing factual course';
  source.plan.observation_sha256=host.digest(source.before);const s=setup(source);
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context,s.parent),/empty_unsaved_placeholder/);assert.deepEqual(s.calls,[]);
});

test('save cannot run from an intermediate header/row stage',async()=>{
  const s=setup(stages[0]);await assert.rejects(s.api.saveAndRead(s.tab,s.plan,s.context,s.parent),/complete_academic_records/);
  assert.deepEqual(s.calls,[]);
});

test('whole-page mismatch blocks a draft save',async()=>{
  const s=setup(stages.at(-1));s.setPage(structuredClone(s.s.after));s.getPage().fields[4].value='Wrong subject';
  await assert.rejects(s.api.saveAndRead(s.tab,s.plan,s.context,s.parent),/complete_academic_records/);assert.deepEqual(s.calls,[]);
});

test('generic host methods reject the staged academic scope',async()=>{
  const s=setup(stages[0]),tab={...s.tab,playwright:{...s.tab.playwright,evaluate:async()=>structuredClone(s.s.before)}};
  await assert.rejects(host.applyWrites(tab,{...s.plan,allowed_origin:contract.origin},s.context),/dedicated_common_page_port/);
  await assert.rejects(host.saveAndRead(tab,{...s.plan,allowed_origin:contract.origin},s.context),/dedicated_common_page_port/);
  assert.deepEqual(s.calls,[]);
});
