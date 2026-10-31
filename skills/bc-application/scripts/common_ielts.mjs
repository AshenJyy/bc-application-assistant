/** Common App's observed whole-page IELTS form, not a generic record editor. */
import {readFile} from 'node:fs/promises';
import {createChoiceControls} from './choice_controls.mjs';
import {createCommonPage} from './common_page.mjs';
export const contract=JSON.parse(await readFile(new URL('./bc_application/data/common_ielts.json',import.meta.url),'utf8'));
export async function readIeltsNative(tab) {
  return tab.playwright.evaluate(()=>{
    const visible=e=>!!e.getClientRects().length&&e.type!=='hidden'&&!e.closest('[hidden],[inert]')&&
      !['hidden','collapse'].includes(getComputedStyle(e).visibility);
    const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
    const main=document.querySelector('main');if(!main)throw Error('observed_ielts_main_required');
    const controls=Array.from(main.querySelectorAll('input[role=combobox]')).filter(visible).map(e=>({
      key:'i:'+e.id,tag:e.tagName,type:e.type,role:e.getAttribute('role'),popup:e.getAttribute('aria-haspopup'),
      expanded:e.getAttribute('aria-expanded'),wrapper:e.closest('ng-select')?.tagName||''}));
    const auxiliary=[],buttons=Array.from(document.querySelectorAll('button,input[type=submit],input[type=button]')).filter(visible);
    for(const [index,b] of buttons.entries()) {
      if(!main.contains(b))continue;
      const label=b.getAttribute('aria-label')||'';
      if(label==='Clear selection') {
        const inputs=Array.from(b.closest('ng-select')?.querySelectorAll('input[role=combobox]')||[]).filter(visible);
        if(inputs.length!==1)throw Error('observed_choice_clear_owner_required');
        auxiliary.push({index,kind:'clear',field_key:'i:'+inputs[0].id});
      } else if(label==='Open calendar dialog') {
        const inputs=Array.from(b.closest('mat-form-field')?.querySelectorAll('input')||[]).filter(visible);
        if(inputs.length!==1||b.parentElement.tagName!=='MAT-DATEPICKER-TOGGLE')throw Error('observed_calendar_owner_required');
        auxiliary.push({index,kind:'calendar',field_key:'i:'+inputs[0].id});
      } else if(!['clear_ques_160','sectionContinue10'].includes(b.id)&&text(b)!=='Preview Testing Section, Opens dialog') {
        throw Error('unknown_ielts_form_action');
      }
    }
    let content=(main.innerText||'').replace(/\s+/g,' ').trim();
    const status=document.getElementById('pageHeaderStatus');
    if(status&&main.contains(status)) {
      const statusText=(status.innerText||'').replace(/\s+/g,' ').trim();
      if(!statusText||content.split(statusText).length!==2)throw Error('unique_ielts_page_status_required');
      content=content.replace(statusText,'<page-status>');
    }
    // Merely focusing an empty required combo can reveal this validation text.
    // Keep actual invalid flags in the observation; other notices are not ignored.
    content=content.replaceAll('Error Please complete this required question.','').replace(/\s+/g,' ').trim();
    return {schema:'common-ielts-native/1',heading:text(document.getElementById('pageTitle')),
      content,controls,auxiliary};
  });
}

export function createCommonIelts(host) {
  const origin='https://apply.commonapp.org',url=origin+contract.path,choice=createChoiceControls(host);
  function decorate(raw,native,choices) {
    if(raw.url!==url||raw.title!==contract.title||raw.frames_present||raw.collections?.length||raw.scope||
       native.heading!==contract.heading||host.digest(native.content)!==contract.content_sha256)
      throw Error('observed_common_ielts_contract_required');
    const tag={schema:'common-ielts-page/1',content_sha256:contract.content_sha256};
    let page=host.normalizeCommonAppRadios({...raw,common_ielts:tag});
    const expected=new Map(contract.fields.map(f=>[f.key,f])),choiceKeys=contract.fields.filter(f=>f.control==='choice_input').map(f=>f.key),
      dates=contract.fields.filter(f=>f.control==='text').map(f=>f.key);
    if(page.fields.length!==12||new Set(page.fields.map(f=>f.key)).size!==12||native.controls.length!==6||
       new Set(native.controls.map(c=>c.key)).size!==6)throw Error('observed_common_ielts_shape_required');
    for(const c of native.controls)if(!choiceKeys.includes(c.key)||c.tag!=='INPUT'||c.type!=='text'||c.role!=='combobox'||
        c.popup!=='listbox'||c.expanded!=='false'||c.wrapper!=='NG-SELECT')throw Error('observed_common_ielts_choice_widgets_required');
    page.fields=page.fields.map(f=>{
      const spec=expected.get(f.key);
      if(!spec||f.label!==spec.label||f.group!==spec.group||f.control!==(spec.control==='choice_input'?'unsupported':spec.control)||
         !f.required||f.disabled||f.readonly||!f.selector||(f.selector_count??1)!==1||(f.selector_index??0)!==0)
        throw Error('observed_common_ielts_fields_required');
      return {...f,control:spec.control};
    });
    const calendars=native.auxiliary.filter(a=>a.kind==='calendar'),clears=native.auxiliary.filter(a=>a.kind==='clear');
    if(native.auxiliary.length!==calendars.length+clears.length||host.digest(calendars.map(a=>a.field_key).sort())!==host.digest([...dates].sort())||
       new Set(clears.map(a=>a.field_key)).size!==clears.length||clears.some(a=>!choiceKeys.includes(a.field_key)))
      throw Error('observed_common_ielts_auxiliary_required');
    const auxiliary=new Map(native.auxiliary.map(a=>[a.index,a]));
    if(auxiliary.size!==native.auxiliary.length)throw Error('observed_common_ielts_auxiliary_required');
    const occurrences=new Map();
    page.actions=page.actions.flatMap((a,i)=>{
      const aux=auxiliary.get(i);
      if(aux){if(a.label!==''||a.selector!==null)throw Error('observed_ielts_auxiliary_identity_required');
        return aux.kind==='clear'?[]:[{...a,key:'aux:calendar:'+aux.field_key,label:'Open calendar dialog'}];}
      if(a.key.startsWith('a:')){
        if(!a.label)throw Error('unknown_ielts_anonymous_action');
        const n=occurrences.get(a.label)||0;occurrences.set(a.label,n+1);return [{...a,key:`a:${a.label}:${n}`}];
      }
      return [a];
    });
    if(page.actions.filter(a=>a.key==='i:sectionContinue10'&&a.label==='Continue to next section'&&!a.disabled).length!==1)
      throw Error('observed_common_ielts_draft_save_required');
    const {content,...metadata}=native;
    return {...page,common_ielts_native:metadata,choice_observations:choices};
  }
  async function wait(tab) {
    await tab.playwright.getByRole('heading',{name:'IELTS',exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('[id="sectionContinue10"]').waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('[id="tertiaryNavItem2_10"] .nav-item__status forge-screen-reader-text').waitFor({state:'attached',timeoutMs:10000});
  }
  async function observe(tab,choices={}) {
    await wait(tab);const raw=await host.observe(tab),native=await readIeltsNative(tab);
    return decorate(raw,native,choices);
  }
  async function inspect(tab) {
    const before=await observe(tab),choices={};
    for(const f of before.fields.filter(f=>f.control==='choice_input')) {
      let options;try{options=await choice.options(tab,f);}finally{await choice.close(tab,f);}
      choices[f.key]=options.map(o=>({value:o.label,label:o.label,disabled:o.disabled}));
    }
    const after=await observe(tab,choices);
    if(host.digest({...after,choice_observations:{}})!==host.digest(before))throw Error('ielts_choice_inspection_changed_values');
    return after;
  }
  return {...createCommonPage(host,{origin,url,marker:'common_ielts',name:'ielts',observe,inspect}),decorate};
}
