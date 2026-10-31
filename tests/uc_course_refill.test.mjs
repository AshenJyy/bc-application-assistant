// Fictional conditional UC form. Native options rebuild after term selection.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createUcCourseRefill} from '../skills/bc-application/scripts/uc_course_refill.mjs';

const initial=JSON.parse(await readFile(new URL('./fixtures/uc_courses_page.json',import.meta.url),'utf8'));
const stateInitial=JSON.parse(await readFile(new URL('./fixtures/uc_review_state.json',import.meta.url),'utf8'));
const commentsInitial=JSON.parse(await readFile(new URL('./fixtures/uc_empty_comments_page.json',import.meta.url),'utf8'));
const origin='https://apply.universityofcalifornia.edu',url=origin+'/my-application/acadHistFrHighSchoolClasses/editClasses/11/123456';
const summaryUrl=origin+'/my-application/acadHistFrGrades/11',vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
const field=(i,suffix,label,value,options)=>({key:`i:academics_hs_classes_add_${i}_${suffix}`,
  selector:`[id="academics_hs_classes_add_${i}_${suffix}"]`,selector_count:1,selector_index:0,name:`row${i}.${suffix}`,label,group:'',
  control:suffix==='class_title'?'text':'select',value,options:options.map(([value,label])=>({value,label,disabled:false})),
  required:true,disabled:false,readonly:false,invalid:false});

function port({blank=false,real=true}={}) {
  const calls=[],page={...structuredClone(initial),url,fields:[]},state=structuredClone(stateInitial),comments=structuredClone(commentsInitial);
  delete page.uc_course_editor;delete page.uc_course_parent;delete page.uc_academic_auxiliary;
  state.page_url=url;let currentUrl=url,expanded=false,saved;
  const grade=(i,j,value)=>field(i,'grade'+j,'Grade '+j,value,[['','--'],['084','84'],['078','78'],['Z','NO']]);
  for(let i=0;i<2;i++) {
    page.fields.push(field(i,'subject','Subject Area/Course Category','4',[['4','English']]),
      field(i,'class_title','Course Name','Synthetic course '+i,[]),field(i,'honors','Honor Type',i?'NH':'AP',[['NH','NH'],['AP','AP']]),
      field(i,'term','Term System',blank?'':'S',[['','--'],['F','Full'],['S','Semester']]));
    if(!blank)page.fields.push(grade(i,1,'Z'),grade(i,2,i?'078':'084'));
  }
  saved=structuredClone(page.fields);
  const summaryData=()=>({heading:'11th grade',school:'Synthetic School',year:'2025 - 2026 academic year',
    lists:['Grading system:','0-100 (Canada - BC)','Term system:','Full year (1 final grade per year) Semester'],
    columns:['Subject area/Course category','Course name','Hnrs','Term','G1','G2','G3','G4','Language name'],
    rows:[0,1].map(i=>{
      const get=s=>{const f=saved.find(f=>f.key===`i:academics_hs_classes_add_${i}_${s}`);
        return !f?'':f.control==='text'?f.value:f.options.find(o=>o.value===f.value).label;};
      return ['B-English',get('class_title'),get('honors'),get('term')==='--'?'':get('term'),get('grade1'),get('grade2'),'','',''];
    })});
  const doAction=(role,name,selector)=>async()=>{
    calls.push(name||selector);
    if(name==='Cancel'||selector==='[id="cancel-btn"]'){page.fields=structuredClone(saved);currentUrl=summaryUrl;}
    else if(name==='Save & continue'&&currentUrl===url){saved=structuredClone(page.fields);currentUrl=summaryUrl;}
    else if(selector==='[id="save-btn"]'||(name==='Save & continue'&&currentUrl===comments.url))currentUrl=origin+'/my-application/acadHistReview';
    else if(name==='Edit')currentUrl=url;
    else if(name==='Edit grade'||name==='11th grade section incomplete')currentUrl=summaryUrl;
    else if(name==='Additional information section incomplete')currentUrl=comments.url;
    else if(name==='Review & submit'){currentUrl=state.review_url;expanded=false;}
    else if(name==='Application status')currentUrl=state.status_url;
    else if(name===state.term){currentUrl=state.review_url;expanded=false;}
    else if(name==='Expand all')expanded=true;
    else if(name==='Continue')currentUrl=origin+'/my-application/acadHistFrGrades/12';
    else throw Error('unexpected action '+name+' '+selector);
  };
  const locator=(selector,role,name)=>{
    const handle={count:async()=>name==='continue'?0:1,isVisible:async()=>name==='continue'?false:name==='Expand all'?!expanded:true,
      waitFor:async()=>{},and:()=>handle,filter:()=>handle,click:doAction(role,name,selector),press:async()=>doAction(role,name,selector)(),
      selectOption:async choice=>{
        const f=page.fields.find(f=>f.selector===selector);assert.ok(f);f.value=choice.value??choice;calls.push('input');
        if(f.key.endsWith('_term')) {
          const i=Number(/add_(\d+)_/.exec(f.key)[1]);page.fields=page.fields.filter(x=>!new RegExp(`add_${i}_grade[12]$`).test(x.key));
          const n=f.value===''?0:f.value==='F'?1:2;for(let j=1;j<=n;j++)page.fields.push(grade(i,j,''));
          page.fields.sort((a,b)=>Number(/add_(\d+)_/.exec(a.key)[1])-Number(/add_(\d+)_/.exec(b.key)[1]));
        }
      }};return handle;
  };
  const tab={url:async()=>currentUrl,playwright:{locator:s=>locator(s),getByRole:(r,o)=>locator(null,r,o.name),
    domSnapshot:async()=>'',waitForURL:async expected=>assert.equal(currentUrl,expected),expectNavigation:async action=>action(),
    evaluate:async fn=>{
      const code=fn.toString();
      if(code.includes("querySelectorAll('a[href]')"))return ['/my-application/reviewSubmit','/my-application/appStatus'];
      if(code.includes('termHeadings'))return {term:state.term,sections:structuredClone(state.sections)};
      if(code.includes('markers='))return {term:state.term,draft_marker:state.draft_marker};
      if(code.includes('[role="alert"] li'))return [];
      if(code.includes("querySelector('main table')")){const d=summaryData();return {columns:d.columns,rows:d.rows};}
      return summaryData();
    }}};
  const observe=async()=>structuredClone(currentUrl===comments.url?comments:page),api=createUcCourseRefill({...host,observe});
  const context={browser_family:'edge',transport:'extension',origin,access_verified:true,journal_persisted:true,real_account_test:real};
  return {tab,page,api,calls,state,context,observe,summaryData};
}

async function prepare(p) {
  const bundle=await p.api.observe(p.tab),context=p.context;
  if(context.real_account_test)Object.assign(context,{full_state_restoration_verified:true,
    restoration_strategy:{kind:'restore_uc_course_refill',page_url:url,baseline_state_sha256:host.digest(bundle.state_metadata),
      baseline_parent_sha256:host.digest(bundle.summary.parent)}});
  const rows=[0,1].map(i=>({row:i,field_key:`i:academics_hs_classes_add_${i}_term`,value:i?'S':'F',fact_ref:`education.fixture.term${i}`,
    grades:[]}));
  const plan={schema:'uc-course-refill-plan/1',ready:true,checkpoint_id:'checkpoint:fictional',system:'uc',allowed_origin:origin,page_url:url,
    bundle_sha256:host.digest(bundle),rows,context:bundle.summary.context,
    writes:rows.filter(r=>vals(bundle.page)[r.field_key]!==r.value).map(({field_key,value,fact_ref})=>({field_key,value,fact_ref}))};
  return {bundle,plan,context};
}

function gradePlan(p,plan,{restoration=false,original}={}) {
  const desired=restoration?vals(original.page):{...vals(p.page),
    'i:academics_hs_classes_add_0_grade1':'084','i:academics_hs_classes_add_1_grade1':'Z','i:academics_hs_classes_add_1_grade2':'078'};
  return {...plan,schema:'uc-course-grade-plan/1',restoration,observation_sha256:host.digest(p.page),structure_sha256:host.digest(host.structure(p.page)),
    expected_values_sha256:host.digest(desired),writes:Object.entries(desired).filter(([key,value])=>vals(p.page)[key]!==value)
      .map(([field_key,value])=>({field_key,value})),save_action:p.page.actions[0]};
}

test('blank conditional terms expose one annual grade and two semester grades before saved readback',async()=>{
  const p=port({blank:true,real:false}),{bundle,plan,context}=await prepare(p);
  const exposed=await p.api.applyTerms(p.tab,plan,context);assert.equal(exposed.fields.filter(f=>f.label==='Grade 1').length,2);
  assert.equal(exposed.fields.filter(f=>f.label==='Grade 2').length,1);
  const grades=gradePlan(p,plan);await p.api.applyGrades(p.tab,grades,context,bundle);
  const result=await p.api.saveAndRead(p.tab,grades,context,bundle);
  assert.equal(result.revisited_after_save,true);assert.equal(result.bundle.summary.context.row_terms[0],'Full year');
  assert.equal(result.bundle.summary.cells.rows[0][4],'84');assert.equal(result.bundle.summary.cells.rows[0][5],'');
});

test('saved term change and original two-semester grades restore through a restarted host',async()=>{
  const p=port(),{bundle,plan,context}=await prepare(p);await p.api.applyTerms(p.tab,plan,context);
  const grades=gradePlan(p,plan);await p.api.applyGrades(p.tab,grades,context,bundle);await p.api.saveAndRead(p.tab,grades,context,bundle);
  const recovery={plan,context,original:bundle,term_writes:bundle.page.fields.filter(f=>f.key.endsWith('_term')).map(f=>({field_key:f.key,value:f.value}))};
  const restarted=createUcCourseRefill({...host,observe:p.observe});await restarted.restoreTerms(p.tab,recovery);
  const restoredPlan=gradePlan(p,plan,{restoration:true,original:bundle});await restarted.applyGrades(p.tab,restoredPlan,context,bundle);
  const result=await restarted.saveAndRead(p.tab,restoredPlan,context,bundle);
  assert.deepEqual(result.bundle,bundle);
});

test('unsaved conditional inputs cancel without a draft save',async()=>{
  const p=port(),{bundle,plan,context}=await prepare(p);await p.api.applyTerms(p.tab,plan,context);
  const result=await p.api.restoreTerms(p.tab,{plan,context,original:bundle},{unsaved:true});
  assert.deepEqual(result.bundle,bundle);assert.equal(p.calls.filter(x=>x==='Save & continue').length,0);
});

for(const change of ['journal','source_origin','stale','unknown_control','narrative','duplicate','missing_grade','wrong_option']) {
  test(`${change} refuses a conditional transaction before saving`,async()=>{
    const p=port(),prepared=await prepare(p),{bundle,plan,context}=prepared;
    if(change==='journal')context.journal_persisted=false;
    else if(change==='source_origin')context.origin='https://example.org';
    else if(change==='stale')plan.bundle_sha256='0'.repeat(64);
    else if(change==='unknown_control')p.page.fields[0].key='i:unknown';
    else if(change==='narrative')p.page.fields[1].control='textarea';
    else if(change==='duplicate')p.page.fields[0].selector_count=2;
    else if(change==='missing_grade')p.page.fields.pop();
    else p.page.fields.find(f=>f.key.endsWith('_term')).options[1].label='Inferred yearly';
    await assert.rejects(p.api.applyTerms(p.tab,plan,context));
    assert.equal(p.calls.filter(x=>x==='Save & continue').length,0);
  });
}

test('new field after native input stops the whole-page draft save',async()=>{
  const p=port(),{bundle,plan,context}=await prepare(p);await p.api.applyTerms(p.tab,plan,context);
  const grades=gradePlan(p,plan);await p.api.applyGrades(p.tab,grades,context,bundle);
  p.page.fields.push(field(2,'class_title','Course Name','Unknown',[]));
  await assert.rejects(p.api.saveAndRead(p.tab,grades,context,bundle));
  assert.equal(p.calls.filter(x=>x==='Save & continue').length,0);
});
