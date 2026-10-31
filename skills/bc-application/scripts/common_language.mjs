/** Build language rows first; the ordinary whole-page port fills only a fresh plan. */
import {contracts,createCommonFactual} from './common_factual.mjs';

export function createCommonLanguage(host) {
  const spec=contracts.find(s=>s.kind==='language'),page=createCommonFactual(host,'language');
  const origin='https://apply.commonapp.org',url=origin+spec.path,key=spec.count_field.key;
  async function changeCount(tab,plan,context) {
    const before=await page.inspect(tab);host.guard(context,before,origin);
    if(context.journal_persisted!==true||context.real_account_test||context.restore_after_test||
       plan.schema!=='common-language-count-plan/1'||plan.system!=='common_app'||plan.ready!==true||plan.page_url!==url||
       !Number.isInteger(plan.desired_count)||plan.desired_count<1||plan.desired_count>5||
       host.digest(before)!==plan.observation_sha256||host.digest(before.common_factual)!==host.digest(plan.common_factual))
      throw Error('prepared_common_language_count_required');
    const count=before.fields.find(f=>f.key===key),options=count.options;
    if(options.length!==5||options.some((o,i)=>o.label!==String(i+1)||o.disabled)||new Set(options.map(o=>o.value)).size!==5)
      throw Error('observed_language_count_choices_required');
    const selected=options.find(o=>o.label===String(plan.desired_count)),expected=count.value===selected.value?[]:[{field_key:key,value:selected.value}];
    if(host.digest(plan.writes)!==host.digest(expected))throw Error('source_bound_language_count_write_required');
    if(expected.length)await host.writeObserved(tab,before,expected);
    await tab.playwright.locator('main input[role="combobox"]').nth(plan.desired_count-1).waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('main input[role="combobox"]').nth(plan.desired_count).waitFor({state:'hidden',timeoutMs:10000});
    const after=await page.inspect(tab),field=after.fields.find(f=>f.key===key);
    if(after.common_factual.rows.length!==plan.desired_count||field.value!==selected.value)
      throw Error('language_count_transition_not_observed');
    return {page:after,count_selected:expected.length>0,saved:false,requires_fresh_fields_plan:true};
  }
  async function cancelUnsaved(tab,context) {
    const before=await page.observe(tab);host.guard(context,before,origin,true);
    if(context.journal_persisted!==true||context.real_account_test||context.restore_after_test)
      throw Error('prepared_common_language_intended_update_required');
    for(const item of before.state_metadata.items) {
      if(!/^(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)$/.test(item.key))throw Error('observed_status_key_unsupported');
    }
    await tab.reload();
    for(const item of before.state_metadata.items) {
      await tab.playwright.locator(`[id="${item.key}"] .nav-item__status forge-screen-reader-text`).waitFor({state:'attached',timeoutMs:10000});
    }
    return {page:await page.inspect(tab),revisited_saved_draft:true,restore_save_performed:false};
  }
  return {...page,changeCount,cancelUnsaved};
}
