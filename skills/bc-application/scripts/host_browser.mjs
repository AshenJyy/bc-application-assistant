/** Documented host-tool bridge. Pass an existing Chrome/Edge extension tab.
 * No browser launch, network API, CDP, cookies, private framework state or eval
 * DOM mutation. Inputs use documented locators or fresh accessibility targets.
 */
import {createHash} from 'node:crypto';

const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])) : v;
export const digest = v => createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
export function genericFieldIdentities(fields,knownFields=[]){
  const meaning=f=>digest({label:f.label,control:f.control,required:f.required,readonly:f.readonly,disabled:f.disabled,
    widget:f.widget||null,options:f.options.map(o=>({label:o.label,group:o.group||'',disabled:o.disabled}))});
  const base=f=>digest({label:f.label,group:f.group,control:f.control,required:f.required});
  return fields.map(f=>{
    const {context_anchor,...field}=f;
    const prior=knownFields.filter(old=>meaning(old)===meaning(f));
    const unique=fields.filter(other=>meaning(other)===meaning(f)).length===1;
    const contextual=[field.group,context_anchor?`Following: ${context_anchor}`:''].filter(Boolean).join(' / ');
    const anchored=prior.filter(old=>old.group===contextual);
    if(context_anchor&&anchored.length===1)field.group=contextual;
    else if(unique&&prior.length===1){
      // Do not carry a witnessed section identity into a different section just
      // because its currently unique label/options happen to match.
      field.group=prior[0].group.includes('Following: ')&&context_anchor?contextual:prior[0].group;
    }
    else if(fields.filter(other=>base(other)===base(f)).length>1){
      // A saved descriptor can identify an existing question only when its
      // complete live option catalogue is unique. Otherwise use actual layout
      // context; identical unresolved questions still stop below.
      if(context_anchor)field.group=[field.group,`Following: ${context_anchor}`].filter(Boolean).join(' / ');
    }
    return field;
  });
}
function commonQuestionId(page,field) {
  const url=new URL(page.url);
  const factual=page.common_factual?.schema==='common-factual-page/1'&&['/common/3/16','/common/5/26','/common/13/58'].includes(url.pathname);
  if(!['https://apply.commonapp.org','http://127.0.0.1:8765','http://localhost:8765'].includes(url.origin)||
      !(url.pathname==='/common/3/11'||factual||url.pathname==='/common/2/10'&&page.common_ielts?.schema==='common-ielts-page/1')||field.control!=='radio'||!/^mat-radio-group-\d+$/.test(field.name)||
      !field.label||field.group!==field.label||field.options.length<2)return null;
  const ids=field.options.map(o=>/^\[id="option_ques_(\d+)_\d+-input"\]$/.exec(o.selector||'')?.[1]);
  if(ids.some(id=>!id)||new Set(ids).size!==1||field.selector!==field.options[0].selector||
      [field,...field.options].some(o=>(o.selector_count??1)!==1||(o.selector_index??0)!==0))return null;
  return ids[0];
}
export function normalizeCommonAppRadios(page) {
  const fields=page.fields.map(f=>{
    const question=commonQuestionId(page,f);
    return question ? {...f,key:`r:ques_${question}`,identity_kind:'common_app_question_radio'} : f;
  });
  if(new Set(fields.map(f=>f.key)).size!==fields.length)throw Error('ambiguous_observed_controls');
  return {...page,fields};
}
export const structure = p => ({schema:p.schema,url:p.url,title:p.title||'',frames_present:p.frames_present||false,
  collections:p.collections||[],
  ...(p.mit_coursework?{mit_coursework:p.mit_coursework}:{}),
  ...(p.uc_course_editor?{uc_course_editor:p.uc_course_editor}:{}),
  ...(p.uc_academic_auxiliary?{uc_academic_auxiliary:p.uc_academic_auxiliary}:{}),
  ...(p.uc_school_terms?{uc_school_terms:p.uc_school_terms}:{}),
  ...(p.uc_course_refill?{uc_course_refill:p.uc_course_refill}:{}),
  ...(p.uc_factual?{uc_factual:p.uc_factual}:{}),
  ...(p.common_ielts?{common_ielts:p.common_ielts}:{}),
  ...(p.common_factual?{common_factual:p.common_factual}:{}),
  ...(p.common_academic?{common_academic:p.common_academic}:{}),
  ...(p.academic_layout?{academic_layout:p.academic_layout}:{}),
  ...(p.generic_form?{generic_form:{...p.generic_form,scope:{selector_count:p.generic_form.scope.selector_count,selector_index:p.generic_form.scope.selector_index},
    ...(p.generic_form.dialog?{dialog:{name:p.generic_form.dialog.name,selector_count:p.generic_form.dialog.selector_count}}:{}),
    ...(p.generic_form.record_collections?{record_collections:p.generic_form.record_collections.map(({selector,...c})=>c)}:{})}}:{}),
  ...(p.scope?{scope:p.scope,requirement_groups:p.requirement_groups||[]}:{}),
  fields:p.fields.map(f=>{
    if(p.generic_form)return {...Object.fromEntries(Object.entries(f).filter(([k])=>!['value','invalid','selector','name'].includes(k))),
      options:f.options.map(o=>Object.fromEntries(Object.entries(o).filter(([k])=>!['selector','native_value'].includes(k))))};
    const stable=f.identity_kind==='common_app_question_radio';
    const question=stable ? commonQuestionId(p,f) : null;
    if(stable&&(!question||f.key!==`r:ques_${question}`))throw Error('observed_radio_identity_invalid');
    // Only the Angular-generated group name is transient. Keep the actual
    // option IDs, labels, values, order and selector multiplicity unchanged.
    return Object.fromEntries(Object.entries(f).filter(([k])=>!['value','invalid'].includes(k)&&!(stable&&k==='name')));
  }),actions:p.generic_form?p.actions.map(a=>Object.fromEntries(Object.entries(a).filter(([k])=>k!=='selector'))):p.actions});
const values = p => Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
const manualPattern = /essay|personal insight|declar|certif|attest|signature|submit|payment|credit card|invit|recommendation request|why (are|do|did|would)|describe|explain|reflect|greatest|most meaningful|leadership|agree to|waiv|consent|authoriz|authoris|i permit|i (have reported all|confirm|affirm|acknowledge|agree|understand|have read|have reviewed)|i['’]ve finished|indicate that you have reported all/i;
const manualField=f=>!(f.key==='n:citizenshipStatus'&&f.control==='radio'&&
  f.label==='What will your citizenship status be on the date you submit this application? *'&&f.group===f.label)&&manualPattern.test(f.label+' '+f.group);
const factualTextareaLabels = ['first name','last name','middle name','legal first given','legal last family','middle',
  'street','street address','address line 1','address line 2'];
const normalizeLabel = label => label.toLowerCase().replace(/optional.*$/,'').replace(/[^a-z0-9]+/g,' ').trim();
const courseworkNotes = [
  'List any course(s) with standardized exams (A-level, Baccalauréat, CAPEs, etc.) taken or underway. (If you have taken the exam, please list the test date and score.) Advanced Placement or International Baccalaureate exams should be reported on the next page.',
  "If there is anything we should know about your school's course offerings, extenuating circumstances regarding your coursework or access to standardized testing, or school's grading system, please use the space below.optional; 100 words or fewer"
].map(normalizeLabel);
function blankCourseworkNote(f,page,plan) {
  return plan.system==='mit' && ['self reported coursework','synthetic mit self reported coursework'].includes(normalizeLabel(page.title)) &&
    f.control==='textarea' && f.value==='' && !f.required && !f.invalid && courseworkNotes.includes(normalizeLabel(f.label)) &&
    !manualPattern.test(f.label+' '+f.group);
}

export async function observe(tab,options={}) {
  const result = await tab.playwright.evaluate(settings => {
    const text = s => (s||'').replace(/\s+/g,' ').trim();
    const escape = s => String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"');
    const selector = e => e.id ? `[id="${escape(e.id)}"]` : e.name ? `[name="${escape(e.name)}"]` : null;
    const visible = e => !!e.getClientRects().length && e.type !== 'hidden' && !e.closest('[hidden],[inert]') &&
      !['hidden','collapse'].includes(getComputedStyle(e).visibility);
    const labelText=e=>settings.generic_form?(e?.innerText??e?.textContent):e?.textContent;
    const labelled = e => text((e?.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>labelText(document.getElementById(id))||'').join(' '));
    const nearbyLabel = e => {
      // A public layout label immediately preceding a control cell. Never use
      // IDs, hidden values or a whole section as the question's meaning.
      for(let box=e,depth=0;box&&box!==document.body&&depth<3;box=box.parentElement,depth++){
        const previous=box.previousElementSibling;
        if(previous&&visible(previous)&&!previous.querySelector('input,select,textarea,[role=combobox]')){
          const value=text(previous.innerText);
          if(value&&value.length<=500)return value;
        }
      }
      return '';
    };
    const labels = e => {
      const direct=text(e.getAttribute('aria-label') || labelled(e) || Array.from(e.labels||[]).map(labelText).join(' '));
      if (direct) return direct;
      if(settings.generic_form){
        const focus=e.getAttribute('role')==='combobox'?e.querySelector('input[aria-labelledby]'):null;
        const nearby=nearbyLabel(e);
        if(focus&&labelled(focus))return labelled(focus);
        if(nearby)return nearby;
      }
      // UC has labels with a stale for= value. Use only an observed wrapper
      // containing one label and exactly one visible control, never a row guess.
      const wrapper=e.closest('.field-wrapper'), local=wrapper?.querySelectorAll('label');
      const controls=wrapper ? Array.from(wrapper.querySelectorAll('input,select,textarea,[role=combobox]')).filter(visible) : [];
      return local?.length===1 && controls.length===1 && controls[0]===e ? text(local[0].textContent) : '';
    };
    const identity = e => {
      const selected=selector(e);
      const matches=selected ? Array.from(document.querySelectorAll(selected)) : [];
      return {selector:selected,selector_count:matches.length,selector_index:matches.indexOf(e)};
    };
    const group = e => {
      const address=e.closest('.form_address');
      const header=address?.previousElementSibling?.classList.contains('form_header') ? address.previousElementSibling.textContent : '';
      return text(e.closest('fieldset')?.querySelector('legend')?.textContent ||
        labelled(e.closest('[role=radiogroup],[role=group]')) || header || e.closest('.form_question')?.querySelector('.form_label')?.textContent);
    };
    let root=document,scope,genericDialog;
    if(settings.generic_form){
      let forms=Array.from(document.querySelectorAll('form')).filter(visible);
      const dialogs=Array.from(document.querySelectorAll('[role=dialog]')).filter(visible);
      if(settings.generic_dialog){
        if(dialogs.length!==1||!labelled(dialogs[0])&&!text(dialogs[0].getAttribute('aria-label')))throw Error('unique_named_native_dialog_required');
        const dialog=dialogs[0],id=identity(dialog);
        forms=forms.filter(f=>dialog.contains(f));
        if(forms.length!==1||!id.selector||id.selector_count!==1)throw Error('unique_dialog_owned_native_form_required');
        genericDialog={name:labelled(dialog)||text(dialog.getAttribute('aria-label')),selector:id.selector,selector_count:1};
      }
      if(forms.length!==1||document.querySelector('iframe')||!settings.generic_dialog&&dialogs.length)
        throw Error(`single_native_form_required:${forms.length}:${document.querySelectorAll('iframe').length}:${Array.from(document.querySelectorAll('[role=dialog]')).filter(visible).length}`);
      root=forms[0];
      const outside=Array.from(document.querySelectorAll('input,select,textarea,[contenteditable=true],[role=combobox]')).filter(e=>visible(e)&&!root.contains(e)&&e.type!=='search');
      if(outside.length&&!settings.generic_dialog)throw Error('unscoped_form_controls_require_review');
    }
    if(settings.grade_dialog) {
      const dialogs=Array.from(document.querySelectorAll('[role=dialog]')).filter(visible);
      if(dialogs.length!==1||!/^\/common\/13\/(55|56|57|58|59)$/.test(location.pathname)||
         !['https://apply.commonapp.org','http://127.0.0.1:8765','http://localhost:8765'].includes(location.origin)||
         dialogs[0].getAttribute('aria-modal')!=='true'||labelled(dialogs[0])!=='Courses & Grades')
        throw Error('observed_common_app_grade_dialog_required');
      root=dialogs[0];scope={kind:settings.grade_creation?'common_app_grade_creation':'common_app_grade_dialog',name:'Courses & Grades',heading:text(root.querySelector('h3')?.textContent)};
    }
    const controlQuery='input,select,textarea,[contenteditable=true],[role=combobox]'+(settings.generic_form?',[role=checkbox],[role=radio],[role=listbox],[role=textbox],[role=switch],[role=slider],[role=spinbutton]':'');
    const controls = Array.from(root.querySelectorAll(controlQuery)).filter(e=>
      visible(e) && (!settings.generic_form||!e.parentElement?.closest('[role=combobox]')) &&
      (settings.generic_form||e.type!=='search' && e.id!=='appFaqSearchControl' && !e.id.startsWith('ckySwitch')));
    if (controls.some(e=>e.type==='password')) throw Error('authentication_form_excluded_from_profile');
    const fields=[], seen=new Set(),nodes=new Map();
    for (const e of controls) {
      if (['submit','button','reset'].includes(e.type)) continue;
      const radio = e.type === 'radio';
      const identified=identity(e);
      const base = radio && e.name ? `n:${e.name}` : e.id ? `i:${e.id}` : e.name ? `n:${e.name}` : `l:${labels(e)}`;
      const key = !radio && identified.selector_count>1 ? `${base}@${identified.selector_index}` : base;
      if (radio && seen.has(key)) continue;
      seen.add(key);
      nodes.set(key,e);
      const members = radio ? controls.filter(x=>x.type==='radio' && x.name===e.name) : [e];
      const backedSelect=settings.generic_form&&e.getAttribute('role')==='combobox'&&e.querySelectorAll('select').length===1&&!e.querySelector('select').multiple&&!!e.getAttribute('aria-owns')&&e.querySelectorAll(':scope > label').length===1;
      const selectionMatches=!backedSelect||text(e.querySelector(':scope > label').textContent)===text(e.querySelector('select').selectedOptions[0]?.textContent);
      const calendar=settings.generic_form&&e.tagName==='INPUT'&&e.readOnly&&e.getAttribute('data-p-pattern')==='dd-mm-yy'&&e.parentElement.querySelectorAll('button[aria-haspopup=true]').length===1;
      const control = radio ? 'radio' : backedSelect ? 'select' : scope&&e.tagName==='MAT-SELECT'&&e.getAttribute('role')==='combobox'&&e.getAttribute('aria-multiselectable')!=='true' ? 'material_select' :
        e.tagName==='SELECT' && !e.multiple ? 'select' : e.tagName==='TEXTAREA' ? 'textarea' :
        e.getAttribute('role')==='combobox' ? 'unsupported' :
        ['text','email','tel','number','date','checkbox'].includes(e.type) ? e.type : 'unsupported';
      const label = radio ? group(e)||e.getAttribute('data-p-label')||labels(e) : labels(e);
      const options = radio ? members.map(x=>({value:x.value,label:labels(x),...identity(x),disabled:!!x.disabled})) :
        control==='select' ? Array.from((backedSelect?e.querySelector('select'):e).options).map(x=>({value:x.value,label:text(x.textContent),
          ...(x.parentElement.tagName==='OPTGROUP'?{group:text(x.parentElement.label)}:{}),
          disabled:!!x.disabled||!!x.parentElement.disabled})) : [];
      const peers=settings.generic_form?Array.from(e.parentElement.children).filter(x=>controls.includes(x)&&x.type!=='radio'):[];
      const segment=settings.generic_form&&peers.length>1?`Part ${peers.indexOf(e)+1} of ${peers.length}`:'';
      const calendarPart=calendar&&text(e.getAttribute('placeholder'))?`Date part: ${text(e.getAttribute('placeholder'))}`:'';
      let contextAnchor='';
      if(settings.generic_form)for(let box=e.parentElement;box&&box!==root;box=box.parentElement){
        const siblings=controls.filter(c=>box.contains(c)&&c.type!=='radio');
        if(siblings.length>1&&siblings[0]!==e&&labels(siblings[0])&&labels(siblings[0])!==label){contextAnchor=labels(siblings[0]);break;}
      }
      fields.push({key,name:e.name||'',label,group:[group(e),segment,calendarPart].filter(Boolean).join(' / '),control,...identified,
        ...(settings.generic_form?{context_anchor:contextAnchor}:{}),
        required:members.some(x=>x.required||x.getAttribute('aria-required')==='true')||label.includes('*')||group(e).includes('*'),
        disabled:members.every(x=>!!x.disabled||x.getAttribute('aria-disabled')==='true'),readonly:!!e.readOnly&&!calendar,
        ...(backedSelect?{widget:{kind:'owned_native_select'}}:calendar?{widget:{kind:'calendar',native_readonly:true}}:{}),
        value:radio ? members.find(x=>x.checked)?.value||'' : control==='checkbox' ? !!e.checked :
          e.tagName==='SELECT'&&e.multiple ? Array.from(e.selectedOptions).map(o=>o.value) :
          backedSelect?(selectionMatches?e.querySelector('select').value:''):['INPUT','SELECT','TEXTAREA'].includes(e.tagName)&&typeof e.value==='string' ? e.value : e.getAttribute('aria-valuetext')||text(e.innerText),options,
        invalid:!selectionMatches||members.some(x=>x.getAttribute('aria-invalid')==='true'||x.validity?.valid===false)});
    }
    const actions=Array.from(root.querySelectorAll('button,input[type=submit],input[type=button]')).filter(visible).map((e,i)=>({
      key:e.id?`i:${e.id}`:`a:${text(e.textContent||e.value)}:${i}`,label:text(e.textContent||e.value),selector:selector(e),disabled:!!e.disabled}));
    const recordTables=[];
    if(settings.generic_form){
      const calendarParents=controls.filter(e=>e.tagName==='INPUT'&&e.readOnly&&e.getAttribute('data-p-pattern')==='dd-mm-yy'&&e.parentElement.querySelectorAll('button[aria-haspopup=true]').length===1).map(e=>e.parentElement);
      const helpers=Array.from(root.querySelectorAll('button')).filter(e=>calendarParents.some(p=>p.contains(e)));
      for(let i=actions.length-1;i>=0;i--)if(helpers.some(e=>selector(e)===actions[i].selector&&text(e.textContent)===actions[i].label))actions.splice(i,1);
      if(!genericDialog)for(const table of Array.from(root.querySelectorAll('table,[role=grid]')).filter(visible)){
        const owned=e=>e.closest('table,[role=grid]')===table;
        const headers=Array.from(table.querySelectorAll('th,[role=columnheader]')).filter(e=>visible(e)&&owned(e)).map(e=>text(e.innerText));
        const rows=Array.from(table.querySelectorAll('tbody tr,[role=row]')).filter(e=>visible(e)&&owned(e)&&e.querySelector('td,[role=gridcell]'));
        if(headers.length<2||!rows.length||rows.some(r=>r.querySelector('input,select,textarea,[contenteditable=true]')||!r.querySelector('a,button')))continue;
        const cells=rows.map(r=>Array.from(r.querySelectorAll('td,[role=gridcell]')).filter(owned).map(c=>text(c.innerText)));
        let id=identity(table);
        if(!id.selector){
          const anchor=table.parentElement.closest('[id],[name]'),base=anchor&&selector(anchor);
          const query=base?base+' '+table.tagName.toLowerCase()+(table.getAttribute('role')==='grid'?'[role="grid"]':''):null;
          const matches=query?Array.from(document.querySelectorAll(query)):[];
          id={selector:query,selector_count:matches.length};
          if(matches.length!==1||matches[0]!==table)throw Error('unique_rectangular_record_summary_required');
        }
        if(!id.selector||id.selector_count!==1||cells.some(row=>row.length!==headers.length))throw Error('unique_rectangular_record_summary_required');
        recordTables.push({headers,rows:cells,caption:text(table.querySelector('caption')?.innerText),selector:id.selector,selector_count:1});
        const buttons=Array.from(table.querySelectorAll('button,input[type=submit],input[type=button]')).filter(visible);
        for(let i=actions.length-1;i>=0;i--)if(buttons.some(e=>selector(e)===actions[i].selector))actions.splice(i,1);
      }
    }
    const result={schema:'observed-page/1',title:document.title,frames_present:!!document.querySelector('iframe'),fields,actions};
    if(settings.generic_form){
      const formSelector=selector(root)||'form',matches=Array.from(document.querySelectorAll(formSelector));
      const fragments=[root,...Array.from(root.querySelectorAll('*'))].filter(e=>visible(e)&&!e.closest('input,select,textarea,button,label,legend,[role=status]'))
        .flatMap(e=>Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>text(n.textContent))).filter(Boolean)
        .filter(t=>!fields.some(f=>text(f.label)===t||f.options.some(o=>o.label===t)));
      result.generic_context={instructions:fragments.join(' ')};
      const selectedViews=Array.from(root.querySelectorAll('[role=tab][aria-selected=true]')).filter(visible).map(e=>text(e.innerText||e.textContent)).filter(Boolean);
      const formViews=Array.from(root.querySelectorAll('[role=tab]')).filter(visible).map(e=>text(e.innerText||e.textContent)).filter(Boolean);
      result.generic_form={schema:'generic-form/1',scope:{selector:formSelector,selector_count:matches.length,selector_index:matches.indexOf(root)},
        ...(genericDialog?{dialog:genericDialog}:{}),
        ...(!genericDialog&&selectedViews.length===1?{view:{name:selectedViews[0]}}:{}),
        ...(!genericDialog&&formViews.length?{views:formViews}:{}),
        ...(recordTables.length?{record_collections:recordTables}:{}),
        destination:{action:root.action||location.href,method:root.method.toLowerCase()}};
    }
    if(scope) {
      result.scope=scope;result.requirement_groups=[];
      const rows=new Map();
      for(const f of fields) {
        const match=/^Transcript (\d+), Course (\d+), (.*?)(?:undefined)?$/.exec(f.label);
        if(!match)continue;
        const row=`T${match[1]}C${match[2]}`,part=match[3];
        if(!rows.has(row))rows.set(row,{grades:[],credits:[],na:null});
        const item=rows.get(row);
        let kind;
        if(/^(Semester [12]|Trimester [123]|Quarter [1-4]|Final)( Grade)?$/.test(part))kind='grades';
        else if(/^(Semester [12]|Trimester [123]|Quarter [1-4]) Credit$/.test(part)||part==='Final Credits')kind='credits';
        else if(part==='Credits not applicable')item.na=f.key;
        if(kind) {
          item[kind].push(f.key);f.requirement_group={row,kind};f.required=false;
          const node=nodes.get(f.key);
          // Official Common App guidance requires one applicable term, not
          // every blank period. Suppress only native valueMissing, never an
          // aria-invalid error or a malformed nonempty value.
          if(f.value===''&&node?.validity?.valueMissing&&node.getAttribute('aria-invalid')!=='true')f.invalid=false;
        }
      }
      if(settings.grade_creation)result.common_academic={schema:'common-academic-page/1',pending_rows:[],
        instructions:Array.from(root.querySelectorAll('p')).filter(visible).map(e=>text(e.innerText))};
      for(const [row,item] of rows) {
        const transcript=/^T(\d+)C/.exec(row)[1],headers=['gradingScale','schedule'].map(part=>fields.find(f=>f.key===`i:${part}Control${transcript}`));
        if(settings.grade_creation&&headers.some(f=>f&&['','Select'].includes(f.value))&&(!item.grades.length||!item.credits.length||!item.na)) {
          result.common_academic.pending_rows.push(row);
          for(const f of fields)if(f.requirement_group?.row===row)delete f.requirement_group;
          continue;
        }
        for(const kind of ['grades','credits']) {
        if(!item[kind].length||!item.na)throw Error('complete_observed_course_term_groups_required');
        const rule={row,kind,field_keys:item[kind],...(kind==='credits'?{not_applicable_key:item.na}:{})};
        result.requirement_groups.push(rule);
        const present=item[kind].some(key=>fields.find(f=>f.key===key).value!=='');
        const na=kind==='credits'&&fields.find(f=>f.key===item.na).value===true;
        if(!present&&!na)fields.find(f=>f.key===item[kind][0]).invalid=true;
        }
      }
    }
    if(!settings.generic_form&&location.origin==='https://apply.mitadmissions.org'&&/^\/apply\/(frm|tes)$/.test(location.pathname)) {
      // Slate record summaries expose edit/Add New links instead of inputs.
      // Record only headers and counts, never applicant row values or names.
      result.collections=Array.from(document.querySelectorAll('table')).filter(visible).map(t=>({
        kind:'editable_table',label:Array.from(t.querySelectorAll('thead th,[role=columnheader]')).map(e=>text(e.textContent)).join(' | ')||'Unlabeled editable table',
        row_count:t.querySelectorAll('tbody tr').length,
        editor_control_count:Array.from(t.querySelectorAll('a')).filter(a=>visible(a)&&a.getAttribute('href')==='//').length
      })).filter(t=>t.editor_control_count>0);
      if(document.title==='Self-reported coursework'&&location.pathname==='/apply/frm') {
        const classes='This section is only required for students in the U.S. or who attend U.S.-based school systems. Report all classes you have taken or will take in high school or for high school credit.';
        const stem='All students are required to fill out this section. Please indicate the status and year taken (or to be taken) of each class listed below. If you took these classes in a year that is not listed, or you did not take the class, you can leave the year blank. If you have taken a class multiple times, please list the year you most recently took it.';
        const paragraphs=Array.from(document.querySelectorAll('.form_p .form_label')).filter(visible).map(e=>text(e.textContent));
        const pairs=[];
        for(const f of fields.filter(f=>f.control==='select'&&f.label==='Year')) {
          const question=nodes.get(f.key).closest('.form_question'),prev=question?.previousElementSibling;
          const statusNode=prev?.classList.contains('form_question')&&prev.parentElement===question.parentElement&&prev.querySelectorAll('select').length===1 ? prev.querySelector('select') : null;
          const status=fields.find(x=>nodes.get(x.key)===statusNode),subject=(status?.label||'').replace(/\*$/,'').toLowerCase();
          if(['calculus','physics','biology','chemistry'].includes(subject))pairs.push({subject,status_key:status.key,year_key:f.key});
        }
        if(paragraphs.filter(p=>p.startsWith(classes)).length===1&&paragraphs.filter(p=>p===stem).length===1&&pairs.length===4)
          result.mit_coursework={schema:'mit-coursework/1',classes_instruction:classes,stem_instruction:stem,subject_year_pairs:pairs};
      }
    }
    if(!settings.generic_form&&!scope&&location.origin==='https://apply.universityofcalifornia.edu') {
      const recordTables=Array.from(document.querySelectorAll('main table')).filter(visible).map(t=>({
        kind:'editable_table',label:Array.from(t.querySelectorAll('th,[role=columnheader]')).map(e=>text(e.textContent)).join(' | ')||'Unlabeled editable table',
        row_count:Array.from(t.querySelectorAll('tr')).filter(r=>r.querySelector('td')).length,
        editor_control_count:Array.from(t.querySelectorAll('a,button,input[type=button]')).filter(e=>visible(e)&&
          /^(Edit|Delete|Add(?: .*)?)$/.test(text(e.value||e.textContent))).length
      })).filter(t=>t.editor_control_count>0);
      if(recordTables.length)result.collections=recordTables;
      if(location.pathname==='/my-application/testScoreToefl') {
        const cards=Array.from(document.querySelectorAll('[id="reportedTestLayer"]')).filter(visible);
        const editors=cards.flatMap(c=>Array.from(c.querySelectorAll('button'))).filter(e=>visible(e)&&/^(Edit|Delete)$/.test(text(e.textContent)));
        if(cards.length&&editors.length)result.collections=[...(result.collections||[]),{
          kind:'editable_table',label:'Reported English language proficiency tests',row_count:cards.length,editor_control_count:editors.length}];
      }
    }
    if (!settings.generic_form&&!scope&&['https://apply.commonapp.org','http://127.0.0.1:8765','http://localhost:8765'].includes(location.origin)) {
      const route=/^\/common\/(\d+)\/(\d+)$/.exec(location.pathname);
      if(route) {
        const items=Array.from(document.querySelectorAll('a[id^="secondaryNavItem"],a[id^="tertiaryNavItem"]')).filter(visible)
          .map(e=>({key:e.id,status:text(e.querySelector('.nav-item__status')?.textContent).toLowerCase()}))
          .filter(e=>['complete','in progress','incomplete','not started'].includes(e.status)).sort((a,b)=>a.key.localeCompare(b.key));
        const current_page_key=`tertiaryNavItem${route[1]}_${route[2]}`;
        if(items.some(e=>e.key===current_page_key))result.state_metadata={schema:'observed-state/1',
          coverage:'common_app_visible_navigation',current_page_key,items};
      }
    }
    return result;
  },{grade_dialog:options.grade_dialog===true,grade_creation:options.grade_creation===true,generic_form:options.generic_form===true,generic_dialog:options.generic_dialog===true});
  const page={...result,url:await tab.url()};
  if(options.generic_form){
    if(page.generic_form.record_collections){
      page.generic_form.record_collections=page.generic_form.record_collections.map(c=>({...c,key:'rc:'+digest({headers:c.headers,caption:c.caption}).slice(0,24)}));
      if(new Set(page.generic_form.record_collections.map(c=>c.key)).size!==page.generic_form.record_collections.length)throw Error('ambiguous_record_summary_identity');
    }
    page.generic_form.instructions_sha256=digest(page.generic_context.instructions);
    page.fields=genericFieldIdentities(page.fields,options.generic_identity_fields||[]).map(f=>{
      const key='g:'+digest({label:f.label,group:f.group,control:f.control,required:f.required}).slice(0,24);
      if(!['radio','select'].includes(f.control))return {...f,key};
      const selected=f.options.find(o=>o.value===f.value),buckets=new Map();
      for(const o of f.options){const id=digest({label:o.label,group:o.group||''});if(!buckets.has(id))buckets.set(id,[]);buckets.get(id).push(o);}
      const normalized=Array.from(buckets,([value,items])=>items.length===1?{...items[0],native_value:items[0].value,value}:
        {...items[0],native_value:'',value,disabled:true,ambiguous:true,occurrences:items.length});
      const selectedId=selected?digest({label:selected.label,group:selected.group||''}):'';
      const ambiguous=selected&&buckets.get(selectedId).length>1;
      return {...f,key,options:normalized,value:ambiguous?'':selectedId,invalid:f.invalid||!!ambiguous};
    });
    page.actions=page.actions.map(a=>({...a,key:'a:'+digest(a.label).slice(0,24)}));
    if(new Set(page.fields.map(f=>f.key)).size!==page.fields.length||new Set(page.actions.map(a=>a.key)).size!==page.actions.length)
      throw Error('ambiguous_generic_semantic_controls');
    return page;
  }
  return normalizeCommonAppRadios(page);
}

export function guard(context,page,allowedOrigin,restoration=false) {
  const origin=new URL(page.url).origin;
  if (!['chrome','edge'].includes(context.browser_family)||context.transport!=='extension'||
      context.access_verified!==true||context.origin!==origin) throw Error('documented_host_browser_permission_required');
  const synthetic=context.synthetic_test===true && ['http://127.0.0.1:8765','http://localhost:8765'].includes(origin);
  if (origin!==allowedOrigin&&!synthetic) throw Error('application_origin_mismatch');
  if(page.generic_form){
    if(page.generic_form.schema!=='generic-form/1'||context.application_authorized!==true||context.authorized_origin!==origin||
       typeof context.target_id!=='string'||context.real_account_test||context.restore_after_test||restoration||
       (!origin.startsWith('https://')&&!synthetic))throw Error('generic_target_origin_authorization_required');
    return;
  }
  if(origin==='https://apply.universityofcalifornia.edu'&&new URL(page.url).pathname!=='/my-application/accountPersonal'&&
     !['uc_course_editor','uc_factual','uc_course_refill','uc_school_terms'].some(tag=>page[tag]))
    throw Error('observed_uc_page_contract_required');
  const commonFactual=page.common_factual?.schema==='common-factual-page/1'&&
    ({language:'/common/3/16',household:'/common/5/26',grade12_status:'/common/13/58'})[page.common_factual.kind]===new URL(page.url).pathname;
  const commonAcademic=page.common_academic?.schema==='common-academic-page/1'&&page.scope?.kind==='common_app_grade_creation'&&
    /^\/common\/13\/(55|56|57)$/.test(new URL(page.url).pathname);
  const commonSchool=page.common_school?.schema==='common-school-page/1'&&page.schema==='observed-school-page/1'&&
    ({current:'/common/4/18',other:'/common/4/19'})[page.common_school.kind]===new URL(page.url).pathname;
  const commonCurrent=page.common_current?.schema==='common-current-page/1'&&page.schema==='observed-current-page/1'&&new URL(page.url).pathname==='/common/4/24';
  if(origin==='https://apply.commonapp.org'&&new URL(page.url).pathname!=='/common/3/11'&&
     page.scope?.kind!=='common_app_grade_dialog'&&!commonAcademic&&!page.common_ielts&&!commonFactual&&!commonSchool&&!commonCurrent)
    throw Error('observed_common_app_page_contract_required');
  if (context.real_account_test) {
    if(context.full_state_restoration_verified!==true) throw Error('real_test_restoration_not_established');
    const state=page.state_metadata,strategy=context.restoration_strategy;
    if(strategy?.kind==='restore_uc_factual') {
      const current=state?.sections?.flatMap(s=>s.pages).find(i=>origin+i.href===page.url);
      if(origin!=='https://apply.universityofcalifornia.edu'||page.uc_factual?.schema!=='uc-factual-page/1'||
         state?.schema!=='observed-state/1'||state.coverage!=='uc_visible_review_and_draft'||state.page_url!==page.url||
         state.term!=='Fall quarter/semester 2027'||state.draft_marker!=='Open application'||strategy.page_url!==page.url||
         !/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||
         !strategy.review_label||!strategy.section||
         (!restoration&&(strategy.baseline_state_sha256!==digest(state)||current?.label!==strategy.review_label||
           state.sections.find(s=>s.label===strategy.section)?.completion_text!=='Section Complete')))
        throw Error('observed_uc_factual_restoration_evidence_required');
      return;
    }
    if(strategy?.kind==='restore_uc_course_refill') {
      const route=page.uc_course_refill?.context?.summary_url,all=state?.sections?.flatMap(s=>s.pages)||[];
      if(origin!=='https://apply.universityofcalifornia.edu'||page.uc_course_refill?.schema!=='uc-course-refill/1'||
         state?.schema!=='observed-state/1'||state.coverage!=='uc_visible_review_and_draft'||state.page_url!==page.url||
         state.term!=='Fall quarter/semester 2027'||state.draft_marker!=='Open application'||strategy.page_url!==page.url||
         !/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||!/^[a-f0-9]{64}$/.test(strategy.baseline_parent_sha256)||
         (!restoration&&(strategy.baseline_state_sha256!==digest(state)||
           !all.some(i=>origin+i.href===route&&i.label==='Edit grade')||
           !all.some(i=>i.href==='/my-application/acadHistAddInformation'&&i.label==='Edit Additional information')||
           state.sections.find(s=>s.label==='Academic history')?.completion_text!=='Section Complete')))
        throw Error('observed_uc_refill_restoration_evidence_required');
      return;
    }
    if(strategy?.kind==='restore_uc_school_terms') {
      const current=state?.sections?.flatMap(s=>s.pages)||[];
      if(origin!=='https://apply.universityofcalifornia.edu'||page.uc_school_terms?.schema!=='uc-school-terms/1'||
         state?.coverage!=='uc_visible_review_and_draft'||state.page_url!==page.url||
         state.term!=='Fall quarter/semester 2027'||state.draft_marker!=='Open application'||strategy.page_url!==page.url||
         !/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||
         (!restoration&&(strategy.baseline_state_sha256!==digest(state)||
           !current.some(i=>i.href==='/my-application/acadhistFrHighSchool'&&i.label==='Edit High schools')||
           !current.some(i=>i.href==='/my-application/acadHistAddInformation'&&i.label==='Edit Additional information')||
           state.sections.find(s=>s.label==='Academic history')?.completion_text!=='Section Complete')))
        throw Error('observed_uc_school_restoration_evidence_required');
      return;
    }
    if(strategy?.kind==='restore_uc_courses') {
      const course=page.uc_course_editor,parent=page.uc_course_parent;
      const current=state?.sections?.flatMap(s=>s.pages).find(i=>origin+i.href===course?.summary_url);
      if(origin!=='https://apply.universityofcalifornia.edu'||course?.schema!=='uc-course-editor/1'||
         parent?.schema!=='uc-course-parent/1'||state?.schema!=='observed-state/1'||
         state.coverage!=='uc_visible_review_and_draft'||state.page_url!==page.url||
         state.term!=='Fall quarter/semester 2027'||state.draft_marker!=='Open application'||
         strategy.page_url!==page.url||!/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||
         !/^[a-f0-9]{64}$/.test(strategy.baseline_parent_sha256)||
         (!restoration&&(strategy.baseline_state_sha256!==digest(state)||strategy.baseline_parent_sha256!==digest(parent)||
           current?.label!=='Edit grade'||
           !state.sections.flatMap(s=>s.pages).some(i=>i.href==='/my-application/acadHistAddInformation'&&i.label==='Edit Additional information')||
           state.sections.find(s=>s.label==='Academic history')?.completion_text!=='Section Complete')))
        throw Error('observed_uc_course_restoration_evidence_required');
      return;
    }
    if(strategy?.kind==='restore_uc_personal') {
      const current=state?.sections?.flatMap(s=>s.pages).find(i=>i.href==='/my-application/accountPersonal');
      if(page.url!=='https://apply.universityofcalifornia.edu/my-application/accountPersonal'||
         state?.schema!=='observed-state/1'||state.coverage!=='uc_visible_review_and_draft'||state.page_url!==page.url||
         state.term!=='Fall quarter/semester 2027'||state.draft_marker!=='Open application'||
         strategy.page_url!==page.url||!/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||
         (!restoration&&(strategy.baseline_state_sha256!==digest(state)||current?.label!=='Edit Personal information'||
           state.sections.find(s=>s.label==='About you')?.completion_text!=='Section Complete')))
        throw Error('observed_uc_restoration_evidence_required');
      return;
    }
    if(strategy?.kind==='restore_mit_coursework') {
      if(origin!=='https://apply.mitadmissions.org'||page.mit_coursework?.schema!=='mit-coursework/1'||
         state?.schema!=='observed-state/1'||state.coverage!=='mit_visible_review_and_draft'||state.page_url!==page.url||
         state.application_status!=='In Progress'||!Array.isArray(state.errors)||!Array.isArray(state.warnings)||
         strategy.page_url!==page.url||!/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||
         (!restoration&&(strategy.baseline_state_sha256!==digest(state)||state.errors.some(i=>i.section==='Self-reported coursework'))))
        throw Error('observed_mit_restoration_evidence_required');
      return;
    }
    const grade=strategy?.kind==='restore_completed_grade_dialog';
    const strategyKnown=grade ? page.scope?.kind==='common_app_grade_dialog'&&page.editor_state?.schema==='grade-parent/1'&&
      strategy.baseline_parent_sha256===digest(page.editor_state)&&page.editor_state.completion_checked===true : strategy?.kind==='restore_completed_native_page';
    if((!synthetic&&origin!=='https://apply.commonapp.org')||state?.schema!=='observed-state/1'||state.coverage!=='common_app_visible_navigation'||
       !strategyKnown||strategy.current_page_key!==state.current_page_key||
       !/^[a-f0-9]{64}$/.test(strategy.baseline_state_sha256)||
       (!restoration&&(!state.items.some(e=>e.key===state.current_page_key&&e.status==='complete')||strategy.baseline_state_sha256!==digest(state))))
      throw Error('observed_completed_page_restoration_evidence_required');
  }
}

export async function applyWrites(tab,plan,context) {
  const page=await observe(tab,{generic_form:!!plan.generic_form,generic_identity_fields:plan.generic_identity_fields});
  guard(context,page,plan.allowed_origin);
  if(page.generic_form)throw Error('dedicated_generic_page_port_required');
  if(page.common_factual||page.common_ielts||page.common_academic||page.common_school||page.common_current)throw Error('dedicated_common_page_port_required');
  if(page.collections?.length)throw Error('repeatable_record_editors_not_supported');
  if (!plan.ready||context.journal_persisted!==true) throw Error('persisted_ready_checkpoint_required');
  if (digest(page)!==plan.observation_sha256) throw Error('page_changed_since_preparation');
  await writeObserved(tab,page,plan.writes);
  const after=await observe(tab);
  if (digest(structure(after))!==plan.structure_sha256) throw Error('conditional_page_changed_collect_before_save');
  if (after.fields.some(f=>f.invalid)) throw Error('website_validation_unresolved');
  if (digest(values(after))!==plan.expected_values_sha256) throw Error('unexpected_page_values_before_save');
  return after;
}

export function genericTextareaAllowed(f,bindings){
  const b=bindings?.find(b=>b.key===f.key&&b.role==='factual'),ref=b?.ref||'';
  return !!b&&((b.purpose==='academic_name'&&ref.startsWith('psr:')&&/:(description|course_description)$/.test(ref))||
    b.purpose==='name'&&/^personal\.(legal_given_name|legal_family_name|middle_name)$/.test(ref)||
    b.purpose==='address'&&/^address\.(permanent|mailing)\.(street|street_1|street_2|line_1|line_2|city|postal_code)$/.test(ref));
}

export async function writeObserved(tab,page,writes,{semantic_bindings}={}) {
  if(page.generic_form&&manualPattern.test([page.title,page.generic_context?.instructions,page.generic_form.dialog?.name].filter(Boolean).join(' ')))throw Error('manual_application_section_excluded');
  for (const w of writes) {
    const f=page.fields.find(f=>f.key===w.field_key);
    if (!f||f.disabled||f.readonly||!['text','textarea','email','tel','number','date','select','radio','checkbox'].includes(f.control)) throw Error('observed_editable_field_required');
    if(w.native_event&&(f.control!=='select'||f.widget?.kind!=='owned_native_select'))throw Error('matching_owned_select_reaffirmation_required');
    if(w.count_input&&(!page.generic_form||!['text','number'].includes(f.control)||f.widget||! /^(?:0|[1-9]\d{0,2})$/.test(String(w.value))))throw Error('bounded_native_count_input_required');
    if(w.numeric_input&&(!page.generic_form||!['text','number'].includes(f.control)||!/^\d{1,3}\.\d{2}$/.test(String(w.value))||Number(w.value)>100||!semantic_bindings?.some(i=>i.key===f.key&&i.ref===w.fact_ref&&i.ref.startsWith('psr-average:')&&i.format==='decimal_fixed_2'&&i.role==='factual')))throw Error('source_bound_percentage_numeric_input_required');
    if (f.control==='textarea'&&!(page.generic_form?genericTextareaAllowed(f,semantic_bindings):factualTextareaLabels.includes(normalizeLabel(f.label)))) throw Error('narrative_control_excluded');
    if (manualField(f))
      throw Error('manual_field_excluded');
    if (f.control==='radio') {
      const o=f.options.find(o=>o.value===w.value&&!o.disabled);
      if (!o?.selector) throw Error('observed_radio_option_required');
      const label=page.generic_form?await visibleControlLabel(tab,o,o.label):null;
      if(label)await tab.playwright.locator(label).click();
      else await (await observedLocator(tab,o)).check();
    } else {
      if (!f.selector) throw Error('unambiguous_observed_selector_required');
      const locator=await observedLocator(tab,f);
      if (f.control==='select') {
        const option=f.options.find(o=>o.value===w.value&&!o.disabled);
        if (!option) throw Error('observed_select_option_required');
        if(w.native_event){
          if(f.widget?.kind!=='owned_native_select'||f.value!==w.value)throw Error('matching_owned_select_reaffirmation_required');
          await locator.evaluate((e,option)=>{
            const select=e.querySelector('select'),label=(e.querySelector(':scope > label')?.textContent||'').replace(/\s+/g,' ').trim();
            if(e.getAttribute('role')!=='combobox'||e.querySelectorAll('select').length!==1||select.disabled||select.multiple||!select.getAttribute('onchange')||
               select.value!==option.native_value||label!==option.label||Array.from(select.options).filter(o=>o.value===option.native_value&&(o.textContent||'').replace(/\s+/g,' ').trim()===option.label&&!o.disabled).length!==1)
              throw Error('matching_native_change_handler_required');
          },option);
          const control=locator.locator('select');if(await control.count()!==1)throw Error('unique_observed_native_select_required');
          await control.selectOption({value:option.native_value});
          await waitForGenericLoader(tab);
          if(typeof tab.getAXState==='function')await tab.getAXState({emit:false});else await tab.playwright.domSnapshot();
        }
        else if(f.widget?.kind==='owned_native_select')await chooseOwnedNativeSelect(tab,locator,f,option);
        else await locator.selectOption({value:page.generic_form?option.native_value:w.value});
      } else if (f.control==='checkbox') await locator.setChecked(w.value);
      else if(f.widget?.kind==='calendar')await chooseCalendarDate(tab,locator,f,String(w.value));
      else if(w.numeric_input){if(typeof tab.clipboard?.writeText!=='function')throw Error('documented_browser_clipboard_required');await tab.clipboard.writeText(String(w.value));await locator.click();await locator.press('Control+A');await locator.press('Control+V');await locator.press('Tab');}
      else if(w.count_input){await locator.fill('');await locator.pressSequentially(String(w.value));await locator.press('Tab');}
      else await locator.fill(String(w.value));
    }
  }
}

async function visibleControlLabel(tab,field,label){
  return tab.playwright.evaluate(({selector,label})=>{
    const elements=document.querySelectorAll(selector);if(elements.length!==1)return null;
    const e=elements[0],matches=Array.from(e.labels||[]).filter(l=>l.getClientRects().length&&(l.innerText||'').replace(/\s+/g,' ').trim()===label);
    return matches.length===1&&e.id?`label[for="${e.id.replaceAll('\\','\\\\').replaceAll('"','\\"')}"]`:null;
  },{selector:field.selector,label});
}

async function chooseOwnedNativeSelect(tab,locator,field,option){
  const before=await locator.evaluate(e=>({role:e.getAttribute('role'),owns:e.getAttribute('aria-owns'),expanded:e.getAttribute('aria-expanded'),selects:e.querySelectorAll('select').length,label:e.querySelector(':scope > label')?.id}));
  if(before.role!=='combobox'||!before.owns||!before.label||before.selects!==1||before.expanded!=='false')throw Error('closed_owned_native_select_required');
  const escape=value=>value.replaceAll('\\','\\\\').replaceAll('"','\\"');
  await tab.playwright.locator(`[id="${escape(before.label)}"]`).click();
  await tab.playwright.locator(`[id="${escape(before.owns)}"]`).waitFor({state:'visible',timeoutMs:10000});
  if(typeof tab.getAXState==='function')await tab.getAXState({emit:false});
  else await tab.playwright.domSnapshot();
  const selected=await tab.playwright.evaluate(({selector,label,native})=>{
    const controls=document.querySelectorAll(selector);if(controls.length!==1)throw Error('unique_live_choice_owner_required');
    const owner=controls[0],select=owner.querySelector('select'),panel=document.getElementById(owner.getAttribute('aria-owns'));
    const n=Array.from(select?.options||[]).filter(o=>(o.textContent||'').replace(/\s+/g,' ').trim()===label&&o.value===native&&!o.disabled);
    if(n.length!==1||!panel||!panel.getClientRects().length||owner.getAttribute('aria-expanded')!=='true')throw Error('owned_choice_evidence_changed');
    const found=Array.from(panel.querySelectorAll('[role=option]')).filter(o=>o.getClientRects().length&&(o.innerText||'').replace(/\s+/g,' ').trim()===label&&o.getAttribute('aria-disabled')!=='true');
    if(found.length!==1||!found[0].id)throw Error('unique_visible_owned_option_required');
    return {id:found[0].id,selector:`[id="${found[0].id.replaceAll('\\','\\\\').replaceAll('"','\\"')}"]`};
  },{selector:field.selector,label:option.label,native:option.native_value});
  const target=tab.playwright.locator(selected.selector);if(await target.count()!==1)throw Error('unique_visible_owned_option_required');
  if(typeof tab.getAXState==='function'&&typeof tab.click==='function'){
    const ax=await tab.getAXState({emit:false,disableDiffing:true});
    const escaped=selected.id.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const pattern=new RegExp(`^\\s*(\\d+) .*ID: ${escaped}(?:,|$)`);
    const matches=String(ax).split('\n').map(line=>pattern.exec(line)).filter(Boolean);
    if(matches.length!==1)throw Error('unique_accessible_owned_option_required');
    await tab.click(Number(matches[0][1]));
  }else await target.click();
  await waitForGenericLoader(tab);
  if(typeof tab.getAXState==='function')await tab.getAXState({emit:false});
  else await tab.playwright.domSnapshot();
  const matches=await locator.evaluate((e,label)=>(e.querySelector(':scope > label')?.textContent||'').replace(/\s+/g,' ').trim()===label,option.label);
  if(!matches)throw Error('owned_select_visible_readback_mismatch');
}

async function chooseCalendarDate(tab,locator,field,value){
  const parsed=/^(\d{2})-(\d{2})-(\d{4})$/.exec(value);
  if(!parsed)throw Error('complete_dmy_calendar_date_required');
  const [day,month,year]=parsed.slice(1).map(Number),date=new Date(Date.UTC(year,month-1,day));
  if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day)throw Error('valid_calendar_date_required');
  const button=await locator.evaluate(e=>{
    if(!e.readOnly||e.getAttribute('data-p-pattern')!=='dd-mm-yy')throw Error('observed_calendar_format_required');
    const buttons=e.parentElement.querySelectorAll('button[aria-haspopup=true]');
    if(buttons.length!==1||!e.id)throw Error('unique_observed_calendar_trigger_required');
    return `[id="${e.id.replaceAll('\\','\\\\').replaceAll('"','\\"')}"] ~ button[aria-haspopup=true]`;
  });
  await tab.playwright.locator(button).click();
  const picker=await tab.playwright.evaluate(()=>{
    const year=Array.from(document.querySelectorAll('select[aria-label="select year"]')).filter(e=>e.getClientRects().length);
    const month=Array.from(document.querySelectorAll('select[aria-label="select month"]')).filter(e=>e.getClientRects().length);
    if(year.length!==1||month.length!==1)throw Error('unique_visible_calendar_header_required');
    return {years:Array.from(year[0].options).map(o=>o.value),months:Array.from(month[0].options).map(o=>o.value)};
  });
  if(!picker.years.includes(String(year))||!picker.months.includes(String(month-1)))throw Error('observed_calendar_date_out_of_range');
  await tab.playwright.locator('select[aria-label="select year"]').filter({visible:true}).selectOption({value:String(year)});
  await tab.playwright.locator('select[aria-label="select month"]').filter({visible:true}).selectOption({value:String(month-1)});
  const target=await tab.playwright.evaluate(({day,month,year})=>{
    const cells=Array.from(document.querySelectorAll('td[data-year][data-month]')).filter(e=>e.getClientRects().length&&Number(e.getAttribute('data-year'))===year&&Number(e.getAttribute('data-month'))===month-1);
    const links=cells.flatMap(e=>Array.from(e.querySelectorAll('a'))).filter(e=>e.getClientRects().length&&e.textContent.trim()===String(day));
    if(links.length!==1)throw Error('unique_observed_calendar_day_required');
    return `td[data-year="${year}"][data-month="${month-1}"] a`;
  },{day,month,year});
  await tab.playwright.locator(target).getByText(String(day),{exact:true}).click();
  if(await locator.evaluate(e=>e.value)!==value)throw Error('calendar_date_readback_mismatch');
}

async function observedLocator(tab,identity) {
  const locator=tab.playwright.locator(identity.selector);
  const count=identity.selector_count??1, index=identity.selector_index??0;
  if (!Number.isInteger(count)||!Number.isInteger(index)||count<1||index<0||index>=count||await locator.count()!==count)
    throw Error('observed_selector_changed_or_ambiguous');
  return count===1 ? locator : locator.nth(index);
}

export async function inspectOptions(tab,fieldKey) {
  // Read-only choice discovery for an observed Material single-select. Opening
  // and closing its listbox must preserve every field and visible status.
  // Discovery does not promote unsupported controls into editable plan fields.
  const before=await observe(tab),field=before.fields.find(f=>f.key===fieldKey);
  if(!field||field.control!=='unsupported'||!field.selector||field.disabled)throw Error('observed_custom_combobox_required');
  const locator=await observedLocator(tab,field);
  const widget=await locator.evaluate(e=>({tag:e.tagName,role:e.getAttribute('role'),expanded:e.getAttribute('aria-expanded')}));
  if(widget.tag!=='MAT-SELECT'||widget.role!=='combobox'||widget.expanded!=='false')throw Error('closed_material_single_select_required');
  let discovered;
  try {
    await locator.click();
    discovered=await tab.playwright.evaluate(label=>{
      const visible=e=>!!e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
      const panels=Array.from(document.querySelectorAll('[role=listbox]')).filter(e=>visible(e)&&e.getAttribute('aria-label')===label);
      if(panels.length!==1||panels[0].getAttribute('aria-multiselectable')==='true')throw Error('unique_observed_single_listbox_required');
      const options=Array.from(panels[0].querySelectorAll('[role=option]')).filter(visible).map(e=>({
        label:(e.innerText||'').replace(/\s+/g,' ').trim(),disabled:e.getAttribute('aria-disabled')==='true',selected:e.getAttribute('aria-selected')==='true'}));
      if(!options.length||options.some(o=>!o.label)||options.filter(o=>o.selected).length>1)throw Error('observed_option_labels_required');
      return {schema:'observed-options/1',options};
    },field.label);
  } finally {
    await locator.press('Escape');
    const after=await observe(tab);
    if(digest(after)!==digest(before))throw Error('options_inspection_changed_page_state');
  }
  return {...discovered,field_key:fieldKey,filling_supported:false};
}

export async function saveAndRead(tab,plan,context) {
  return saveObserved(tab,plan,context,false);
}

export async function saveGenericDraft(tab,plan,context){
  if(!plan.generic_form)throw Error('generic_form_plan_required');
  return saveObserved(tab,plan,context,false,false);
}

export async function waitForGenericLoader(tab){
  const busy=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('[role=dialog]'))
    .filter(e=>e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility)&&
      !(e.innerText||'').trim()&&!e.querySelector('button,input,select,textarea,a,[role=button]'))
    .map(e=>e.id).filter(Boolean));
  if(Array.isArray(busy)&&busy.length===1)await tab.playwright.locator(`[id="${busy[0].replaceAll('\\','\\\\').replaceAll('"','\\"')}"]`).waitFor({state:'hidden',timeoutMs:10000});
}

async function saveObserved(tab,plan,context,restoration,revisit=true) {
  if(plan.generic_stage)throw Error('branch_discovery_cannot_save');
  if(revisit&&plan.generic_form?.dialog)throw Error('dialog_requires_saveDraft_and_independent_saved_reader');
  const page=await observe(tab,{generic_form:!!plan.generic_form,generic_dialog:!!plan.generic_form?.dialog,generic_identity_fields:plan.generic_identity_fields});
  guard(context,page,plan.allowed_origin,restoration);
  if(page.generic_form&&plan.target_id!==context.target_id)throw Error('generic_plan_target_mismatch');
  if(page.common_factual||page.common_ielts||page.common_academic||page.common_school||page.common_current)throw Error('dedicated_common_page_port_required');
  if(page.collections?.length)throw Error('repeatable_record_editors_not_supported');
  if (!plan.ready||context.journal_persisted!==true||digest(structure(page))!==plan.structure_sha256)
    throw Error('prepared_page_structure_required');
  if (digest(values(page))!==plan.expected_values_sha256||page.fields.some(f=>f.invalid))
    throw Error('unexpected_page_values_before_save');
  if(page.fields.some(f=>f.required&&/optional\b/i.test(f.label+' '+f.group)))
    throw Error('conflicting_required_signals');
  if (manualPattern.test([page.title,page.generic_form?.dialog?.name].filter(Boolean).join(' ')) || page.fields.some(f=>manualField(f) ||
      (f.control==='textarea'&&!(page.generic_form?genericTextareaAllowed(f,plan.semantic_bindings):factualTextareaLabels.includes(normalizeLabel(f.label))||blankCourseworkNote(f,page,plan)))))
    throw Error('manual_page_save_excluded');
  if(page.generic_form&&manualPattern.test(page.generic_context?.instructions||''))throw Error('manual_form_instructions_excluded');
  const a=page.actions.find(a=>a.key===plan.save_action?.key);
  const draftLabel=/^save\s*(?:&\s*continue|and continue|draft)?$/i.test(a?.label||'');
  const commonDraft=plan.system==='common_app' && /^i:sectionContinue\d+$/.test(a?.key||'') && /^Continue(?: to next section)?$/i.test(a?.label||'');
  const genericDraft=page.generic_form&&(/^save(?:\s+draft|\s+changes|\s*(?:&|and)\s*(?:continue|next))?$/i.test(a?.label?.trim()||'')||
    !!page.generic_form.dialog&&plan.record_action?.kind==='add_draft'&&typeof plan.record_action.record?.ref==='string'&&a?.label?.trim()==='Add'&&!revisit);
  if (!a||a.disabled||(!draftLabel&&!commonDraft&&!genericDraft)||a.label!==plan.save_action.label)
    throw Error('observed_draft_save_required');
  if (a.selector) {const button=tab.playwright.locator(a.selector);if(page.generic_form&&await button.count()!==1)throw Error('unique_generic_save_action_required');await button.click();}
  else await tab.playwright.getByRole('button',{name:a.label,exact:true}).click();
  await tab.playwright.domSnapshot();
  if(page.generic_form){
    await waitForGenericLoader(tab);
    // Next-section AJAX can start after the first snapshot. Wait on the actual
    // observed form instead of immediately treating a still-visible form as a
    // failure, or reloading and discarding unsaved validation feedback.
    let advanced=true;
    if(page.generic_form.dialog||/(?:and|&)\s*(?:next|continue)$/i.test(a.label)){
      try {await tab.playwright.locator(page.generic_form.scope.selector).waitFor({state:'hidden',timeoutMs:10000});}
      catch {advanced=false;}
    }
    const errors=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('.ui-message-error,.ui-messages-error,.ui-state-error,[role=alert][aria-live=assertive]'))
      .filter(e=>e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility))
      .map(e=>(e.innerText||e.getAttribute('data-p-label')||e.getAttribute('aria-label')||'Unresolved website validation').replace(/\s+/g,' ').trim()).filter(Boolean));
    if(Array.isArray(errors)&&errors.length)throw Error('draft_save_validation_feedback: '+errors.join(' | '));
    if(!advanced)throw Error('draft_save_did_not_advance_review_current_feedback');
  }
  if(!revisit)return {schema:'generic-draft-save/1',save_performed:true,revisited_after_save:false,verification_required:true,
    target_id:plan.target_id,page_url:plan.page_url,structure_sha256:plan.structure_sha256,
    expected_values_sha256:plan.expected_values_sha256,save_action_key:plan.save_action.key};
  if (await tab.url()===plan.page_url) await tab.reload();
  else await tab.goto(plan.page_url);
  // A returned URL is not proof that an asynchronous form has finished loading.
  const anchor=page.generic_form?null:page.fields.find(f=>f.selector);
  if(page.generic_form)await tab.playwright.locator('form').filter({visible:true}).waitFor({state:'visible',timeoutMs:10000});
  if(anchor) {
    let locator=tab.playwright.locator(anchor.selector);
    if((anchor.selector_count??1)>1)locator=locator.nth(anchor.selector_index??0);
    await locator.waitFor({state:'visible',timeoutMs:10000});
  }
  if(page.state_metadata?.coverage==='common_app_visible_navigation') {
    for(const item of page.state_metadata.items) {
      if(!/^(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)$/.test(item.key))throw Error('observed_status_key_unsupported');
      // Status components hydrate separately from form fields. Wait for their
      // accessible text to exist, then compare the statuses rather than assume
      // that a complete field tree also means complete navigation state.
      await tab.playwright.locator(`[id="${item.key}"] .nav-item__status forge-screen-reader-text`)
        .waitFor({state:'attached',timeoutMs:10000});
    }
  }
  return {page:await observe(tab,{generic_form:!!plan.generic_form,generic_identity_fields:plan.generic_identity_fields}),revisited_after_save:true};
}

export async function restore(tab,plan,writes,context) {
  const page=await observe(tab);
  guard(context,page,plan.allowed_origin,true);
  if (context.journal_persisted!==true||digest(structure(page))!==plan.structure_sha256)
    throw Error('restoration_structure_changed_handoff_required');
  await writeObserved(tab,page,writes);
  const expected={...values(page),...Object.fromEntries(writes.map(w=>[w.field_key,w.value]))};
  return saveObserved(tab,{...plan,expected_values_sha256:digest(expected)},context,true);
}

/** Read-only recovery after a dispatched Save-and-Next outlives its loading wait. */
export async function recoverGenericNavigationReceipt(tab,plan,context){
  if(!plan.ready||!plan.generic_form||plan.generic_form.dialog||plan.generic_stage||plan.saved_page_readback!==false||
     context.journal_persisted!==true||context.save_attempted!==true||plan.target_id!==context.target_id||
     !/^save\s*(?:and|&)\s*(?:next|continue)$/i.test(plan.save_action?.label?.trim()||''))throw Error('dispatched_generic_next_save_required');
  const url=await tab.url();guard(context,{url,generic_form:plan.generic_form},plan.allowed_origin);
  if(url!==plan.page_url||await tab.playwright.locator(plan.generic_form.scope.selector).isVisible())throw Error('observed_saved_navigation_required');
  const evidence=await tab.playwright.evaluate(()=>{
    const visible=e=>e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
    const forms=Array.from(document.querySelectorAll('form')).filter(visible);
    const errors=Array.from(document.querySelectorAll('.ui-message-error,.ui-messages-error,.ui-state-error,[role=alert][aria-live=assertive]')).filter(visible);
    return {one_form:forms.length===1,form_id:forms[0]?.id||'',success:Array.from(document.querySelectorAll('body *')).some(e=>visible(e)&&e.childElementCount===0&&/Save Success!?/.test(e.textContent||'')),errors:errors.length};
  });
  const earlierSuccess=context.save_success_observed===true&&typeof context.observed_next_form_id==='string'&&context.observed_next_form_id===evidence.form_id;
  if(!evidence.one_form||!evidence.form_id||/login/i.test(evidence.form_id)||!evidence.success&&!earlierSuccess||evidence.errors)throw Error('observed_success_without_validation_required');
  return {schema:'generic-draft-save/1',save_performed:true,revisited_after_save:false,verification_required:true,
    target_id:plan.target_id,page_url:plan.page_url,structure_sha256:plan.structure_sha256,
    expected_values_sha256:plan.expected_values_sha256,save_action_key:plan.save_action.key};
}
