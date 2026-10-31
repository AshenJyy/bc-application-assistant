/** Common App existing-course modal. Only documented host locators and public DOM.
 * No add/remove records, header reconfiguration, outer Continue or attestations.
 */
import {createChoiceControls} from './choice_controls.mjs';
export function createGradeEditor({observe,digest,structure,writeObserved,guard}) {
if([observe,digest,structure,writeObserved,guard].some(f=>typeof f!=='function'))throw Error('documented_host_port_required');

const {options:materialOptions,close:closeOptions,select:selectMaterial}=createChoiceControls({digest});
const commonOrigin='https://apply.commonapp.org';
const dialog=tab=>tab.playwright.getByRole('dialog',{name:'Courses & Grades',exact:true});
const allValues=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
const draftLabel=/^Continue\s*,\s*Closes dialog$/;

async function captureParent(tab) {
  const p=await observe(tab);
  if(!/^\/common\/13\/(55|56|57)$/.test(new URL(p.url).pathname))throw Error('existing_grade_page_required');
  if(await dialog(tab).count())throw Error('closed_grade_parent_required');
  const checks=p.fields.filter(f=>f.control==='checkbox'&&f.label==='I have reported all of my courses for this grade');
  const action=p.actions.filter(a=>a.key==='i:addCG'&&/^Edit (9th|10th|11th) grade$/.test(a.label));
  if(checks.length!==1||p.fields.length!==1||action.length!==1||!p.state_metadata)throw Error('observed_grade_parent_state_required');
  const rendered=await tab.playwright.evaluate(()=>({
    heading:(document.getElementById('pageTitle')?.textContent||'').replace(/\s+/g,' ').trim(),
    text:(document.querySelector('main')?.innerText||'').replace(/\s+/g,' ').trim()}));
  if(!rendered.text||!rendered.heading)throw Error('observed_parent_summary_required');
  const controls=p.fields.map(f=>({label:f.label,control:f.control,required:f.required,disabled:f.disabled,readonly:f.readonly}));
  return {schema:'grade-parent/1',url:p.url,heading:rendered.heading,reopen_action:action[0],
    controls_sha256:digest(controls),values_sha256:digest(p.fields.map(f=>({label:f.label,control:f.control,value:f.value}))),
    summary_sha256:digest(rendered.text),completion_checked:checks[0].value===true,state_metadata:p.state_metadata};
}

async function openGradeEditor(tab,parent) {
  const action=tab.playwright.locator(parent.reopen_action.selector);
  if(await action.count()!==1)throw Error('unique_observed_grade_edit_action_required');
  await action.click();await dialog(tab).waitFor({state:'visible',timeoutMs:10000});
  await dialog(tab).getByRole('combobox',{name:'Transcript 1 School Name',exact:true}).waitFor({state:'visible',timeoutMs:10000});
  return observeGradeEditor(tab,parent);
}

async function observeGradeEditor(tab,parent,choices={}) {
  const p=await observe(tab,{grade_dialog:true});
  return {...p,editor_state:parent,state_metadata:parent.state_metadata,
    ...(Object.keys(choices).length?{choice_observations:choices}:{})};
}

async function inspectGradeOptions(tab,parent,fieldKey) {
  const before=await observeGradeEditor(tab,parent),f=before.fields.find(f=>f.key===fieldKey);
  if(f?.control!=='material_select'||f.disabled)throw Error('observed_grade_material_select_required');
  let options;
  try {options=await materialOptions(tab,f);}
  finally {await closeOptions(tab,f);}
  const after=await observeGradeEditor(tab,parent);
  if(digest(after)!==digest(before))throw Error('choice_inspection_changed_editor');
  return options.map(o=>({label:o.label,value:o.label,disabled:o.disabled}));
}

function eligible(page,plan,context,restoration=false) {
  guard(context,page,commonOrigin,restoration);
  if(page.scope?.kind!=='common_app_grade_dialog'||page.editor_state?.schema!=='grade-parent/1'||
      !plan.ready||context.journal_persisted!==true)throw Error('prepared_grade_editor_required');
  if(page.fields.some(f=>f.control==='unsupported'||/essay|declar|attest|reported all|signature|consent/i.test(f.label+' '+f.group)))
    throw Error('factual_grade_scope_required');
  for(const f of page.fields) {
    const header=/^Transcript \d+ (School Name|School Year|Grading Scale|Schedule)$/.test(f.label);
    const course=/^Transcript \d+, Course \d+, (Subject|Course Level|Course Nameundefined|Credits not applicable|(?:Semester [12]|Trimester [123]|Quarter [1-4]|Final)(?:undefined| Grade)?|(?:Semester [12]|Trimester [123]|Quarter [1-4]) Credit|Final Credits)$/.test(f.label);
    if((!header&&!course)||!['text','number','checkbox','material_select'].includes(f.control))throw Error('known_factual_grade_controls_required');
  }
}

async function writes(tab,page,items,choices,realTest) {
  for(const w of items) {
    const f=page.fields.find(f=>f.key===w.field_key);
    if(!f||f.disabled||f.readonly)throw Error('observed_editable_field_required');
    if(/^i:(schoolName|schoolYear|gradingScale|schedule)Control/.test(f.key))throw Error('grade_header_reconfiguration_excluded');
    if(f.control==='material_select'&&w.value==='')throw Error('material_clear_recovery_handoff_required');
    if(f.control==='material_select')await selectMaterial(tab,page,f,w.value,choices?.[f.key]);
    else await writeObserved(tab,page,[w]);
  }
}

async function applyGradeWrites(tab,plan,context) {
  const page=await observeGradeEditor(tab,plan.editor_state,plan.choice_observations);
  eligible(page,plan,context);
  if(digest(page)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
  await writes(tab,page,plan.writes,plan.choice_observations,context.real_account_test);
  const after=await observeGradeEditor(tab,plan.editor_state,plan.choice_observations);
  if(digest(structure(after))!==plan.structure_sha256)throw Error('conditional_page_changed_collect_before_save');
  if(after.fields.some(f=>f.invalid)||digest(allValues(after))!==plan.expected_values_sha256)throw Error('unexpected_grade_values_before_save');
  return after;
}

async function saveGradeAndRead(tab,plan,context,restoration=false) {
  const page=await observeGradeEditor(tab,plan.editor_state,plan.choice_observations);
  eligible(page,plan,context,restoration);
  if(digest(structure(page))!==plan.structure_sha256||digest(allValues(page))!==plan.expected_values_sha256||page.fields.some(f=>f.invalid))
    throw Error('prepared_valid_grade_values_required');
  const candidates=page.actions.filter(a=>draftLabel.test(a.label)&&!a.disabled);
  if(candidates.length!==1||candidates[0].key!==plan.save_action?.key)throw Error('observed_grade_dialog_save_required');
  const save=dialog(tab).getByRole('button',{name:draftLabel});
  if(await save.count()!==1)throw Error('unique_grade_dialog_save_required');
  // Keyboard activation targets the known modal draft button even when the
  // long course grid has scrolled; it never targets the outer Continue.
  await save.press('Enter');await tab.playwright.domSnapshot();
  const modal=dialog(tab);
  if(await modal.count()&&await modal.isVisible()) {
    try {await modal.waitFor({state:'detached',timeoutMs:20000});}
    catch(error) {await tab.playwright.domSnapshot();if(await modal.count()&&await modal.isVisible())throw error;}
  }
  if(await modal.count()&&await modal.isVisible())throw Error('grade_dialog_save_not_closed');
  await tab.reload();
  await tab.playwright.getByRole('heading',{name:plan.editor_state.heading,exact:true}).waitFor({state:'visible',timeoutMs:10000});
  for(const item of plan.editor_state.state_metadata.items)
    await tab.playwright.locator(`[id="${item.key}"] .nav-item__status forge-screen-reader-text`).waitFor({state:'attached',timeoutMs:10000});
  const parent=await captureParent(tab);
  await openGradeEditor(tab,parent);
  return {page:await observeGradeEditor(tab,parent,plan.choice_observations),revisited_after_save:true};
}

async function restoreGrade(tab,plan,items,context) {
  const page=await observeGradeEditor(tab,plan.editor_state,plan.choice_observations);
  eligible(page,plan,context,true);
  if(digest(structure(page))!==plan.structure_sha256)throw Error('restoration_structure_changed_handoff_required');
  await writes(tab,page,items,plan.choice_observations,context.real_account_test);
  const expected={...allValues(page),...Object.fromEntries(items.map(w=>[w.field_key,w.value]))};
  return saveGradeAndRead(tab,{...plan,expected_values_sha256:digest(expected)},context,true);
}
return {captureParent,openGradeEditor,observeGradeEditor,inspectGradeOptions,applyGradeWrites,saveGradeAndRead,restoreGrade};
}
