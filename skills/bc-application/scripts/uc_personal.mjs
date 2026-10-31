/** UC Personal information: factual native controls and visible review recovery.
 * Inject host_browser exports. observe() leaves the page to read status, so use
 * it only on a saved baseline; saveAndRead() takes apply()'s local observation.
 */
import {createUcReview} from './uc_review.mjs';
export function createUcPersonal(host,configuration=null) {
  const review=createUcReview(host);
  const checkState=state=>review.checkState(state,pageUrl);
  const goReview=review.goReview;
  const {observe:rawObserve,digest,structure,guard,writeObserved}=host;
  const origin='https://apply.universityofcalifornia.edu',pageUrl=configuration?.pageUrl||origin+'/my-application/accountPersonal';
  const readPage=async tab=>configuration?.decorate ? configuration.decorate(await rawObserve(tab)) : rawObserve(tab);
  const names=['firstName','middleName','lastName','suffixName','hasLivedName','otherNames','birthDateMM',
    'birthDateDD','birthDateYYYY','birthCountryCode','birthCity','hasAttendedCaPublicSchool'];
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));

  function checkPage(page) {
    if(configuration){configuration.checkPage(page);return;}
    if(page.url!==pageUrl||page.title!=='Personal information - About you - UC application'||
       page.frames_present||page.collections?.length||page.scope||page.fields.length!==12||
       new Set(page.fields.map(f=>f.name)).size!==12||
       page.fields.some(f=>!names.includes(f.name)||!['text','select','radio'].includes(f.control)||f.disabled||f.readonly||!f.selector))
      throw Error('observed_uc_personal_page_required');
    const allowed={firstName:'First/Given name *',middleName:'Middle name',lastName:'Last / Family / Surname *',suffixName:'Suffix',
      hasLivedName:'Do you have a lived name?',otherNames:'Have you ever had a different legal name?',birthDateMM:'Month *',
      birthDateDD:'Day *',birthDateYYYY:'Year *',birthCountryCode:'Country *',birthCity:'City *',
      hasAttendedCaPublicSchool:'Have you ever attended a California public school? ?'};
    const radios=['hasLivedName','otherNames','hasAttendedCaPublicSchool'];
    const texts=['firstName','middleName','lastName','birthCity'];
    if(page.fields.some(f=>f.label!==allowed[f.name]||f.control!==(radios.includes(f.name)?'radio':texts.includes(f.name)?'text':'select')))
      throw Error('observed_uc_personal_labels_required');
    // The tested configuration contains no conditional lived/former-name or
    // California-school follow-ups. Another configuration needs its own scope.
    if(page.fields.some(f=>radios.includes(f.name)&&f.value!==f.options.find(o=>o.label==='No'&&!o.disabled)?.value))
      throw Error('uc_personal_conditional_configuration_unsupported');
  }


  function prepared(plan,context,local,restoration=false) {
    checkPage(local);checkState(local.state_metadata);guard(context,local,origin,restoration);
    if(plan.system!=='uc'||!plan.ready||plan.allowed_origin!==origin||plan.page_url!==pageUrl||context.journal_persisted!==true)
      throw Error('prepared_uc_personal_checkpoint_required');
  }

  async function openPersonal(tab) {
    if(configuration) {
      const expand=tab.playwright.getByRole('link',{name:'Expand all',exact:true});
      if(await expand.count()===1)await expand.click();
      const edit=configuration.reviewSelector ? tab.playwright.locator(configuration.reviewSelector) :
        tab.playwright.getByRole('button',{name:configuration.reviewLabel,exact:true});
      await edit.waitFor({state:'visible',timeoutMs:10000});await edit.press('Enter');
      await tab.playwright.getByRole('heading',{name:configuration.heading,exact:true}).waitFor({state:'visible',timeoutMs:10000});
      return;
    }
    const edit=tab.playwright.getByRole('button',{name:'Edit Personal information',exact:true});
    if(!await edit.isVisible())await tab.playwright.getByRole('link',{name:'About you Section Complete',exact:true}).click();
    await edit.waitFor({state:'visible',timeoutMs:10000});
    await edit.press('Enter');
    await tab.playwright.getByRole('heading',{name:'Personal information',exact:true}).waitFor({state:'visible',timeoutMs:10000});
  }

  async function observe(tab) {
    const before=await readPage(tab);checkPage(before);
    const state=await review.collect(tab,pageUrl,openPersonal);
    const after=await readPage(tab);checkPage(after);
    if(digest(before)!==digest(after))throw Error('uc_status_inspection_changed_personal_page');
    return {...after,state_metadata:state};
  }

  async function apply(tab,plan,context) {
    if(context.journal_persisted!==true)throw Error('prepared_uc_personal_checkpoint_required');
    const page=await observe(tab);prepared(plan,context,page);
    if(digest(page)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
    if(!configuration&&plan.writes.some(w=>{
      const f=page.fields.find(f=>f.key===w.field_key);
      return f?.control==='radio'&&w.value!==f.options.find(o=>o.label==='No'&&!o.disabled)?.value;
    }))throw Error('uc_personal_conditional_answers_require_handoff');
    await writeObserved(tab,page,plan.writes);
    const after=await readPage(tab);checkPage(after);
    if(digest(structure(after))!==plan.structure_sha256||after.fields.some(f=>f.invalid)||digest(vals(after))!==plan.expected_values_sha256)
      throw Error('unexpected_uc_page_after_input');
    return {...after,state_metadata:page.state_metadata};
  }

  async function saveAndRead(tab,plan,context,local,restoration=false) {
    prepared(plan,context,local,restoration);
    const page=await readPage(tab);checkPage(page);
    if(digest(structure(page))!==plan.structure_sha256||digest(vals(page))!==plan.expected_values_sha256||page.fields.some(f=>f.invalid))
      throw Error('prepared_uc_page_values_required');
    const a=page.actions.find(a=>a.key===plan.save_action?.key);
    if(!a||a.key!=='i:save'||a.disabled||a.label!=='Save & continue'||a.label!==plan.save_action.label)
      throw Error('observed_uc_draft_save_required');
    await tab.playwright.expectNavigation(()=>configuration?.nativeSaveClick ? tab.playwright.locator(a.selector).click() :
      tab.playwright.locator(a.selector).press('Enter'),{timeoutMs:10000,waitUntil:'domcontentloaded'});
    await tab.playwright.domSnapshot();
    await goReview(tab);await openPersonal(tab);
    return {page:await observe(tab),revisited_after_save:true};
  }

  async function restore(tab,plan,writes,context,options={}) {
    if(options.unsaved===true) {
      // Repair the unsaved controls before status navigation can discard them.
      // The canonical journal, not the current website, supplies the baseline.
      const page={...await readPage(tab),state_metadata:options.original_state_metadata};
      prepared(plan,context,page,true);
      if(digest(page.state_metadata)!==context.restoration_strategy.baseline_state_sha256||
         digest(structure(page))!==plan.structure_sha256||!/^[a-f0-9]{64}$/.test(options.original_values_sha256||''))
        throw Error('original_uc_recovery_baseline_required');
      await writeObserved(tab,page,writes);
      const after=await readPage(tab);checkPage(after);
      if(digest(structure(after))!==plan.structure_sha256||digest(vals(after))!==options.original_values_sha256||after.fields.some(f=>f.invalid))
        throw Error('original_uc_unsaved_values_required');
      return {page:await observe(tab),revisited_after_save:true,restore_save_performed:false,recovered_before_save:true};
    }
    const page=await observe(tab);prepared(plan,context,page,true);
    if(digest(structure(page))!==plan.structure_sha256)throw Error('restoration_structure_changed_handoff_required');
    if(!writes.length)return {page,revisited_after_save:true,restore_save_performed:false};
    await writeObserved(tab,page,writes);
    const local={...await readPage(tab),state_metadata:page.state_metadata};
    return saveAndRead(tab,{...plan,expected_values_sha256:digest(vals(local))},context,local,true);
  }

  return {observe,apply,saveAndRead,restore,checkPage,checkState,open:openPersonal};
}
