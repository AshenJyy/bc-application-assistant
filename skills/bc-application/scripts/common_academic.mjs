/** Common App transcript creation through public DOM and documented host locators. */
import {readFile} from 'node:fs/promises';
export function reportingControlShape(fields) {
  if(fields.length!==1||fields[0].control!=='checkbox'||fields[0].label!=='I have reported all of my courses for this grade')
    throw Error('one_observed_reporting_checkbox_required');
  // This outer attestation is observed only, never edited. Its generated DOM
  // ID/name may change after visiting Education; retain its complete semantics.
  return fields.map(f=>Object.fromEntries(Object.entries(f).filter(([k])=>!['value','invalid','key','name','selector'].includes(k))));
}
import {createChoiceControls} from './choice_controls.mjs';
export const contract=JSON.parse(await readFile(new URL('./bc_application/data/common_academic.json',import.meta.url),'utf8'));

export function createCommonAcademic(host) {
  const choice=createChoiceControls(host),dialog=tab=>tab.playwright.getByRole('dialog',{name:'Courses & Grades',exact:true});
  const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
  async function waitStatuses(tab) {
    await tab.playwright.getByText('Please wait, the page is loading.',{exact:true}).waitFor({state:'hidden',timeoutMs:15000});
    const route=/^\/common\/13\/(55|56|57)$/.exec(new URL(await tab.url()).pathname);
    if(!route)throw Error('observed_academic_route_required');
    const status=key=>tab.playwright.locator(`[id="${key}"] .nav-item__status forge-screen-reader-text`)
      .filter({hasText:/complete|in progress|not started/i});
    await status('tertiaryNavItem13_'+route[1]).waitFor({state:'attached',timeoutMs:15000});
    const keys=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('a[id^="secondaryNavItem"],a[id^="tertiaryNavItem"]'))
      .filter(e=>e.getClientRects().length).map(e=>e.id));
    for(const key of keys) {
      if(!/^(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)$/.test(key))throw Error('observed_navigation_identity_required');
      await status(key).waitFor({state:'attached',timeoutMs:10000});
    }
  }
  async function captureParent(tab) {
    await tab.playwright.locator('[id="addCG"]').waitFor({state:'visible',timeoutMs:15000});
    await tab.playwright.getByRole('checkbox',{name:'I have reported all of my courses for this grade',exact:true}).waitFor({state:'visible',timeoutMs:15000});
    await waitStatuses(tab);const raw=await host.observe(tab),path=new URL(raw.url).pathname;
    if(!Object.values(contract.paths).includes(path)||await dialog(tab).count())throw Error('closed_supported_academic_parent_required');
    const checks=raw.fields.filter(f=>f.control==='checkbox'&&f.label==='I have reported all of my courses for this grade');
    const actions=raw.actions.filter(a=>a.key==='i:addCG'&&/^(Edit|Enter|Add) (9th|10th|11th) grade$/.test(a.label)&&!a.disabled);
    if(raw.fields.length!==1||checks.length!==1||actions.length!==1||!raw.state_metadata)throw Error('observed_academic_parent_required');
    const native=await tab.playwright.evaluate(()=>({heading:(document.getElementById('pageTitle')?.textContent||'').trim(),
      text:(document.querySelector('main')?.innerText||'').replace(/\s+/g,' ').trim()}));
    const counts=Array.from(native.text.matchAll(/Completed courses & grades entered:\s*(\d+)\s*Incomplete courses & grades entered:\s*(\d+)/g))
      .map(m=>({complete:Number(m[1]),incomplete:Number(m[2])}));
    if(!native.heading||!native.text||counts.length>25)throw Error('observed_academic_summary_required');
    return {schema:'grade-parent/1',url:raw.url,heading:native.heading,reopen_action:actions[0],counts,
      controls_sha256:host.digest(reportingControlShape(raw.fields)),
      values_sha256:host.digest(raw.fields.map(f=>({label:f.label,control:f.control,value:f.value}))),
      summary_sha256:host.digest(native.text),completion_checked:checks[0].value===true,state_metadata:raw.state_metadata};
  }
  async function readLayout(tab) {
    return tab.playwright.evaluate(()=>{
      const visible=e=>!!e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
      const dialogs=Array.from(document.querySelectorAll('[role=dialog]')).filter(visible);
      if(dialogs.length!==1)throw Error('one_visible_academic_dialog_required');const d=dialogs[0];
      const transcripts=Array.from(d.querySelectorAll('ca-cng-transcript')).filter(visible).map(e=>{
        const headers=Array.from(e.querySelectorAll('[id^="schoolNameControl"]')).filter(visible);
        if(headers.length!==1||!/^schoolNameControl\d+$/.test(headers[0].id))throw Error('public_transcript_owner_required');
        const number=Number(headers[0].id.replace('schoolNameControl','')),selector=`ca-cng-transcript:has([id="${headers[0].id}"])`;
        const add=Array.from(e.querySelectorAll('button')).filter(b=>visible(b)&&(b.innerText||'').trim()==='Add another course');
        if(add.length!==1)throw Error('unique_owned_add_course_required');
        const rows=Array.from(e.querySelectorAll('ca-cng-course')).filter(visible).map(row=>{
          const names=Array.from(row.querySelectorAll('[id^="courseNameControl_"]')).filter(visible);
          const match=names.length===1&&new RegExp(`^courseNameControl_T${number}C(\\d+)$`).exec(names[0].id);
          if(!match)throw Error('public_course_owner_required');
          const selector=`ca-cng-course:has([id="${names[0].id}"])`,buttons=Array.from(row.querySelectorAll('button')).filter(visible);
          if(buttons.length>1)throw Error('unknown_course_action');
          return {number:Number(match[1]),selector,selector_count:document.querySelectorAll(selector).length,
            remove_label:buttons[0]?.getAttribute('aria-label')||null};
        });
        return {number,selector,selector_count:document.querySelectorAll(selector).length,rows};
      });
      return {schema:'common-academic-layout/1',transcripts};
    });
  }
  async function observe(tab,parent,choices={}) {
    const page=await host.observe(tab,{grade_dialog:true,grade_creation:true});
    if(!page.common_academic||host.digest(page.common_academic.instructions)!==host.digest(contract.instructions))
      throw Error('observed_academic_instructions_required');
    return {...page,academic_layout:await readLayout(tab),editor_state:parent,state_metadata:parent.state_metadata,choice_observations:choices};
  }
  async function open(tab,parent) {
    if(await tab.playwright.locator(parent.reopen_action.selector).count()!==1)throw Error('unique_academic_open_action_required');
    await tab.playwright.locator(parent.reopen_action.selector).click();await dialog(tab).waitFor({state:'visible',timeoutMs:10000});
    return observe(tab,parent);
  }
  async function inspectChoices(tab,parent,keys) {
    const before=await observe(tab,parent),choices={};
    if(!Array.isArray(keys)||new Set(keys).size!==keys.length||keys.length>500)throw Error('bounded_academic_choice_keys_required');
    for(const key of keys) {
      const field=before.fields.find(f=>f.key===key);
      if(field?.control!=='material_select'||field.disabled)throw Error('observed_academic_choice_field_required');
      try{choices[key]=(await choice.options(tab,field)).map(o=>({label:o.label,value:o.label,disabled:o.disabled}));}
      finally{await choice.close(tab,field);}
    }
    const after=await observe(tab,parent,choices);
    if(host.digest({...after,choice_observations:{}})!==host.digest(before))throw Error('academic_choice_inspection_changed_page');
    return after;
  }
  function eligible(page,plan,context) {
    host.guard(context,page,contract.origin);
    if(context.journal_persisted!==true||context.real_account_test||context.restore_after_test||plan.schema!=='common-academic-step/1'||
      plan.system!=='common_app'||plan.ready!==true||plan.page_url!==page.url||page.scope?.kind!=='common_app_grade_creation')
      throw Error('prepared_academic_intended_update_required');
  }
  async function applyStep(tab,plan,context,parent) {
    const before=await observe(tab,parent,plan.choice_observations);eligible(before,plan,context);
    if(host.digest(before)!==plan.observation_sha256)throw Error('academic_page_changed_since_preparation');
    const transcript=before.academic_layout.transcripts.find(t=>t.number===plan.transcript);
    if(['add_course','remove_placeholder','header','credit_mode'].includes(plan.stage)&&!transcript)
      throw Error('observed_academic_action_owner_required');
    if(plan.stage==='add_transcript') {
      if(plan.transcript!==before.academic_layout.transcripts.length+1)throw Error('next_transcript_only');
      await dialog(tab).getByRole('button',{name:contract.add_transcript,exact:true}).click();
      await dialog(tab).locator(`[id="schoolNameControl${plan.transcript}"]`).waitFor({state:'visible',timeoutMs:10000});
    } else if(plan.stage==='add_course') {
      if(plan.row!==transcript.rows.length+1)throw Error('next_course_only');
      await tab.playwright.locator(transcript.selector).getByRole('button',{name:contract.add_course,exact:true}).click();
      await dialog(tab).locator(`[id="courseNameControl_T${plan.transcript}C${plan.row}"]`).waitFor({state:'visible',timeoutMs:10000});
    } else if(plan.stage==='remove_placeholder') {
      const row=transcript.rows.at(-1),prefix=`Transcript ${plan.transcript}, Course ${plan.row}, `;
      const fields=before.fields.filter(f=>f.label.startsWith(prefix));
      if(plan.row!==row.number||plan.row<2||!fields.length||fields.some(f=>f.control==='checkbox'?f.value!==false:!['','Select'].includes(f.value)))
        throw Error('only_empty_unsaved_placeholder_may_be_removed');
      await tab.playwright.locator(row.selector).getByRole('button',{name:row.remove_label,exact:true}).click();
      const confirmation=tab.playwright.getByRole('dialog',{name:`Remove course ${plan.row} of ${transcript.rows.length}`,exact:true});
      await confirmation.waitFor({state:'visible',timeoutMs:10000});
      if((await confirmation.innerText()).replace(/\s+/g,'')!==`Remove course ${plan.row} of ${transcript.rows.length} Are you sure you want to permanently remove this course? Cancel Remove`.replace(/\s+/g,''))
        throw Error('known_blank_placeholder_confirmation_required');
      await confirmation.locator('[id="alert_rc_r"]').click();await confirmation.waitFor({state:'detached',timeoutMs:10000});
      await dialog(tab).locator(`[id="courseNameControl_T${plan.transcript}C${plan.row}"]`).waitFor({state:'detached',timeoutMs:10000});
    } else if(['header','credit_mode','fields'].includes(plan.stage)) {
      if(!Array.isArray(plan.writes))throw Error('academic_source_writes_required');
      for(const write of plan.writes) {
        const f=before.fields.find(f=>f.key===write.field_key);if(!f)throw Error('observed_academic_field_required');
        if(plan.stage==='header'&&(!f.label.startsWith(`Transcript ${plan.transcript} `)||!/^i:(schoolName|schoolYear|gradingScale|schedule)Control\d+$/.test(f.key)))
          throw Error('academic_header_step_scope_required');
        if(plan.stage==='credit_mode'&&f.key!==`i:creditNA_T${plan.transcript}C${plan.row}-input`)
          throw Error('academic_credit_mode_step_scope_required');
        if(plan.stage==='fields'&&/^i:(schoolName|schoolYear|gradingScale|schedule)Control/.test(f.key))throw Error('academic_header_requires_separate_stage');
        if(f.control==='material_select')await choice.select(tab,before,f,write.value,plan.choice_observations[f.key]);
        else await host.writeObserved(tab,before,[write]);
      }
    } else throw Error('known_academic_step_required');
    const after=await observe(tab,parent);
    if(plan.stage==='add_transcript'&&after.academic_layout.transcripts.length!==before.academic_layout.transcripts.length+1)
      throw Error('academic_transcript_creation_not_observed');
    if(['add_course','remove_placeholder'].includes(plan.stage)) {
      const actual=after.academic_layout.transcripts.find(t=>t.number===plan.transcript);
      if(!actual||actual.rows.length!==transcript.rows.length+(plan.stage==='add_course'?1:-1))throw Error('academic_row_change_not_observed');
    }
    if(['header','credit_mode'].includes(plan.stage)&&plan.writes.some(w=>vals(after)[w.field_key]!==w.value))
      throw Error('academic_stage_value_not_observed');
    if(plan.stage==='fields'&&(host.digest(host.structure(after))!==plan.structure_sha256||host.digest(vals(after))!==plan.expected_values_sha256||after.fields.some(f=>f.invalid)))
      throw Error('whole_academic_page_mismatch_before_save');
    return after;
  }
  async function savedRead(tab,parent) {
    await tab.reload();const current=await captureParent(tab);return open(tab,current);
  }
  async function saveAndRead(tab,plan,context,parent) {
    const page=await observe(tab,parent,plan.choice_observations);eligible(page,plan,context);
    if(plan.stage!=='fields'||host.digest(host.structure(page))!==plan.structure_sha256||host.digest(vals(page))!==plan.expected_values_sha256||page.fields.some(f=>f.invalid))
      throw Error('complete_academic_records_required_before_save');
    const action=dialog(tab).getByRole('button',{name:/^Continue\s*,\s*Closes dialog$/});
    if(await action.count()!==1)throw Error('unique_academic_modal_draft_save_required');
    await action.press('Enter');await dialog(tab).waitFor({state:'detached',timeoutMs:20000});
    return {page:await savedRead(tab,parent),revisited_after_save:true};
  }
  async function cancelUnsaved(tab,context,parent) {
    const page=await observe(tab,parent);host.guard(context,page,contract.origin,true);
    if(context.journal_persisted!==true)throw Error('academic_journal_required');
    await dialog(tab).locator('[id="changePreferencesClose"]').click();await dialog(tab).waitFor({state:'detached',timeoutMs:10000});
    return {page:await savedRead(tab,parent),revisited_saved_draft:true,restore_save_performed:false};
  }
  return {captureParent,open,observe,inspectChoices,applyStep,saveAndRead,cancelUnsaved};
}
