/** Existing native UC course editors. Never creates/deletes rows or changes headers. */
import {createUcReview} from './uc_review.mjs';

export function createUcCourses(host) {
  const {observe:rawObserve,digest,structure,guard,writeObserved}=host;
  const review=createUcReview(host),origin='https://apply.universityofcalifornia.edu';
  const checkAuxiliary=review.checkEmptyComments,inspectComments=review.inspectEmptyComments;
  const labels={subject:'Subject Area/Course Category',class_title:'Course Name',honors:'Honor Type',
    grade_system:'Grading System',grade1:'Grade 1',grade2:'Grade 2',grade1Other:'Grade 1',
    grade2Other:'Grade 2',subject_language_code:'Language Name',term:'Term System'};
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  const summaryPattern=/^https:\/\/apply\.universityofcalifornia\.edu\/my-application\/acadHistFrGrades\/(09|10|11|12)$/;
  const editorPattern=/^https:\/\/apply\.universityofcalifornia\.edu\/my-application\/acadHistFrHighSchoolClasses\/editClasses\/(09|10|11|12)\/[0-9]+$/;


  function checkPage(p) {
    const c=p.uc_course_editor,parent=p.uc_course_parent,match=editorPattern.exec(p.url);
    const columns=['Subject area/Course category','Course name','Hnrs','Term','G1','G2','G3','G4','Language name'];
    if(c?.columns?.includes('GRDG System'))columns.splice(4,0,'GRDG System');
    if(!match||p.title!=='Enter HS classes - Academic history - UC application'||p.frames_present||p.collections?.length||p.scope||
       c?.schema!=='uc-course-editor/1'||c.grade!==match[1]||c.summary_url!==origin+'/my-application/acadHistFrGrades/'+c.grade||
       !Number.isInteger(c.row_count)||c.row_count<1||c.row_count>100||!/^\d{4} - \d{4} academic year$/.test(c.year)||
       !/^[a-f0-9]{64}$/.test(c.context_sha256)||digest(c.columns)!==digest(columns)||
       c.row_terms?.length!==c.row_count||c.row_terms.some(t=>!['Semester','Full year'].includes(t))||
       parent?.schema!=='uc-course-parent/1'||parent.url!==c.summary_url||parent.row_count!==c.row_count||
       parent.context_sha256!==c.context_sha256||!/^[a-f0-9]{64}$/.test(parent.summary_sha256))
      throw Error('observed_uc_course_context_required');
    const rows=new Map();
    for(const f of p.fields) {
      const m=/^i:academics_hs_classes_add_(\d+)_(\w+)$/.exec(f.key),suffix=m?.[2];
      if(!m||Number(m[1])>=c.row_count||!Object.hasOwn(labels,suffix)||f.label!==labels[suffix]||f.disabled||f.readonly||
         f.control!==(['class_title','grade1Other','grade2Other'].includes(suffix)?'text':'select')||
         f.selector!==`[id="${f.key.slice(2)}"]`||(f.selector_count??1)!==1||(f.selector_index??0)!==0)
        throw Error('observed_uc_course_fields_required');
      if(!rows.has(Number(m[1])))rows.set(Number(m[1]),new Set());
      rows.get(Number(m[1])).add(suffix);
    }
    if(rows.size!==c.row_count||new Set(p.fields.map(f=>f.key)).size!==p.fields.length)throw Error('observed_uc_course_rows_required');
    for(let i=0;i<c.row_count;i++) {
      const row=rows.get(i);
      if(!row||!['subject','class_title','honors'].every(k=>row.has(k))||
         row.has('grade_system')!==c.columns.includes('GRDG System')||
         ['grade1','grade1Other'].filter(k=>row.has(k)).length!==1||
         ['grade2','grade2Other'].filter(k=>row.has(k)).length!==Number(c.row_terms[i]==='Semester'))
        throw Error('observed_uc_course_rows_required');
    }
    if(p.fields.some(f=>f.key.endsWith('_term')))for(let i=0;i<c.row_count;i++) {
      const f=p.fields.find(f=>f.key===`i:academics_hs_classes_add_${i}_term`);
      if(!f||f.value!==(c.row_terms[i]==='Full year'?'F':'S')||
         digest(f.options.map(o=>[o.value,o.label]))!==digest([['','--'],['F','Full'],['S','Semester']]))
        throw Error('observed_uc_course_terms_required');
    }
  }

  async function readSummary(tab,{include_rows=false}={}) {
    const url=await tab.url(),match=summaryPattern.exec(url);
    if(!match)throw Error('observed_uc_grade_summary_required');
    const data=await tab.playwright.evaluate(()=>{
      const text=e=>(e?.innerText||'').replace(/\s+/g,' ').trim();
      const main=document.querySelector('main'),headings=Array.from(main?.querySelectorAll('h2')||[]);
      const years=Array.from(main?.querySelectorAll('h3')||[]),tables=Array.from(main?.querySelectorAll('table')||[]);
      const edit=Array.from(main?.querySelectorAll('a')||[]).filter(a=>text(a)==='Edit'&&a.getAttribute('href')==='JavaScript:Void(0);');
      if(!main||headings.length!==1||years.length!==1||tables.length!==1||edit.length!==1)
        throw Error('single_existing_uc_school_year_required');
      const table=tables[0],columns=Array.from(table.querySelectorAll('th')).map(text);
      const rows=Array.from(table.querySelectorAll('tr')).filter(r=>r.querySelectorAll('td').length)
        .map(r=>Array.from(r.querySelectorAll('td')).map(text));
      if(!columns.length||!rows.length||rows.some(r=>r.length!==columns.length))throw Error('observed_uc_summary_columns_required');
      return {heading:text(main.querySelector('h1')),school:text(headings[0]),year:text(years[0]),
        lists:Array.from(main.querySelectorAll('ul')).map(text),columns,rows};
    });
    if(data.heading!==`${Number(match[1])}th grade`)throw Error('uc_summary_grade_mismatch');
    const context_sha256=digest({heading:data.heading,school:data.school,year:data.year,lists:data.lists});
    const c={schema:'uc-course-editor/1',grade:match[1],summary_url:url,year:data.year,context_sha256,
      columns:data.columns,row_count:data.rows.length,row_terms:data.rows.map(r=>{
        const term=r[data.columns.indexOf('Term')];return term==='Full'?'Full year':term;
      })};
    const parent={schema:'uc-course-parent/1',url,context_sha256,row_count:c.row_count,summary_sha256:digest(data)};
    return {context:c,parent,rows_sha256:digest({columns:data.columns,rows:data.rows}),
      ...(include_rows?{cells:{columns:data.columns,rows:data.rows}}:{})};
  }

  async function openEditor(tab,summary) {
    await tab.playwright.expectNavigation(()=>tab.playwright.getByRole('link',{name:'Edit',exact:true})
      .and(tab.playwright.locator('a[href="JavaScript:Void(0);"]')).press('Enter'),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.getByRole('heading',{name:`${Number(summary.context.grade)}th grade - Enter courses & grades`,exact:true})
      .waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('[id="academics_hs_classes_add_0_subject"]').waitFor({state:'visible',timeoutMs:10000});
    const p={...await rawObserve(tab),uc_course_editor:summary.context,uc_course_parent:summary.parent};checkPage(p);return p;
  }

  async function open(tab) {return openEditor(tab,await readSummary(tab));}


  async function cancel(tab) {
    const p=await rawObserve(tab),a=p.actions.filter(a=>a.key==='i:cancel-btn'&&a.label==='Cancel'&&!a.disabled);
    if(!editorPattern.test(p.url)||a.length!==1)throw Error('observed_uc_course_cancel_required');
    await tab.playwright.expectNavigation(()=>tab.playwright.locator(a[0].selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.getByRole('heading',{name:`${Number(editorPattern.exec(p.url)[1])}th grade`,exact:true})
      .waitFor({state:'visible',timeoutMs:10000});
    return readSummary(tab);
  }

  async function observe(tab) {
    // This inspection deliberately cancels/reopens a saved editor. Never call
    // it on unsaved changes: use apply's local result or unsaved recovery.
    const before=await rawObserve(tab),summary=await cancel(tab);
    const page={...before,uc_course_editor:summary.context,uc_course_parent:summary.parent};checkPage(page);
    const auxiliary=await inspectComments(tab);
    let reopened;
    const state=await review.collect(tab,page.url,async()=>{
      const edit=tab.playwright.getByRole('button',{name:'Edit grade',exact:true})
        .and(tab.playwright.locator(`a[href="${new URL(summary.context.summary_url).pathname}"]`));
      if(!await edit.isVisible())await tab.playwright.getByRole('link',{name:/^Academic history(?: Section Complete)?$/}).click();
      await edit.waitFor({state:'visible',timeoutMs:10000});await edit.press('Enter');
      await tab.playwright.getByRole('heading',{name:`${Number(summary.context.grade)}th grade`,exact:true})
        .waitFor({state:'visible',timeoutMs:10000});
      reopened=await open(tab);
    });
    if(digest(reopened)!==digest(page))throw Error('uc_course_inspection_changed_saved_editor');
    return {...reopened,uc_academic_auxiliary:auxiliary,state_metadata:state};
  }

  function prepared(plan,context,p,restoration=false) {
    checkPage(p);checkAuxiliary(p.uc_academic_auxiliary);review.checkState(p.state_metadata,p.url);guard(context,p,origin,restoration);
    if(!plan.ready||plan.system!=='uc'||plan.allowed_origin!==origin||plan.page_url!==p.url||context.journal_persisted!==true)
      throw Error('prepared_uc_course_checkpoint_required');
  }

  async function apply(tab,plan,context) {
    if(context.journal_persisted!==true)throw Error('prepared_uc_course_checkpoint_required');
    const p=await observe(tab);prepared(plan,context,p);
    if(digest(p)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
    // Header/term/classification mutations can reconstruct grade controls. This
    // port intentionally edits existing names/marks and reaffirms classifications.
    if(plan.writes.some(w=>!/_class_title$|_grade[12](?:Other)?$/.test(w.field_key)&&
       w.value!==p.fields.find(f=>f.key===w.field_key)?.value))throw Error('uc_course_reconfiguration_requires_workflow');
    await writeObserved(tab,p,plan.writes);
    const local={...await rawObserve(tab),uc_course_editor:p.uc_course_editor,uc_course_parent:p.uc_course_parent,
      uc_academic_auxiliary:p.uc_academic_auxiliary,state_metadata:p.state_metadata};
    checkPage(local);
    if(digest(structure(local))!==plan.structure_sha256||digest(vals(local))!==plan.expected_values_sha256||local.fields.some(f=>f.invalid))
      throw Error('unexpected_uc_course_page_after_input');
    return local;
  }

  async function saveAndRead(tab,plan,context,local,restoration=false) {
    prepared(plan,context,local,restoration);
    const p={...await rawObserve(tab),uc_course_editor:local.uc_course_editor,uc_course_parent:local.uc_course_parent,
      uc_academic_auxiliary:local.uc_academic_auxiliary,state_metadata:local.state_metadata};
    checkPage(p);
    if(digest(structure(p))!==plan.structure_sha256||digest(vals(p))!==plan.expected_values_sha256||p.fields.some(f=>f.invalid))
      throw Error('prepared_uc_course_values_required');
    const a=p.actions.find(a=>a.key===plan.save_action?.key);
    if(a?.key!=='i:save'||a.disabled||a.label!=='Save & continue'||a.label!==plan.save_action.label)
      throw Error('observed_uc_course_draft_save_required');
    await tab.playwright.expectNavigation(()=>tab.playwright.locator(a.selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await tab.playwright.waitForURL(local.uc_course_editor.summary_url,{timeoutMs:10000});
    await tab.playwright.getByRole('heading',{name:`${Number(local.uc_course_editor.grade)}th grade`,exact:true})
      .waitFor({state:'visible',timeoutMs:10000});
    if(context.real_account_test)await inspectComments(tab,local.uc_academic_auxiliary,true);
    // Save may advance to another grade. Return through the observed sidebar.
    await tab.playwright.getByRole('link',{name:`${Number(local.uc_course_editor.grade)}th grade section incomplete`,exact:true}).press('Enter');
    await tab.playwright.getByRole('heading',{name:`${Number(local.uc_course_editor.grade)}th grade`,exact:true})
      .waitFor({state:'visible',timeoutMs:10000});
    await open(tab);
    return {page:await observe(tab),revisited_after_save:true};
  }

  async function restore(tab,plan,writes,context,options={}) {
    if(options.unsaved===true) {
      const local={...await rawObserve(tab),uc_course_editor:plan.uc_course_editor,
        uc_course_parent:plan.uc_course_parent,uc_academic_auxiliary:plan.uc_academic_auxiliary,state_metadata:options.original_state_metadata};
      prepared(plan,context,local,true);
      if(digest(local.state_metadata)!==context.restoration_strategy.baseline_state_sha256||
         digest(local.uc_course_parent)!==context.restoration_strategy.baseline_parent_sha256||
         digest(structure(local))!==plan.structure_sha256||!/^[a-f0-9]{64}$/.test(options.original_values_sha256||''))
        throw Error('original_uc_course_baseline_required');
      await writeObserved(tab,local,writes);
      const p=await rawObserve(tab);
      if(digest(vals(p))!==options.original_values_sha256||p.fields.some(f=>f.invalid))throw Error('original_uc_unsaved_course_values_required');
      return {page:await observe(tab),revisited_after_save:true,restore_save_performed:false};
    }
    const p=await observe(tab);prepared(plan,context,p,true);
    if(digest(structure(p))!==plan.structure_sha256)throw Error('restoration_structure_changed_handoff_required');
    if(!writes.length)return {page:p,revisited_after_save:true,restore_save_performed:false};
    await writeObserved(tab,p,writes);
    const local={...await rawObserve(tab),uc_course_editor:p.uc_course_editor,uc_course_parent:p.uc_course_parent,
      uc_academic_auxiliary:p.uc_academic_auxiliary,state_metadata:p.state_metadata};
    return saveAndRead(tab,{...plan,expected_values_sha256:digest(vals(local))},context,local,true);
  }
  return {open,observe,apply,saveAndRead,restore,checkPage,readSummary};
}
