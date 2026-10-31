/** MIT's factual STEM page, using only documented host locators and visible DOM.
 * Inject host_browser.mjs exports; there is no independent browser driver.
 * observe() navigates read-only review/portal pages, so never call it on an
 * unsaved draft. apply() returns a local observation for saveAndRead().
 */
export function createMitCoursework(host) {
  const {observe:rawObserve,digest,structure,guard,writeObserved}=host;
  const origin='https://apply.mitadmissions.org';
  const reviewUrl=origin+'/apply/review',portalUrl=origin+'/portal/apply';
  const subjects=['calculus','physics','biology','chemistry'];
  const classesHeader='Subject Category | Year Taken | Level | Class Name | Grade Received';
  const classesInstruction='This section is only required for students in the U.S. or who attend U.S.-based school systems. Report all classes you have taken or will take in high school or for high school credit.';
  const stemInstruction='All students are required to fill out this section. Please indicate the status and year taken (or to be taken) of each class listed below. If you took these classes in a year that is not listed, or you did not take the class, you can leave the year blank. If you have taken a class multiple times, please list the year you most recently took it.';
  const noteLabels=[
    'List any course(s) with standardized exams (A-level, Baccalauréat, CAPEs, etc.) taken or underway. (If you have taken the exam, please list the test date and score.) Advanced Placement or International Baccalaureate exams should be reported on the next page.',
    "If there is anything we should know about your school's course offerings, extenuating circumstances regarding your coursework or access to standardized testing, or school's grading system, please use the space below.optional; 100 words or fewer"
  ];
  const normalize=s=>s.toLowerCase().replace(/optional.*$/,'').replace(/[^a-z0-9]+/g,' ').trim();
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

  function checkPage(page) {
    const url=new URL(page.url),ctx=page.mit_coursework,pairs=ctx?.subject_year_pairs;
    if(url.origin!==origin||url.pathname!=='/apply/frm'||!/^\?[a-f0-9-]{36}$/.test(url.search)||
       page.title!=='Self-reported coursework'||page.frames_present||ctx?.schema!=='mit-coursework/1'||
       !Array.isArray(pairs)||pairs.length!==4||new Set(pairs.map(p=>p.subject)).size!==4||
       pairs.some(p=>!subjects.includes(p.subject))||page.fields.length!==10||
       ctx.classes_instruction!==classesInstruction||ctx.stem_instruction!==stemInstruction)
      throw Error('observed_mit_coursework_page_required');
    const used=[];
    for(const pair of pairs) {
      for(const part of ['status','year']) {
        const f=page.fields.find(f=>f.key===pair[part+'_key']);used.push(f?.key);
        const labels=(f?.options||[]).filter(o=>o.value).map(o=>o.label).sort();
        const expected=part==='status'?['Taken','In progress/will take','Will not take']:['9th','10th','11th','12th'];
        if(!f||f.control!=='select'||f.disabled||f.readonly||!f.selector||
           normalize(f.label)!==(part==='status'?pair.subject:'year')||digest(labels)!==digest(expected.sort()))
          throw Error('observed_mit_subject_pairs_required');
      }
    }
    if(new Set(used).size!==8)throw Error('observed_mit_subject_pairs_required');
    const notes=page.fields.filter(f=>!used.includes(f.key));
    if(notes.length!==2||notes.some(f=>f.control!=='textarea'||f.value!==''||f.required||f.invalid)||
       digest(notes.map(f=>normalize(f.label)).sort())!==digest(noteLabels.map(normalize).sort()))
      throw Error('untouched_empty_mit_notes_required');
    if(digest(page.collections)!==digest([{kind:'editable_table',label:classesHeader,row_count:0,editor_control_count:1}]))
      throw Error('empty_observed_mit_classes_required');
  }

  function policy(plan) {
    const p=plan.collection_policy;
    if(plan.system!=='mit'||!plan.ready||plan.allowed_origin!==origin||p?.allowed!==true||
       p.kind!=='mit_non_us_empty_classes'||digest(p.fact_ids)!==digest([
         'education.current_school_country','education.us_based_school_system']))
      throw Error('prepared_mit_non_us_policy_required');
  }

  async function observe(tab) {
    const before=await rawObserve(tab);checkPage(before);
    // These are actual public links, not generated query UUIDs or private state.
    const links=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('[role=navigation] a')).map(a=>a.getAttribute('href')));
    if(!links.includes('review')||!links.includes('/portal/apply'))throw Error('observed_mit_status_links_required');
    let state;
    try {
      await tab.goto(reviewUrl);
      await tab.playwright.getByRole('heading',{name:'Review and submit',exact:true}).waitFor({state:'visible',timeoutMs:10000});
      const review=await tab.playwright.evaluate(()=>{
        const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
        const visible=e=>!!e.getClientRects().length;
        const tables=Array.from(document.querySelectorAll('table')).filter(visible);
        const take=header=>{
          const matching=tables.filter(t=>Array.from(t.querySelectorAll('thead th')).map(text).join(' | ')===header);
          if(matching.length!==1)throw Error('observed_mit_review_tables_required');
          return Array.from(matching[0].querySelectorAll('tbody tr')).map(row=>{
            const cells=row.querySelectorAll('td'),a=cells[0]?.querySelector('a');
            if(cells.length!==2||!a)throw Error('observed_mit_review_row_required');
            return {section:text(a),message:text(cells[1]),href:a.getAttribute('href')};
          });
        };
        return {errors:take('Section | Required Field or Error'),warnings:take('Section | Warning')};
      });
      if(await tab.url()!==reviewUrl)throw Error('mit_review_navigation_unverified');
      await tab.goto(portalUrl);
      await tab.playwright.getByRole('heading',{name:'MIT application portal',exact:true}).waitFor({state:'visible',timeoutMs:10000});
      const application_status=await tab.playwright.evaluate(()=>{
        const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
        const tables=Array.from(document.querySelectorAll('table')).filter(t=>Array.from(t.querySelectorAll('thead th')).map(text).join(' | ')==='Your Applications | Type | Status | Started | Submitted');
        const rows=tables.flatMap(t=>Array.from(t.querySelectorAll('tbody tr'))).filter(r=>text(r.querySelector('td a'))==='First-Year Application');
        if(rows.length!==1||rows[0].querySelectorAll('td').length!==4)throw Error('unique_mit_draft_required');
        const cells=rows[0].querySelectorAll('td');
        if(text(cells[3])||text(cells[1])!=='In Progress')throw Error('unsubmitted_mit_draft_required');
        return text(cells[1]);
      });
      if(await tab.url()!==portalUrl)throw Error('mit_portal_navigation_unverified');
      state={schema:'observed-state/1',coverage:'mit_visible_review_and_draft',page_url:before.url,
        review_url:reviewUrl,portal_url:portalUrl,application_status,...review};
    } finally {
      await tab.goto(before.url);
      await tab.playwright.getByRole('heading',{name:'Self-reported coursework',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    }
    const after=await rawObserve(tab);checkPage(after);
    if(digest(before)!==digest(after))throw Error('mit_status_inspection_changed_coursework');
    return {...after,state_metadata:state};
  }

  async function apply(tab,plan,context) {
    policy(plan);
    if(context.journal_persisted!==true)throw Error('persisted_ready_checkpoint_required');
    const page=await observe(tab);guard(context,page,origin);
    if(digest(page)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
    const keys=page.mit_coursework.subject_year_pairs.flatMap(p=>[p.status_key,p.year_key]);
    if(plan.writes.some(w=>!keys.includes(w.field_key)))throw Error('mit_stem_fields_only');
    await writeObserved(tab,page,plan.writes);
    const after=await rawObserve(tab);checkPage(after);
    if(digest(structure(after))!==plan.structure_sha256)throw Error('conditional_page_changed_collect_before_save');
    if(after.fields.some(f=>f.invalid)||digest(vals(after))!==plan.expected_values_sha256)throw Error('unexpected_page_values_before_save');
    return {...after,state_metadata:page.state_metadata};
  }

  async function saveAndRead(tab,plan,context,local,restoration=false) {
    policy(plan);checkPage(local);guard(context,local,origin,restoration);
    const page=await rawObserve(tab);checkPage(page);
    if(context.journal_persisted!==true||digest(structure(page))!==plan.structure_sha256||
       digest(vals(page))!==plan.expected_values_sha256||page.fields.some(f=>f.invalid))
      throw Error('prepared_mit_page_values_required');
    const a=page.actions.find(a=>a.key===plan.save_action?.key);
    if(page.actions.length!==1||!a||a.disabled||a.label!=='Save and Continue'||a.label!==plan.save_action.label)
      throw Error('unique_mit_draft_save_required');
    const button=a.selector?tab.playwright.locator(a.selector):tab.playwright.getByRole('button',{name:a.label,exact:true});
    // Keyboard activation avoids Slate's click/navigation focus race.
    await button.press('Enter');
    await tab.playwright.domSnapshot();
    if(await tab.url()===page.url)await tab.reload();else await tab.goto(page.url);
    await tab.playwright.getByRole('heading',{name:'Self-reported coursework',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    return {page:await observe(tab),revisited_after_save:true};
  }

  async function restore(tab,plan,writes,context) {
    policy(plan);
    const page=await observe(tab);guard(context,page,origin,true);
    if(context.journal_persisted!==true||digest(structure(page))!==plan.structure_sha256)
      throw Error('restoration_structure_changed_handoff_required');
    const keys=page.mit_coursework.subject_year_pairs.flatMap(p=>[p.status_key,p.year_key]);
    if(writes.some(w=>!keys.includes(w.field_key)))throw Error('mit_stem_fields_only');
    if(!writes.length)return {page,revisited_after_save:true,restore_save_performed:false};
    await writeObserved(tab,page,writes);
    const local={...await rawObserve(tab),state_metadata:page.state_metadata};
    return saveAndRead(tab,{...plan,expected_values_sha256:digest(vals(local))},context,local,true);
  }

  return {observe,apply,saveAndRead,restore,checkPage};
}
