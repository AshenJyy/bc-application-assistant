// Entirely fictional school/course state; no account or browser network access.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createUcTermSetup} from '../skills/bc-application/scripts/uc_term_setup.mjs';

const load=async name=>JSON.parse(await readFile(new URL('./fixtures/'+name,import.meta.url),'utf8'));
const schoolFixture=await load('uc_school_terms_page.json'),courseFixture=await load('uc_courses_page.json');
const commentsFixture=await load('uc_empty_comments_page.json'),stateFixture=await load('uc_review_state.json');
const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
const annotate=b=>({...b.school,uc_school_terms:{schema:'uc-school-terms/1',identity_sha256:b.school_identity_sha256},state_metadata:b.state_metadata});

async function port(options={}) {
  const school=structuredClone(schoolFixture),comments=structuredClone(commentsFixture),state=structuredClone(stateFixture),calls=[];
  const origin=new URL(school.url).origin,summaryUrl=g=>origin+'/my-application/acadHistFrGrades/'+g;
  const editorUrl=g=>origin+'/my-application/acadHistFrHighSchoolClasses/editClasses/'+g+'/123456';
  state.page_url=school.url;let url=school.url,expanded=false,savedSchool=structuredClone(school.fields),warningModal=false;
  let identityText='Synthetic School School code: 424242',pendingDismiss=false;
  const alias=origin+'/my-application/acadHistFrInfo';
  const pages=Object.fromEntries(['09','10','11','12'].map(g=>[g,{...structuredClone(courseFixture),url:editorUrl(g)}]));
  for(const p of Object.values(pages))for(const k of Object.keys(p))if(k.startsWith('uc_'))delete p[k];
  const full=()=>school.fields.find(f=>f.key==='i:onefinal').value;
  const summary=g=>({heading:`${Number(g)}th grade`,school:'Synthetic School '+g,year:'2024 - 2025 academic year',
    lists:['Grading system:','0-100 (Canada - BC) BC Proficiency','Term system:',full()&&['09','10'].includes(g)?'Full year Semester':'Semester'],
    columns:courseFixture.uc_course_editor.columns,
    rows:[0,1].map(i=>{
      const get=suffix=>{const f=pages[g].fields.find(f=>f.key===`i:academics_hs_classes_add_${i}_${suffix}`);
        return f?.control==='select'?f.options.find(o=>o.value===f.value)?.label:f?.value;};
      return ['B-English',get('class_title'),get('honors'),'Semester',get('grade_system'),
        get('grade1'+(i?'':'Other')),get('grade2'+(i?'':'Other')),'','',''];
    })});
  function role(role,opts={},selector='') {
    const handle={selector,count:async()=>opts.name==='Expand all'?Number(!expanded):1,isVisible:async()=>role==='dialog'?warningModal:expanded,
      waitFor:async()=>{},and:other=>roleHandle(role,opts,other.selector),
      getByRole:(r,o)=>roleHandle(r,o,'warning'),
      innerText:async()=>"Warning If you change the grading system or term system for this school, you’ll need to re-enter the grades received for the courses taken at this school. Are you sure you want to change the grading system or term system? Yes No close",
      click:async()=>activate(role,opts.name,selector),press:async key=>{assert.equal(key,'Enter');await activate(role,opts.name,selector);}};
    return handle;
  }
  const roleHandle=role;
  async function activate(role,name,selector) {
    if(name==='No'&&selector==='warning'){
      assert.equal(warningModal,true);calls.push('warning-no');
      if(options.deferWarningDismiss)pendingDismiss=true;
      else if(!options.neverDismiss)warningModal=false;
      if(options.identityChangesAfterWarning)identityText='Different synthetic school';return;
    }
    if(name==='Expand all'||name==='About you Section Complete'||name instanceof RegExp){expanded=true;return;}
    if(name==='Review & submit'){url=state.review_url;expanded=false;return;}
    if(name==='Application status'){url=state.status_url;return;}
    if(name===state.term){url=state.review_url;expanded=false;return;}
    if(name==='Additional information section incomplete'){url=comments.url;return;}
    const grade=typeof name==='string'?/^(9|10|11|12)th grade section incomplete$/.exec(name):null;
    if(grade){url=summaryUrl(grade[1].padStart(2,'0'));return;}
    if(role==='button'&&selector.includes('acadHistFrGrades/')){url=summaryUrl(/Grades\/(\d+)/.exec(selector)[1]);return;}
    if(name==='Edit'&&selector.includes('acadHistFrInfo')){url=school.url;school.fields=structuredClone(savedSchool);return;}
    if(name==='Edit'&&selector.includes('JavaScript:Void')){url=editorUrl(/Grades\/(\d+)$/.exec(url)[1]);return;}
    throw Error('Unexpected navigation '+name+' '+selector);
  }
  const locator=selector=>({selector,count:async()=>1,waitFor:async()=>{},click:async()=>{
    if(selector==='[id="cancel-btn"]') {
      calls.push('cancel');const m=/editClasses\/(\d+)\//.exec(url);
      if(m)url=summaryUrl(m[1]);else {school.fields=structuredClone(savedSchool);url=origin+'/my-application/acadhistFrHighSchool';}
      return;
    }
    if(selector==='[id="save-btn"]'&&url===school.url){
      if(options.warningOnSave&&full()){
        calls.push('school-save-attempt');warningModal=true;url=alias;return;
      }
      calls.push('school-save');savedSchool=structuredClone(school.fields);url=origin+'/my-application/acadhistFrHighSchool';
      const academic=state.sections.find(s=>s.label==='Academic history');academic.completion_text='';
      academic.pages.find(i=>i.href.endsWith('acadHistAddInformation')).label='To do Additional information';return;
    }
    if(selector==='[id="save-btn"]'&&url===comments.url){
      assert.equal(comments.fields[0].value,'');calls.push('comments-save');url=origin+'/my-application/acadHistReview';
      const academic=state.sections.find(s=>s.label==='Academic history');academic.completion_text='Section Complete';
      academic.pages.find(i=>i.href.endsWith('acadHistAddInformation')).label='Edit Additional information';return;
    }
    throw Error('Unexpected mutable button '+selector);
  },setChecked:async value=>{
    assert.ok(url===school.url||url===alias);assert.equal(selector,'[id="onefinal"]');calls.push('school-input');
    school.fields.find(f=>f.key==='i:onefinal').value=value;
  },fill:async()=>{throw Error('Course/narrative input forbidden');},selectOption:async()=>{throw Error('Course selection forbidden');}});
  const tab={url:async()=>url,playwright:{locator,getByRole:role,domSnapshot:async()=>'',
    expectNavigation:async action=>action(),waitForURL:async expected=>assert.equal(url,expected),evaluate:async fn=>{
      if(fn.toString().includes('role=alertdialog'))return !!options.warning;
      if(fn.toString().includes('School code:'))return identityText;
      if(fn.toString().includes("querySelectorAll('a[href]')"))return ['/my-application/reviewSubmit','/my-application/appStatus'];
      if(url===state.review_url)return {term:state.term,sections:structuredClone(state.sections)};
      if(url===state.status_url)return {term:state.term,draft_marker:state.draft_marker};
      const grade=/Grades\/(\d+)$/.exec(url)?.[1];if(grade)return summary(grade);
      throw Error('Unexpected DOM read '+url);
    }}};
  const api=createUcTermSetup({...host,observe:async()=>{
    if(url===school.url||url===alias)return {...structuredClone(school),url};
    if(url===comments.url)return structuredClone(comments);
    const grade=/editClasses\/(\d+)\//.exec(url)?.[1];
    if(grade){
      const p=structuredClone(pages[grade]);
      if(full()&&['09','10'].includes(grade))p.fields.push({...structuredClone(p.fields[0]),
        key:'i:synthetic_new_term',selector:'[id="synthetic_new_term"]',label:'Synthetic term availability'});
      return p;
    }
    throw Error('Unexpected form read '+url);
  }});
  const baseline=await api.observe(tab);
  const context={browser_family:'edge',transport:'extension',origin,access_verified:true,real_account_test:true,
    full_state_restoration_verified:true,journal_persisted:true,restoration_strategy:{kind:'restore_uc_school_terms',
      page_url:school.url,baseline_state_sha256:host.digest(baseline.state_metadata),baseline_related_sha256:host.digest(baseline.courses)}};
  const plan={schema:'uc-school-term-plan/1',ready:true,system:'uc',allowed_origin:origin,page_url:school.url,
    bundle_sha256:host.digest(baseline),structure_sha256:host.digest(host.structure(annotate(baseline))),
    expected_values_sha256:host.digest({...vals(school),'i:onefinal':true}),
    original_values_sha256:host.digest(vals(school)),school_identity_sha256:baseline.school_identity_sha256,
    native_shape_sha256:host.digest({...host.structure(school),url:null}),
    writes:[{field_key:'i:onefinal',value:true,fact_ref:'education.uc_ap_reporting_term'}],save_action:school.actions[0],
    auxiliary:baseline.auxiliary};
  const recovery=()=>({plan,context,writes:[{field_key:'i:onefinal',value:false}],
    original_state_metadata:baseline.state_metadata,original_values_sha256:host.digest(vals(baseline.school))});
  const warningRecovery=()=>({...recovery(),post_warning_cancel:true,requires_fresh_ui_identity_verification:true});
  const advanceHostCall=()=>{if(pendingDismiss){warningModal=false;pendingDismiss=false;}};
  return {api,tab,school,comments,state,calls,baseline,plan,context,recovery,warningRecovery,advanceHostCall,pages};
}

test('school availability saves and inspects new course controls read-only, then restores the complete original bundle',async()=>{
  const {api,tab,baseline,plan,context,recovery,calls}=await port();
  const local=await api.apply(tab,plan,context);const saved=await api.saveAndRead(tab,plan,context,local);
  assert.equal(saved.revisited_after_save,true);
  assert.equal(saved.bundle.courses[0].page.fields.length,baseline.courses[0].page.fields.length+1);
  for(let i=0;i<4;i++)for(const [key,value] of Object.entries(vals(baseline.courses[i].page)))
    assert.equal(vals(saved.bundle.courses[i].page)[key],value);
  const restored=await api.restore(tab,recovery());assert.deepEqual(restored.bundle,baseline);
  assert.equal(calls.filter(c=>c==='school-input').length,2);
  assert.equal(calls.filter(c=>c==='school-save').length,2);
  assert.equal(calls.filter(c=>c==='comments-save').length,2);
});

test('a destructive-change warning stops before save and unsaved recovery cancels without changing any saved value',async()=>{
  const {api,tab,baseline,plan,context,recovery,calls}=await port({warning:true});
  await assert.rejects(api.apply(tab,plan,context),/warning_requires_recovery/);
  assert.equal(calls.filter(c=>c==='school-save').length,0);
  const restored=await api.restore(tab,recovery(),{unsaved:true});assert.deepEqual(restored.bundle,baseline);
  assert.equal(calls.filter(c=>c==='school-save'||c==='comments-save').length,0);
});

for(const change of ['journal','nonreal','stale_bundle','other_field','wrong_fact','wrong_origin']) {
  test(`${change} cannot enable school or course writes`,async()=>{
    const {api,tab,plan,context,calls}=await port();
    if(change==='journal')context.journal_persisted=false;
    else if(change==='nonreal')context.real_account_test=false;
    else if(change==='stale_bundle')plan.bundle_sha256='0'.repeat(64);
    else if(change==='other_field')plan.writes[0].field_key='i:semester';
    else if(change==='wrong_fact')plan.writes[0].fact_ref='education.invented';
    else context.origin='https://example.invalid';
    await assert.rejects(api.apply(tab,plan,context));
    assert.equal(calls.filter(c=>['school-input','school-save','comments-save'].includes(c)).length,0);
  });
}

test('nonempty optional academic comments block the availability preflight without saving',async()=>{
  const {api,tab,comments,plan,context,calls}=await port();comments.fields[0].value='Synthetic narrative';
  await assert.rejects(api.apply(tab,plan,context),/empty_optional_uc_comments/);
  assert.equal(calls.filter(c=>['school-input','school-save','comments-save'].includes(c)).length,0);
});

test('the actual post-save grade re-entry warning is declined and all original pages verified without confirming the reset',async()=>{
  const {api,tab,baseline,plan,context,calls,warningRecovery,advanceHostCall}=await port({warningOnSave:true,deferWarningDismiss:true});
  const local=await api.apply(tab,plan,context),transition=await api.saveAndRead(tab,plan,context,local);
  assert.equal(transition.requires_fresh_host_call,true);assert.equal(transition.bundle,undefined);
  assert.equal(calls.filter(c=>c==='school-input').length,1);
  advanceHostCall();const result=await api.resumeWarningCancel(tab,warningRecovery());
  assert.equal(result.change_cancelled,true);assert.equal(result.grade_reentry_required,true);
  assert.equal(result.availability_change_verified,false);assert.deepEqual(result.bundle,baseline);
  assert.equal(calls.filter(c=>c==='warning-no').length,1);
  assert.equal(calls.filter(c=>c==='school-save').length,0);
  assert.equal(calls.filter(c=>c==='comments-save').length,0);
});

test('post-warning school identity drift stops local checkbox recovery before another input',async()=>{
  const {api,tab,plan,context,calls,warningRecovery}=await port({warningOnSave:true,identityChangesAfterWarning:true});
  const local=await api.apply(tab,plan,context);
  await api.saveAndRead(tab,plan,context,local);
  await assert.rejects(api.resumeWarningCancel(tab,warningRecovery()),/identity_changed/);
  assert.equal(calls.filter(c=>c==='school-input').length,1);
  assert.equal(calls.filter(c=>c==='school-save').length,0);
});

test('two unsuccessful No actions stop with recovery retained instead of looping',async()=>{
  const {api,tab,plan,context,calls,warningRecovery}=await port({warningOnSave:true,neverDismiss:true});
  const local=await api.apply(tab,plan,context);await api.saveAndRead(tab,plan,context,local);
  assert.equal((await api.resumeWarningCancel(tab,warningRecovery())).requires_fresh_host_call,true);
  await assert.rejects(api.resumeWarningCancel(tab,warningRecovery()),/manual_handoff_required/);
  assert.equal(calls.filter(c=>c==='warning-no').length,2);
  assert.equal(calls.filter(c=>c==='school-input').length,1);
});
