/** Native-form capability over the existing observer/writer/saved reader. */
export function createGenericForms(host,{knownFields=[],dialog=false}={}){
  const values=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  let identities=knownFields;
  const observe=async tab=>{const page=await host.observe(tab,{generic_form:true,generic_dialog:dialog,generic_identity_fields:identities});identities=page.fields;return page;};
  function eligible(page,plan,context){
    host.guard(context,page,plan.allowed_origin);
    if(!page.generic_form||!plan.generic_form||!plan.ready||context.journal_persisted!==true||plan.target_id!==context.target_id||
      page.url!==plan.page_url||!Array.isArray(plan.semantic_bindings))throw Error('prepared_generic_plan_required');
  }
  async function apply(tab,plan,context){
    let page=await observe(tab);eligible(page,plan,context);
    if(host.digest(page)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
    for(const write of plan.writes){
      const binding=plan.semantic_bindings.find(b=>b.key===write.field_key&&b.ref===write.fact_ref&&b.role==='factual');
      if(!binding)throw Error('prepared_semantic_source_binding_required');
      await host.writeObserved(tab,page,[write],{semantic_bindings:plan.semantic_bindings});
      if(host.waitForGenericLoader)await host.waitForGenericLoader(tab);
      try {page=await observe(tab);}catch(error){
        // An AJAX form can briefly expose its loading dialog. Reobserve once
        // after a fresh documented snapshot; never repeat the input or dismiss it.
        if(!String(error.message).includes('single_native_form_required'))throw error;
        const busy=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('[role=dialog]'))
          .filter(e=>e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility)&&
            !(e.innerText||'').trim()&&!e.querySelector('button,input,select,textarea,a,[role=button]'))
          .map(e=>e.id).filter(Boolean));
        if(Array.isArray(busy)&&busy.length===1)await tab.playwright.locator(`[id="${busy[0].replaceAll('\\','\\\\').replaceAll('"','\\"')}"]`).waitFor({state:'hidden',timeoutMs:10000});
        else if(typeof tab.getAXState==='function')await tab.getAXState({emit:false});
        else await tab.playwright.domSnapshot();
        page=await observe(tab);
      }
      if(host.digest(host.structure(page))!==plan.structure_sha256||plan.generic_stage&&host.digest(values(page))!==plan.expected_values_sha256)return {status:'page_changed',page,save_performed:false};
    }
    if(page.fields.some(f=>f.invalid)||host.digest(values(page))!==plan.expected_values_sha256)throw Error('whole_generic_page_values_required');
    return {status:'filled',page,save_performed:false};
  }
  async function saveAndRead(tab,plan,context){
    if(plan.generic_stage)throw Error('branch_discovery_cannot_save');
    const page=await observe(tab);eligible(page,plan,context);
    return host.saveAndRead(tab,{...plan,generic_identity_fields:identities},context);
  }
  async function saveDraft(tab,plan,context){
    if(plan.generic_stage)throw Error('branch_discovery_cannot_save');
    const page=await observe(tab);eligible(page,plan,context);
    return host.saveGenericDraft(tab,{...plan,generic_identity_fields:identities},context);
  }
  async function saveAndContinue(tab,plan,context){
    if(plan.saved_page_readback!==false)throw Error('explicit_readback_opt_out_plan_required');
    return saveDraft(tab,plan,context);
  }
  async function cancelUnsaved(tab,plan,context){
    if(dialog)throw Error('dialog_cancel_requires_independent_original_state');
    const page=await observe(tab);eligible(page,plan,context);
    await tab.reload();await tab.playwright.locator('form').filter({visible:true}).waitFor({state:'visible',timeoutMs:10000});
    return {page:await observe(tab),revisited_saved_draft:true};
  }
  return {observe,apply,saveAndRead,saveDraft,saveAndContinue,cancelUnsaved};
}
