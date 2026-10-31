/** Connected intended-update workflow. Caller supplies documented ports/CLI relay.
 * No browser launch, external service, secondary profile or final application action.
 */
export function createCommonWorkflow({host,schools,academic,relay,inspectSaved,onEvent=()=>{}}) {
  if(!host||!schools||!academic||typeof relay!=='function'||typeof inspectSaved!=='function')throw Error('documented_workflow_dependencies_required');
  const gradeDialog=tab=>tab.playwright.getByRole('dialog',{name:'Courses & Grades',exact:true});
  const prefix=j=>j.kind==='common_school'?'common-school-':'common-academic-';
  async function closeGrade(tab,saved) {
    const close=gradeDialog(tab).locator('[id="changePreferencesClose"]');
    if(await close.count()!==1)throw Error('observed_academic_close_required');
    await close.click();await gradeDialog(tab).waitFor({state:'detached',timeoutMs:10000});
    if(host.digest(await academic.captureParent(tab))!==host.digest(saved.editor_state))throw Error('saved_academic_parent_changed');
  }
  async function run(tab,request,context,{maxStages=150}={}) {
    if(context?.workflow_authorized!==true||context.browser_family!=='edge'||context.transport!=='extension'||context.access_verified!==true||
        context.real_account_test||context.restore_after_test||!Number.isInteger(maxStages)||maxStages<1||maxStages>250)
      throw Error('intended_edge_workflow_only');
    let agenda=await relay('workflow-preview',request),checkpoint=null,job=null,page=null,parent=null,stageCount=0;
    const verified=[];let frozen=null,previousVerified=false,start=0,originalValues=null;
    const result=(status,extra={})=>({schema:'common-workflow-result/1',status,verified_pages:verified,
      full_application_complete:false,...extra});
    if(agenda.recovery_required.length){
      const active=agenda.recovery_required;
      if(active.length!==1||!active[0].job_id||active[0].context?.real_account_test||active[0].context?.restore_after_test)
        return result('recovery_required',{agenda});
      start=agenda.jobs.findIndex(j=>j.job_id===active[0].job_id);checkpoint=active[0].checkpoint_id;
      parent=active[0].original_parent||null;
      originalValues=active[0].original_values_sha256||null;
    }else if(!agenda.ready)return result('information_or_implementation_required',{agenda});
    job=agenda.jobs[start];
    if(await tab.url()!==job.page_url)return result('navigation_required',{next_page_url:job.page_url,checkpoint_id:checkpoint});
    if(new URL(job.page_url).origin!==context.origin)throw Error('workflow_origin_mismatch');
    try{
      if(!checkpoint&&agenda.directory_discovery.length){
        if(job.kind!=='common_school'||job.expected_kind!=='current')throw Error('current_school_lookup_stage_required');
        page=await schools.observe(tab);host.guard(context,page,'https://apply.commonapp.org');
        for(const item of agenda.directory_discovery){
          const lookup=await schools.lookup(tab,'245',item.query,context);
          const remembered=await relay('school-lookup-remember',{lookup,context},{school:item.psr_school_id});
          if(!remembered.ready)return result('school_directory_review_required',{reason:remembered.reason});
        }
        agenda=await relay('workflow-preview',request);
        if(!agenda.ready||agenda.directory_discovery.length)return result('information_or_implementation_required',{agenda});
      }
      frozen=agenda.source_set_sha256||null;
      const queue=[...agenda.jobs.slice(start),...agenda.jobs.slice(0,start)];
      for(const nextJob of queue){
        job=nextJob;onEvent({event:'page_started',job_id:job.job_id,kind:job.kind});
        if(previousVerified){
          const fresh=await relay('workflow-preview',request);
          if(!fresh.ready||fresh.directory_discovery.length||frozen&&fresh.source_set_sha256!==frozen)
            return result('sources_changed',{agenda:fresh});
          frozen=fresh.source_set_sha256;
          if(await tab.url()!==job.page_url)await tab.goto(job.page_url);
        }
        if(await tab.url()!==job.page_url)throw Error('observed_workflow_page_required');
        let step,touched=checkpoint!==null;
        if(job.kind==='common_school'){
          page=await schools.settleValidation(tab);host.guard(context,page,'https://apply.commonapp.org');
        }else{
          if(await gradeDialog(tab).count()){
            if(!checkpoint||!parent)throw Error('untracked_academic_dialog_requires_review');
            page=await academic.observe(tab,parent);
          }else{parent=await academic.captureParent(tab);page=await academic.open(tab,parent);}
        }
        const prepare=()=>relay(prefix(job)+(checkpoint?'advance':'prepare'),{page,...(!checkpoint?{context}:{})},
          checkpoint?{checkpoint}:{target:job.target_id,report_ref:job.report_ref});
        step=await prepare();if(step.checkpoint_id)checkpoint=step.checkpoint_id;
        while(true){
          if(++stageCount>maxStages)return result('bounded_pause',{checkpoint_id:checkpoint,job_id:job.job_id});
          const mode=step.stage||step.next?.stage;
          if(!step.ready&&mode==='choices'&&job.kind==='common_academic'){
            page=await academic.inspectChoices(tab,parent,step.choice_keys||step.next.choice_keys);
            step=await prepare();if(step.checkpoint_id)checkpoint=step.checkpoint_id;continue;
          }
          if(!step.ready||!step.plan||!checkpoint)return result('page_source_or_control_blocked',{checkpoint_id:checkpoint,job_id:job.job_id});
          const plan=step.plan,ctx={...context,journal_persisted:true};
          onEvent({event:'page_stage',job_id:job.job_id,stage:plan.stage});
          if(plan.stage==='fields'){
            let saved;
            if(plan.writes.length===0&&(!touched||plan.expected_values_sha256===originalValues)){
              saved=await inspectSaved(job);
              if(saved?.independent_saved_draft!==true)throw Error('independent_saved_draft_required');
              const checked=await relay(prefix(job)+'verify',{page:saved.page,revisited_after_save:true},{checkpoint});
              if(!checked.verified)return result('saved_page_mismatch',{checkpoint_id:checkpoint,job_id:job.job_id});
              verified.push({job_id:job.job_id,target_ids:job.target_ids,checkpoint_id:checkpoint,verified:true,save_performed:false,...checked});
            }else{
              page=await (job.kind==='common_school'?schools.applyStep(tab,plan,ctx):academic.applyStep(tab,plan,ctx,parent));
              saved=await (job.kind==='common_school'?schools.saveAndRead(tab,plan,ctx):academic.saveAndRead(tab,plan,ctx,parent));
              const checked=await relay(prefix(job)+'verify',saved,{checkpoint});
              if(!checked.verified)return result('saved_page_mismatch',{checkpoint_id:checkpoint,job_id:job.job_id});
              verified.push({job_id:job.job_id,target_ids:job.target_ids,checkpoint_id:checkpoint,verified:true,save_performed:true,...checked});
            }
            if(job.kind==='common_academic')await closeGrade(tab,saved.page);
            checkpoint=null;parent=null;originalValues=null;previousVerified=true;onEvent({event:'page_verified',job_id:job.job_id});break;
          }
          page=await (job.kind==='common_school'?schools.applyStep(tab,plan,ctx):academic.applyStep(tab,plan,ctx,parent));
          touched=true;step=await relay(prefix(job)+'advance',{page},{checkpoint});
        }
        if(!frozen){const fresh=await relay('workflow-preview',request);if(!fresh.ready)return result('sources_changed',{agenda:fresh});frozen=fresh.source_set_sha256;}
      }
      return result('provided_pages_verified',{source_set_sha256:frozen,scope:agenda.scope});
    }catch(error){
      // No speculative cleanup/Save: the per-page original journal stays canonical.
      return result('interrupted',{checkpoint_id:checkpoint,job_id:job?.job_id||null,
        reason:typeof error.message==='string'?error.message:'workflow_interrupted'});
    }
  }
  return {run};
}
