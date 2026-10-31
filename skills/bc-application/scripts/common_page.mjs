/** Whole-page Common App lifecycle shared by observed factual ports. */
import {createChoiceControls} from './choice_controls.mjs';

export function createCommonPage(host,{origin,url,marker,name,observe,inspect}) {
  const choice=createChoiceControls(host),values=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  function eligible(page,plan,context,restoration=false) {
    host.guard(context,page,origin,restoration);
    if(plan.system!=='common_app'||!plan.ready||plan.page_url!==url||context.journal_persisted!==true||
       host.digest(plan[marker])!==host.digest(page[marker]))throw Error(`prepared_common_${name}_checkpoint_required`);
  }
  async function waitStatuses(tab,page) {
    for(const item of page.state_metadata.items) {
      if(!/^(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)$/.test(item.key))throw Error('observed_status_key_unsupported');
      await tab.playwright.locator(`[id="${item.key}"] .nav-item__status forge-screen-reader-text`)
        .waitFor({state:'attached',timeoutMs:10000});
    }
  }
  async function write(tab,page,writes,choices) {
    for(const w of writes) {
      const f=page.fields.find(f=>f.key===w.field_key);if(!f)throw Error('observed_common_field_required');
      if(f.control==='choice_input')await choice.select(tab,page,f,w.value,choices[f.key]);
      else {await host.writeObserved(tab,page,[w]);if(f.control==='text')await tab.playwright.locator(f.selector).press('Tab');}
    }
  }
  async function apply(tab,plan,context) {
    const page=await observe(tab,plan.choice_observations);eligible(page,plan,context);
    if(host.digest(page)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
    await write(tab,page,plan.writes,plan.choice_observations);
    const after=await observe(tab,plan.choice_observations);
    if(host.digest(host.structure(after))!==plan.structure_sha256||host.digest(values(after))!==plan.expected_values_sha256||
       after.fields.some(f=>f.invalid))throw Error(`unexpected_common_${name}_page_after_input`);
    return after;
  }
  async function saveAndRead(tab,plan,context,restoration=false) {
    const page=await observe(tab,plan.choice_observations);eligible(page,plan,context,restoration);
    if(host.digest(host.structure(page))!==plan.structure_sha256||host.digest(values(page))!==plan.expected_values_sha256||
       page.fields.some(f=>f.invalid))throw Error(`prepared_valid_${name}_values_required`);
    const a=page.actions.find(a=>a.key===plan.save_action?.key),id='sectionContinue'+new URL(url).pathname.split('/').at(-1);
    if(a?.key!=='i:'+id||a.selector!==`[id="${id}"]`||a.disabled||a.label!=='Continue to next section')
      throw Error('observed_common_draft_save_required');
    await tab.playwright.locator(a.selector).click();
    await tab.playwright.locator(a.selector).waitFor({state:'detached',timeoutMs:15000});
    await tab.playwright.domSnapshot();await tab.goto(url);await waitStatuses(tab,page);
    return {page:await observe(tab,plan.choice_observations),revisited_after_save:true};
  }
  async function cancelUnsaved(tab,plan,context) {
    const page=await observe(tab,plan.choice_observations);eligible(page,plan,context,true);
    await tab.reload();await waitStatuses(tab,page);
    return {page:await observe(tab,plan.choice_observations),revisited_after_save:true,restore_save_performed:false,recovered_before_save:true};
  }
  async function restore(tab,recovery,{unsaved=false}={}) {
    const {plan,context,writes}=recovery;
    if(unsaved)return cancelUnsaved(tab,plan,context);
    if(recovery.original_invalid_fields?.length)throw Error(`incomplete_${name}_original_requires_cancel_or_resume`);
    const page=await observe(tab,plan.choice_observations);eligible(page,plan,context,true);
    if(host.digest(host.structure(page))!==plan.structure_sha256)throw Error('restoration_structure_changed_handoff_required');
    for(const w of writes)if(page.fields.find(f=>f.key===w.field_key)?.control==='choice_input'&&!w.value)
      throw Error(`empty_${name}_choice_requires_cancel_or_resume`);
    await write(tab,page,writes,plan.choice_observations);
    const local=await observe(tab,plan.choice_observations);
    if(host.digest(values(local))!==recovery.original_values_sha256||local.fields.some(f=>f.invalid))throw Error('original_common_values_required_before_save');
    return saveAndRead(tab,{...plan,expected_values_sha256:recovery.original_values_sha256},context,true);
  }
  return {observe,inspect,apply,saveAndRead,cancelUnsaved,restore};
}
