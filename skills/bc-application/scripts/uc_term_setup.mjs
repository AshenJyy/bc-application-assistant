/** One reversible school-term availability change; related course editors are read-only. */
import {createUcReview} from './uc_review.mjs';
import {createUcCourses} from './uc_courses.mjs';

export function createUcTermSetup(host) {
  const {observe:rawObserve,digest,structure,guard,writeObserved}=host;
  const review=createUcReview(host),courses=createUcCourses(host);
  const warningAttempts=new Map();
  const origin='https://apply.universityofcalifornia.edu';
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  const annotate=b=>({...b.school,uc_school_terms:{schema:'uc-school-terms/1',identity_sha256:b.school_identity_sha256},state_metadata:b.state_metadata});
  const gradeUrl=grade=>origin+'/my-application/acadHistFrGrades/'+grade;
  const expectedKeys=new Set([
    ...['startMonth','startYear','endMonth','endYear','hsDegreeSelect','gradMonth','gradYear','langOfInstruction',
      'specialCurr-carrpath','specialCurr-ib','specialCurr-magnet','specialCurr-other','onefinal','semester','Trimester','Quarter'].map(k=>'i:'+k),
    ...[0,1,2,3].flatMap(i=>['grade','syear','summer'].map(part=>`i:attend${part}${i}`)),
    ...['A','B','3','4','5','6','7','8','9','D','E','F','13','14','15','16','27','18','19','20','26','21','28','I','29','30','23','H','C','G'].map(k=>'i:grading_sys_'+k),
    'n:currentAcadHistFrHighSchool.graduationFlag']);

  function checkSchool(p,{post_alias=false}={}) {
    const url=new URL(p.url);
    const route=url.searchParams.get('action')==='edit'&&/^\d+$/.test(url.searchParams.get('schId')||'')&&
      Array.from(url.searchParams.keys()).sort().join(',')==='action,schId';
    if(url.origin!==origin||url.pathname!=='/my-application/acadHistFrInfo'||(!route&&!(post_alias&&url.search===''))||
       p.title!=='High school information - Academic history - UC application'||p.frames_present||p.collections?.length||p.scope||
       p.fields.length!==59||new Set(p.fields.map(f=>f.key)).size!==59||
       p.fields.some(f=>!expectedKeys.has(f.key)||!['select','radio','checkbox'].includes(f.control)||f.readonly||f.invalid||!f.selector||
         (f.control!=='radio'&&(f.selector!==`[id="${f.key.slice(2)}"]`||(f.selector_count??1)!==1||(f.selector_index??0)!==0))))
      throw Error('observed_uc_school_term_shape_required');
    const full=p.fields.find(f=>f.key==='i:onefinal');
    if(full.control!=='checkbox'||full.label!=='Full year (1 final grade per year)'||full.disabled||typeof full.value!=='boolean'||
       !p.fields.find(f=>f.key==='i:semester')?.value)
      throw Error('observed_uc_full_year_availability_required');
  }

  async function schoolIdentity(tab) {
    const identity=await tab.playwright.evaluate(()=>{
      const parts=Array.from(document.querySelectorAll('main fieldset,main [role="group"]'))
        .filter(e=>e.getClientRects().length&&/School code:/.test(e.innerText||''))
        .map(e=>(e.innerText||'').replace(/\s+/g,' ').trim());
      if(parts.length!==1||!parts[0])throw Error('unique_school_identity_required');
      return parts[0];
    });
    return digest(identity);
  }

  function associatedGrade(p) {
    const f=p.fields.find(f=>/^i:attendgrade\d$/.test(f.key)&&f.value);
    const label=f?.options.find(o=>o.value===f.value&&!o.disabled)?.label;
    if(!/^(9|10|11|12)th$/.test(label||''))throw Error('observed_associated_school_grade_required');
    return label.slice(0,-2).padStart(2,'0');
  }

  async function navigateGrade(tab,grade) {
    await tab.playwright.expectNavigation(()=>tab.playwright.getByRole('link',{name:`${Number(grade)}th grade section incomplete`,exact:true}).click(),
      {timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();await tab.playwright.waitForURL(gradeUrl(grade),{timeoutMs:10000});
    await tab.playwright.getByRole('heading',{name:`${Number(grade)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
  }

  async function openSchool(tab,schoolUrl) {
    const url=new URL(schoolUrl),relative=url.pathname+url.search;
    const edit=tab.playwright.getByRole('link',{name:'Edit',exact:true}).and(tab.playwright.locator(`a[href=${JSON.stringify(relative)}]`));
    if(await edit.count()!==1)throw Error('unique_observed_school_edit_required');
    await tab.playwright.expectNavigation(()=>edit.click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();await tab.playwright.waitForURL(schoolUrl,{timeoutMs:10000});
    await tab.playwright.getByRole('heading',{name:'High school information',exact:true}).waitFor({state:'visible',timeoutMs:10000});
  }

  async function readCourse(tab,grade) {
    const summary=await courses.readSummary(tab);
    const edit=tab.playwright.getByRole('link',{name:'Edit',exact:true}).and(tab.playwright.locator('a[href="JavaScript:Void(0);"]'));
    if(await edit.count()!==1)throw Error('unique_existing_course_edit_required');
    await tab.playwright.expectNavigation(()=>edit.click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.getByRole('heading',{name:`${Number(grade)}th grade - Enter courses & grades`,exact:true})
      .waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('[id="academics_hs_classes_add_0_subject"]').waitFor({state:'visible',timeoutMs:10000});
    const page=await rawObserve(tab);
    const a=page.actions.filter(a=>a.key==='i:cancel-btn'&&a.label==='Cancel'&&!a.disabled);
    if(a.length!==1||!page.url.startsWith(origin+'/my-application/acadHistFrHighSchoolClasses/editClasses/'+grade+'/'))
      throw Error('observed_read_only_course_cancel_required');
    await tab.playwright.expectNavigation(()=>tab.playwright.locator(a[0].selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.getByRole('heading',{name:`${Number(grade)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
    if(digest(await courses.readSummary(tab))!==digest(summary))throw Error('read_only_course_inspection_changed_summary');
    return {page,summary};
  }

  async function observe(tab,{allow_partial=false}={}) {
    // Only on a saved baseline. This cancels/reopens school/course forms.
    const school=await rawObserve(tab);checkSchool(school);const associated=associatedGrade(school);
    const school_identity_sha256=await schoolIdentity(tab);
    const cancel=school.actions.find(a=>a.key==='i:cancel-btn'&&a.label==='Cancel'&&!a.disabled);
    if(!cancel)throw Error('observed_school_cancel_required');
    await tab.playwright.expectNavigation(()=>tab.playwright.locator(cancel.selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.getByRole('heading',{name:'High schools',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    const related=[];
    for(const grade of ['09','10','11','12']) {
      await navigateGrade(tab,grade);
      try {related.push(await readCourse(tab,grade));}
      catch(error) {
        if(!allow_partial)throw error;
        // Return to a known summary through its actual sidebar before doing
        // anything else. Do not interact with any unknown course control.
        await navigateGrade(tab,grade);
        related.push({grade,inspection_failed:true});
      }
    }
    const auxiliary=await review.inspectEmptyComments(tab);
    const state=await review.collect(tab,school.url,async()=>{
      const edit=tab.playwright.getByRole('button').and(tab.playwright.locator(`a[href="${new URL(gradeUrl(associated)).pathname}"]`));
      if(!await edit.isVisible())await tab.playwright.getByRole('link',{name:/^Academic history(?: Section Complete)?$/}).click();
      await edit.waitFor({state:'visible',timeoutMs:10000});
      await tab.playwright.expectNavigation(()=>edit.click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
      await tab.playwright.domSnapshot();
      await tab.playwright.getByRole('heading',{name:`${Number(associated)}th grade`,exact:true}).waitFor({state:'visible',timeoutMs:10000});
      await openSchool(tab,school.url);
    });
    const after=await rawObserve(tab);checkSchool(after);
    if(digest(after)!==digest(school)||await schoolIdentity(tab)!==school_identity_sha256)throw Error('school_inspection_changed_saved_form');
    return {schema:'uc-school-term-bundle/1',school_identity_sha256,school:after,courses:related,auxiliary,state_metadata:state};
  }

  function prepared(plan,context,bundle,restoration=false) {
    checkSchool(bundle.school);review.checkState(bundle.state_metadata,bundle.school.url);review.checkEmptyComments(bundle.auxiliary);
    guard(context,annotate(bundle),origin,restoration);
    if(plan.schema!=='uc-school-term-plan/1'||!plan.ready||plan.page_url!==bundle.school.url||plan.system!=='uc'||
       plan.allowed_origin!==origin||context.journal_persisted!==true||context.real_account_test!==true||
       context.restoration_strategy?.kind!=='restore_uc_school_terms'||bundle.school_identity_sha256!==plan.school_identity_sha256)
      throw Error('prepared_school_term_test_required');
  }

  async function apply(tab,plan,context) {
    if(context.journal_persisted!==true)throw Error('prepared_school_term_test_required');
    const bundle=await observe(tab);prepared(plan,context,bundle);
    if(digest(bundle)!==plan.bundle_sha256||plan.writes.length!==1||plan.writes[0].field_key!=='i:onefinal'||
       plan.writes[0].value!==true||plan.writes[0].fact_ref!=='education.uc_ap_reporting_term')
      throw Error('prepared_single_full_year_availability_change_required');
    warningAttempts.set(plan.checkpoint_id||plan.page_url,0);
    await writeObserved(tab,bundle.school,plan.writes);
    const local={...bundle,school:await rawObserve(tab)};checkSchool(local.school);
    if(digest(structure(annotate(local)))!==plan.structure_sha256||digest(vals(local.school))!==plan.expected_values_sha256)
      throw Error('unexpected_school_values_after_term_selection');
    const danger=await tab.playwright.evaluate(()=>{
      const text=(document.querySelector('main')?.innerText||'').replace(/\s+/g,' ');
      return /(?:will|would|may) (?:be )?(?:delete|remove|erase|lose)|(?:courses|grades).{0,50}(?:deleted|erased|lost)/i.test(text)||
        Array.from(document.querySelectorAll('[role=alertdialog],[role=dialog]')).some(e=>e.getClientRects().length);
    });
    if(danger)throw Error('school_term_change_warning_requires_recovery_before_save');
    return local;
  }

  async function saveAndRead(tab,plan,context,local,restoration=false) {
    prepared(plan,context,local,restoration);
    const p=await rawObserve(tab);checkSchool(p);
    if(digest(structure(annotate({...local,school:p})))!==plan.structure_sha256||digest(vals(p))!==plan.expected_values_sha256)
      throw Error('prepared_school_term_values_required');
    const a=p.actions.find(a=>a.key===plan.save_action?.key);
    if(a?.key!=='i:save-btn'||a.label!=='Save & continue'||a.disabled||a.selector!=='[id="save-btn"]')
      throw Error('observed_school_draft_save_required');
    await tab.playwright.expectNavigation(()=>tab.playwright.locator(a.selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    const modal=tab.playwright.getByRole('dialog');
    if(await modal.isVisible()) {
      const text=(await modal.innerText()).replace(/\s+/g,' ').replace(/’/g,"'");
      if(!text.includes("If you change the grading system or term system for this school, you'll need to re-enter the grades received for the courses taken at this school.")||
         !text.includes('Are you sure you want to change the grading system or term system?'))
        throw Error('unknown_school_confirmation_recovery_preserved');
      // This port has no grade-reset/re-entry transaction. Decline the exact
      // warning, restore the local checkbox and cancel without another Save.
      await modal.getByRole('button',{name:'No',exact:true}).click();
      warningAttempts.set(plan.checkpoint_id||plan.page_url,1);
      // The connected browser may finish closing this modal only after this
      // host call returns. Return a transition, never a fabricated saved bundle.
      return {schema:'uc-school-warning/1',checkpoint_id:plan.checkpoint_id,
        requires_fresh_host_call:true,grade_reentry_required:true,availability_change_verified:false};
    }
    await tab.playwright.getByRole('heading',{name:'High schools',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await review.inspectEmptyComments(tab,local.auxiliary,true);
    const associated=associatedGrade(local.school);await navigateGrade(tab,associated);await openSchool(tab,plan.page_url);
    return {bundle:await observe(tab,{allow_partial:true}),revisited_after_save:true};
  }

  async function resumeWarningCancel(tab,recovery) {
    const {plan,context}=recovery,key=plan.checkpoint_id||plan.page_url;
    if(recovery.post_warning_cancel!==true||recovery.requires_fresh_ui_identity_verification!==true||
       !['edge','chrome'].includes(context.browser_family)||context.transport!=='extension'||context.origin!==origin||
       context.access_verified!==true||context.real_account_test!==true||context.full_state_restoration_verified!==true||
       context.journal_persisted!==true||context.restoration_strategy?.kind!=='restore_uc_school_terms'||
       context.restoration_strategy.page_url!==plan.page_url||plan.schema!=='uc-school-term-plan/1'||!plan.ready||
       plan.allowed_origin!==origin||digest(recovery.original_state_metadata)!==context.restoration_strategy.baseline_state_sha256||
       recovery.original_values_sha256!==plan.original_values_sha256)
      throw Error('persisted_school_warning_recovery_required');
    review.checkState(recovery.original_state_metadata,plan.page_url);
    if(![origin+'/my-application/acadHistFrInfo',plan.page_url].includes(await tab.url()))
      throw Error('known_school_post_warning_route_required');
    await tab.playwright.domSnapshot();
    const modal=tab.playwright.getByRole('dialog');
    if(await modal.isVisible()) {
      const text=(await modal.innerText()).replace(/\s+/g,' ').replace(/’/g,"'");
      if(!text.includes("If you change the grading system or term system for this school, you'll need to re-enter the grades received for the courses taken at this school.")||
         !text.includes('Are you sure you want to change the grading system or term system?'))
        throw Error('unknown_school_confirmation_recovery_preserved');
      const attempts=warningAttempts.get(key)??1;
      if(attempts>=2)throw Error('school_warning_not_closed_manual_handoff_required');
      await modal.getByRole('button',{name:'No',exact:true}).click();warningAttempts.set(key,attempts+1);
      return {schema:'uc-school-warning/1',checkpoint_id:plan.checkpoint_id,
        requires_fresh_host_call:true,grade_reentry_required:true,availability_change_verified:false};
    }
    const cancelled=await rawObserve(tab);checkSchool(cancelled,{post_alias:true});
    if(![origin+'/my-application/acadHistFrInfo',plan.page_url].includes(cancelled.url)||
       await schoolIdentity(tab)!==plan.school_identity_sha256||
       digest({...structure(cancelled),url:null})!==plan.native_shape_sha256)
      throw Error('school_post_warning_identity_changed_recovery_preserved');
    if(cancelled.fields.find(f=>f.key==='i:onefinal').value!==false)
      await writeObserved(tab,cancelled,[{field_key:'i:onefinal',value:false}]);
    if(digest(vals(await rawObserve(tab)))!==plan.original_values_sha256)throw Error('original_school_values_required');
    const cancel=cancelled.actions.find(a=>a.key==='i:cancel-btn'&&a.label==='Cancel'&&!a.disabled);
    if(!cancel)throw Error('observed_school_cancel_required');
    await tab.playwright.expectNavigation(()=>tab.playwright.locator(cancel.selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.getByRole('heading',{name:'High schools',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await navigateGrade(tab,associatedGrade(cancelled));await openSchool(tab,plan.page_url);
    return {bundle:await observe(tab,{allow_partial:true}),revisited_after_save:true,
      change_cancelled:true,grade_reentry_required:true,availability_change_verified:false};
  }

  async function restore(tab,recovery,{unsaved=false}={}) {
    const {plan,context,writes}=recovery;
    const p=await rawObserve(tab);checkSchool(p);
    const identity=await schoolIdentity(tab);
    if(writes.some(w=>w.field_key!=='i:onefinal'||w.value!==false)||digest(structure(annotate({school:p,school_identity_sha256:identity,state_metadata:recovery.original_state_metadata})))!==plan.structure_sha256)
      throw Error('known_school_checkbox_recovery_required');
    const local={school:p,school_identity_sha256:identity,auxiliary:plan.auxiliary,state_metadata:recovery.original_state_metadata};
    prepared(plan,context,local,true);
    await writeObserved(tab,p,writes);
    local.school=await rawObserve(tab);checkSchool(local.school);
    if(digest(vals(local.school))!==recovery.original_values_sha256)throw Error('original_school_values_required');
    if(unsaved)return {bundle:await observe(tab,{allow_partial:true}),revisited_after_save:true,restore_save_performed:false};
    if(!writes.length) {
      // No redundant school save. Repair only the already preflighted empty
      // auxiliary draft, then inspect all original pages and visible statuses.
      await review.inspectEmptyComments(tab,plan.auxiliary,true);
      await navigateGrade(tab,associatedGrade(local.school));await openSchool(tab,plan.page_url);
      return {bundle:await observe(tab,{allow_partial:true}),revisited_after_save:true,restore_save_performed:false};
    }
    return saveAndRead(tab,{...plan,expected_values_sha256:recovery.original_values_sha256},context,local,true);
  }
  return {observe,apply,saveAndRead,restore,resumeWarningCancel,checkSchool};
}
