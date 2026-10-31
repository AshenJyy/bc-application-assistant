/** Exact-option selects through documented locators and public ARIA metadata. */
export function createChoiceControls({digest}) {
const panelFor=(tab,f)=>tab.playwright.getByRole('listbox',{name:f.control==='choice_input'?'Options':f.label,exact:true});
async function materialOptions(tab,f) {
  const locator=tab.playwright.locator(f.selector);
  if(await locator.count()!==1)throw Error('unique_material_locator_required');
  const widget=await locator.evaluate(e=>({tag:e.tagName,role:e.getAttribute('role'),expanded:e.getAttribute('aria-expanded'),
    type:e.getAttribute('type'),popup:e.getAttribute('aria-haspopup')}));
  const input=f.control==='choice_input';
  if((input ? widget.tag!=='INPUT'||widget.type!=='text'||widget.popup!=='listbox' : widget.tag!=='MAT-SELECT')||
     widget.role!=='combobox'||widget.expanded!=='false')throw Error('closed_single_select_required');
  await locator.click();
  try {
    const panel=panelFor(tab,f);
    await panel.waitFor({state:'visible',timeoutMs:10000});
    if(await panel.count()!==1)throw Error('unique_observed_single_listbox_required');
    if(input) {
      const controls=await locator.getAttribute('aria-controls');
      if(!controls||await panel.getAttribute('id')!==controls)throw Error('observed_input_listbox_association_required');
    }
    return await panel.evaluate(e=>{
      if(e.getAttribute('aria-multiselectable')==='true')throw Error('single_listbox_required');
      const nodes=Array.from(e.querySelectorAll('[role=option]')).filter(o=>o.getClientRects().length);
      const options=nodes.map((o,index)=>({label:(o.innerText||'').replace(/\s+/g,' ').trim(),
        disabled:o.getAttribute('aria-disabled')==='true',index}));
      if(!options.length||new Set(options.map(o=>o.label)).size!==options.length)throw Error('unique_observed_option_labels_required');
      return options;
    });
  } catch(error) {await closeOptions(tab,f);throw error;}
}

async function closeOptions(tab,f) {
  const panel=panelFor(tab,f);
  if(await panel.count()) {
    // Keep focus inside the actual open listbox. Refocusing the underlying
    // combobox before Escape can send it to the containing portal dialog.
    if(await panel.isVisible()) {
      if(f.control==='choice_input')await tab.playwright.locator(f.selector).press('Escape');
      else await panel.press('Escape');
    }
    await waitOptionsClosed(tab,panel);
  }
}

async function waitOptionsClosed(tab,panel) {
  await tab.playwright.domSnapshot();
  // Material removes its overlay node after selection. A hidden-only wait
  // can miss that lifecycle; use removal when the visible node still exists.
  if(await panel.count()&&await panel.isVisible()) {
    try {await panel.waitFor({state:'detached',timeoutMs:20000});}
    catch(error) {await tab.playwright.domSnapshot();if(await panel.count()&&await panel.isVisible())throw error;}
  }
  if(await panel.count()&&await panel.isVisible())throw Error('grade_option_panel_still_open');
}

async function selectMaterial(tab,page,f,value,choices) {
  if(!choices?.length)throw Error('observed_material_choices_required');
  const options=await materialOptions(tab,f);
  const comparison=options.map(o=>({value:o.label,label:o.label,disabled:o.disabled}));
  let selectionAttempted=false;
  try {
    if(digest(comparison)!==digest(choices))throw Error('material_choices_changed');
    const selected=options.filter(o=>o.label===value&&!o.disabled);
    if(selected.length!==1)throw Error('exact_observed_material_choice_required');
    const panel=panelFor(tab,f);
    const locator=panel.getByRole('option');
    if(await locator.count()!==options.length)throw Error('material_option_count_changed');
    selectionAttempted=true;
    await locator.nth(selected[0].index).click();
    // Selection closes its own panel asynchronously. Do not refocus or send
    // Escape during that transition: it can reach the parent dialog instead.
    await waitOptionsClosed(tab,panel);
  } catch(error) {
    if(!selectionAttempted)await closeOptions(tab,f);
    throw error;
  }
}

return {options:materialOptions,close:closeOptions,select:selectMaterial};
}
