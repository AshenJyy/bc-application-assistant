// Fictional in-memory host-port tests, no browser or applicant profile access.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createMitCoursework} from '../skills/bc-application/scripts/mit_coursework.mjs';

const fixture=JSON.parse(await readFile(new URL('./fixtures/mit_coursework_page.json',import.meta.url),'utf8'));
const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

function port() {
  const page=structuredClone(fixture),calls=[];
  page.collections=[{kind:'editable_table',label:'Subject Category | Year Taken | Level | Class Name | Grade Received',row_count:0,editor_control_count:1}];
  for(const f of page.fields.filter(f=>f.control==='select'))f.value=f.options.find(o=>['Taken','11th'].includes(o.label)).value;
  let url=page.url;
  const review={errors:[{section:'Essays',message:'Missing essay response(s)',href:'frm?00000000-0000-4000-8000-000000000000'}],warnings:[]};
  const state={schema:'observed-state/1',coverage:'mit_visible_review_and_draft',page_url:page.url,
    review_url:'https://apply.mitadmissions.org/apply/review',portal_url:'https://apply.mitadmissions.org/portal/apply',
    application_status:'In Progress',...structuredClone(review)};
  const context={browser_family:'edge',transport:'extension',origin:'https://apply.mitadmissions.org',access_verified:true,
    real_account_test:true,full_state_restoration_verified:true,journal_persisted:true,
    restoration_strategy:{kind:'restore_mit_coursework',page_url:page.url,baseline_state_sha256:host.digest(state)}};
  const plan={ready:true,system:'mit',allowed_origin:context.origin,page_url:page.url,
    collection_policy:{allowed:true,kind:'mit_non_us_empty_classes',fact_ids:['education.current_school_country','education.us_based_school_system']},
    observation_sha256:host.digest({...page,state_metadata:state}),structure_sha256:host.digest(host.structure(page)),
    expected_values_sha256:host.digest(vals(page)),save_action:page.actions[0],writes:[]};
  const locator=selector=>({count:async()=>1,waitFor:async()=>{},press:async key=>{
    assert.equal(key,'Enter');calls.push('save');url='https://apply.mitadmissions.org/apply/tes';},
    selectOption:async choice=>{calls.push('select');page.fields.find(f=>f.selector===selector).value=choice.value;}});
  const tab={url:async()=>url,goto:async dest=>{url=dest;calls.push('goto:'+new URL(dest).pathname);},
    reload:async()=>calls.push('reload'),playwright:{locator,getByRole:()=>locator('button'),domSnapshot:async()=>'',
      evaluate:async()=>{
        if(url.endsWith('/review'))return structuredClone(review);
        if(url.endsWith('/portal/apply'))return 'In Progress';
        return ['review','/portal/apply'];
      }}};
  const api=createMitCoursework({...host,observe:async()=>structuredClone(page)});
  return {api,tab,page,plan,context,calls,review};
}

test('eight native reaffirmations save, revisit, compare review and draft, then need no extra restoration save',async()=>{
  const {api,tab,page,plan,context,calls}=port();
  plan.writes=page.fields.filter(f=>f.control==='select').map(f=>({field_key:f.key,value:f.value}));
  const local=await api.apply(tab,plan,context);
  assert.equal(calls.filter(c=>c==='select').length,8);
  const saved=await api.saveAndRead(tab,plan,context,local);
  assert.equal(saved.revisited_after_save,true);
  assert.deepEqual(saved.page.fields,page.fields);
  assert.equal(saved.page.state_metadata.application_status,'In Progress');
  const restored=await api.restore(tab,plan,[],context);
  assert.equal(restored.restore_save_performed,false);
  assert.equal(calls.filter(c=>c==='save').length,1);
});

for(const change of ['row','other_table','instructions','subject_pair','unknown_control','nonempty_note','required_note']) {
  test(`the MIT port blocks unsupported ${change} before writes or saves`,async()=>{
    const {api,tab,page,plan,context,calls}=port();
    if(change==='row')page.collections[0].row_count=1;
    if(change==='other_table')page.collections[0].label='School Name';
    if(change==='instructions')page.mit_coursework.classes_instruction='All students';
    if(change==='subject_pair')page.mit_coursework.subject_year_pairs[0].year_key=page.mit_coursework.subject_year_pairs[1].year_key;
    if(change==='unknown_control')page.fields.push({...page.fields[0],key:'new'});
    if(change==='nonempty_note')page.fields[0].value='Fictional existing narrative';
    if(change==='required_note')page.fields[0].required=true;
    await assert.rejects(api.apply(tab,plan,context));
    assert.deepEqual(calls,[]);
  });
}

for(const change of ['policy','journal','state_hash','observation','essay_write']) {
  test(`prepared ${change} is checked before any MIT input`,async()=>{
    const {api,tab,page,plan,context,calls}=port();
    if(change==='policy')plan.collection_policy.kind='ignore_everything';
    if(change==='journal')context.journal_persisted=false;
    if(change==='state_hash')context.restoration_strategy.baseline_state_sha256='0'.repeat(64);
    if(change==='observation')plan.observation_sha256='0'.repeat(64);
    if(change==='essay_write')plan.writes=[{field_key:page.fields[0].key,value:'Fictional narrative'}];
    await assert.rejects(api.apply(tab,plan,context));
    assert.equal(calls.filter(c=>c==='select'||c==='save').length,0);
  });
}

test('an unexpected field after selecting retains caller recovery and never saves',async()=>{
  const {api,tab,page,plan,context,calls}=port();
  const f=page.fields.find(f=>f.control==='select');
  plan.writes=[{field_key:f.key,value:f.options.find(o=>o.label==='10th')?.value||f.options[2].value}];
  // The plan still expects the original value; any discrepancy stops save.
  await assert.rejects(api.apply(tab,plan,context),/unexpected_page_values_before_save/);
  assert.equal(calls.filter(c=>c==='save').length,0);
});

test('changed originals use the same protected draft-save and full status collection for recovery',async()=>{
  const {api,tab,page,plan,context,calls}=port();
  const year=page.fields.find(f=>f.label==='Year'),original=year.value;
  year.value=year.options.find(o=>o.label==='10th').value;
  const result=await api.restore(tab,plan,[{field_key:year.key,value:original}],context);
  assert.equal(result.revisited_after_save,true);
  assert.equal(year.value,original);
  assert.equal(calls.filter(c=>c==='save').length,1);
});

test('review status drift remains observable and cannot be hidden during recovery',async()=>{
  const {api,tab,plan,context,review}=port();
  review.errors[0].message='Changed missing response';
  await assert.rejects(api.apply(tab,plan,context),/observed_mit_restoration_evidence_required/);
  const result=await api.restore(tab,plan,[],context);
  assert.equal(result.page.state_metadata.errors[0].message,'Changed missing response');
});
