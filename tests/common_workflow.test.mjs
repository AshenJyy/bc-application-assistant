import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {mkdtempSync,readFileSync,readdirSync,rmSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {createCommonWorkflow} from '../skills/bc-application/scripts/common_workflow.mjs';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.BC_TEST_PYTHON||(process.platform==='win32'?root+'work/.venv/Scripts/python.exe':'python3');
const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8',TEMP:root+'work/tmp',TMP:root+'work/tmp'};
const fixture=JSON.parse(execFileSync(python,['-B',root+'tests/workflow_host_scenario.py'],{cwd:root,encoding:'utf8',env,maxBuffer:4e6}));

function setup({missing=false,interrupt=false,sourceChange=false,wrongSaved=false,failIndependentOnce=false}={}){
  const folder=mkdtempSync(root+'work/workflow-host-'),profile=folder+'/applicant.json',data=structuredClone(fixture);
  execFileSync(python,['-B',root+'tests/workflow_host_scenario.py','init',profile,...(missing?['missing']:[])],{cwd:root,encoding:'utf8',env});
  const pages=structuredClone(data.pages),saved=structuredClone(data.pages),calls=[];let url=data.steps[0].page_url,dialog=false,fire=true,savedReads=0;
  const relay=async(command,payload,extra={})=>{
    const args=['-B',root+'skills/bc-application/scripts/run.py',command,'--profile',profile];
    for(const [k,v]of Object.entries(extra)){args.push('--'+k.replaceAll('_','-'));if(v!==true)args.push(v);}
    return JSON.parse(execFileSync(python,args,{input:JSON.stringify(payload),cwd:root,encoding:'utf8',env,maxBuffer:4e6}));
  };
  const transition=(plan,isSaved=false)=>{
    pages[url]=JSON.parse(execFileSync(python,['-B',root+'tests/workflow_host_scenario.py','transition'],{
      input:JSON.stringify({page:pages[url],plan,saved:isSaved}),cwd:root,encoding:'utf8',env,maxBuffer:4e6}));
  };
  const read=()=>{const p=structuredClone(pages[url]);if(p.common_academic)p.choice_observations={};return p;};
  const tab={url:async()=>url,goto:async next=>{assert.ok(next in pages);url=next;calls.push('navigate');},playwright:{getByRole:()=>({
    count:async()=>Number(dialog),locator:()=>({count:async()=>1,click:async()=>{dialog=false;calls.push('close-grade');}}),waitFor:async()=>{}})}};
  const schools={observe:async()=>read(),settleValidation:async()=>read(),lookup:async(_tab,q,query)=>{calls.push('lookup');return structuredClone(data.lookups[query]);},
    applyStep:async(_tab,plan)=>{calls.push('input:'+plan.stage);transition(plan);return read();},
    saveAndRead:async(_tab,plan)=>{calls.push('save-school');transition(plan,true);saved[url]=structuredClone(pages[url]);return {page:read(),revisited_after_save:true};}};
  const academic={captureParent:async()=>structuredClone(pages[url].editor_state),open:async()=>{
    const registry=Object.values(saved).flatMap(p=>Object.values(p.school_values||{})).filter(Boolean);
    assert.equal(registry.length,2,'education must create school choices before academic input');dialog=true;calls.push('open-grade');return read();},
    observe:async()=>read(),inspectChoices:async()=>{calls.push('choices');return structuredClone(pages[url]);},
    applyStep:async(_tab,plan)=>{calls.push('input:'+plan.stage);transition(plan);return read();},
    saveAndRead:async(_tab,plan)=>{calls.push('save-academic');transition(plan,true);saved[url]=structuredClone(pages[url]);return {page:read(),revisited_after_save:true};}};
  const onEvent=event=>{
    if(interrupt&&fire&&event.event==='page_stage'&&event.stage==='header'){fire=false;throw Error('fictional_port_interruption');}
    if(sourceChange&&fire&&event.event==='page_verified'){fire=false;
      execFileSync(python,['-B',root+'skills/bc-application/scripts/run.py','profile-update','--profile',profile,'--stdin'],{
        input:JSON.stringify([{op:'statement',id:'changed',text:'A fictional graduation-date correction.'},
          {op:'fact',field:'education.graduation_date',value:'2027-02',source:'changed'}]),cwd:root,encoding:'utf8',env});}
  };
  const api=createCommonWorkflow({host,schools,academic,relay,onEvent,inspectSaved:async job=>{
    if(failIndependentOnce&&savedReads++===0)throw Error('Fictional independent read interrupted');
    calls.push('independent-saved-read');const p=structuredClone(saved[job.page_url]);
    if(wrongSaved)p.fields[0].value='Wrong fictional saved value';
    return {page:p,independent_saved_draft:true};}});
  return {api,tab,calls,data,profile,relay,pages,saved,getURL:()=>url,setURL:u=>{url=u;},cleanup:()=>{
    if(!resolve(folder).startsWith(resolve(root+'work')+sep))throw Error('Test cleanup escaped workspace');
    rmSync(folder,{recursive:true,force:true});},
    request:()=>({steps:data.steps,routes:data.routes}),load:()=>JSON.parse(readFileSync(profile)),jsonFiles:()=>readdirSync(folder).filter(f=>f.endsWith('.json'))};
}

test('connected workflow creates schools then courses with one canonical file',async()=>{
  const s=setup();try{const result=await s.api.run(s.tab,s.request(),s.data.context);
    assert.equal(result.status,'provided_pages_verified');assert.equal(result.verified_pages.length,3);assert.ok(!result.full_application_complete);
    assert.equal(s.calls.filter(c=>c==='save-school').length,2);assert.equal(s.calls.filter(c=>c==='save-academic').length,1);
    assert.equal(s.calls.filter(c=>c==='lookup').length,2);assert.equal(s.jsonFiles().length,1);
    assert.deepEqual(s.load().academic,fixture.profile.academic);assert.ok(Object.values(s.load().checkpoints).every(c=>c.journal===null));
    assert.equal(s.pages[s.data.steps[2].page_url].editor_state.completion_checked,false);
  }finally{s.cleanup();}
});

test('missing source answer stops all application inputs before lookup or navigation',async()=>{
  const s=setup({missing:true});try{const before=readFileSync(s.profile),result=await s.api.run(s.tab,s.request(),s.data.context);
    assert.equal(result.status,'information_or_implementation_required');assert.equal(result.agenda.questions[0].fact_id,'education.boarding');
    assert.equal(s.calls.length,0);assert.deepEqual(readFileSync(s.profile),before);
  }finally{s.cleanup();}
});

test('ambiguous public school lookup stops the joined workflow before application input',async()=>{
  const s=setup();try{const lookup=s.data.lookups['Fictional Secondary 2'];lookup.total=2;
    lookup.options.push({...lookup.options[0],ceeb:'999999',label:lookup.options[0].label.replace('123452','999999'),selector:'[id="selectionListResult999-"]'});
    const before=readFileSync(s.profile),result=await s.api.run(s.tab,s.request(),s.data.context);
    assert.equal(result.status,'school_directory_review_required');assert.ok(!s.calls.some(c=>c.startsWith('input:')||c.startsWith('save-')));
    assert.deepEqual(readFileSync(s.profile),before);
  }finally{s.cleanup();}
});

test('an interrupted course stage resumes the same journal then rechecks earlier schools',async()=>{
  const s=setup({interrupt:true});try{const first=await s.api.run(s.tab,s.request(),s.data.context);
    assert.equal(first.status,'interrupted');assert.ok(first.checkpoint_id);const original=structuredClone(s.load().checkpoints[first.checkpoint_id].journal);
    const second=await s.api.run(s.tab,s.request(),s.data.context);assert.equal(second.status,'provided_pages_verified');
    assert.equal(second.verified_pages.length,3);assert.ok(second.verified_pages.some(p=>p.checkpoint_id===first.checkpoint_id));
    assert.ok(original);assert.equal(s.calls.filter(c=>c==='save-school').length,2);assert.equal(s.calls.filter(c=>c==='save-academic').length,1);
    assert.equal(s.calls.filter(c=>c==='independent-saved-read').length,2);assert.ok(Object.values(s.load().checkpoints).every(c=>c.journal===null));
  }finally{s.cleanup();}
});

test('another university shares the saved pages without repeated writes or duplicate records',async()=>{
  const s=setup();try{assert.equal((await s.api.run(s.tab,s.request(),s.data.context)).status,'provided_pages_verified');
    await s.relay('profile-update',[{op:'statement',id:'new',text:'A fictional second university choice.'},
      {op:'target',id:'new-target',system:'common_app',school:'Another fictional target',source:'new'}],{stdin:true});
    const other=Object.keys(s.load().targets).find(t=>t!==s.data.target),existing=structuredClone(s.saved),beforeSaves=s.calls.filter(c=>c.startsWith('save-')).length;
    s.data.steps.push(...s.data.steps.map(step=>({...step,target_id:other})));s.setURL(s.data.steps[0].page_url);
    const result=await s.api.run(s.tab,s.request(),s.data.context);assert.equal(result.status,'provided_pages_verified');
    assert.equal(result.verified_pages.length,3);assert.ok(result.verified_pages.every(p=>p.target_ids.length===2&&!p.save_performed));
    assert.equal(s.calls.filter(c=>c.startsWith('save-')).length,beforeSaves);assert.deepEqual(s.saved,existing);assert.equal(s.jsonFiles().length,1);
  }finally{s.cleanup();}
});

test('source changes stop before entering a later page',async()=>{
  const s=setup({sourceChange:true});try{const result=await s.api.run(s.tab,s.request(),s.data.context);
    assert.equal(result.status,'sources_changed');assert.equal(result.verified_pages.length,1);assert.ok(!s.calls.includes('navigate'));
  }finally{s.cleanup();}
});

test('current unsaved page is not discarded to reach the first workflow route',async()=>{
  const s=setup();try{s.setURL(s.data.steps[1].page_url);const result=await s.api.run(s.tab,s.request(),s.data.context);
    assert.equal(result.status,'navigation_required');assert.equal(s.calls.length,0);
  }finally{s.cleanup();}
});

test('bounded execution pauses with its journal and can resume without duplicate schools',async()=>{
  const s=setup();try{const first=await s.api.run(s.tab,s.request(),s.data.context,{maxStages:1});
    assert.equal(first.status,'bounded_pause');assert.ok(s.load().checkpoints[first.checkpoint_id].journal);
    const result=await s.api.run(s.tab,s.request(),s.data.context);assert.equal(result.status,'provided_pages_verified');
    assert.equal(s.calls.filter(c=>c==='save-school').length,2);assert.equal(s.calls.filter(c=>c==='save-academic').length,1);
  }finally{s.cleanup();}
});

test('an independently saved mismatch is not silently saved or counted as complete',async()=>{
  const s=setup({wrongSaved:true});try{assert.equal((await s.api.run(s.tab,s.request(),s.data.context)).status,'provided_pages_verified');
    s.setURL(s.data.steps[0].page_url);const before=s.calls.filter(c=>c.startsWith('save-')).length;
    const result=await s.api.run(s.tab,s.request(),s.data.context);assert.equal(result.status,'saved_page_mismatch');
    assert.equal(result.verified_pages.length,0);assert.ok(s.load().checkpoints[result.checkpoint_id].journal);
    assert.equal(s.calls.filter(c=>c.startsWith('save-')).length,before);
  }finally{s.cleanup();}
});

test('resuming an interrupted matching-page read still avoids unnecessary Save',async()=>{
  const s=setup({failIndependentOnce:true});try{assert.equal((await s.api.run(s.tab,s.request(),s.data.context)).status,'provided_pages_verified');
    s.setURL(s.data.steps[0].page_url);const before=s.calls.filter(c=>c.startsWith('save-')).length;
    const interrupted=await s.api.run(s.tab,s.request(),s.data.context);assert.equal(interrupted.status,'interrupted');assert.ok(interrupted.checkpoint_id);
    const result=await s.api.run(s.tab,s.request(),s.data.context);assert.equal(result.status,'provided_pages_verified');
    assert.equal(s.calls.filter(c=>c.startsWith('save-')).length,before);assert.ok(result.verified_pages.every(p=>!p.save_performed));
  }finally{s.cleanup();}
});

for(const flag of ['real_account_test','restore_after_test'])test(`${flag} cannot authorize connected record creation QA`,async()=>{
  const s=setup();try{await assert.rejects(s.api.run(s.tab,s.request(),{...s.data.context,[flag]:true}),/intended_edge_workflow_only/);assert.equal(s.calls.length,0);}
  finally{s.cleanup();}
});
