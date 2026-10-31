// Pure host-port safety tests. No browser, network or applicant file access.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {digest,structure,saveAndRead,restore,inspectOptions,applyWrites,normalizeCommonAppRadios} from '../skills/bc-application/scripts/host_browser.mjs';

const fixture=JSON.parse(await readFile(new URL('./fixtures/mit_coursework_page.json',import.meta.url),'utf8'));
const commonFixture=JSON.parse(await readFile(new URL('./fixtures/common_app_personal_page.json',import.meta.url),'utf8'));
const context={browser_family:'chrome',transport:'extension',origin:'http://127.0.0.1:8765',
  synthetic_test:true,access_verified:true,journal_persisted:true};

for(const path of ['bioHousehold','campusMap','campusmajor','apply-scholarships','support-programs']) {
  test(`unverified UC ${path} cannot save through a fabricated empty plan`,async()=>{
    const p=page();p.url='https://apply.universityofcalifornia.edu/my-application/'+path;p.fields=[];
    const {tab,plan,calls}=port(p);plan.system='uc';plan.allowed_origin='https://apply.universityofcalifornia.edu';
    const ctx={...context,origin:plan.allowed_origin,synthetic_test:false};
    await assert.rejects(saveAndRead(tab,plan,ctx),/observed_uc_page_contract_required/);
    await assert.rejects(applyWrites(tab,{...plan,writes:[],observation_sha256:digest(p)},ctx),/observed_uc_page_contract_required/);
    assert.deepEqual(calls,[]);
  });
}

function port(page) {
  const calls=[];
  const click=async()=>{calls.push('save');};
  const tab={
    playwright:{evaluate:async()=>structuredClone(page),locator:()=>({click,waitFor:async()=>{}}),
      getByRole:()=>({click}),domSnapshot:async()=>''},
    url:async()=>page.url,reload:async()=>{calls.push('revisit');}
  };
  const plan={ready:true,system:'mit',allowed_origin:'https://apply.mitadmissions.org',page_url:page.url,
    structure_sha256:digest(structure(page)),
    expected_values_sha256:digest(Object.fromEntries(page.fields.map(f=>[f.key,f.value]))),
    save_action:page.actions[0]};
  return {tab,plan,calls};
}

for(const path of ['7/250','4/22','4/197','13/54','2/2','5/30']) {
  test(`uncontracted Common App ${path} cannot input/save an empty fabricated plan`,async()=>{
    const p=structuredClone(commonFixture);p.url='https://apply.commonapp.org/common/'+path;p.fields=[];
    const {tab,plan,calls}=port(p);plan.system='common_app';plan.allowed_origin='https://apply.commonapp.org';
    const ctx={...context,origin:plan.allowed_origin,synthetic_test:false};
    await assert.rejects(saveAndRead(tab,plan,ctx),/observed_common_app_page_contract_required/);
    await assert.rejects(applyWrites(tab,{...plan,writes:[],observation_sha256:digest(p)},ctx),/observed_common_app_page_contract_required/);
    assert.deepEqual(calls,[]);
  });
}

function page() {
  const result=structuredClone(fixture);
  result.url='http://127.0.0.1:8765/mit_coursework.html';
  return result;
}

function commonRadioPage() {
  const p=structuredClone(commonFixture);
  p.url='http://127.0.0.1:8765/common/3/11';
  p.fields.forEach(f=>{f.invalid=false;});
  return normalizeCommonAppRadios(p);
}

test('Common App question IDs survive regenerated group names while full observations detect staleness',async()=>{
  const p=commonRadioPage(),{tab,plan,calls}=port(p);plan.system='common_app';
  plan.save_action=p.actions.find(a=>a.key==='i:sectionContinue11');
  const before=structuredClone(p);
  tab.reload=async()=>{calls.push('revisit');p.fields.filter(f=>f.control==='radio').forEach((f,i)=>{f.name=`mat-radio-group-${i+12}`;});};
  const result=await saveAndRead(tab,plan,context);
  assert.notEqual(digest(before),digest(result.page));
  assert.equal(digest(structure(before)),digest(structure(result.page)));
  assert.deepEqual(before.fields.map(f=>[f.key,f.value]),result.page.fields.map(f=>[f.key,f.value]));
  await assert.rejects(applyWrites(tab,{...plan,observation_sha256:digest(before),writes:[]},context),/page_changed_since_preparation/);
  assert.deepEqual(calls,['save','revisit']);
});

for(const change of ['option_id','option_label','option_value','multiplicity','different_page']) {
  test(`stable radio normalization preserves rejection of ${change}`,async()=>{
    const p=commonRadioPage(),{tab,plan,calls}=port(p);plan.system='common_app';
    plan.save_action=p.actions.find(a=>a.key==='i:sectionContinue11');
    const f=p.fields.find(f=>f.control==='radio');
    if(change==='option_id')f.options[1].selector='[id="option_ques_1975_9999-input"]';
    if(change==='option_label')f.options[1].label='Different factual choice';
    if(change==='option_value')f.options[1].value='9999';
    if(change==='multiplicity')f.options[1].selector_count=2;
    if(change==='different_page')p.url='http://127.0.0.1:8765/common/5/1';
    await assert.rejects(saveAndRead(tab,plan,context),/prepared_page_structure_required|observed_radio_identity_invalid/);
    assert.deepEqual(calls,[]);
  });
}

test('duplicate stable question IDs remain ambiguous rather than merging answers',()=>{
  const p=commonRadioPage(),f=structuredClone(p.fields.find(f=>f.control==='radio'));
  f.name='mat-radio-group-99';f.key='n:mat-radio-group-99';p.fields.push(f);
  assert.throws(()=>normalizeCommonAppRadios(p),/ambiguous_observed_controls/);
});

test('untouched empty observed MIT notes permit factual draft save and revisit',async()=>{
  const p=page(),{tab,plan,calls}=port(p);
  const result=await saveAndRead(tab,plan,context);
  assert.deepEqual(calls,['save','revisit']);
  assert.equal(result.revisited_after_save,true);
  assert.deepEqual(result.page.fields.filter(f=>f.control==='textarea').map(f=>f.value),['','']);
});

for (const change of ['existing_note','required_note','unknown_note','other_page','common_app']) {
  test(`save backstop refuses ${change} even with a matching fabricated plan`,async()=>{
    const p=page();
    if(change==='existing_note')p.fields[0].value='Existing synthetic note';
    if(change==='required_note')p.fields[0].required=true;
    if(change==='unknown_note')p.fields[0].label='Other narrative';
    if(change==='other_page')p.title='Personal information';
    const {tab,plan,calls}=port(p);
    if(change==='common_app')plan.system='common_app';
    await assert.rejects(saveAndRead(tab,plan,context),/manual_page_save_excluded/);
    assert.deepEqual(calls,[]);
  });
}

test('an untouched consent field cannot be transmitted by a draft save',async()=>{
  const p=page();p.fields.push({key:'i:consent',name:'consent',label:'I have read and agree',group:'',
    control:'checkbox',value:false,options:[],required:false,disabled:false,readonly:false,invalid:false});
  const {tab,plan,calls}=port(p);
  await assert.rejects(saveAndRead(tab,plan,context),/manual_page_save_excluded/);
  assert.deepEqual(calls,[]);
});

for(const label of ['I authorize the University of California to share my contact information.',
    "I authorize the University of California to share my parent's contact information.",
    'I authorise text messages and accept responsibility for any charges incurred.']) {
  test('an actual-style authorization cannot be submitted by a factual draft save: '+label,async()=>{
    const p=page();p.fields.push({key:'i:authorization',name:'authorization',label,group:'',control:'checkbox',
      value:false,options:[],required:false,disabled:false,readonly:false,invalid:false});
    const {tab,plan,calls}=port(p);await assert.rejects(saveAndRead(tab,plan,context),/manual_page_save_excluded/);
    assert.deepEqual(calls,[]);
  });
}

test('a fabricated ready plan cannot save contradictory optional and required signals',async()=>{
  const p=page();p.fields=[{key:'i:preferred',name:'preferred',label:'Preferred Last Nameoptional',
    group:'',control:'text',value:'Invented',options:[],required:true,disabled:false,readonly:false,invalid:false}];
  const {tab,plan,calls}=port(p);
  await assert.rejects(saveAndRead(tab,plan,context),/conflicting_required_signals/);
  assert.deepEqual(calls,[]);
});

test('a record summary cannot be written or saved through a fabricated ready plan',async()=>{
  const p=page();p.fields=[];p.collections=[{kind:'editable_table',label:'School Name | School Country',row_count:2,editor_control_count:3}];
  const {tab,plan,calls}=port(p);
  await assert.rejects(applyWrites(tab,{...plan,observation_sha256:digest(p),writes:[]},context),/repeatable_record_editors_not_supported/);
  await assert.rejects(saveAndRead(tab,plan,context),/repeatable_record_editors_not_supported/);
  assert.deepEqual(calls,[]);
});

test('a note changed after preparation stops before save and preserves caller recovery',async()=>{
  const p=page(),{tab,plan,calls}=port(p);
  p.fields[0].value='Unexpected synthetic note';
  await assert.rejects(saveAndRead(tab,plan,context),/unexpected_page_values_before_save/);
  assert.deepEqual(calls,[]);
});

for (const system of ['uc','mit','common_app']) {
  test(`${system} factual legal-name-only port remains eligible for draft save`,async()=>{
    const p=JSON.parse(await readFile(new URL(`./fixtures/${system}_personal_page.json`,import.meta.url),'utf8'));
    p.url='http://127.0.0.1:8765/personal';
    const {tab,plan,calls}=port(p);plan.system=system;
    plan.save_action=p.actions.find(a=>system==='common_app' ? a.key==='i:sectionContinue11' : /^save/i.test(a.label));
    // Isolate the manual-content backstop with a name-only invented page.
    // The actual MIT full page has contradictory optional/required signals.
    p.fields=p.fields.filter(f=>/^(?:First\/Given name|Legal First\(Given\)|First name)\s*\*?$/.test(f.label));
    assert.equal(p.fields.length,1);
    p.fields.forEach(f=>{f.invalid=false;});
    plan.structure_sha256=digest(structure(p));
    plan.expected_values_sha256=digest(Object.fromEntries(p.fields.map(f=>[f.key,f.value])));
    await saveAndRead(tab,plan,context);
    assert.deepEqual(calls,['save','revisit']);
  });
}

test('real save cannot be authorized by a restoration boolean alone',async()=>{
  const p=page(),{tab,plan,calls}=port(p);
  await assert.rejects(saveAndRead(tab,plan,{...context,real_account_test:true,
    full_state_restoration_verified:true}),/observed_completed_page_restoration_evidence_required/);
  assert.deepEqual(calls,[]);
});

test('status drift stops a normal save but permits recovery followed by core verification',async()=>{
  const p=page();p.state_metadata={schema:'observed-state/1',coverage:'common_app_visible_navigation',
    current_page_key:'tertiaryNavItem3_11',items:[{key:'tertiaryNavItem3_11',status:'complete'}]};
  const ctx={...context,real_account_test:true,full_state_restoration_verified:true,
    restoration_strategy:{kind:'restore_completed_native_page',current_page_key:'tertiaryNavItem3_11',
      baseline_state_sha256:digest(p.state_metadata)}};
  p.state_metadata.items[0].status='in progress';
  const {tab,plan,calls}=port(p);
  await assert.rejects(saveAndRead(tab,plan,ctx),/observed_completed_page_restoration_evidence_required/);
  const result=await restore(tab,plan,[],ctx);
  assert.deepEqual(calls,['save','revisit']);
  assert.equal(result.page.state_metadata.items[0].status,'in progress');
  // Host readback is not a restoration-success claim; Python must compare the
  // captured original statuses and retain the journal while this differs.
});

test('readback waits for status hydration after the native fields are already present',async()=>{
  const p=page();p.state_metadata={schema:'observed-state/1',coverage:'common_app_visible_navigation',
    current_page_key:'tertiaryNavItem3_11',items:[{key:'secondaryNavItem3',status:'complete'},
      {key:'tertiaryNavItem3_11',status:'complete'}]};
  const {tab,plan,calls}=port(p);let pending=false;const statusWaits=[];
  tab.reload=async()=>{calls.push('revisit');pending=true;};
  tab.playwright.evaluate=async()=>{const result=structuredClone(p);if(pending)delete result.state_metadata;return result;};
  tab.playwright.locator=selector=>({click:async()=>{calls.push('save');},waitFor:async()=>{
    if(selector.includes('.nav-item__status')) {statusWaits.push(selector);pending=false;}
  }});
  const result=await saveAndRead(tab,plan,context);
  assert.equal(statusWaits.length,2);
  assert.deepEqual(result.page.state_metadata,p.state_metadata);
  assert.deepEqual(calls,['save','revisit']);
});

for(const scenario of ['success','popup_error','changed_value']) {
  test(`custom choice inspection preserves state and closes popup: ${scenario}`,async()=>{
    const p=page();p.fields=[{key:'i:scale',name:'scale',label:'Transcript 1 Grading Scale',group:'',
      control:'unsupported',selector:'[id="scale"]',selector_count:1,selector_index:0,
      required:true,disabled:false,readonly:false,value:'Other',invalid:false,options:[]}];
    const {tab}=port(p),calls=[];
    tab.playwright.locator=()=>({count:async()=>1,
      evaluate:async()=>({tag:'MAT-SELECT',role:'combobox',expanded:'false'}),
      click:async()=>{calls.push('open');},press:async key=>{assert.equal(key,'Escape');calls.push('close');}});
    tab.playwright.evaluate=async(fn,label)=>{
      if(typeof label==='string') {
        if(scenario==='popup_error')throw Error('unique_observed_single_listbox_required');
        if(scenario==='changed_value')p.fields[0].value='1-100';
        return {schema:'observed-options/1',options:[{label:'Other',selected:true,disabled:false}]};
      }
      return structuredClone(p);
    };
    if(scenario==='success') {
      const result=await inspectOptions(tab,'i:scale');
      assert.equal(result.filling_supported,false);assert.equal(p.fields[0].value,'Other');
    } else await assert.rejects(inspectOptions(tab,'i:scale'),scenario==='popup_error' ?
      /unique_observed_single_listbox_required/ : /options_inspection_changed_page_state/);
    assert.deepEqual(calls,['open','close']);
  });
}
