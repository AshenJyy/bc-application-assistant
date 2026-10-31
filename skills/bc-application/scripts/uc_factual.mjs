/** Fixed observed UC factual shapes; shares personal-page save/recovery engine. */
import {readFile} from 'node:fs/promises';
import {createUcPersonal} from './uc_personal.mjs';
export const contracts=JSON.parse(await readFile(new URL('./bc_application/data/uc_native_forms.json',import.meta.url),'utf8'));
export function createUcFactual(host,kind) {
  const spec=contracts.find(c=>c.kind===kind);
  if(!spec)throw Error('observed_uc_factual_contract_required');
  const pageUrl='https://apply.universityofcalifornia.edu'+spec.path;
  const decorate=page=>({...page,uc_factual:{schema:'uc-factual-page/1',kind}});
  function checkPage(page) {
    if(page.url!==pageUrl||page.title!==spec.title||page.frames_present||page.collections?.length||page.scope||
       page.uc_factual?.schema!=='uc-factual-page/1'||page.uc_factual.kind!==kind||
       page.fields.length!==spec.fields.length||new Set(page.fields.map(f=>f.key)).size!==spec.fields.length)
      throw Error('observed_uc_factual_shape_required');
    for(const expected of spec.fields) {
      const f=page.fields.find(f=>f.key===expected.key);
      if(!f||['label','group','control'].some(k=>f[k]!==expected[k])||f.disabled||f.readonly||!f.selector||
         (f.selector_count??1)!==1||(f.selector_index??0)!==0)
        throw Error('observed_uc_factual_fields_required');
    }
    if(page.actions.filter(a=>a.key==='i:save'&&a.label==='Save & continue'&&!a.disabled&&a.selector==='[id="save"]').length!==1)
      throw Error('observed_uc_factual_draft_save_required');
  }
  const reviewSelector=`[role="button"][href=${JSON.stringify(spec.path)}]`;
  return {...createUcPersonal(host,{pageUrl,heading:spec.heading,reviewLabel:spec.review_label,reviewSelector,nativeSaveClick:true,decorate,checkPage}),spec,decorate};
}
