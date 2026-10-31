/** Public semantic associations for existing Common App language/household pages. */
import {readFile} from 'node:fs/promises';
import {createChoiceControls} from './choice_controls.mjs';
import {createCommonPage} from './common_page.mjs';
export const contracts=JSON.parse(await readFile(new URL('./bc_application/data/common_native_forms.json',import.meta.url),'utf8'));

export async function readCommonNative(tab,kind) {
  const spec=contracts.find(s=>s.kind===kind);if(!spec)throw Error('known_common_factual_kind_required');
  return tab.playwright.evaluate(({kind,number,section})=>{
    const visible=e=>!!e.getClientRects().length&&e.type!=='hidden'&&!e.closest('[hidden],[inert]')&&
      !['hidden','collapse'].includes(getComputedStyle(e).visibility);
    const text=e=>(e?.innerText||'').replace(/\s+/g,' ').trim(),main=document.querySelector('main');
    if(!main)throw Error('observed_common_main_required');
    const inputs=Array.from(main.querySelectorAll('input[role=combobox]')).filter(visible),rows=[];
    for(const input of inputs) {
      if(kind!=='language')throw Error('unknown_household_combobox');
      const block=input.closest('ca-single-select-dropdown');let group=block?.nextElementSibling;
      while(group&&!text(group)&&!Array.from(group.querySelectorAll('input,select,textarea,button')).some(visible))group=group.nextElementSibling;
      const label=block?.querySelector('[id^="title_ques_"]'),fieldset=group?.querySelector('fieldset'),legend=fieldset?.querySelector('legend [id^="title_ques_"]');
      if(block?.parentElement.parentElement.tagName!=='CA-QUESTIONS'||group?.tagName!=='CA-MULTI-SELECT-CHECKBOX'||!visible(group)||!fieldset||!label||!legend||
         text(label)!=='Select language'||text(legend)!=='Language proficiency'||
         block.querySelectorAll('input[role=combobox]').length!==1||group.querySelectorAll('fieldset').length!==1||
         label.id!=='title_ques_'+input.id.replace('text_ques_',''))throw Error('observed_language_pair_required');
      const proficiency=Array.from(fieldset.querySelectorAll('input')).filter(visible).map(e=>({raw_key:'i:'+e.id,
        value:e.value,label:text(Array.from(e.labels||[])[0]),selector_count:main.querySelectorAll(
          `fieldset:has([id="${legend.id}"]) input[type="checkbox"][value="${e.value}"]`).length}));
      rows.push({language_key:'i:'+input.id,proficiency_id:legend.id.replace('title_ques_',''),proficiency,
        text:(text(block)+' '+text(group)).trim()});
    }
    const controls=inputs.map(e=>({key:'i:'+e.id,tag:e.tagName,type:e.type,role:e.getAttribute('role'),
      popup:e.getAttribute('aria-haspopup'),expanded:e.getAttribute('aria-expanded'),wrapper:e.closest('ng-select')?.tagName||''}));
    const auxiliary=[],buttons=Array.from(document.querySelectorAll('button,input[type=submit],input[type=button]')).filter(visible);
    for(const [index,b] of buttons.entries()) {
      if(!main.contains(b))continue;
      if(b.getAttribute('aria-label')==='Clear selection') {
        const owner=Array.from(b.closest('ng-select')?.querySelectorAll('input[role=combobox]')||[]).filter(visible);
        if(owner.length!==1)throw Error('observed_common_clear_owner_required');
        auxiliary.push({index,field_key:'i:'+owner[0].id});
      } else if(!/^clear_ques_\d+$/.test(b.id)&&b.id!=='sectionContinue'+number&&
          text(b)!=='Preview '+section+' Section, Opens dialog')throw Error('unknown_common_factual_action');
    }
    let content=text(main),status=text(document.getElementById('pageHeaderStatus'));
    if(!status||content.split(status).length!==2)throw Error('unique_common_page_status_required');
    content=content.replace(status,'<page-status>');
    for(const row of rows) {
      if(!row.text||!content.includes(row.text))throw Error('observed_language_row_text_required');
      content=content.replace(row.text,'<language-row>');
    }
    if(kind==='language'&&!rows.length)content=content.replace('Clear answer','');
    if(kind==='grade12_status')content=content.replace('Clear answer','');
    content=content.replace(/(?:<language-row>\s*)+/g,'<language-rows> ').replaceAll('Error Please complete this required question.','').replace(/\s+/g,' ').trim();
    return {schema:'common-factual-native/1',heading:text(document.getElementById('pageTitle')),content,
      controls,rows:rows.map(({text,...r})=>r),auxiliary};
  },{kind,number:spec.path.split('/').at(-1),section:spec.section});
}

export function createCommonFactual(host,kind,{browserOrigin='https://apply.commonapp.org'}={}) {
  const spec=contracts.find(s=>s.kind===kind);if(!spec)throw Error('known_common_factual_kind_required');
  if(!['https://apply.commonapp.org','http://127.0.0.1:8765','http://localhost:8765'].includes(browserOrigin))throw Error('known_common_browser_origin_required');
  const origin='https://apply.commonapp.org',url=browserOrigin+spec.path,choice=createChoiceControls(host);
  function decorate(raw,native,choices={}) {
    const contentHash=kind==='language'&&!native.rows.length?spec.empty_content_sha256:spec.content_sha256;
    if(raw.url!==url||raw.title!==spec.title||raw.frames_present||raw.scope||raw.collections?.length||
       native.schema!=='common-factual-native/1'||native.heading!==spec.heading||host.digest(native.content)!==contentHash)
      throw Error('observed_common_factual_contract_required');
    const rows=native.rows.map(({language_key,proficiency_id})=>({language_key,proficiency_id})),tag={schema:'common-factual-page/1',
      kind,content_sha256:contentHash,...(kind==='language'?{rows}:{})};
    let page=host.normalizeCommonAppRadios({...raw,common_factual:tag});
    const expected=kind!=='language'?spec.fields:[spec.count_field,...rows.flatMap(row=>[
      {key:row.language_key,label:spec.language_label,group:'',control:'choice_input',required:true},
      ...spec.proficiencies.map(p=>({key:`g:${row.proficiency_id}:${p.part}`,label:p.label,group:spec.proficiency_label,
        control:'checkbox',required:false,selector:`fieldset:has([id="title_ques_${row.proficiency_id}"]) input[type="checkbox"][value="${p.value}"]`}))])];
    if(kind==='language'&&(rows.length>5||new Set(rows.map(r=>r.language_key)).size!==rows.length||
       new Set(rows.map(r=>r.proficiency_id)).size!==rows.length||
       new Set(rows.flatMap(r=>[r.language_key.replace('i:text_ques_',''),r.proficiency_id])).size!==rows.length*2))throw Error('observed_language_rows_required');
    const checkbox=new Map();
    for(const row of native.rows) {
      if(row.proficiency.length!==5)throw Error('observed_language_proficiencies_required');
      for(const part of spec.proficiencies) {
        const matches=row.proficiency.filter(p=>p.label===part.label&&p.value===part.value&&p.selector_count===1);
        if(matches.length!==1||checkbox.has(matches[0].raw_key))throw Error('observed_language_proficiencies_required');
        checkbox.set(matches[0].raw_key,expected.find(f=>f.key===`g:${row.proficiency_id}:${part.part}`));
      }
    }
    const byKey=new Map(expected.map(f=>[f.key,f]));
    page.fields=page.fields.map(f=>{
      const mapped=checkbox.get(f.key),wanted=mapped||byKey.get(f.key);
      if(!wanted||f.label!==wanted.label||f.group!==wanted.group||f.required!==wanted.required||f.disabled||f.readonly||
         f.control!==(wanted.control==='choice_input'?'unsupported':wanted.control)||!f.selector||
         (f.selector_count??1)!==1||(f.selector_index??0)!==0)throw Error('observed_common_factual_fields_required');
      if(mapped){const {name,...stable}=f;return {...stable,key:mapped.key,selector:mapped.selector,selector_count:1,selector_index:0};}
      return {...f,control:wanted.control};
    });
    if(page.fields.length!==expected.length||new Set(page.fields.map(f=>f.key)).size!==expected.length)
      throw Error('observed_common_factual_shape_required');
    if(kind==='grade12_status'){
      const field=page.fields[0],selected=field.options.find(o=>o.value===field.value)?.label;
      if(field.value!==''&&selected!=='No')throw Error('grade12_official_grade_layout_not_supported');
    }
    if(kind==='language') {
      const count=page.fields.find(f=>f.key===spec.count_field.key),options=count.options;
      const selected=options.find(o=>o.value===count.value)?.label;
      if(options.length!==5||options.some((o,i)=>o.label!==String(i+1)||o.disabled)||new Set(options.map(o=>o.value)).size!==5||
         (count.value===''&&rows.length)||(count.value!==''&&selected!==String(rows.length)))throw Error('observed_language_count_rows_required');
    }
    const choiceKeys=expected.filter(f=>f.control==='choice_input').map(f=>f.key);
    if(native.controls.length!==choiceKeys.length||new Set(native.controls.map(c=>c.key)).size!==choiceKeys.length||
       native.controls.some(c=>!choiceKeys.includes(c.key)||c.tag!=='INPUT'||c.type!=='text'||c.role!=='combobox'||
        c.popup!=='listbox'||c.expanded!=='false'||c.wrapper!=='NG-SELECT'))throw Error('observed_common_factual_widgets_required');
    if(new Set(native.auxiliary.map(a=>a.index)).size!==native.auxiliary.length||
       new Set(native.auxiliary.map(a=>a.field_key)).size!==native.auxiliary.length||
       native.auxiliary.some(a=>!choiceKeys.includes(a.field_key)))throw Error('observed_common_factual_auxiliary_required');
    const aux=new Map(native.auxiliary.map(a=>[a.index,a])),occurrences=new Map();
    page.actions=page.actions.flatMap((a,i)=>{
      if(aux.has(i)){if(a.label!==''||a.selector!==null)throw Error('observed_common_auxiliary_identity_required');return [];}
      if(a.key.startsWith('a:')){if(!a.label)throw Error('unknown_common_anonymous_action');
        const n=occurrences.get(a.label)||0;occurrences.set(a.label,n+1);return [{...a,key:`a:${a.label}:${n}`}];}
      return [a];
    });
    const id='sectionContinue'+spec.path.split('/').at(-1);
    if(page.actions.filter(a=>a.key==='i:'+id&&a.selector===`[id="${id}"]`&&!a.disabled&&a.label==='Continue to next section').length!==1)
      throw Error('observed_common_factual_draft_save_required');
    return {...page,common_factual_native:{schema:native.schema,heading:native.heading,controls:native.controls},choice_observations:choices};
  }
  async function observe(tab,choices={}) {
    await tab.playwright.getByRole('heading',{name:spec.heading,exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator(`[id="${spec.current_key}"] .nav-item__status forge-screen-reader-text`).waitFor({state:'attached',timeoutMs:10000});
    return decorate(await host.observe(tab),await readCommonNative(tab,kind),choices);
  }
  async function inspect(tab) {
    const before=await observe(tab),choices={};
    for(const f of before.fields.filter(f=>f.control==='choice_input')){
      let options;try{options=await choice.options(tab,f);}finally{await choice.close(tab,f);}
      choices[f.key]=options.map(o=>({value:o.label,label:o.label,disabled:o.disabled}));
    }
    const after=await observe(tab,choices);
    if(host.digest({...after,choice_observations:{}})!==host.digest(before))throw Error('common_choice_inspection_changed_values');
    return after;
  }
  return {...createCommonPage(host,{origin,url,marker:'common_factual',name:'factual',observe,inspect}),decorate};
}
