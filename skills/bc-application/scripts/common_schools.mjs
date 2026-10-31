/** Public Common App school lookup and whole-page factual school workflow. */
import {readFile} from 'node:fs/promises';
export const contract=JSON.parse(await readFile(new URL('./bc_application/data/common_schools.json',import.meta.url),'utf8'));
const normal=s=>(s||'').replace(/[\u200b-\u200f\u2060\ufeff*]/g,'').replace(/\s+/g,' ').trim();
const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
export const schoolStructure=p=>Object.fromEntries(['schema','url','title','common_school','actions'].map(k=>[k,p[k]]).concat([
  ['fields',p.fields.map(f=>Object.fromEntries(Object.entries(f).filter(([k])=>!['value','invalid','statement_format'].includes(k)&&!(k==='name'&&['radio','checkbox'].includes(f.control)))))]]));
export const schoolValues=p=>({...Object.fromEntries(p.fields.map(f=>[f.key,f.value])),'@schools':p.school_values,
  '@statement_formats':Object.fromEntries(p.fields.filter(f=>f.control==='school_statement').map(f=>[f.key,f.statement_format]))});

async function native(tab) {
  return tab.playwright.evaluate(()=>{
    const visible=e=>!!e.getClientRects().length&&!e.closest('[hidden],[inert]')&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
    const text=s=>(s||'').replace(/[\u200b-\u200f\u2060\ufeff*]/g,'').replace(/\s+/g,' ').trim();
    const main=document.querySelector('main');if(!main)throw Error('observed_school_main_required');
    const records=Array.from(main.querySelectorAll('ca-lookup')).filter(visible).map(e=>{
      const match=/^text_ques_(\d+)$/.exec(e.id);if(!match)throw Error('public_school_lookup_owner_required');
      const question_id=match[1],label=text(document.getElementById(e.getAttribute('aria-labelledby'))?.textContent);
      const rendered=(e.innerText||'').split(/\n/).map(s=>s.trim()).filter(Boolean),at=rendered.findIndex(s=>/^CEEB Code\s*:\s*\d{6}$/.test(s));
      const buttons=Array.from(e.querySelectorAll('button')).filter(visible).map(b=>({id:b.id,text:text(b.innerText)}));
      let selected=null;
      if(at>=0)selected={name:rendered[0],ceeb:/\d{6}/.exec(rendered[at])[0],text:rendered.slice(0,at+1).join('\n')};
      if(selected ? !buttons.some(b=>b.id==='changeSchool'+question_id&&b.text.startsWith('Change')) :
          buttons.length!==1||buttons[0].id!=='findSchool'+question_id||buttons[0].text!=='Find school')throw Error('observed_owned_school_action_required');
      return {question_id,label,selected};
    });
    const notes=Array.from(main.querySelectorAll('[contenteditable=true]')).filter(visible).map(e=>{
      const match=/^title_ques_(\d+)$/.exec(e.getAttribute('aria-labelledby')||'');if(!match||e.getAttribute('role')!=='textbox')throw Error('observed_school_statement_owner_required');
      const selector=`[role="textbox"][contenteditable="true"][aria-labelledby="title_ques_${match[1]}"]`,children=Array.from(e.children);
      return {question_id:match[1],selector,selector_count:document.querySelectorAll(selector).length,text:e.innerText.trim(),
        format:!e.innerText.trim()?'empty':children.length===1&&children[0].tagName==='P'&&children[0].children.length===0?'plain_paragraph':'rich'};
    });
    const progression=Array.from(main.querySelectorAll('fieldset')).filter(e=>visible(e)&&e.querySelector('[id="title_ques_265"]')).flatMap(e=>
      Array.from(e.querySelectorAll('input[type=checkbox]')).filter(visible).map(c=>({id:c.id,value:c.value,
        label:text(Array.from(c.labels||[]).map(l=>l.textContent).join(' ')),selector:`fieldset:has([id="title_ques_265"]) input[type="checkbox"][value="${c.value}"]`})))
      .map(c=>({...c,selector_count:document.querySelectorAll(c.selector).length}));
    return {heading:text(document.getElementById('pageTitle')?.textContent),records,notes,progression};
  });
}

export function createCommonSchools(host) {
  const dialog=tab=>tab.playwright.getByRole('dialog',{name:contract.lookup_title,exact:true});
  async function waitStatuses(tab) {
    await tab.playwright.getByText('Please wait, the page is loading.',{exact:true}).waitFor({state:'hidden',timeoutMs:15000});
    const route=/^\/common\/4\/(18|19)$/.exec(new URL(await tab.url()).pathname);
    if(!route)throw Error('observed_school_route_required');
    const status=key=>tab.playwright.locator(`[id="${key}"] .nav-item__status forge-screen-reader-text`)
      .filter({hasText:/complete|in progress|not started/i});
    await status('tertiaryNavItem4_'+route[1]).waitFor({state:'attached',timeoutMs:15000});
    const keys=await tab.playwright.evaluate(()=>Array.from(document.querySelectorAll('a[id^="secondaryNavItem"],a[id^="tertiaryNavItem"]'))
      .filter(e=>e.getClientRects().length).map(e=>e.id));
    for(const key of keys){if(!/^(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)$/.test(key))throw Error('observed_school_navigation_required');
      await status(key).waitFor({state:'attached',timeoutMs:10000});}
  }
  function decorate(raw,seen) {
    const kind=Object.keys(contract).find(k=>['current','other'].includes(k)&&new URL(raw.url).pathname===contract[k].path),s=contract[kind];
    if(!s||raw.title!==contract.title||raw.frames_present||seen.heading!==s.heading)throw Error('observed_school_page_required');
    const fields=raw.fields.map(f=>{
      if(f.control==='radio'){
        const questions=f.options.map(o=>/^\[id="option_ques_(\d+)_\d+-input"\]$/.exec(o.selector||'')?.[1]);
        if(!questions[0]||new Set(questions).size!==1)throw Error('observed_school_radio_association_required');
        return {...f,key:'r:ques_'+questions[0],identity_kind:undefined};
      }
      if(f.control==='checkbox'){
        const item=seen.progression.find(p=>'i:'+p.id===f.key),part=contract.progression.find(p=>p.value===item?.value);
        if(!item||!part||item.selector_count!==1||item.label!==part.label)throw Error('observed_school_progression_association_required');
        return {...f,key:'g:265:'+part.part,selector:item.selector,selector_count:1,selector_index:0};
      }
      if(f.control==='unsupported'){
        const note=seen.notes.find(n=>n.question_id===s.statement.question_id);
        if(!note||f.label!==s.statement.label||note.selector_count!==1||f.value!==note.text)throw Error('only_scoped_factual_school_statement_supported');
        return {...f,key:'statement:'+note.question_id,control:'school_statement',selector:note.selector,selector_count:1,selector_index:0,statement_format:note.format};
      }
      return f;
    }).map(f=>{const result={...f};if(result.identity_kind===undefined)delete result.identity_kind;return result;});
    if(seen.notes.length!==fields.filter(f=>f.control==='school_statement').length)throw Error('unexpected_school_statement');
    const id='sectionContinue'+s.path.split('/').at(-1),save=raw.actions.filter(a=>a.key==='i:'+id&&!a.disabled);
    if(save.length!==1||normal(save[0].label.replace(/[()]/g,''))!=='Continue to next section')throw Error('known_school_page_draft_save_required');
    return {schema:'observed-school-page/1',url:raw.url,title:raw.title,heading:seen.heading,frames_present:raw.frames_present,
      fields,actions:[{...save[0],label:'Continue to next section'}],common_school:{schema:'common-school-page/1',kind,
        records:seen.records.map(({selected,...r})=>r)},school_values:Object.fromEntries(seen.records.map(r=>[r.question_id,r.selected])),state_metadata:raw.state_metadata};
  }
  async function observe(tab) {
    if(await dialog(tab).count())throw Error('close_school_lookup_before_page_observation');
    await waitStatuses(tab);return decorate(await host.observe(tab),await native(tab));
  }
  async function settleValidation(tab) {
    const before=await observe(tab);
    // CKEditor's required state can remain stale after load until blur. Trigger
    // its ordinary public validation; never suppress an invalid flag ourselves.
    for(const f of before.fields.filter(f=>f.control==='school_statement'&&f.invalid))await tab.playwright.locator(f.selector).press('Tab');
    const after=await observe(tab);
    // Save/navigation status may finish loading during blur; the persisted
    // checkpoint independently verifies every status against its baseline.
    if(host.digest(schoolValues(after))!==host.digest(schoolValues(before))||host.digest(schoolStructure(after))!==host.digest(schoolStructure(before)))
      throw Error('school_validation_changed_application');
    return after;
  }
  async function openLookup(tab,page,question) {
    if(!page.common_school.records.some(r=>r.question_id===question))throw Error('observed_school_lookup_owner_required');
    const selected=page.school_values[question],id=(selected?'changeSchool':'findSchool')+question;
    const owner=tab.playwright.locator(`ca-lookup[id="text_ques_${question}"]`),button=owner.locator(`[id="${id}"]`);
    if(await owner.count()!==1||await button.count()!==1)throw Error('unique_school_lookup_action_required');
    await button.click();await dialog(tab).waitFor({state:'visible',timeoutMs:10000});
    await dialog(tab).locator(`[id="searchTermControl${question}"]`).waitFor({state:'visible',timeoutMs:10000});
  }
  async function readLookup(tab,question) {
    const data=await dialog(tab).evaluate((d,question)=>{
      const visible=e=>!!e.getClientRects().length&&!['hidden','collapse'].includes(getComputedStyle(e).visibility);
      const text=s=>(s||'').replace(/\s+/g,' ').trim();
      const search=d.querySelector(`[id="searchTermControl${question}"]`),by=d.querySelector(`[id="searchByControl${question}"]`),list=d.querySelector(`[id="selectionListControl${question}"]`);
      if(!search||search.type!=='search'||!by||by.getAttribute('role')!=='combobox'||!list||list.getAttribute('role')!=='listbox')throw Error('public_school_search_controls_required');
      const options=Array.from(list.querySelectorAll('[role=option]')).filter(visible).map(e=>{
        const label=text(e.innerText);if(['Homeschooled',"I don't see my high school in this list"].includes(label))return {kind:'manual',label};
        const parts=Array.from(e.querySelectorAll('p')).filter(visible).map(p=>text(p.innerText));
        const location=parts.length===2&&/^(.*), ([^,]+), (.+) \| CEEB: (\d{6})$/.exec(parts[1]);
        if(!location||!/^selectionListResult\d+-$/.test(e.id))throw Error('public_school_candidate_identity_required');
        const selector=`[id="${e.id}"]`;
        return {kind:'school',name:parts[0],city:location[1],region:location[2],country:location[3],ceeb:location[4],label,selector,
          selector_count:document.querySelectorAll(selector).length,selected:e.getAttribute('aria-selected')==='true'};
      });
      const total=Array.from(d.querySelectorAll('p')).filter(visible).map(e=>/(-?\d+)\s*high schools resulted in your search/.exec(text(e.innerText))).find(Boolean);
      if(!total)throw Error('observed_school_search_count_required');
      const close=d.querySelector('[id="dialogClose"]'),save=d.querySelector(`[id="lookupContinue${question}"]`);
      if(!close||text(close.innerText)!=='Close dialog'||!save||text(save.innerText)!=='Continue , Close dialog')throw Error('known_school_lookup_footer_required');
      return {schema:'observed-school-lookup/1',question_id:question,title:'High School Lookup',query:search.value,search_by:by.value,
        query_key:search.id,total:Number(total[1]),options,loading:Array.from(d.querySelectorAll('[role=status]')).some(e=>visible(e)&&text(e.innerText).includes('Please wait'))};
    },question);
    return {...data,page_url:await tab.url()};
  }
  async function searchLookup(tab,question,query) {
    const by=dialog(tab).locator(`[id="searchByControl${question}"]`);
    if(await by.evaluate(e=>e.value)!==contract.lookup_search)throw Error('school_name_search_mode_required');
    await dialog(tab).locator(`[id="searchTermControl${question}"]`).fill(query);
    // Waiting for a source-named public option avoids accepting the pre-debounce list.
    await dialog(tab).getByRole('option').filter({hasText:new RegExp(escape(query),'i')}).first().waitFor({state:'visible',timeoutMs:15000});
    await dialog(tab).getByText('Please wait, the page is loading.',{exact:true}).waitFor({state:'hidden',timeoutMs:15000});
    return readLookup(tab,question);
  }
  async function lookup(tab,question,query,context) {
    const before=await observe(tab);host.guard(context,before,contract.origin);
    await openLookup(tab,before,question);
    let result;
    try{result=await searchLookup(tab,question,query);}
    finally{await dialog(tab).getByRole('button',{name:'Close dialog',exact:true}).click();await dialog(tab).waitFor({state:'detached',timeoutMs:10000});}
    const after=await observe(tab);
    if(host.digest(valuesAndState(after))!==host.digest(valuesAndState(before))||host.digest(schoolStructure(after))!==host.digest(schoolStructure(before)))
      throw Error('school_directory_discovery_changed_application');
    return result;
  }
  const valuesAndState=p=>({values:schoolValues(p),state:p.state_metadata});
  function eligible(page,plan,context,restoration=false) {
    host.guard(context,page,contract.origin,restoration);
    if(context.journal_persisted!==true||plan.schema!=='common-school-plan/1'||plan.system!=='common_app'||plan.ready!==true||plan.page_url!==page.url)
      throw Error('prepared_school_page_required');
    if(context.real_account_test&&plan.stage!=='fields')throw Error('real_school_creation_or_shape_change_qa_unverified');
  }
  async function write(tab,page,writes) {
    for(const w of writes){const f=page.fields.find(f=>f.key===w.field_key);if(!f)throw Error('observed_school_field_required');
      if(f.control==='school_statement'){
        const s=contract[page.common_school.kind];if(f.key!=='statement:'+s.statement.question_id||f.label!==s.statement.label||typeof w.value!=='string'||!w.value.trim()||w.value.split(/\s+/).length>250)
          throw Error('student_supplied_scoped_school_statement_required');
        const editor=tab.playwright.locator(f.selector);
        // CKEditor's model can retain old text after contenteditable fill. Use
        // normal Windows editing keys and verify deletion before inserting.
        await editor.press('Control+A');await editor.press('Backspace');
        if(normal(await editor.innerText()))throw Error('school_statement_clear_not_observed');
        await editor.fill(w.value);await editor.press('Tab');
      }else{await host.writeObserved(tab,page,[w]);if(f.control==='text')await tab.playwright.locator(f.selector).press('Tab');}
    }
  }
  async function applyStep(tab,plan,context) {
    const page=await observe(tab);eligible(page,plan,context,plan.restoration===true);
    if(host.digest(page)!==plan.observation_sha256)throw Error('school_page_changed_since_preparation');
    const s=contract[page.common_school.kind];
    if(plan.stage==='school'){
      if(page.school_values[plan.question_id]!==null)throw Error('existing_school_replacement_unverified');
      await openLookup(tab,page,plan.question_id);const lookup=await searchLookup(tab,plan.question_id,plan.identity.name);
      const options=lookup.options.filter(o=>o.kind==='school'),matches=options.filter(o=>['name','city','region','country','ceeb'].every(k=>o[k]===plan.identity[k]));
      const named=options.filter(o=>normal(o.name).toLowerCase()===normal(plan.identity.name).toLowerCase()&&o.region==='BC'&&o.country==='Canada');
      if(lookup.loading||lookup.total!==options.length||matches.length!==1||named.length!==1)throw Error('fresh_exact_complete_school_match_required');
      await dialog(tab).locator(matches[0].selector).click();const selected=await readLookup(tab,plan.question_id);
      if(selected.options.filter(o=>o.kind==='school'&&o.selected).length!==1||!selected.options.some(o=>o.kind==='school'&&o.ceeb===matches[0].ceeb&&o.selected))throw Error('selected_school_not_observed');
      await dialog(tab).locator(`[id="lookupContinue${plan.question_id}"]`).click();await dialog(tab).waitFor({state:'detached',timeoutMs:15000});
      await tab.playwright.locator(`[id="changeSchool${plan.question_id}"]`).waitFor({state:'visible',timeoutMs:10000});
    }else if(['count','graduation_mode','progression_mode','fields'].includes(plan.stage)){
      if(!Array.isArray(plan.writes))throw Error('school_source_writes_required');
      const allowed=plan.stage==='count'?[s.count?.key]:plan.stage==='graduation_mode'?[s.graduate?.key]:plan.stage==='progression_mode'?contract.progression.map(p=>'g:265:'+p.part):
        page.fields.filter(f=>f.control==='text'||f.control==='school_statement'||f.key===s.boarding?.key).map(f=>f.key);
      if(plan.writes.some(w=>!allowed.includes(w.field_key)))throw Error('school_stage_write_scope_required');
      await write(tab,page,plan.writes);
      if(plan.stage==='count'){
        const n=Number(plan.writes[0].value);
        if(n)await tab.playwright.locator(`ca-lookup[id="text_ques_${s.records[n-1].question_id}"]`).waitFor({state:'visible',timeoutMs:10000});
        if(n<s.records.length)await tab.playwright.locator(`ca-lookup[id="text_ques_${s.records[n].question_id}"]`).waitFor({state:'hidden',timeoutMs:10000});
      }
      if(plan.stage==='graduation_mode')await tab.playwright.locator(`[id="${s.graduation.key.slice(2)}"]`).waitFor({state:'visible',timeoutMs:10000});
      if(plan.stage==='progression_mode'){
        const changed=plan.writes.some(w=>w.field_key!=='g:265:unchanged'&&w.value===true);
        await tab.playwright.locator(`[role="textbox"][contenteditable="true"][aria-labelledby="title_ques_${s.statement.question_id}"]`).waitFor({state:changed?'visible':'hidden',timeoutMs:10000});
      }
    }else throw Error('known_school_stage_required');
    const after=await observe(tab);
    if(plan.stage==='school'&&(after.school_values[plan.question_id]?.ceeb!==plan.identity.ceeb||after.school_values[plan.question_id]?.name!==plan.identity.name))throw Error('school_selection_not_observed');
    if(['count','graduation_mode','progression_mode'].includes(plan.stage)&&plan.writes.some(w=>after.fields.find(f=>f.key===w.field_key)?.value!==w.value))throw Error('school_stage_value_not_observed');
    if(plan.stage==='fields'&&(host.digest(schoolStructure(after))!==plan.structure_sha256||host.digest(schoolValues(after))!==plan.expected_values_sha256||after.fields.some(f=>f.invalid)))throw Error('whole_school_page_mismatch_before_save');
    return after;
  }
  async function saveAndRead(tab,plan,context) {
    const page=await observe(tab);eligible(page,plan,context,plan.restoration===true);
    if(plan.stage!=='fields'||host.digest(schoolStructure(page))!==plan.structure_sha256||host.digest(schoolValues(page))!==plan.expected_values_sha256||page.fields.some(f=>f.invalid))throw Error('complete_school_page_required_before_save');
    const action=page.actions[0];await tab.playwright.locator(action.selector).click();await tab.playwright.locator(action.selector).waitFor({state:'detached',timeoutMs:15000});
    await tab.playwright.domSnapshot();await tab.goto(plan.page_url);return {page:await settleValidation(tab),revisited_after_save:true};
  }
  async function cancelUnsaved(tab,context) {
    if(await dialog(tab).count()){await dialog(tab).getByRole('button',{name:'Close dialog',exact:true}).click();await dialog(tab).waitFor({state:'detached',timeoutMs:10000});}
    const page=await observe(tab);host.guard(context,page,contract.origin,true);if(context.journal_persisted!==true)throw Error('school_journal_required');
    await tab.reload();return {page:await settleValidation(tab),revisited_saved_draft:true,restore_save_performed:false};
  }
  return {decorate,observe,settleValidation,lookup,readLookup,applyStep,saveAndRead,cancelUnsaved};
}
