/** Conditional Full/Semester course controls, through documented host locators. */
import {createUcCourses} from './uc_courses.mjs';
import {createUcReview} from './uc_review.mjs';

export function createUcCourseRefill(host) {
  const {observe:rawObserve,digest,structure,guard,writeObserved}=host;
  const courses=createUcCourses(host),review=createUcReview(host),origin='https://apply.universityofcalifornia.edu';
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  const annotate=b=>({...b.page,uc_course_refill:{schema:'uc-course-refill/1',context:b.summary.context},state_metadata:b.state_metadata});
  const labels={subject:'Subject Area/Course Category',class_title:'Course Name',honors:'Honor Type',term:'Term System',
    grade_system:'Grading System',grade1:'Grade 1',grade2:'Grade 2',grade1Other:'Grade 1',grade2Other:'Grade 2',subject_language_code:'Language Name'};

  function checkNative(p,c) {
    if(p.url!==origin+new URL(p.url).pathname||!new RegExp('^'+origin+'/my-application/acadHistFrHighSchoolClasses/editClasses/(09|10|11|12)/[0-9]+$').test(p.url)||
       p.title!=='Enter HS classes - Academic history - UC application'||p.frames_present||p.collections?.length||p.scope||
       c?.schema!=='uc-course-editor/1'||!Number.isInteger(c.row_count)||c.row_count<1||c.row_count>100||
       !p.url.includes('/editClasses/'+c.grade+'/')||c.summary_url!==origin+'/my-application/acadHistFrGrades/'+c.grade||
       !/^\d{4} - \d{4} academic year$/.test(c.year)||!/^[a-f0-9]{64}$/.test(c.context_sha256))
      throw Error('observed_uc_refill_context_required');
    const rows=Array.from({length:c.row_count},()=>new Map());
    for(const f of p.fields) {
      const key=/^i:academics_hs_classes_add_(\d+)_(\w+)$/.exec(f.key),suffix=key?.[2];
      if(!key||!rows[Number(key[1])]||!Object.hasOwn(labels,suffix)||f.label!==labels[suffix]||f.disabled||f.readonly||
         f.selector!==`[id="${f.key.slice(2)}"]`||(f.selector_count??1)!==1||(f.selector_index??0)!==0||
         f.control!==(['class_title','grade1Other','grade2Other'].includes(suffix)?'text':'select')||rows[Number(key[1])].has(suffix))
        throw Error('observed_uc_refill_fields_required');
      rows[Number(key[1])].set(suffix,f);
    }
    for(const row of rows) {
      const term=row.get('term');
      if(!['subject','class_title','honors','term'].every(k=>row.has(k))||
         digest(term.options.map(o=>[o.value,o.label]))!==digest([['','--'],['F','Full'],['S','Semester']])||!['','F','S'].includes(term.value))
        throw Error('observed_uc_refill_terms_required');
      const n=term.value===''?0:term.value==='F'?1:2;
      for(let j=1;j<=2;j++)if(Number(row.has('grade'+j))+Number(row.has('grade'+j+'Other'))!==Number(j<=n))
        throw Error('observed_uc_conditional_grades_required');
    }
    if(p.actions.length!==2||!p.actions.some(a=>a.key==='i:save'&&a.label==='Save & continue'&&!a.disabled)||
       !p.actions.some(a=>a.key==='i:cancel-btn'&&a.label==='Cancel'&&!a.disabled))throw Error('observed_uc_refill_save_cancel_required');
  }

  async function open(tab) {
    const summary=await courses.readSummary(tab,{include_rows:true});
    await tab.playwright.getByRole('link',{name:'Edit',exact:true}).and(tab.playwright.locator('a[href="JavaScript:Void(0);"]')).click();
    await tab.playwright.getByRole('heading',{name:`${Number(summary.context.grade)}th grade - Enter courses & grades`,exact:true})
      .waitFor({state:'visible',timeoutMs:10000});
    const warning=tab.playwright.getByRole('button',{name:'continue',exact:true});
    if(await warning.isVisible()) {
      const errors=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('[role="alert"] li'))
        .filter(e=>e.getClientRects().length).map(e=>(e.innerText||'').trim()));
      if(!errors.length||errors.some(e=>e!=='Please select the term type.'))throw Error('unknown_uc_validation_warning');
      await warning.click();
    }
    const page=await rawObserve(tab);checkNative(page,summary.context);return {page,summary};
  }

  async function cancel(tab,summary) {
    await tab.playwright.getByRole('button',{name:'Cancel',exact:true}).click();
    await tab.playwright.waitForURL(summary.context.summary_url,{timeoutMs:10000});
    await tab.playwright.getByRole('heading',{name:`${Number(summary.context.grade)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
    return courses.readSummary(tab,{include_rows:true});
  }

  async function observe(tab) {
    const page=await rawObserve(tab),grade=/\/editClasses\/(09|10|11|12)\//.exec(page.url)?.[1];
    if(!grade)throw Error('saved_uc_refill_editor_required');
    const summary=await cancel(tab,{context:{grade,summary_url:origin+'/my-application/acadHistFrGrades/'+grade}});
    checkNative(page,summary.context);
    const auxiliary=await review.inspectEmptyComments(tab);let reopened;
    const state=await review.collect(tab,page.url,async()=>{
      const expand=tab.playwright.getByRole('link',{name:'Expand all',exact:true});if(await expand.isVisible())await expand.click();
      await tab.playwright.getByRole('button',{name:'Edit grade',exact:true})
        .and(tab.playwright.locator(`[href="${new URL(summary.context.summary_url).pathname}"]`)).click();
      await tab.playwright.getByRole('heading',{name:`${Number(grade)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
      reopened=await open(tab);
    });
    if(digest(reopened.page)!==digest(page)||digest(reopened.summary)!==digest(summary))throw Error('uc_refill_inspection_changed_baseline');
    return {schema:'uc-course-refill-bundle/1',...reopened,auxiliary,state_metadata:state};
  }

  function prepared(plan,context,bundle,restoration=false) {
    checkNative(bundle.page,bundle.summary.context);review.checkState(bundle.state_metadata,bundle.page.url);review.checkEmptyComments(bundle.auxiliary);
    guard(context,annotate(bundle),origin,restoration);
    if(!plan.ready||plan.allowed_origin!==origin||plan.page_url!==bundle.page.url||context.journal_persisted!==true||
       plan.system!=='uc'||plan.schema!=='uc-course-refill-plan/1')throw Error('persisted_uc_refill_plan_required');
  }

  async function applyTerms(tab,plan,context) {
    if(context.journal_persisted!==true)throw Error('persisted_uc_refill_plan_required');
    const bundle=await observe(tab);prepared(plan,context,bundle);
    if(digest(bundle)!==plan.bundle_sha256||plan.writes.some(w=>!w.field_key.endsWith('_term')||!['F','S'].includes(w.value)))
      throw Error('fresh_uc_refill_term_plan_required');
    await writeObserved(tab,bundle.page,plan.writes);
    const page=await rawObserve(tab);checkNative(page,plan.context);
    for(const f of bundle.page.fields)if(!/_grade[12](Other)?$/.test(f.key)) {
      const desired=plan.rows.find(r=>r.field_key===f.key)?.value??f.value;
      if(page.fields.find(x=>x.key===f.key)?.value!==desired)throw Error('uc_refill_retained_value_changed');
    }
    return page;
  }

  async function applyGrades(tab,plan,context,original) {
    const p=await rawObserve(tab);checkNative(p,plan.context);
    guard(context,annotate({...original,page:p}),origin,true);
    if(plan.schema!=='uc-course-grade-plan/1'||!plan.ready||context.journal_persisted!==true||p.url!==plan.page_url||
       digest(p)!==plan.observation_sha256||digest(structure(p))!==plan.structure_sha256||
       plan.writes.some(w=>!/_grade[12](Other)?$/.test(w.field_key)))throw Error('fresh_uc_refill_grade_plan_required');
    await writeObserved(tab,p,plan.writes);
    const after=await rawObserve(tab);checkNative(after,plan.context);
    if(digest(structure(after))!==plan.structure_sha256||digest(vals(after))!==plan.expected_values_sha256||after.fields.some(f=>f.invalid))
      throw Error('uc_refill_whole_page_values_required');
    return after;
  }

  async function saveAndRead(tab,gradePlan,context,original) {
    const p=await rawObserve(tab);checkNative(p,gradePlan.context);
    const guardPage={...p,uc_course_refill:{schema:'uc-course-refill/1',context:gradePlan.context},state_metadata:original.state_metadata};
    guard(context,guardPage,origin,gradePlan.restoration);
    if(context.journal_persisted!==true||gradePlan.schema!=='uc-course-grade-plan/1'||p.url!==gradePlan.page_url||
       digest(structure(p))!==gradePlan.structure_sha256||digest(vals(p))!==gradePlan.expected_values_sha256||p.fields.some(f=>f.invalid))
      throw Error('prepared_uc_refill_save_required');
    await tab.playwright.getByRole('button',{name:'Save & continue',exact:true}).click();
    await tab.playwright.waitForURL(gradePlan.context.summary_url,{timeoutMs:10000});
    await tab.playwright.getByRole('heading',{name:`${Number(gradePlan.context.grade)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
    // Validate the saved summary through its actual column labels, including
    // Full's single grade. No fixed indexing across school grading variants.
    const rows=await tab.playwright.evaluate(()=>{
      const table=document.querySelector('main table');if(!table)throw Error('saved_uc_summary_required');
      const text=e=>(e.innerText||'').replace(/\s+/g,' ').trim();
      return {columns:Array.from(table.querySelectorAll('th')).map(text),rows:Array.from(table.querySelectorAll('tr'))
        .filter(r=>r.querySelector('td')).map(r=>Array.from(r.querySelectorAll('td')).map(text))};
    });
    if(rows.rows.length!==gradePlan.rows.length)throw Error('saved_uc_refill_row_count_changed');
    for(const r of gradePlan.rows) {
      const row=rows.rows[r.row],pre=`i:academics_hs_classes_add_${r.row}_`,fields=p.fields.filter(f=>f.key.startsWith(pre));
      const term=fields.find(f=>f.key.endsWith('_term')).value;
      if(row[rows.columns.indexOf('Term')]!==(term==='F'?'Full':'Semester')||
         row[rows.columns.indexOf('Course name')]!==fields.find(f=>f.key.endsWith('_class_title')).value)
        throw Error('saved_uc_refill_summary_mismatch');
      for(let j=1;j<=2;j++) {
        const field=fields.find(f=>new RegExp('_grade'+j+'(Other)?$').test(f.key));
        const displayed=field?(field.control==='select'?field.options.find(o=>o.value===field.value)?.label:field.value):'';
        if(row[rows.columns.indexOf('G'+j)]!==displayed)throw Error('saved_uc_refill_summary_grade_mismatch');
      }
    }
    const current=original.state_metadata.sections.flatMap(s=>s.pages).find(i=>origin+i.href===gradePlan.context.summary_url);
    if(!context.real_account_test&&current?.label.startsWith('To do')) {
      const next=gradePlan.context.grade==='12'?'/my-application/acadHistFrCollege':
        '/my-application/acadHistFrGrades/'+String(Number(gradePlan.context.grade)+1).padStart(2,'0');
      if(await tab.playwright.locator(`a[href="${next}"]`).count()!==1)throw Error('observed_next_uc_grade_required');
      await tab.playwright.getByRole('button',{name:'Continue',exact:true}).click();
      await tab.playwright.waitForURL(origin+next,{timeoutMs:10000});
    }
    await review.inspectEmptyComments(tab,original.auxiliary,true);
    await tab.playwright.getByRole('link',{name:`${Number(gradePlan.context.grade)}th grade section incomplete`,exact:true}).click();
    await tab.playwright.getByRole('heading',{name:`${Number(gradePlan.context.grade)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await open(tab);
    return {bundle:await observe(tab),revisited_after_save:true};
  }

  async function restoreTerms(tab,recovery,{unsaved=false}={}) {
    const {plan,context,original}=recovery,p=await rawObserve(tab);checkNative(p,plan.context);
    prepared(plan,context,{...original,page:p},true);
    if(unsaved) {
      const summary=await cancel(tab,original.summary);
      if(digest(summary)!==digest(original.summary))throw Error('uc_refill_unsaved_cancel_changed_summary');
      await open(tab);return {bundle:await observe(tab),revisited_after_save:true,unsaved_cancelled:true};
    }
    if(recovery.term_writes.some(w=>!['F','S'].includes(w.value)))
      throw Error('incomplete_original_uc_draft_resume_refill_instead');
    await writeObserved(tab,p,recovery.term_writes.filter(w=>vals(p)[w.field_key]!==w.value));
    const after=await rawObserve(tab);checkNative(after,plan.context);return {page:after};
  }
  return {open,observe,checkNative,applyTerms,applyGrades,saveAndRead,restoreTerms};
}
