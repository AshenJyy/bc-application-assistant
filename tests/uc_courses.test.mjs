// Fictional native UC grade editor and browser lifecycle. No actual applicant data.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {createUcCourses} from '../skills/bc-application/scripts/uc_courses.mjs';

const fixture=JSON.parse(await readFile(new URL('./fixtures/uc_courses_page.json',import.meta.url),'utf8'));
const stateFixture=JSON.parse(await readFile(new URL('./fixtures/uc_review_state.json',import.meta.url),'utf8'));
const commentsFixture=JSON.parse(await readFile(new URL('./fixtures/uc_empty_comments_page.json',import.meta.url),'utf8'));
const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

function port() {
  const page=structuredClone(fixture),state=structuredClone(stateFixture),calls=[];
  const comments=structuredClone(commentsFixture);
  state.page_url=page.url;
  let url=page.url,expanded=false,saved=structuredClone(page.fields);
  const summaryData=()=>({heading:'9th grade',school:'Synthetic School',year:'2024 - 2025 academic year',
    lists:['Grading system:','0-100 (Canada - BC) BC Proficiency','Term system:','Semester'],
    columns:page.uc_course_editor.columns,
    rows:[0,1].map(i=>{
      const get=suffix=>{const f=saved.find(f=>f.key===`i:academics_hs_classes_add_${i}_${suffix}`);
        return f?.control==='select'?f.options.find(o=>o.value===f.value)?.label:f?.value;};
      return ['B-English',get('class_title'),get('honors'),'Semester',get('grade_system'),
        get('grade1'+(i?'':'Other')),get('grade2'+(i?'':'Other')),'','',''];
    })});
  const data=summaryData(),ctxHash=host.digest({heading:data.heading,school:data.school,year:data.year,lists:data.lists});
  page.uc_course_editor.context_sha256=ctxHash;page.uc_course_parent.context_sha256=ctxHash;
  page.uc_course_parent.summary_sha256=host.digest(data);
  const context={browser_family:'edge',transport:'extension',origin:new URL(page.url).origin,access_verified:true,
    real_account_test:true,full_state_restoration_verified:true,journal_persisted:true,
    restoration_strategy:{kind:'restore_uc_courses',page_url:page.url,baseline_state_sha256:host.digest(state),
      baseline_parent_sha256:host.digest(page.uc_course_parent)}};
  const plan={ready:true,system:'uc',allowed_origin:context.origin,page_url:page.url,
    observation_sha256:host.digest({...page,state_metadata:state}),structure_sha256:host.digest(host.structure(page)),
    expected_values_sha256:host.digest(vals(page)),writes:[],save_action:page.actions[0],
    uc_course_editor:structuredClone(page.uc_course_editor),uc_course_parent:structuredClone(page.uc_course_parent),
    uc_academic_auxiliary:structuredClone(page.uc_academic_auxiliary)};
  const locator=selector=>({count:async()=>1,waitFor:async()=>{},click:async()=>{
    if(selector==='[id="save"]'){
      calls.push('save');saved=structuredClone(page.fields);url=page.uc_course_editor.summary_url;
      const academic=state.sections.find(s=>s.label==='Academic history');academic.completion_text='';
      academic.pages.find(i=>i.href.endsWith('acadHistAddInformation')).label='To do Additional information';
      academic.pages.push({href:'/my-application/acadHistReview',label:'To do Review'});
    }
    else if(selector==='[id="save-btn"]'){
      assert.equal(comments.fields[0].value,'');calls.push('comments-save');
      const academic=state.sections.find(s=>s.label==='Academic history');academic.completion_text='Section Complete';
      academic.pages.find(i=>i.href.endsWith('acadHistAddInformation')).label='Edit Additional information';
      academic.pages=academic.pages.filter(i=>i.href!=='/my-application/acadHistReview');
      url=context.origin+'/my-application/acadHistReview';
    }
    else if(selector==='[id="cancel-btn"]'){calls.push('cancel');page.fields=structuredClone(saved);url=page.uc_course_editor.summary_url;}
    else throw Error('unexpected button');
  },fill:async value=>{calls.push('input');page.fields.find(f=>f.selector===selector).value=value;},
  selectOption:async choice=>{calls.push('input');page.fields.find(f=>f.selector===selector).value=choice.value;}});
  const role=(role,opts)=>{
    const handle={count:async()=>opts.name==='Expand all'?Number(!expanded):1,isVisible:async()=>expanded,waitFor:async()=>{},
      click:async()=>{expanded=true;},and:()=>handle,press:async key=>{
        assert.equal(key,'Enter');calls.push(opts.name);
        if(opts.name==='Review & submit'){url=state.review_url;expanded=false;}
        else if(opts.name==='Application status')url=state.status_url;
        else if(opts.name===state.term){url=state.review_url;expanded=false;}
        else if(opts.name==='Edit grade'||opts.name==='9th grade section incomplete')url=page.uc_course_editor.summary_url;
        else if(opts.name==='Additional information section incomplete')url=comments.url;
        else if(opts.name==='Edit')url=page.url;
        else throw Error('unexpected navigation');
      }};return handle;
  };
  const tab={url:async()=>url,playwright:{locator,getByRole:role,domSnapshot:async()=>'',
    waitForURL:async expected=>expected instanceof RegExp?assert.match(url,expected):assert.equal(url,expected),expectNavigation:async action=>action(),
    evaluate:async fn=>{
      if(fn.toString().includes("querySelectorAll('a[href]')"))return ['/my-application/reviewSubmit','/my-application/appStatus'];
      if(url===state.review_url)return {term:state.term,sections:structuredClone(state.sections)};
      if(url===state.status_url)return {term:state.term,draft_marker:state.draft_marker};
      return summaryData();
    }}};
  const observe=async()=>structuredClone(url===comments.url?comments:page);
  const api=createUcCourses({...host,observe});
  return {page,state,calls,plan,context,tab,api,comments,observe,setSaved:()=>{saved=structuredClone(page.fields);}};
}

test('native whole-page changed course name saves, reopens, verifies summary, and restores after restart',async()=>{
  const {page,state,calls,plan,context,tab,api,observe}=port(),original=vals(page),f=page.fields[1];
  plan.writes=[{field_key:f.key,value:'Synthetic corrected course'}];
  plan.expected_values_sha256=host.digest({...original,[f.key]:plan.writes[0].value});
  const local=await api.apply(tab,plan,context);
  const saved=await api.saveAndRead(tab,plan,context,local);
  assert.equal(saved.revisited_after_save,true);
  assert.notEqual(saved.page.uc_course_parent.summary_sha256,plan.uc_course_parent.summary_sha256);
  assert.deepEqual(saved.page.state_metadata,state);
  const restarted=createUcCourses({...host,observe});
  const restored=await restarted.restore(tab,JSON.parse(JSON.stringify(plan)),[{field_key:f.key,value:original[f.key]}],context);
  assert.deepEqual(vals(restored.page),original);
  assert.deepEqual(restored.page.uc_course_parent,plan.uc_course_parent);
  assert.deepEqual(restored.page.state_metadata,state);
  assert.equal(calls.filter(c=>c==='save').length,2);
  assert.equal(calls.filter(c=>c==='comments-save').length,2);
});

for(const change of ['new_field','wrong_label','narrative','duplicate_selector','new_row','wrong_parent','different_grade']) {
  test(`${change} stops native input and saving`,async()=>{
    const {page,calls,plan,context,tab,api,setSaved}=port();
    if(change==='new_field')page.fields.push({...page.fields[0],key:'i:unknown'});
    else if(change==='wrong_label')page.fields[0].label='Preferred major';
    else if(change==='narrative')page.fields[1].control='textarea';
    else if(change==='duplicate_selector')page.fields[0].selector_count=2;
    else if(change==='new_row')page.uc_course_editor.row_count=3;
    else if(change==='wrong_parent')page.uc_course_parent.row_count=4;
    else page.uc_course_editor.grade='10';
    setSaved();
    assert.throws(()=>api.checkPage(page));
    assert.equal(calls.length,0);
  });
}

for(const change of ['journal','stale_plan','parent_hash','state_hash','incomplete','submitted','reconfigure']) {
  test(`${change} cannot bypass the actual course-page restoration boundary`,async()=>{
    const {page,state,calls,plan,context,tab,api}=port();
    if(change==='journal')context.journal_persisted=false;
    else if(change==='stale_plan')plan.observation_sha256='0'.repeat(64);
    else if(change==='parent_hash')context.restoration_strategy.baseline_parent_sha256='0'.repeat(64);
    else if(change==='state_hash')context.restoration_strategy.baseline_state_sha256='0'.repeat(64);
    else if(change==='incomplete')state.sections.find(s=>s.label==='Academic history').completion_text='';
    else if(change==='submitted')state.draft_marker='Submitted';
    else plan.writes=[{field_key:page.fields[0].key,value:'19'}];
    await assert.rejects(api.apply(tab,plan,context));
    assert.equal(calls.filter(c=>['input','save'].includes(c)).length,0);
  });
}

test('unexpected change after input stops save and repairs unsaved original values before cancellation',async()=>{
  const {page,state,calls,plan,context,tab,api}=port(),original=vals(page),f=page.fields[1];
  const local=await api.apply(tab,plan,context);page.fields.find(x=>x.key===f.key).value='Unexpected local value';
  await assert.rejects(api.saveAndRead(tab,plan,context,local));
  const n=calls.length;
  const restored=await api.restore(tab,plan,[{field_key:f.key,value:original[f.key]}],context,
    {unsaved:true,original_state_metadata:state,original_values_sha256:host.digest(original)});
  assert.equal(calls[n],'input');assert.deepEqual(vals(restored.page),original);
  assert.equal(calls.filter(c=>c==='save').length,0);
});

test('zero-delta saved recovery performs no additional save and exposes remaining status drift',async()=>{
  const {state,calls,plan,context,tab,api}=port();
  state.sections.at(-1).pages[0].label='Edit Introduction';
  const restored=await api.restore(tab,plan,[],context);
  assert.equal(restored.page.state_metadata.sections.at(-1).pages[0].label,'Edit Introduction');
  assert.equal(restored.restore_save_performed,false);
  assert.equal(calls.filter(c=>c==='save').length,0);
});

for(const change of ['nonempty','required','extra_field','wrong_save','structure_changed']) {
  test(`auxiliary ${change} stops before the first course write`,async()=>{
    const {comments,calls,plan,context,tab,api}=port();
    if(change==='nonempty')comments.fields[0].value='Synthetic narrative is never transmitted';
    else if(change==='required')comments.fields[0].required=true;
    else if(change==='extra_field')comments.fields.push({...comments.fields[0],key:'i:declaration'});
    else if(change==='wrong_save')comments.actions[0].label='Submit';
    else comments.fields[0].name='changedComments';
    await assert.rejects(api.apply(tab,plan,context));
    assert.equal(calls.filter(c=>['input','save','comments-save'].includes(c)).length,0);
  });
}
