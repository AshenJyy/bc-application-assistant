// Synthetic UC relay tests: no browser, account, network or personal data.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createUcPersonal} from '../skills/bc-application/scripts/uc_personal.mjs';

const fixture=JSON.parse(await readFile(new URL('./fixtures/uc_personal_page.json',import.meta.url),'utf8'));
const stateFixture=JSON.parse(await readFile(new URL('./fixtures/uc_review_state.json',import.meta.url),'utf8'));
const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

function port(options={}) {
  const page=structuredClone(fixture),state=structuredClone(stateFixture),calls=[];
  page.title='Personal information - About you - UC application';
  for(const f of page.fields) {
    f.invalid=false;
    if(f.name==='firstName')f.value='Synthetic';
    if(f.name==='lastName')f.value='Applicant';
    if(f.control==='radio')f.value=f.options.find(o=>o.label==='No').value;
  }
  let url=page.url,expanded=false;
  const context={browser_family:'edge',transport:'extension',origin:new URL(page.url).origin,access_verified:true,
    real_account_test:true,full_state_restoration_verified:true,journal_persisted:true,
    restoration_strategy:{kind:'restore_uc_personal',page_url:page.url,baseline_state_sha256:host.digest(state)}};
  const plan={ready:true,system:'uc',allowed_origin:context.origin,page_url:page.url,
    observation_sha256:host.digest({...page,state_metadata:state}),structure_sha256:host.digest(host.structure(page)),
    expected_values_sha256:host.digest(vals(page)),writes:[],save_action:page.actions.find(a=>a.key==='i:save')};
  const control=selector=>({count:async()=>1,waitFor:async()=>{},press:async key=>{
    assert.equal(key,'Enter');assert.equal(selector,'[id="save"]');calls.push('save');url=context.origin+'/my-application/applicationAddress';},
    fill:async value=>{calls.push('input');page.fields.find(f=>f.selector===selector).value=value;},
    selectOption:async choice=>{
      calls.push('input');const f=page.fields.find(f=>f.selector===selector);f.value=choice.value;
      if(options.countryClearsCity&&f.name==='birthCountryCode')page.fields.find(f=>f.name==='birthCity').value='';
    }});
  const role=(role,options)=>({waitFor:async()=>{},isVisible:async()=>expanded,count:async()=>options.name==='Expand all'?Number(!expanded):1,
    click:async()=>{expanded=true;calls.push('expand');},press:async key=>{
      assert.equal(key,'Enter');calls.push(options.name);
      if(options.name==='Review & submit'){url=state.review_url;expanded=false;}
      else if(options.name==='Application status')url=state.status_url;
      else if(options.name===state.term){url=state.review_url;expanded=false;}
      else if(options.name==='Edit Personal information')url=page.url;
      else throw Error('unexpected navigation');
    }});
  const tab={url:async()=>url,playwright:{locator:control,getByRole:role,domSnapshot:async()=>'',waitForURL:async expected=>assert.equal(url,expected),
    expectNavigation:async action=>action(),evaluate:async()=>{
      if(url===state.review_url)return {term:state.term,sections:structuredClone(state.sections)};
      if(url===state.status_url)return {term:state.term,draft_marker:state.draft_marker};
      return ['/my-application/reviewSubmit','/my-application/appStatus'];
    }}};
  const api=createUcPersonal({...host,observe:async()=>structuredClone(page)});
  return {page,state,plan,context,calls,tab,api};
}

test('UC whole-page factual writes save, revisit and restore all values with full visible state',async()=>{
  const {page,state,plan,context,calls,tab,api}=port(),f=page.fields.find(f=>f.name==='firstName'),original=f.value;
  plan.writes=[{field_key:f.key,value:'SYNTHETIC'}];
  plan.expected_values_sha256=host.digest({...vals(page),[f.key]:'SYNTHETIC'});
  const local=await api.apply(tab,plan,context);
  assert.equal(calls.filter(c=>c==='input').length,1);
  const saved=await api.saveAndRead(tab,plan,context,local);
  assert.equal(saved.revisited_after_save,true);
  assert.deepEqual(saved.page.state_metadata,state);
  const restored=await api.restore(tab,plan,[{field_key:f.key,value:original}],context);
  assert.equal(restored.page.fields.find(x=>x.key===f.key).value,original);
  assert.deepEqual(restored.page.state_metadata,state);
  assert.equal(calls.filter(c=>c==='save').length,2);
});

for(const change of ['unknown_field','wrong_label','essay_control','different_page','frame','collection']) {
  test(`UC ${change} stops before input or draft-save`,async()=>{
    const {page,plan,context,calls,tab,api}=port();
    if(change==='unknown_field')page.fields.push({...page.fields[0],key:'i:new',name:'unknown'});
    if(change==='wrong_label')page.fields[0].label='Parent first name *';
    if(change==='essay_control')page.fields[0].control='textarea';
    if(change==='different_page')page.url=page.url.replace('accountPersonal','bioFamily');
    if(change==='frame')page.frames_present=true;
    if(change==='collection')page.collections=[{kind:'editable_table'}];
    await assert.rejects(api.apply(tab,plan,context));
    assert.deepEqual(calls,[]);
  });
}

for(const change of ['journal','plan','observation','state_hash','current_status','section_status','other_term','submitted']) {
  test(`UC ${change} cannot bypass preparation evidence`,async()=>{
    const {state,plan,context,calls,tab,api}=port();
    if(change==='journal')context.journal_persisted=false;
    if(change==='plan')plan.ready=false;
    if(change==='observation')plan.observation_sha256='0'.repeat(64);
    if(change==='state_hash')context.restoration_strategy.baseline_state_sha256='0'.repeat(64);
    if(change==='current_status')state.sections[0].pages[0].label='To do Personal information';
    if(change==='section_status')state.sections[0].completion_text='';
    if(change==='other_term')state.term='Fall quarter/semester 2028';
    if(change==='submitted')state.draft_marker='Submitted application';
    await assert.rejects(api.apply(tab,plan,context));
    assert.equal(calls.filter(c=>['input','save'].includes(c)).length,0);
  });
}

test('a stale or mislabeled save action cannot be activated',async()=>{
  const {page,plan,context,calls,tab,api}=port();
  const local=await api.apply(tab,plan,context);
  page.actions.find(a=>a.key==='i:save').label='Start submission';
  plan.structure_sha256=host.digest(host.structure(page));
  await assert.rejects(api.saveAndRead(tab,plan,context,local),/observed_uc_draft_save_required/);
  assert.equal(calls.filter(c=>c==='save').length,0);
});

test('another page completion change remains visible during recovery',async()=>{
  const {state,plan,context,tab,api}=port();
  state.sections.at(-1).pages[0].label='Edit Introduction';
  await assert.rejects(api.apply(tab,plan,context),/observed_uc_restoration_evidence_required/);
  const result=await api.restore(tab,plan,[],context);
  assert.equal(result.page.state_metadata.sections.at(-1).pages[0].label,'Edit Introduction');
  assert.equal(result.restore_save_performed,false);
});

test('duplicate child page routes do not collapse into one completion state',async()=>{
  const {state,tab,api}=port();
  state.sections[0].pages.push(structuredClone(state.sections[0].pages[0]));
  await assert.rejects(api.observe(tab),/observed_uc_review_state_required/);
});

test('a conditional answer is refused before changing the first value',async()=>{
  const {page,plan,context,calls,tab,api}=port(),f=page.fields.find(f=>f.name==='hasLivedName');
  plan.writes=[{field_key:f.key,value:f.options.find(o=>o.label==='Yes').value}];
  await assert.rejects(api.apply(tab,plan,context),/uc_personal_conditional_answers_require_handoff/);
  assert.equal(calls.filter(c=>c==='input').length,0);
});

test('source-backed city reapplication handles the actual country-change reset before saving',async()=>{
  const {page,plan,context,tab,api}=port({countryClearsCity:true});
  const country=page.fields.find(f=>f.name==='birthCountryCode'),city=page.fields.find(f=>f.name==='birthCity');
  city.value='Synthetic City';plan.observation_sha256=host.digest({...page,state_metadata:stateFixture});
  plan.writes=[{field_key:country.key,value:country.options.find(o=>o.label==='Canada').value},{field_key:city.key,value:city.value}];
  plan.expected_values_sha256=host.digest({...vals(page),[country.key]:plan.writes[0].value});
  const local=await api.apply(tab,plan,context);
  assert.equal(local.fields.find(f=>f.key===city.key).value,'Synthetic City');
  assert.equal((await api.saveAndRead(tab,plan,context,local)).revisited_after_save,true);
});

test('an unexpected country reset stops save, then unsaved recovery repairs before navigating',async()=>{
  const {page,state,plan,context,tab,api,calls}=port({countryClearsCity:true});
  const country=page.fields.find(f=>f.name==='birthCountryCode'),city=page.fields.find(f=>f.name==='birthCity');
  city.value='Synthetic City';const original=vals(page);
  plan.observation_sha256=host.digest({...page,state_metadata:state});
  const value=country.options.find(o=>o.label==='Canada').value;
  plan.writes=[{field_key:country.key,value}];plan.expected_values_sha256=host.digest({...original,[country.key]:value});
  await assert.rejects(api.apply(tab,plan,context),/unexpected_uc_page_after_input/);
  assert.equal(calls.filter(c=>c==='save').length,0);
  const beforeRecovery=calls.length;
  const result=await api.restore(tab,plan,[{field_key:country.key,value:original[country.key]},{field_key:city.key,value:original[city.key]}],context,
    {unsaved:true,original_state_metadata:state,original_values_sha256:host.digest(original)});
  assert.deepEqual(calls.slice(beforeRecovery,beforeRecovery+2),['input','input']);
  assert.deepEqual(vals(result.page),original);
  assert.equal(result.recovered_before_save,true);
  assert.equal(calls.filter(c=>c==='save').length,0);
});
