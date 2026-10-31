import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {contracts,createUcFactual} from '../skills/bc-application/scripts/uc_factual.mjs';
const initial=JSON.parse(await readFile(new URL('./fixtures/uc_review_state.json',import.meta.url),'utf8'));
const origin='https://apply.universityofcalifornia.edu',vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

function port(kind) {
  const spec=contracts.find(s=>s.kind===kind),calls=[],state=structuredClone(initial),page={schema:'observed-page/1',
    url:origin+spec.path,title:spec.title,frames_present:false,fields:[],actions:[{key:'i:save',label:'Save & continue',selector:'[id="save"]',disabled:false}]};
  for(const expected of spec.fields) {
    const {key,control}=expected,options=['1','2'].map(v=>({label:'Synthetic '+v,value:v,disabled:false,
      ...(control==='radio'?{selector:`[id="synthetic-${key.slice(2)}-${v}"]`}:{})}));
    page.fields.push({...expected,name:key.slice(2),selector:control==='radio'?options[0].selector:`[id="${key.slice(2)}"]`,
      options:['radio','select'].includes(control)?options:[],value:control==='checkbox'?false:'1',disabled:false,readonly:false,invalid:false});
  }
  state.page_url=page.url;const section=state.sections.find(s=>s.label===spec.section);section.completion_text='Section Complete';
  section.pages.find(p=>p.href===spec.path).label=spec.review_label;
  let url=page.url,expanded=false;
  const locator=selector=>({count:async()=>1,waitFor:async()=>{},click:async()=>{
    assert.equal(selector,'[id="save"]');calls.push('save');url=origin+'/my-application/next';
  },press:async()=>{
    if(selector===`[role="button"][href=${JSON.stringify(spec.path)}]`){calls.push('open');url=page.url;}
    else throw Error('unknown selector');
  },selectOption:async o=>{calls.push('input');page.fields.find(f=>f.selector===selector).value=o.value;},
  fill:async value=>{calls.push('input');page.fields.find(f=>f.selector===selector).value=value;},
  check:async()=>{calls.push('input');const f=page.fields.find(f=>f.options.some(o=>o.selector===selector));f.value=f.options.find(o=>o.selector===selector).value;}});
  const tab={url:async()=>url,playwright:{locator,domSnapshot:async()=>'',expectNavigation:async f=>f(),
    waitForURL:async expected=>assert.equal(url,expected),getByRole:(r,o)=>({waitFor:async()=>{},
      count:async()=>o.name==='Expand all'?Number(!expanded):1,click:async()=>{expanded=true;},press:async()=>{
        if(o.name==='Review & submit')url=state.review_url;
        else if(o.name==='Application status')url=state.status_url;
        else if(o.name===state.term){url=state.review_url;expanded=false;}
        else throw Error('unexpected navigation');
      }}),evaluate:async()=>url===state.review_url?{term:state.term,sections:structuredClone(state.sections)}:
        url===state.status_url?{term:state.term,draft_marker:state.draft_marker}:['/my-application/reviewSubmit','/my-application/appStatus']}};
  const api=createUcFactual({...host,observe:async()=>structuredClone(page)},kind),observed={...api.decorate(page),state_metadata:state};
  const context={browser_family:'edge',transport:'extension',origin,access_verified:true,journal_persisted:true,
    real_account_test:true,full_state_restoration_verified:true,restoration_strategy:{kind:'restore_uc_factual',
      page_url:page.url,baseline_state_sha256:host.digest(state),review_label:spec.review_label,section:spec.section}};
  const field=page.fields.find(f=>f.required),plan={system:'uc',ready:true,allowed_origin:origin,page_url:page.url,
    observation_sha256:host.digest(observed),structure_sha256:host.digest(host.structure(observed)),
    expected_values_sha256:host.digest({...vals(page),[field.key]:'2'}),writes:[{field_key:field.key,value:'2'}],save_action:page.actions[0]};
  return {api,context,page,state,plan,tab,calls,field};
}

for(const {kind} of contracts) {
  test(`UC ${kind} uses whole-page save, observed review route and exact restoration`,async()=>{
    const {api,context,page,state,plan,tab,calls,field}=port(kind),original=vals(page);
    const local=await api.apply(tab,plan,context),saved=await api.saveAndRead(tab,plan,context,local);
    assert.equal(saved.page.fields.find(f=>f.key===field.key).value,'2');assert.deepEqual(saved.page.state_metadata,state);
    const restored=await api.restore(tab,plan,[{field_key:field.key,value:'1'}],context);
    assert.deepEqual(vals(restored.page),original);assert.equal(calls.filter(c=>c==='save').length,2);
  });
}

for(const change of ['new_field','wrong_label','duplicate_selector','wrong_route','collection','missing_journal','stale_plan']) {
  test(`UC factual ${change} stops before any write`,async()=>{
    const {api,context,page,plan,tab,calls}=port('ielts');
    if(change==='new_field')page.fields.push({...page.fields[0],key:'i:new'});
    if(change==='wrong_label')page.fields[0].label='New question';
    if(change==='duplicate_selector')page.fields[0].selector_count=2;
    if(change==='wrong_route')page.url+='&other=1';
    if(change==='collection')page.collections=[{kind:'editable_table'}];
    if(change==='missing_journal')context.journal_persisted=false;
    if(change==='stale_plan')plan.observation_sha256='0'.repeat(64);
    await assert.rejects(api.apply(tab,plan,context));assert.equal(calls.filter(c=>['input','save'].includes(c)).length,0);
  });
}
