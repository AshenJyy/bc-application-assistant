/** Observed current-year course widgets. Public DOM and advertised locators only. */
import {createChoiceControls} from './choice_controls.mjs';
import {readFile} from 'node:fs/promises';

export const currentContract=JSON.parse(await readFile(new URL('./bc_application/data/common_current.json',import.meta.url),'utf8'));
export const currentPath=currentContract.path,currentHeading=currentContract.heading;
const origin=currentContract.origin,values=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
export const currentStructure=p=>({...Object.fromEntries(['schema','url','title','common_current','actions'].map(k=>[k,p[k]])),fields:p.fields.map(f=>
    Object.fromEntries(Object.entries(f).filter(([k])=>!['value','invalid'].includes(k)&&!(k==='name'&&f.control==='radio'))))});
const scheduleLabel=currentContract.scheduling_label;
export const currentContent=rows=>currentContract.content_base+(rows?' '+currentContract.course_content:'')+' '+currentContract.content_end;

export function createCommonCurrent(host,{browserOrigin=origin}={}) {
  if(![origin,'http://127.0.0.1:8765','http://localhost:8765'].includes(browserOrigin))throw Error('known_common_browser_origin_required');
  const url=browserOrigin+currentPath,choice=createChoiceControls(host),digest=host.digest;
  async function native(tab) {
    return tab.playwright.evaluate(()=>{
      const vis=e=>!!e.getClientRects().length&&e.type!=='hidden'&&!e.closest('[hidden],[inert]')&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
      const text=e=>(e?.innerText||'').replace(/\s+/g,' ').trim(),main=document.querySelector('main');
      if(!main)throw Error('observed_current_main_required');
      const widgets=Array.from(main.querySelectorAll('input[role=combobox]')).filter(vis).map(e=>{
        const owner=e.closest('ng-select'),multi=owner?.classList.contains('ng-select-multiple');
        if(!owner||e.type!=='text'||e.getAttribute('aria-haspopup')!=='listbox'||e.getAttribute('aria-expanded')!=='false'||e.value!==''&&multi)
          throw Error('closed_current_widget_required');
        let selected=[];
        if(multi){const container=e.closest('[role=listbox]');
          if(!container||container.closest('ng-select')!==owner||container.getAttribute('aria-labelledby')!=='title_ques_'+e.id.replace('text_ques_',''))
            throw Error('observed_current_selected_owner_required');
          selected=Array.from(container.querySelectorAll('[role=option]')).filter(vis).map(o=>{
            if(o.getAttribute('aria-selected')!=='true')throw Error('selected_current_chip_required');return text(o);});
          if(selected.some(v=>!v)||new Set(selected).size!==selected.length)throw Error('distinct_current_selected_chips_required');
        }
        if(multi&&!['true','false'].includes(e.getAttribute('aria-invalid')))throw Error('observed_current_term_validation_required');
        return {key:'i:'+e.id,multiple:!!multi,selected,selection_text:multi?text(e.closest('[role=listbox]')):'',
          semantic_invalid:multi&&(e.getAttribute('aria-invalid')==='true'||owner.getAttribute('aria-invalid')==='true')};
      });
      const mainButtons=Array.from(main.querySelectorAll('button,input[type=submit],input[type=button]')).filter(vis);
      for(const b of mainButtons)if(b.id!=='sectionContinue24'&&b.id!=='clear_ques_1803'&&text(b)!=='Preview Education Section, Opens dialog'){
        const owner=b.closest('ng-select');
        if(b.getAttribute('aria-label')!=='Clear selection'||!owner||Array.from(owner.querySelectorAll('input[role=combobox]')).filter(vis).length!==1)
          throw Error('unknown_current_course_action');
      }
      let content=text(main),status=text(document.getElementById('pageHeaderStatus'));
      if(!status||content.split(status).length!==2)throw Error('unique_current_page_status_required');
      content=content.replace(status,'<page-status>').replace('Clear answer','').replaceAll('Error Please complete this required question.','').replace(/\s+/g,' ').trim();
      return {heading:text(document.getElementById('pageTitle')),widgets,content};
    });
  }
  function decorate(raw,n,choices={}) {
    if(raw.url!==url||raw.title!=='My Common Application | Common App'||raw.frames_present||raw.scope||raw.collections?.length||n.heading!==currentHeading)
      throw Error('observed_current_page_required');
    const rows=[],byWidget=new Map(n.widgets.map(w=>[w.key,w])),fields=raw.fields.map(f=>{
      const m=/^Course (\d+) (subject|name|level|schedule)$/.exec(f.label),radio=f.control==='radio'&&f.label===scheduleLabel;
      if(!m&&!radio&&f.key!=='i:text_ques_307')throw Error('unknown_current_course_field');
      if(f.required!==true||f.disabled||f.readonly||(f.selector_count??1)!==1||(f.selector_index??0)!==0)throw Error('observed_current_editable_field_required');
      if(radio){if(f.group!==scheduleLabel||f.options.length!==4||f.options.some(o=>!/^\[id="option_ques_1803_\d+-input"\]$/.test(o.selector)))throw Error('observed_current_radio_required');
        return {...f,key:'r:ques_1803',selector_count:1,selector_index:0};}
      if(f.key!=='i:'+f.selector?.match(/^\[id="(text_ques_\d+)"\]$/)?.[1]||f.group)throw Error('observed_current_field_identity_required');
      const part=m?.[2]==='schedule'?'terms':m?.[2],index=m?Number(m[1])-1:null;
      if(m){if(index<0||index>=25)throw Error('bounded_current_course_rows_required');rows[index]??={};if(rows[index][part])throw Error('unique_current_course_part_required');rows[index][part]=f.key;}
      let control,value=f.value,invalid=f.invalid;
      if(part==='name'){if(f.control!=='textarea'||byWidget.has(f.key))throw Error('observed_current_name_textarea_required');control='course_name';}
      else {const w=byWidget.get(f.key);if(!w||f.control!=='unsupported'||w.multiple!==(part==='terms'))throw Error('observed_current_choice_owner_required');
        control=part==='terms'?'term_choices':'choice_input';if(part==='terms'){
          if(typeof w.semantic_invalid!=='boolean')throw Error('observed_current_term_validation_required');
          value=[...w.selected].sort();
          // This input is an empty search box even with selected chips. Its
          // native valueMissing describes the search text, not the course terms.
          invalid=w.semantic_invalid||!value.length;
        }}
      return {...f,control,value,invalid,selector_count:1,selector_index:0};
    });
    if(rows.some(r=>!r||Object.keys(r).length!==4)||n.widgets.length!==1+rows.length*3||new Set(n.widgets.map(w=>w.key)).size!==n.widgets.length||
       fields.length!==1+(rows.length?1:0)+rows.length*4||new Set(fields.map(f=>f.key)).size!==fields.length)throw Error('complete_current_course_rows_required');
    let content=n.content;
    for(let i=0;i<rows.length;i++){
      const selection=byWidget.get(rows[i].terms).selection_text;
      if(typeof selection!=='string'||selection.replace(/\s/g,'')!==byWidget.get(rows[i].terms).selected.join('').replace(/\s/g,''))
        throw Error('observed_current_selection_text_required');
      const segment=['subject','name','level','schedule'].map(p=>'Course '+(i+1)+' '+p).join(' ')+(selection?' '+selection:'');
      if(content.split(segment).length!==2)throw Error('observed_current_course_content_required');content=content.replace(segment,'<course-row>');
    }
    content=content.replace(/(?:<course-row>\s*)+/g,'<course-rows> ').replace(/\s+/g,' ').trim();
    if(content!==currentContent(rows.length))throw Error('unknown_current_page_instructions');
    const actions=raw.actions.filter(a=>a.key==='i:sectionContinue24');
    if(actions.length!==1||actions[0].selector!=='[id="sectionContinue24"]'||actions[0].disabled||actions[0].label!=='Continue to next section')
      throw Error('observed_current_draft_save_required');
    return {schema:'observed-current-page/1',url:raw.url,title:raw.title,frames_present:false,
      common_current:{schema:'common-current-page/1',rows,content_sha256:digest(currentContent(rows.length))},fields,actions,
      choice_observations:choices,state_metadata:raw.state_metadata};
  }
  async function observe(tab,choices={}){
    await tab.playwright.getByRole('heading',{name:currentHeading,exact:true}).waitFor({state:'visible',timeoutMs:10000});
    await tab.playwright.locator('[id="tertiaryNavItem4_24"] .nav-item__status forge-screen-reader-text').waitFor({state:'attached',timeoutMs:10000});
    return decorate(await host.observe(tab),await native(tab),choices);
  }
  async function termOptions(tab,f){
    const input=tab.playwright.locator(f.selector);
    if(await input.count()!==1)throw Error('unique_current_term_input_required');
    await input.click();
    try {const panel=tab.playwright.getByRole('listbox',{name:'Options',exact:true});await panel.waitFor({state:'visible',timeoutMs:10000});
      if(await panel.count()!==1||await input.getAttribute('aria-controls')!==await panel.getAttribute('id'))throw Error('observed_current_term_panel_association_required');
      return await panel.evaluate(e=>{if(!e.classList.contains('ng-select-multiple'))throw Error('current_multiple_listbox_required');
        const options=Array.from(e.querySelectorAll('[role=option]')).filter(o=>o.getClientRects().length).map((o,index)=>({label:(o.innerText||'').replace(/\s+/g,' ').trim(),
          disabled:o.getAttribute('aria-disabled')==='true',selected:o.getAttribute('aria-selected')==='true',index}));
        if(!options.length||options.some(o=>!o.label)||new Set(options.map(o=>o.label)).size!==options.length)throw Error('unique_current_term_labels_required');return options;});
    }catch(e){await choice.close(tab,{...f,control:'choice_input'});throw e;}
  }
  const normalized=opts=>opts.map(o=>({value:o.label,label:o.label,disabled:o.disabled}));
  async function inspect(tab){const before=await observe(tab),choices={};
    for(const f of before.fields.filter(f=>['choice_input','term_choices'].includes(f.control))){
      try{choices[f.key]=normalized(await(f.control==='term_choices'?termOptions(tab,f):choice.options(tab,f)));}
      finally{await choice.close(tab,{...f,control:'choice_input'});}
    }
    const after=await observe(tab,choices);
    if(digest({...after,choice_observations:{}})!==digest(before))throw Error('current_inspection_changed_values');return after;
  }
  function eligible(page,plan,context,restoration=false){host.guard(context,page,origin,restoration);
    if(plan.schema!=='common-current-plan/1'||plan.system!=='common_app'||!plan.ready||plan.page_url!==url||context.journal_persisted!==true)
      throw Error('prepared_current_checkpoint_required');}
  async function setTerms(tab,f,value,choices){
    if(!Array.isArray(value)||value.length!==new Set(value).size||value.some(v=>!choices?.some(o=>o.label===v&&!o.disabled)))throw Error('observed_current_term_values_required');
    let options;
    try {options=await termOptions(tab,f);if(digest(normalized(options))!==digest(choices))throw Error('current_term_options_changed');
      if(digest(options.filter(o=>o.selected).map(o=>o.label).sort())!==digest(f.value))throw Error('current_selected_terms_changed');
    }finally{await choice.close(tab,{...f,control:'choice_input'});}
    for(const item of options.filter(o=>o.selected!==value.includes(o.label))){
      try{const fresh=await termOptions(tab,f);if(digest(normalized(fresh))!==digest(choices))throw Error('current_term_options_changed');
        const panel=tab.playwright.getByRole('listbox',{name:'Options',exact:true}),option=panel.getByRole('option',{name:item.label,exact:true});
        if(await option.count()!==1)throw Error('unique_current_term_option_required');await option.click();
      }finally{await choice.close(tab,{...f,control:'choice_input'});}
    }
  }
  async function apply(tab,plan,context){const page=await observe(tab,plan.choice_observations);eligible(page,plan,context,plan.restoration===true);
    if(digest(page)!==plan.observation_sha256)throw Error('page_changed_since_preparation');
    for(const w of plan.writes){const f=page.fields.find(f=>f.key===w.field_key);if(!f)throw Error('observed_current_write_required');
      if(f.control==='choice_input')await choice.select(tab,page,f,w.value,plan.choice_observations[f.key]);
      else if(f.control==='term_choices')await setTerms(tab,f,w.value,plan.choice_observations[f.key]);
      else if(f.control==='course_name'){if(typeof w.value!=='string'||!w.value.trim())throw Error('explicit_current_course_name_required');
        await tab.playwright.locator(f.selector).fill(w.value);await tab.playwright.locator(f.selector).press('Tab');}
      else if(f.control==='radio'){const option=f.options.filter(o=>o.value===w.value&&!o.disabled);if(option.length!==1)throw Error('observed_current_radio_choice_required');
        await tab.playwright.locator(option[0].selector).check();}
      else throw Error('unsupported_current_course_write');
    }
    if(plan.stage!=='fields')return inspect(tab);
    const after=await observe(tab,plan.choice_observations);
    if(digest(currentStructure(after))!==plan.structure_sha256||digest(values(after))!==plan.expected_values_sha256||after.fields.some(f=>f.invalid))
      throw Error('unexpected_current_page_after_input');return after;
  }
  async function waitStatuses(tab,page){for(const s of page.state_metadata.items){
    if(!/^(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)$/.test(s.key))throw Error('observed_current_status_key_required');
    await tab.playwright.locator(`[id="${s.key}"] .nav-item__status forge-screen-reader-text`).waitFor({state:'attached',timeoutMs:10000});}}
  async function saveAndRead(tab,plan,context){const p=await observe(tab,plan.choice_observations);eligible(p,plan,context,plan.restoration===true);
    if(plan.stage!=='fields'||digest(currentStructure(p))!==plan.structure_sha256||digest(values(p))!==plan.expected_values_sha256||p.fields.some(f=>f.invalid))
      throw Error('prepared_valid_current_page_required');
    const button=tab.playwright.locator(p.actions[0].selector);await button.click();await button.waitFor({state:'detached',timeoutMs:15000});
    await tab.playwright.domSnapshot();await tab.goto(url);await waitStatuses(tab,p);return {page:await inspect(tab),revisited_after_save:true};
  }
  async function cancelUnsaved(tab,plan,context){const p=await observe(tab,plan.choice_observations);eligible(p,plan,context,true);
    await tab.reload();await waitStatuses(tab,p);return {page:await inspect(tab),revisited_saved_draft:true};}
  return {observe,inspect,apply,saveAndRead,cancelUnsaved,decorate};
}
