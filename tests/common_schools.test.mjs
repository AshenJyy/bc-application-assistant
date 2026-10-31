import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createCommonSchools,contract,schoolStructure,schoolValues} from '../skills/bc-application/scripts/common_schools.mjs';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.BC_TEST_PYTHON||(process.platform==='win32'?root+'work/.venv/Scripts/python.exe':'python3');
const stages=JSON.parse(execFileSync(python,['-B',root+'tests/school_host_scenario.py'],{cwd:root,encoding:'utf8',maxBuffer:4e6,
  env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}}));

function setup(source,{noEffect=false,blurValidates=false,blurChangesValue=false,appendOnFill=false,clearNoEffect=false}={}) {
  const s=structuredClone(source),calls=[];let page=s.before,dialogOpen=false,query='',selected=false,saved=structuredClone(page),url=page.url,writes=0;
  let candidates=structuredClone(s.lookup.options);
  const move=()=>{if(!noEffect)page=structuredClone(s.after);};
  function seen(){return {heading:page.heading,records:page.common_school.records.map(r=>({...r,selected:page.school_values[r.question_id]})),
    notes:page.fields.filter(f=>f.control==='school_statement').map(f=>({question_id:f.key.split(':')[1],selector:f.selector,selector_count:1,text:f.value,format:f.statement_format})),
    progression:page.fields.filter(f=>f.control==='checkbox').map(f=>{const part=contract.progression.find(p=>f.key==='g:265:'+p.part);
      return {id:'checkbox_'+part.value,value:part.value,label:f.label,selector:f.selector,selector_count:1};})};}
  function raw(){const p=structuredClone(page);p.schema='observed-page/1';
    p.fields=p.fields.map(f=>{
      if(f.control==='checkbox'){const part=contract.progression.find(p=>f.key==='g:265:'+p.part);f.key='i:checkbox_'+part.value;}
      if(f.control==='school_statement'){f.control='unsupported';f.key='l:'+f.label;f.selector=null;f.selector_count=0;f.selector_index=-1;delete f.statement_format;}
      return f;
    });return p;}
  const locator=selector=>({count:async()=>1,filter:()=>locator(selector),waitFor:async({state})=>{calls.push('wait:'+state);},locator,getByRole:()=>({count:async()=>1}),
    innerText:async()=>page.fields.find(f=>f.selector===selector)?.value||'',
    evaluate:async()=>contract.lookup_search,
    fill:async value=>{
      if(selector.includes('searchTermControl')){query=value;calls.push('query');return;}
      const f=page.fields.find(f=>f.selector===selector);assert.equal(f.control,'school_statement');f.value=appendOnFill?f.value+value:value;f.statement_format='plain_paragraph';calls.push('statement');
    },press:async key=>{const f=page.fields.find(f=>f.selector===selector);if(f?.control==='school_statement'){
      if(key==='Control+A'){calls.push('statement-select');return;}
      if(key==='Backspace'){if(!clearNoEffect){f.value='';f.statement_format='empty';}calls.push('statement-clear');return;}
      calls.push('statement-blur');if(blurValidates)f.invalid=false;if(blurChangesValue)f.value+=' Changed';
    }},click:async()=>{
      if(selector.includes('findSchool')||selector.includes('changeSchool')){dialogOpen=true;calls.push('open-lookup');}
      else if(selector.includes('selectionListResult')){selected=true;calls.push('select-school');}
      else if(selector.includes('lookupContinue')){assert.ok(selected);dialogOpen=false;move();calls.push('school-continue');}
      else if(selector.includes('sectionContinue')){saved=structuredClone(s.saved);page=structuredClone(saved);url='http://127.0.0.1:8765/common/next';calls.push('save');}
      else throw Error('unrecognized selector '+selector);
    }});
  const d={count:async()=>Number(dialogOpen),waitFor:async()=>{},locator,getByText:()=>({waitFor:async()=>{}}),
    getByRole:(role)=>role==='button'?{click:async()=>{dialogOpen=false;calls.push('close-lookup');}}:
      {filter:()=>({first:()=>({waitFor:async()=>{}})})},
    evaluate:async()=>({...structuredClone(s.lookup),query,options:candidates.map(o=>({...o,...(o.kind==='school'?{selected}: {})}))})};
  const tab={url:async()=>url,reload:async()=>{page=structuredClone(saved);url=page.url;calls.push('reload');},
    goto:async target=>{assert.equal(target,s.plan.page_url);page=structuredClone(saved);url=target;calls.push('revisit');},playwright:{locator,
      getByRole:()=>d,getByText:()=>({waitFor:async()=>{}}),domSnapshot:async()=>'',
      evaluate:async fn=>fn.toString().includes('a[id^=')?page.state_metadata.items.map(i=>i.key):seen()}};
  const api=createCommonSchools({...host,observe:async()=>raw(),writeObserved:async(_tab,_page,ws)=>{
    for(const w of ws){calls.push('write:'+w.field_key);if(!noEffect)page.fields.find(f=>f.key===w.field_key).value=w.value;writes++;}
    if(s.plan.stage!=='fields'&&writes===s.plan.writes.length)move();
  }});
  return {s,tab,api,calls,plan:s.plan,context:s.context,getPage:()=>page,setPage:p=>{page=p;url=p.url;},setCandidates:items=>{candidates=items;}};
}

for(const kind of ['current','other'])for(const source of stages.filter(s=>s.before.common_school.kind===kind))test(`${kind} ${source.plan.stage} uses observed school owners and postconditions`,async()=>{
  const s=setup(source),after=await s.api.applyStep(s.tab,s.plan,s.context);
  assert.deepEqual(schoolValues(after),schoolValues(source.after));assert.ok(!s.calls.includes('save'));
});

test('school directory search closes without selecting or changing the application',async()=>{
  const s=setup(stages[0]),question=s.plan.question_id;
  const result=await s.api.lookup(s.tab,question,s.plan.identity.name,s.context);
  assert.equal(result.query,s.plan.identity.name);assert.ok(s.calls.includes('close-lookup'));
  assert.ok(!s.calls.some(c=>['save','select-school','school-continue'].includes(c)));
  assert.deepEqual(schoolValues(s.getPage()),schoolValues(s.s.before));
});

for(const change of ['journal','stale','wrong_stage','wrong_url','real_new_school'])test(`school ${change} blocks before any application input`,async()=>{
  const s=setup(stages[0]);
  if(change==='journal')s.context.journal_persisted=false;
  if(change==='stale')s.plan.observation_sha256='0'.repeat(64);
  if(change==='wrong_stage')s.plan.stage='submit';
  if(change==='wrong_url')s.plan.page_url='https://example.org/';
  if(change==='real_new_school'){s.context.real_account_test=true;s.context.full_state_restoration_verified=true;}
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context));assert.deepEqual(s.calls.filter(c=>!c.startsWith('wait:')),[]);
});

for(const change of ['changed_code','ambiguous','new_same_name_school','incomplete','wrong_country'])test(`fresh school ${change} blocks before selection`,async()=>{
  const s=setup(stages[0]),options=structuredClone(s.s.lookup.options);
  if(change==='changed_code')options[0].ceeb='999999';
  if(change==='wrong_country')options[0].country='United States of America';
  if(change==='ambiguous'){options.push({...options[0],selector:'[id="selectionListResult999-"]'});s.s.lookup.total=2;}
  if(change==='new_same_name_school'){options.push({...options[0],ceeb:'999999',selector:'[id="selectionListResult999-"]'});s.s.lookup.total=2;}
  if(change==='incomplete')s.s.lookup.total=50;
  s.setCandidates(options);await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context),/fresh_exact_complete_school_match/);
  assert.ok(!s.calls.some(c=>['save','select-school','school-continue'].includes(c)));
});

for(const kind of ['school','graduation_mode','progression_mode','count'])test(`no-effect ${kind} stops instead of duplicating or saving`,async()=>{
  const s=setup(stages.find(s=>s.plan.stage===kind),{noEffect:true});
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context),/not_observed|unknown|progression/);assert.ok(!s.calls.includes('save'));
});

for(const change of ['college_essay','foreign_statement_owner','extra_count_write'])test(`${change} cannot use the factual statement exception`,async()=>{
  const s=setup(stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current'));
  if(change==='college_essay')s.getPage().fields.find(f=>f.control==='school_statement').label='Why do you want to attend this college?';
  if(change==='foreign_statement_owner')s.getPage().fields.find(f=>f.control==='school_statement').selector='[id="collegeEssay"]';
  if(change==='extra_count_write')s.plan.writes.push({field_key:'r:ques_255',value:'3'});
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context));assert.ok(!s.calls.includes('statement')&&!s.calls.includes('save'));
});

for(const kind of ['current','other'])test(`${kind} whole page save revisits and checks all entered values`,async()=>{
  const source=stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind===kind),s=setup(source);
  await s.api.applyStep(s.tab,s.plan,s.context);const result=await s.api.saveAndRead(s.tab,s.plan,s.context);
  assert.equal(result.revisited_after_save,true);assert.deepEqual(schoolValues(result.page),schoolValues(source.saved));
  assert.equal(s.calls.filter(c=>c==='save').length,1);assert.ok(s.calls.includes('revisit'));
});

test('an intermediate stage or incomplete fields cannot save',async()=>{
  const s=setup(stages[0]);await assert.rejects(s.api.saveAndRead(s.tab,s.plan,s.context),/complete_school_page/);assert.deepEqual(s.calls.filter(c=>!c.startsWith('wait:')),[]);
});

test('unsaved school cancellation reloads the original without saving',async()=>{
  const s=setup(stages[0]);await s.api.applyStep(s.tab,s.plan,s.context);
  const result=await s.api.cancelUnsaved(s.tab,s.context);
  assert.deepEqual(schoolValues(result.page),schoolValues(s.s.before));assert.equal(result.restore_save_performed,false);assert.ok(!s.calls.includes('save'));
});

test('checkbox render generations do not replace stable public owners',()=>{
  const source=stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current');
  const a=structuredClone(source.before),b=structuredClone(a);
  for(const f of a.fields.filter(f=>f.control==='checkbox'))f.name='ca-checkboxList-5_group';
  for(const f of b.fields.filter(f=>f.control==='checkbox'))f.name='ca-checkboxList-1_group';
  assert.deepEqual(schoolStructure(a),schoolStructure(b));
  b.fields.find(f=>f.control==='checkbox').selector='[id="unrelated"]';assert.notDeepEqual(schoolStructure(a),schoolStructure(b));
});

for(const validates of [true,false])test(`school blur ${validates?'uses':'retains'} website validation after saved revisit`,async()=>{
  const source=structuredClone(stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current'));
  source.saved.fields.find(f=>f.control==='school_statement').invalid=true;
  const s=setup(source,{blurValidates:validates});await s.api.applyStep(s.tab,s.plan,s.context);
  const result=await s.api.saveAndRead(s.tab,s.plan,s.context);
  assert.equal(result.page.fields.find(f=>f.control==='school_statement').invalid,!validates);
  assert.equal(s.calls.filter(c=>c==='save').length,1);assert.ok(s.calls.includes('statement-blur'));
});

test('validation blur cannot silently change school explanation text',async()=>{
  const source=structuredClone(stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current'));
  source.before.fields.find(f=>f.control==='school_statement').invalid=true;
  const s=setup(source,{blurValidates:true,blurChangesValue:true});
  await assert.rejects(s.api.settleValidation(s.tab),/school_validation_changed_application/);assert.ok(!s.calls.includes('save'));
});

test('generic native writer cannot bypass the scoped school statement port',async()=>{
  const source=stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current'),s=setup(source);
  const field=s.s.before.fields.find(f=>f.control==='school_statement');
  await assert.rejects(host.writeObserved(s.tab,s.s.before,[{field_key:field.key,value:'An arbitrary narrative'}]),/observed_editable_field_required/);
  assert.equal(s.calls.length,0);
});

test('school editor clears existing model text before a fill that appends',async()=>{
  const source=structuredClone(stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current'));
  source.before.fields.find(f=>f.control==='school_statement').value='An existing fictional statement.';
  source.plan.observation_sha256=host.digest(source.before);
  const s=setup(source,{appendOnFill:true}),after=await s.api.applyStep(s.tab,s.plan,s.context);
  assert.deepEqual(schoolValues(after),schoolValues(source.after));
  assert.ok(s.calls.indexOf('statement-clear')<s.calls.indexOf('statement'));
});

test('failed school editor deletion stops before inserting or saving',async()=>{
  const source=structuredClone(stages.find(s=>s.plan.stage==='fields'&&s.before.common_school.kind==='current'));
  source.before.fields.find(f=>f.control==='school_statement').value='An existing fictional statement.';
  source.plan.observation_sha256=host.digest(source.before);
  const s=setup(source,{clearNoEffect:true});
  await assert.rejects(s.api.applyStep(s.tab,s.plan,s.context),/school_statement_clear_not_observed/);
  assert.ok(!s.calls.includes('statement')&&!s.calls.includes('save'));
});
