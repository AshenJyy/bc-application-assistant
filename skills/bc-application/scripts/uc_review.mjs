/** Shared UC visible review/draft collector. Call only on saved pages. */
export function createUcReview(host) {
  const {digest,structure,observe:rawObserve}=host;
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  const origin='https://apply.universityofcalifornia.edu';
  const reviewUrl=origin+'/my-application/reviewSubmit',statusUrl=origin+'/my-application/appStatus';
  const term='Fall quarter/semester 2027';
  const sections=['About you','Campuses & majors','Academic history','Test scores','Activities & awards',
    'Scholarships & support programs','Personal insight'];
  function checkState(state, pageUrl) {
    if(state?.schema!=='observed-state/1'||state.coverage!=='uc_visible_review_and_draft'||state.page_url!==pageUrl||
       state.review_url!==reviewUrl||state.status_url!==statusUrl||state.term!==term||state.draft_marker!=='Open application'||
       !Array.isArray(state.sections)||state.sections.length!==7||
       digest(state.sections.map(s=>s.label).sort())!==digest([...sections].sort()))throw Error('observed_uc_review_state_required');
    const hrefs=[];
    for(const section of state.sections) {
      if(!['','Section Complete'].includes(section.completion_text)||!Array.isArray(section.pages)||!section.pages.length)
        throw Error('observed_uc_review_state_required');
      for(const item of section.pages) {
        if(!/^\/my-application\/[a-zA-Z0-9/-]+(?:\?testType=\d+)?$/.test(item.href)||!/^(Edit|To do) .{1,150}$/.test(item.label))
          throw Error('observed_uc_review_state_required');
        hrefs.push(item.href);
      }
    }
    if(new Set(hrefs).size!==hrefs.length)throw Error('observed_uc_review_state_required');
  }


  async function goReview(tab) {
    await tab.playwright.getByRole('link',{name:'Review & submit',exact:true}).press('Enter');
    await tab.playwright.getByRole('heading',{name:'Review & submit',exact:true}).waitFor({state:'visible',timeoutMs:10000});
  }


  async function collect(tab,pageUrl,returnToPage) {
    const links=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('a[href]')).map(a=>a.getAttribute('href')));
    if(!links.includes('/my-application/reviewSubmit')||!links.includes('/my-application/appStatus'))
      throw Error('observed_uc_status_links_required');
    let state;
    {
      await goReview(tab);
      const expand=tab.playwright.getByRole('link',{name:'Expand all',exact:true});
      if(await expand.count()===1)await expand.click();
      else if(await tab.playwright.getByRole('link',{name:'Collapse all',exact:true}).count()!==1)
        throw Error('observed_uc_review_expansion_required');
      await tab.playwright.getByRole('button',{name:'Edit Personal information',exact:true}).waitFor({state:'visible',timeoutMs:10000});
      const review=await tab.playwright.evaluate(()=>{
        const text=e=>(e?.innerText||'').replace(/\s+/g,' ').trim(),visible=e=>!!e.getClientRects().length;
        const termHeadings=Array.from(document.querySelectorAll('h2')).filter(e=>visible(e)&&/^Fall quarter\/semester \d{4}$/.test(text(e)));
        if(termHeadings.length!==1)throw Error('unique_observed_uc_term_required');
        const sections=Array.from(document.querySelectorAll('section')).filter(s=>s.querySelector(':scope > h3.section-header')).map(s=>{
          const heading=text(s.querySelector(':scope > h3.section-header')),complete=heading.endsWith(' Section Complete');
          const content=s.querySelector(':scope > .section-content');
          if(!content||!visible(content))throw Error('expanded_uc_review_sections_required');
          const pages=Array.from(content.querySelectorAll('[role=button]')).filter(visible).map(a=>({href:a.getAttribute('href'),label:text(a)}));
          return {label:complete?heading.slice(0,-' Section Complete'.length):heading,
            completion_text:complete?'Section Complete':'',pages};
        });
        return {term:text(termHeadings[0]),sections};
      });
      if(await tab.url()!==reviewUrl)throw Error('uc_review_navigation_unverified');
      await tab.playwright.getByRole('link',{name:'Application status',exact:true}).press('Enter');
      await tab.playwright.getByRole('heading',{name:'Application status',exact:true}).waitFor({state:'visible',timeoutMs:10000});
      const draft=await tab.playwright.evaluate(()=>{
        const visible=e=>!!e.getClientRects().length,text=e=>(e.innerText||'').replace(/\s+/g,' ').trim();
        const markers=Array.from(document.querySelectorAll('main .title-link')).filter(e=>visible(e)&&!e.closest('h2')).map(text);
        const terms=Array.from(document.querySelectorAll('main h2 a')).filter(visible).map(text);
        if(markers.length!==1||markers[0]!=='Open application'||terms.length!==1)throw Error('unique_open_uc_application_required');
        return {draft_marker:markers[0],term:terms[0]};
      });
      if(draft.term!==term||draft.term!==review.term||await tab.url()!==statusUrl)throw Error('uc_draft_term_unverified');
      state={schema:'observed-state/1',coverage:'uc_visible_review_and_draft',page_url:pageUrl,
        review_url:reviewUrl,status_url:statusUrl,...review,draft_marker:draft.draft_marker};checkState(state,pageUrl);
      // appStatus clears the selected draft. Reopen the observed term link before
      // returning; directly guessing a form route would bounce back to appStatus.
      await tab.playwright.getByRole('link',{name:term,exact:true}).press('Enter');
      await tab.playwright.waitForURL(reviewUrl,{timeoutMs:10000});
      await tab.playwright.getByRole('heading',{name:'Review & submit',exact:true}).waitFor({state:'visible',timeoutMs:10000});
      await returnToPage(tab);
    }
    return state;
  }
  function checkAuxiliary(aux) {
    if(aux?.schema!=='uc-empty-comments/1'||aux.page_url!==origin+'/my-application/acadHistAddInformation'||
       aux.values_sha256!==digest({'i:additional_comments':''})||!/^[a-f0-9]{64}$/.test(aux.structure_sha256))
      throw Error('observed_empty_uc_comments_baseline_required');
  }

  async function inspectComments(tab,expected=null,save=false) {
    // UC invalidates this page's completion after a course save. Preflight its
    // complete empty form before the first course write; never send narrative.
    await tab.playwright.getByRole('link',{name:'Additional information section incomplete',exact:true}).press('Enter');
    await tab.playwright.getByRole('heading',{name:'Additional information',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('[id="additional_comments"]').waitFor({state:'visible',timeoutMs:10000});
    const p=await rawObserve(tab),f=p.fields[0],a=p.actions[0];
    if(p.url!==origin+'/my-application/acadHistAddInformation'||p.title!=='Additional information - Academic history - UC application'||
       p.frames_present||p.collections?.length||p.fields.length!==1||f.key!=='i:additional_comments'||
       f.label!=='additional comments'||f.control!=='textarea'||f.value!==''||f.required||f.invalid||f.disabled||f.readonly||
       f.selector!=='[id="additional_comments"]'||(f.selector_count??1)!==1||(f.selector_index??0)!==0||
       p.actions.length!==1||a.key!=='i:save-btn'||a.label!=='Save & continue'||a.disabled||a.selector!=='[id="save-btn"]')
      throw Error('empty_optional_uc_comments_required');
    const aux={schema:'uc-empty-comments/1',page_url:p.url,structure_sha256:digest(structure(p)),values_sha256:digest(vals(p))};
    if(expected&&digest(aux)!==digest(expected))throw Error('uc_comments_changed_since_preparation');
    if(save) {
      if(!expected)throw Error('prepared_uc_comments_baseline_required');
      await tab.playwright.expectNavigation(()=>tab.playwright.locator(a.selector).click(),{timeoutMs:10000,waitUntil:'domcontentloaded'});
      await tab.playwright.domSnapshot();
      await tab.playwright.waitForURL(origin+'/my-application/acadHistReview',{timeoutMs:10000});
      await tab.playwright.getByRole('heading',{name:'Review',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    }
    return aux;
  }

  return {collect,checkState,goReview,checkEmptyComments:checkAuxiliary,inspectEmptyComments:inspectComments};
}
