import test from 'node:test';
import assert from 'node:assert/strict';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createGenericForms} from '../skills/bc-application/scripts/generic_forms.mjs';

function setup({conditional=false,dialog=false}={}){
  const calls=[];let url='https://invented-forms.invalid/intake',generation=0;
  const make=(label,control,value,group='')=>({key:'raw:'+label,name:'input_'+label,label,group,control,value,options:[],required:true,disabled:false,readonly:false,invalid:false,
    selector:`[id="f_${label.replaceAll(' ','_')}_${generation}"]`,selector_count:1,selector_index:0});
  const country=make('Country of residence','select','old-ca');country.options=[{value:'old-ca',label:'Canada',disabled:false},{value:'old-cn',label:'China',disabled:false}];
  let fields=[make('Official given names','text','Old name'),country,make('Course title','textarea','Old course','Course 1'),make('Original school mark','text','70','Course 1')];
  if(conditional)fields.push(make('Materials under another legal name','checkbox',false));
  let saved=structuredClone(fields);
  function raw(){return {schema:'observed-page/1',title:'Invented factual form',frames_present:false,fields:structuredClone(fields),
    actions:[{key:'raw-save',selector:`[id="save_${generation}"]`,label:'Save draft',disabled:false}],
    generic_form:{schema:'generic-form/1',scope:{selector:`[id="form_${generation}"]`,selector_count:1,selector_index:0},destination:{action:url,method:'post'},
      ...(dialog?{dialog:{name:'Institution record',selector:'#dialog',selector_count:1}}:{})},
    generic_context:{instructions:'Enter original school marks without conversion.'}};}
  function reidentify(){generation++;for(const [i,f]of fields.entries()){
    f.selector=`[id="new_${generation}_${i}"]`;f.name='new_name_'+generation+'_'+i;
    if(f.control==='select'){const label=f.options.find(o=>o.value===f.value)?.label;f.options.forEach((o,j)=>o.value='new_'+generation+'_'+j);f.value=f.options.find(o=>o.label===label)?.value||'';}
  }}
  const locator=selector=>({count:async()=>1,filter:()=>({waitFor:async()=>{}}),waitFor:async()=>{},
    fill:async value=>{fields.find(f=>f.selector===selector).value=value;calls.push('fill');},
    selectOption:async({value})=>{const f=fields.find(f=>f.selector===selector);assert.ok(f.options.some(o=>o.value===value));f.value=value;calls.push('select');},
    setChecked:async value=>{const f=fields.find(f=>f.selector===selector);f.value=value;calls.push('checkbox');
      if(conditional&&value&&!fields.some(f=>f.label==='Former legal name'))fields.push(make('Former legal name','text',''));},
    click:async()=>{assert.equal(selector,`[id="save_${generation}"]`);saved=structuredClone(fields);calls.push('save');}});
  const tab={url:async()=>url,goto:async u=>{url=u;fields=structuredClone(saved);reidentify();calls.push('revisit');},
    reload:async()=>{fields=structuredClone(saved);reidentify();calls.push('reload');},playwright:{evaluate:async()=>raw(),locator,domSnapshot:async()=>''}};
  const context={browser_family:'edge',transport:'extension',origin:url.split('/').slice(0,3).join('/'),access_verified:true,
    target_id:'target:invented',application_authorized:true,authorized_origin:url.split('/').slice(0,3).join('/'),journal_persisted:true};
  async function planned(){const page=await host.observe(tab,{generic_form:true}),desired=Object.fromEntries(page.fields.map(f=>[f.key,f.value]));
    const bindings=page.fields.map(f=>({key:f.key,role:'factual',ref:f.label==='Course title'?'psr:synthetic:description':'personal.legal_given_name',purpose:f.label==='Course title'?'academic_name':'fact'}));
    for(const f of page.fields){if(f.control==='text')desired[f.key]=f.label==='Original school mark'?'97':'Synthetic';
      if(f.control==='select')desired[f.key]=f.options.find(o=>o.label==='China').value;
      if(f.control==='textarea')desired[f.key]='ORIGINAL PSR COURSE';
      if(f.control==='checkbox')desired[f.key]=true;}
    const plan={ready:true,target_id:context.target_id,system:'web',allowed_origin:context.origin,page_url:await tab.url(),
      generic_form:page.generic_form,semantic_bindings:bindings,save_action:page.actions[0],observation_sha256:host.digest(page),
      structure_sha256:host.digest(host.structure(page)),expected_values_sha256:host.digest(desired),writes:page.fields.filter(f=>desired[f.key]!==f.value).map(f=>({field_key:f.key,value:desired[f.key],fact_ref:bindings.find(b=>b.key===f.key).ref}))};
    return {page,plan,desired};
  }
  return {api:createGenericForms(host,{dialog}),tab,context,calls,planned,fields,raw};
}

test('generic native form uses live native choices and verifies across entirely new IDs/values',async()=>{
  const s=setup(),{page,plan}=await s.planned();assert.equal((await s.api.apply(s.tab,plan,s.context)).status,'filled');
  const saved=await s.api.saveAndRead(s.tab,plan,s.context);
  assert.equal(host.digest(Object.fromEntries(saved.page.fields.map(f=>[f.key,f.value]))),plan.expected_values_sha256);
  assert.equal(host.digest(host.structure(saved.page)),plan.structure_sha256);assert.notEqual(saved.page.fields[0].selector,page.fields[0].selector);
  assert.equal(s.calls.filter(c=>c==='save').length,1);
});

test('explicit skip-readback save returns a bound receipt without reload or independent read',async()=>{
  const s=setup(),{plan}=await s.planned();await s.api.apply(s.tab,plan,s.context);
  await assert.rejects(()=>s.api.saveAndContinue(s.tab,plan,s.context),/explicit_readback_opt_out/);
  plan.saved_page_readback=false;
  const receipt=await s.api.saveAndContinue(s.tab,plan,s.context);
  assert.equal(receipt.save_performed,true);assert.equal(receipt.revisited_after_save,false);
  assert.equal(receipt.expected_values_sha256,plan.expected_values_sha256);
  assert.equal(receipt.save_action_key,plan.save_action.key);assert.equal(receipt.page_url,plan.page_url);
  assert.equal(s.calls.filter(c=>c==='save').length,1);assert.equal(s.calls.includes('reload'),false);assert.equal(s.calls.includes('revisit'),false);
});

test('new conditional question stops remaining input and any Save until remapped',async()=>{
  const s=setup({conditional:true}),{plan}=await s.planned();const result=await s.api.apply(s.tab,plan,s.context);
  assert.equal(result.status,'page_changed');assert.ok(result.page.fields.some(f=>f.label==='Former legal name'));assert.equal(s.calls.includes('save'),false);
  await assert.rejects(()=>s.api.saveAndRead(s.tab,plan,s.context));assert.equal(s.calls.includes('save'),false);
});

test('unsaved cancellation restores semantic values despite changed implementation IDs',async()=>{
  const s=setup(),{page,plan}=await s.planned();await s.api.apply(s.tab,plan,s.context);
  const canceled=await s.api.cancelUnsaved(s.tab,plan,s.context);assert.equal(canceled.revisited_saved_draft,true);
  assert.deepEqual(Object.fromEntries(canceled.page.fields.map(f=>[f.key,f.value])),Object.fromEntries(page.fields.map(f=>[f.key,f.value])));
  assert.equal(s.calls.includes('save'),false);
});

for(const change of ['journal','target','origin','authorization','stale','missing_binding','essay_textarea','final_save','real_test'])test(`${change} cannot authorize generic writes or Save`,async()=>{
  const s=setup(),{plan}=await s.planned();
  if(change==='journal')s.context.journal_persisted=false;
  if(change==='target')s.context.target_id='target:other';
  if(change==='origin')s.context.authorized_origin='https://other.invalid';
  if(change==='authorization')s.context.application_authorized=false;
  if(change==='stale')s.fields[0].value='Changed after plan';
  if(change==='missing_binding')plan.semantic_bindings=[];
  if(change==='essay_textarea')plan.semantic_bindings.find(b=>b.purpose==='academic_name').ref='education.some_arbitrary_text';
  if(change==='final_save'){await s.api.apply(s.tab,plan,s.context);plan.save_action={...plan.save_action,label:'Submit application'};}
  if(change==='real_test')s.context.real_account_test=true;
  if(change==='final_save')await assert.rejects(()=>s.api.saveAndRead(s.tab,plan,s.context));
  else await assert.rejects(()=>s.api.apply(s.tab,plan,s.context));
  assert.equal(s.calls.includes('save'),false);
});

test('generic native contracts cannot be driven through legacy generic applyWrites',async()=>{
  const s=setup(),{plan}=await s.planned();await assert.rejects(()=>host.applyWrites(s.tab,plan,s.context),/dedicated_generic/);assert.equal(s.calls.length,0);
});

test('new duplicate labels use live layout context and uniquely witnessed earlier option catalogues',()=>{
  const make=(options,context_anchor)=>({label:'Province *',group:'',control:'select',required:true,readonly:false,disabled:false,
    options:options.map(label=>({label,disabled:false})),context_anchor});
  const old=make(['Alberta','British Columbia'],'Current country *');
  const added=make(['Anhui','Jiangsu'],'Correspondence country *');
  const first=host.genericFieldIdentities([old,added],[old]);
  assert.equal(first[0].group,'');assert.equal(first[1].group,'Following: Correspondence country *');
  const restarted=host.genericFieldIdentities([added,old],first);
  assert.equal(restarted[0].group,first[1].group);assert.equal(restarted[1].group,first[0].group);
  const ambiguous=host.genericFieldIdentities([old,{...old}],[old]);
  assert.equal(ambiguous[0].group,ambiguous[1].group); // Observer rejects the resulting duplicate keys.
});

test('branch plans cannot call the Save capability',async()=>{
  const s=setup(),{plan}=await s.planned();plan.generic_stage=true;
  await assert.rejects(()=>s.api.saveAndRead(s.tab,plan,s.context),/branch_discovery/);
  assert.equal(s.calls.includes('save'),false);
});

test('identical option catalogues keep their layout identity when one branch disappears',()=>{
  const make=anchor=>({label:'City *',group:'',control:'select',required:true,readonly:false,disabled:false,
    options:[{label:'Example City',disabled:false}],context_anchor:anchor});
  const known=host.genericFieldIdentities([make('Residence country'),make('Mailing country')]);
  assert.notEqual(known[0].group,known[1].group);
  const remaining=host.genericFieldIdentities([make('Mailing country')],known);
  assert.equal(remaining[0].group,known[1].group);
  const restored=host.genericFieldIdentities([make('Mailing country'),make('Residence country')],known);
  assert.deepEqual(restored.map(f=>f.group),[known[1].group,known[0].group]);
  const moved=host.genericFieldIdentities([make('Different country')],[known[1]]);
  assert.notEqual(moved[0].group,known[1].group);
});

for(const dialog of [false,true])for(const failure of ['validation','no_advance'])test(`failed asynchronous ${failure} preserves the ${dialog?'dialog':'page'} without a reload`,async()=>{
  const s=setup({dialog}),{plan}=await s.planned();await s.api.apply(s.tab,plan,s.context);
  const originalEvaluate=s.tab.playwright.evaluate;
  const originalLocator=s.tab.playwright.locator;
  s.tab.playwright.evaluate=async(fn,arg)=>{
    if(String(fn).includes('.ui-message-error'))return failure==='validation'?['Unresolved website validation']:[];
    return originalEvaluate(fn,arg);
  };
  if(failure==='no_advance'){
    // Keep all observed actions in the page; the sole draft action advances.
    const raw=s.raw;
    s.tab.playwright.evaluate=async(fn,arg)=>{
      if(String(fn).includes('.ui-message-error'))return [];
      const p=await originalEvaluate(fn,arg);
      if(p?.schema==='observed-page/1')p.actions[0].label='Save and Next';
      return p;
    };
    const observed=await s.api.observe(s.tab);
    plan.save_action=observed.actions[0];plan.structure_sha256=host.digest(host.structure(observed));
    s.tab.playwright.locator=selector=>({...originalLocator(selector),waitFor:async options=>{
      if(options.state==='hidden')throw Error('form did not advance');
    }});
  }
  await assert.rejects(()=>dialog?s.api.saveDraft(s.tab,plan,s.context):s.api.saveAndRead(s.tab,plan,s.context),failure==='validation'?/validation_feedback/:/did_not_advance/);
  assert.equal(s.calls.filter(c=>c==='save').length,1);
  assert.equal(s.calls.includes('reload')||s.calls.includes('revisit'),false);
});

for(const caption of ['Send invitation','Payment','Sign declaration'])test(`dialog caption ${caption} blocks input and draft Save`,async()=>{
  const s=setup({dialog:true}),original=s.tab.playwright.evaluate;
  s.tab.playwright.evaluate=async(fn,arg)=>{const p=await original(fn,arg);if(p?.generic_form)p.generic_form.dialog.name=caption;return p;};
  const {plan}=await s.planned();
  await assert.rejects(()=>s.api.apply(s.tab,plan,s.context),/manual_application_section/);
  assert.equal(s.calls.length,0);
  plan.expected_values_sha256=host.digest(Object.fromEntries((await s.api.observe(s.tab)).fields.map(f=>[f.key,f.value])));
  await assert.rejects(()=>s.api.saveDraft(s.tab,plan,s.context),/manual_page_save/);
  assert.equal(s.calls.length,0);
});

for(const failure of ['multiple_dialogs','unnamed','outside_form','two_owned_forms','duplicate_identity','iframe'])test(`dialog observation rejects ${failure} before reading or writing fields`,async()=>{
  const previousDocument=globalThis.document,previousStyle=globalThis.getComputedStyle;
  const element=(id,name)=>({id,getClientRects:()=>[{}],closest:()=>null,getAttribute:key=>key==='aria-label'?name:null});
  const outside=element('background',''),form=element('editor',''),dialog=element('record','Institution record');
  dialog.contains=e=>failure!=='outside_form'&&e!==outside;
  let forms=[outside,form],dialogs=[dialog];
  if(failure==='multiple_dialogs')dialogs.push(element('other','Other'));
  if(failure==='unnamed')dialog.getAttribute=()=>null;
  if(failure==='two_owned_forms')forms.push(element('extra',''));
  const doc={getElementById:()=>null,querySelector:selector=>selector==='iframe'&&failure==='iframe'?{}:null,
    querySelectorAll:selector=>selector==='form'?forms:selector==='[role=dialog]'?dialogs:selector==='iframe'?failure==='iframe'?[{}]:[]:
      selector==='[id="record"]'?failure==='duplicate_identity'?[dialog,dialog]:[dialog]:[]};
  try{
    globalThis.document=doc;globalThis.getComputedStyle=()=>({visibility:'visible'});
    const tab={playwright:{evaluate:async(fn,arg)=>fn(arg)}};
    await assert.rejects(()=>host.observe(tab,{generic_form:true,generic_dialog:true}),/unique_named_native_dialog|unique_dialog_owned_native_form|single_native_form/);
  }finally{globalThis.document=previousDocument;globalThis.getComputedStyle=previousStyle;}
});

test('native event reaffirmation uses only the uniquely owned current native option',async()=>{
  const s=setup(),{page}=await s.planned(),f=page.fields.find(f=>f.control==='select');
  f.widget={kind:'owned_native_select'};const calls=[];
  const control={count:async()=>1,selectOption:async option=>calls.push(['native',option.value])};
  const owner={count:async()=>1,evaluate:async(fn,option)=>{assert.equal(option.native_value,f.options.find(o=>o.value===f.value).native_value);calls.push(['check']);},
    locator:selector=>{assert.equal(selector,'select');return control;}};
  const tab={playwright:{locator:selector=>{assert.equal(selector,f.selector);return owner;},evaluate:async()=>[],domSnapshot:async()=>''}};
  await host.writeObserved(tab,page,[{field_key:f.key,value:f.value,native_event:true}]);
  assert.deepEqual(calls,[['check'],['native',f.options.find(o=>o.value===f.value).native_value]]);
  calls.length=0;
  await assert.rejects(()=>host.writeObserved(tab,page,[{field_key:f.key,value:f.options.find(o=>o.value!==f.value).value,native_event:true}]),/matching_owned_select/);
  assert.equal(calls.length,0);
  f.widget={kind:'unsupported'};
  await assert.rejects(()=>host.writeObserved(tab,page,[{field_key:f.key,value:f.value,native_event:true}]),/matching_owned_select/);
});

test('a dialog draft saves once and requires an independent saved editor read',async()=>{
  const s=setup({dialog:true}),{plan}=await s.planned();await s.api.apply(s.tab,plan,s.context);
  await assert.rejects(()=>s.api.saveAndRead(s.tab,plan,s.context),/independent_saved_reader/);
  assert.equal(s.calls.includes('save'),false);
  const receipt=await s.api.saveDraft(s.tab,plan,s.context);
  assert.deepEqual(receipt,{schema:'generic-draft-save/1',save_performed:true,revisited_after_save:false,verification_required:true,
    target_id:plan.target_id,page_url:plan.page_url,structure_sha256:plan.structure_sha256,
    expected_values_sha256:plan.expected_values_sha256,save_action_key:plan.save_action.key});
  assert.equal(s.calls.filter(c=>c==='save').length,1);
  assert.equal(s.calls.includes('reload')||s.calls.includes('revisit'),false);
  await assert.rejects(()=>s.api.cancelUnsaved(s.tab,plan,s.context),/independent_original_state/);
});

test('duplicate displayed options are disabled as ambiguous while distinct choices still work',async()=>{
  const s=setup(),country=s.fields.find(f=>f.control==='select');
  country.options.push({label:'Canada',value:'another_code',disabled:false});
  const {page,plan}=await s.planned(),observed=page.fields.find(f=>f.control==='select');
  assert.equal(observed.invalid,true);
  assert.equal(observed.options.filter(o=>o.label==='Canada').length,1);
  assert.deepEqual(observed.options.find(o=>o.label==='Canada').ambiguous,true);
  assert.equal(observed.options.find(o=>o.label==='Canada').disabled,true);
  assert.equal((await s.api.apply(s.tab,plan,s.context)).status,'filled');
  const saved=await s.api.saveAndRead(s.tab,plan,s.context);
  assert.equal(saved.page.fields.find(f=>f.control==='select').invalid,false);
});

test('record-summary identities and all cells survive regenerated selectors and stop changed rows',async()=>{
  const s=setup(),original=s.tab.playwright.evaluate,headers=['Institution','Dates','Action'],caption='Prior studies';let changed=false,generation=0;
  s.tab.playwright.evaluate=async(fn,arg)=>{const p=await original(fn,arg);if(p?.generic_form)p.generic_form.record_collections=[{
    headers,caption,rows:[[changed?'Different school':'Invented school','2021–2022','Action']],selector:'#records'+generation,selector_count:1}];return p;};
  const {page,plan}=await s.planned();const table=page.generic_form.record_collections[0];
  assert.equal(table.key,'rc:'+host.digest({headers,caption}).slice(0,24));
  generation++;assert.equal(host.digest(host.structure(await s.api.observe(s.tab))),plan.structure_sha256);
  changed=true;assert.notEqual(host.digest(host.structure(await s.api.observe(s.tab))),plan.structure_sha256);
  await assert.rejects(()=>s.api.apply(s.tab,plan,s.context),/page_changed_since_preparation/);assert.equal(s.calls.length,0);
});

test('identical summary headers and caption cannot select one of several record tables',async()=>{
  const s=setup(),original=s.tab.playwright.evaluate;
  s.tab.playwright.evaluate=async(fn,arg)=>{const p=await original(fn,arg);if(p?.generic_form)p.generic_form.record_collections=[0,1].map(i=>({headers:['Institution','Action'],caption:'Prior studies',rows:[['School '+i,'Action']],selector:'#records'+i,selector_count:1}));return p;};
  await assert.rejects(()=>s.api.observe(s.tab),/ambiguous_record_summary_identity/);assert.equal(s.calls.length,0);
});

test('bounded count input emits normal typing and blur, and rejects non-count values before input',async()=>{
  const s=setup(),{page}=await s.planned(),f=page.fields.find(f=>f.control==='text');const calls=[];
  const tab={playwright:{locator:()=>({count:async()=>1,fill:async v=>calls.push(['clear',v]),pressSequentially:async v=>calls.push(['type',v]),press:async v=>calls.push(['key',v])})}};
  await host.writeObserved(tab,page,[{field_key:f.key,value:'6',count_input:true}]);
  assert.deepEqual(calls,[['clear',''],['type','6'],['key','Tab']]);
  for(const value of ['-1','1000','06','some text']){
    calls.length=0;await assert.rejects(()=>host.writeObserved(tab,page,[{field_key:f.key,value,count_input:true}]),/bounded_native_count/);assert.equal(calls.length,0);
  }
});

test('a staged branch pauses when another existing field changes without a new question',async()=>{
  const s=setup(),{page,plan}=await s.planned(),original=s.tab.playwright.locator;
  const country=page.fields.find(f=>f.control==='select');plan.generic_stage=true;plan.save_action=null;
  plan.writes=plan.writes.filter(w=>w.field_key===country.key);
  plan.expected_values_sha256=host.digest({...Object.fromEntries(page.fields.map(f=>[f.key,f.value])),[country.key]:plan.writes[0].value});
  s.tab.playwright.locator=selector=>{const locator=original(selector);return {...locator,selectOption:async value=>{await locator.selectOption(value);s.fields.find(f=>f.control==='text').value='Website changed an existing answer';}};};
  const result=await s.api.apply(s.tab,plan,s.context);assert.equal(result.status,'page_changed');assert.equal(result.save_performed,false);
  assert.equal(s.calls.includes('save'),false);
});

test('derived percentage numeric input uses documented clipboard paste and blur events',async()=>{
  const s=setup(),{page}=await s.planned(),f=page.fields.find(f=>f.control==='text'),calls=[];
  const ref='psr-average:course-level-11:percent',binding={key:f.key,ref,role:'factual',format:'decimal_fixed_2'};
  let clipboard='',displayed='',accepted='';
  const tab={clipboard:{writeText:async text=>{clipboard=text;calls.push('clipboard');}},playwright:{locator:()=>({count:async()=>1,
    click:async()=>calls.push('focus'),press:async key=>{calls.push(key);if(key==='Control+V')displayed=clipboard;if(key==='Tab')accepted=displayed;}})}};
  await host.writeObserved(tab,page,[{field_key:f.key,value:'96.40',fact_ref:ref,numeric_input:true}],{semantic_bindings:[binding]});
  assert.equal(accepted,'96.40');assert.deepEqual(calls,['clipboard','focus','Control+A','Control+V','Tab']);
  for(const change of ['raw_mark','unbound','different_ref','wrong_format','rounding','above_scale']){
    calls.length=0;const w={field_key:f.key,value:'96.40',fact_ref:ref,numeric_input:true},b={...binding};
    if(change==='raw_mark'){w.fact_ref='psr:fictional:school_percent';b.ref=w.fact_ref;}
    if(change==='unbound')b.role='unsupported';if(change==='different_ref')b.ref+=':other';
    if(change==='wrong_format')b.format='identity';if(change==='rounding')w.value='96.405';if(change==='above_scale')w.value='100.01';
    await assert.rejects(()=>host.writeObserved(tab,page,[w],{semantic_bindings:[b]}),/source_bound_percentage/);assert.equal(calls.length,0);
  }
  delete tab.clipboard;
  await assert.rejects(()=>host.writeObserved(tab,page,[{field_key:f.key,value:'96.40',fact_ref:ref,numeric_input:true}],{semantic_bindings:[binding]}),/documented_browser_clipboard_required/);
});

test('a dispatched Save and Next can recover a read-only navigation receipt without another Save',async()=>{
  const s=setup(),{plan}=await s.planned();plan.saved_page_readback=false;plan.save_action.label='Save and Next';
  const context={...s.context,save_attempted:true};let evidence={one_form:true,form_id:'nextForm',success:true,errors:0},oldVisible=false;
  s.tab.playwright.locator=()=>({isVisible:async()=>oldVisible});
  s.tab.playwright.evaluate=async()=>evidence;
  const receipt=await host.recoverGenericNavigationReceipt(s.tab,plan,context);
  assert.equal(receipt.save_action_key,plan.save_action.key);assert.equal(receipt.revisited_after_save,false);
  assert.equal(receipt.verification_required,true);assert.equal(s.calls.length,0);
  evidence={...evidence,success:false};
  await assert.rejects(()=>host.recoverGenericNavigationReceipt(s.tab,plan,context),/observed_success/);
  assert.deepEqual(await host.recoverGenericNavigationReceipt(s.tab,plan,{...context,save_success_observed:true,observed_next_form_id:'nextForm'}),receipt);
  for(const patch of [{form_id:'loginForm',success:true},{one_form:false,success:true},{errors:1,success:true}]){
    evidence={one_form:true,form_id:'nextForm',success:true,errors:0,...patch};
    await assert.rejects(()=>host.recoverGenericNavigationReceipt(s.tab,plan,context),/observed_success/);
  }
  evidence={one_form:true,form_id:'nextForm',success:true,errors:0};oldVisible=true;
  await assert.rejects(()=>host.recoverGenericNavigationReceipt(s.tab,plan,context),/observed_saved_navigation/);
  oldVisible=false;
  for(const patch of [{save_attempted:false},{journal_persisted:false},{target_id:'other'}]){
    await assert.rejects(()=>host.recoverGenericNavigationReceipt(s.tab,plan,{...context,...patch}),/dispatched_generic/);
  }
  for(const patch of [{saved_page_readback:true},{generic_stage:true},{save_action:{...plan.save_action,label:'Save'}}]){
    await assert.rejects(()=>host.recoverGenericNavigationReceipt(s.tab,{...plan,...patch},context),/dispatched_generic/);
  }
  assert.equal(s.calls.length,0);
});
