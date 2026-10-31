import test from 'node:test';
import assert from 'node:assert/strict';
import * as host from '../skills/bc-application/scripts/host_browser.mjs';
import {contract,createCommonIelts} from '../skills/bc-application/scripts/common_ielts.mjs';
import {createChoiceControls} from '../skills/bc-application/scripts/choice_controls.mjs';

const vals=p=>Object.fromEntries(p.fields.map(f=>[f.key,f.value]));
const clone=structuredClone;
function setup({incomplete=false}={}) {
  const calls=[],page={schema:'observed-page/1',url:'https://apply.commonapp.org'+contract.path,
    title:contract.title,frames_present:false,fields:[],actions:[],state_metadata:{schema:'observed-state/1',
      coverage:'common_app_visible_navigation',current_page_key:'tertiaryNavItem2_10',items:[
        {key:'secondaryNavItem2',status:incomplete?'in progress':'complete'},
        {key:'secondaryNavItem3',status:'complete'},{key:'tertiaryNavItem2_2',status:'complete'},
        {key:'tertiaryNavItem2_10',status:incomplete?'in progress':'complete'}]}};
  const options={},native={schema:'common-ielts-native/1',heading:'IELTS',content:'Synthetic public contract text',controls:[],auxiliary:[]};
  for(const spec of contract.fields) {
    const {key,label,group,control,required}=spec;
    const f={key,label,group,required,control:control==='choice_input'?'unsupported':control,name:key.slice(2),
      selector:`[id="${key.slice(2)}"]`,value:incomplete?'':'1',invalid:incomplete,disabled:false,readonly:false,options:[]};
    if(control==='choice_input') {
      const labels=key==='i:text_ques_159'?['0','1','2','3','4','5']:['9','8','7.5','7','6.5','6','1','0'];
      options[key]=labels.map((label,index)=>({value:label,label,disabled:false,index}));
      native.controls.push({key,tag:'INPUT',type:'text',role:'combobox',popup:'listbox',expanded:'false',wrapper:'NG-SELECT'});
    } else if(control==='radio') {
      f.name='mat-radio-group-0';f.key='n:mat-radio-group-0';
      f.options=['0','1','2','3'].map((label,i)=>({label,value:String(i+15),disabled:false,selector:`[id="option_ques_160_${i+15}-input"]`}));
      f.selector=f.options[0].selector;if(!incomplete)f.value='15';
    } else if(!incomplete)f.value='January 1, 2024';
    page.fields.push(f);
  }
  const choices=Object.fromEntries(Object.entries(options).map(([k,v])=>[k,v.map(({label,value,disabled})=>({label,value,disabled}))]));
  let open=null,selectionPending=false,url=page.url,saved=clone(page),association='popup',delayed=true;
  function raw() {
    const p=clone(page);p.actions=[{key:'i:sectionContinue10',label:'Continue to next section',selector:'[id="sectionContinue10"]',disabled:false}];
    native.auxiliary=[];
    for(const f of p.fields) {
      if(f.control==='unsupported'&&f.value) {
        const index=p.actions.length;native.auxiliary.push({index,kind:'clear',field_key:f.key});
        p.actions.push({key:'a:'+index,label:'',selector:null,disabled:false});
      }
      if(f.control==='text') {
        const index=p.actions.length;native.auxiliary.push({index,kind:'calendar',field_key:f.key});
        p.actions.push({key:'a:'+index,label:'',selector:null,disabled:false});
      }
    }
    p.actions.push({key:'a:'+p.actions.length,label:'Help',selector:null,disabled:false});return p;
  }
  function locator(selector) {
    const field=page.fields.find(f=>f.selector===selector);
    return {count:async()=>1,evaluate:async()=>({tag:'INPUT',type:'text',role:'combobox',expanded:open?'true':'false',popup:'listbox'}),
      getAttribute:async()=>association,waitFor:async({state})=>{if(state==='detached')assert.notEqual(url,page.url);},
      click:async()=>{
        if(selector==='[id="sectionContinue10"]') {
          calls.push('save');saved=clone(page);for(const i of saved.state_metadata.items)
            if(['secondaryNavItem2','tertiaryNavItem2_10'].includes(i.key))i.status='complete';
          url='https://apply.commonapp.org/common/7/232';return;
        }
        assert.ok(field);open=field.key;calls.push('open:'+field.key);
      },press:async key=>{
        if(key==='Escape'){assert.equal(selectionPending,false);calls.push('close');open=null;}
        else {assert.equal(key,'Tab');calls.push('blur');}
      },fill:async value=>{calls.push('fill');field.value=value;field.invalid=false;},
      check:async()=>{const f=page.fields.find(f=>f.options.some(o=>o.selector===selector));
        calls.push('radio');f.value=f.options.find(o=>o.selector===selector).value;f.invalid=false;}};
  }
  const panel={count:async()=>Number(!!open),isVisible:async()=>!!open,getAttribute:async()=> 'popup',
    waitFor:async({state})=>{if(state==='detached'){calls.push('selection-closed');selectionPending=false;open=null;}else assert.ok(open);},
    evaluate:async()=>options[open].map(({label,disabled,index})=>({label,disabled,index})),
    getByRole:()=>({count:async()=>options[open].length,nth:i=>({click:async()=>{
      const f=page.fields.find(f=>f.key===open);f.value=options[open][i].label;f.invalid=false;
      calls.push('select:'+f.value);selectionPending=delayed;if(!delayed)open=null;
    }})})};
  const tab={url:async()=>url,goto:async dest=>{assert.equal(dest,page.url);url=dest;Object.assign(page,clone(saved));calls.push('revisit');},
    reload:async()=>{Object.assign(page,clone(saved));calls.push('cancel-reload');},playwright:{locator,
      getByRole:role=>role==='listbox'?panel:{waitFor:async()=>{}},
      evaluate:async()=>clone(native),domSnapshot:async()=>''}};
  const api=createCommonIelts({...host,observe:async()=>raw(),digest:v=>v==='Synthetic public contract text'?contract.content_sha256:host.digest(v)});
  const context={browser_family:'edge',transport:'extension',access_verified:true,origin:'https://apply.commonapp.org',journal_persisted:true};
  const observation=api.decorate(raw(),clone(native),choices),desired=vals(observation);
  desired['i:text_ques_159']='3';desired['r:ques_160']='15';desired['i:text_ques_164']='7.5';
  for(const f of observation.fields.filter(f=>f.control==='text'))desired[f.key]='April 12, 2025';
  if(incomplete)for(const f of observation.fields.filter(f=>f.control==='choice_input'&&f.key!=='i:text_ques_159'))desired[f.key]='7';
  const plan={system:'common_app',ready:true,page_url:page.url,common_ielts:observation.common_ielts,choice_observations:choices,
    observation_sha256:host.digest(observation),structure_sha256:host.digest(host.structure(observation)),
    expected_values_sha256:host.digest(desired),writes:Object.entries(desired).filter(([k,v])=>vals(observation)[k]!==v).map(([field_key,value])=>({field_key,value})),
    save_action:observation.actions[0]};
  return {api,tab,page,native,options,choices,context,plan,calls,observation,
    setAssociation:v=>{association=v;},mutateSaved:fn=>fn(saved)};
}

test('read-only choice inspection preserves values and closes every associated input menu',async()=>{
  const s=setup(),before=host.digest(s.page),observed=await s.api.inspect(s.tab);
  assert.deepEqual(observed.choice_observations,s.choices);assert.equal(host.digest(s.page),before);
  assert.equal(s.calls.filter(c=>c==='close').length,6);assert.ok(!s.calls.includes('save'));
});

test('whole-page input, one save and revisit read all twelve fields with stable dynamic auxiliary actions',async()=>{
  const s=setup({incomplete:true});await s.api.apply(s.tab,s.plan,s.context);
  const result=await s.api.saveAndRead(s.tab,s.plan,s.context);
  assert.equal(host.digest(vals(result.page)),s.plan.expected_values_sha256);
  assert.equal(host.digest(host.structure(result.page)),s.plan.structure_sha256);
  assert.equal(s.calls.filter(c=>c==='save').length,1);
  assert.ok(s.calls.includes('selection-closed'));assert.ok(s.calls.includes('radio'));assert.ok(s.calls.includes('revisit'));
});

for(const change of ['journal','stale','new_field','content','widget','calendar','clear_owner','save','origin'])test(`${change} drift stops before input/save`,async()=>{
  const s=setup();
  if(change==='journal')s.context.journal_persisted=false;
  if(change==='stale')s.plan.observation_sha256='0'.repeat(64);
  if(change==='new_field')s.page.fields.push({...s.page.fields[0],key:'i:new'});
  if(change==='content')s.native.content='A new declaration';
  if(change==='widget')s.native.controls[0].wrapper='UNKNOWN';
  if(change==='calendar')s.page.fields.find(f=>f.control==='text').control='email';
  if(change==='clear_owner')s.native.controls.pop();
  if(change==='save')s.plan.ready=false;
  if(change==='origin')s.context.origin='https://other.example';
  await assert.rejects(s.api.apply(s.tab,s.plan,s.context));assert.deepEqual(s.calls,[]);
});

for(const change of ['labels','disabled','order','association'])test(`${change} menu drift closes the menu without choosing`,async()=>{
  const s=setup();
  if(change==='association')s.setAssociation('unrelated-popup');
  else if(change==='order')s.options['i:text_ques_159'].reverse();
  else s.options['i:text_ques_159'][3][change==='disabled'?'disabled':'label']=change==='disabled'?true:'Different';
  await assert.rejects(s.api.apply(s.tab,s.plan,s.context));
  assert.equal(s.calls.some(c=>c.startsWith('select:')||c==='fill'||c==='save'),false);assert.equal(s.calls.at(-1),'close');
});

test('partial or invalid page cannot be saved',async()=>{
  const s=setup({incomplete:true});await assert.rejects(s.api.saveAndRead(s.tab,s.plan,s.context),/prepared_valid_ielts_values_required/);
  assert.deepEqual(s.calls,[]);
});

test('unsaved incomplete original is canceled by reload without a blank page save',async()=>{
  const s=setup({incomplete:true}),original=vals(s.observation);await s.api.apply(s.tab,s.plan,s.context);
  const result=await s.api.restore(s.tab,{plan:s.plan,context:s.context,writes:[],original_invalid_fields:['i:text_ques_164']},{unsaved:true});
  assert.deepEqual(vals(result.page),original);assert.equal(result.restore_save_performed,false);assert.ok(!s.calls.includes('save'));
  await assert.rejects(s.api.restore(s.tab,{plan:s.plan,context:s.context,original_invalid_fields:['i:text_ques_164']}),/incomplete_ielts_original_requires_cancel_or_resume/);
});

test('completed original can be restored by exact choices/dates and whole saved readback',async()=>{
  const s=setup(),original=vals(s.observation);await s.api.apply(s.tab,s.plan,s.context);await s.api.saveAndRead(s.tab,s.plan,s.context);
  const writes=Object.entries(original).filter(([k,v])=>vals(s.page)[k]!==v).map(([field_key,value])=>({field_key,value}));
  const result=await s.api.restore(s.tab,{plan:s.plan,context:s.context,writes,original_invalid_fields:[],original_values_sha256:host.digest(original)});
  assert.deepEqual(vals(result.page),original);assert.equal(s.calls.filter(c=>c==='save').length,2);
});

test('returned saved values remain authoritative; a lost save is exposed to the core verifier',async()=>{
  const s=setup();await s.api.apply(s.tab,s.plan,s.context);const actualGoto=s.tab.goto;
  s.tab.goto=async dest=>{s.mutateSaved(p=>{p.fields[0].value='2';});await actualGoto(dest);};
  const result=await s.api.saveAndRead(s.tab,s.plan,s.context);
  assert.notEqual(host.digest(vals(result.page)),s.plan.expected_values_sha256);
});

test('generic native writer refuses custom choices; only observed option selection is allowed',async()=>{
  const s=setup();await assert.rejects(host.writeObserved(s.tab,s.observation,[{field_key:'i:text_ques_159',value:'3'}]),/observed_editable_field_required/);
  assert.deepEqual(s.calls,[]);
});

test('input menus require the exact public widget and unique observed locator',async()=>{
  const s=setup(),helper=createChoiceControls(host),f=s.observation.fields[0];
  const original=s.tab.playwright.locator;
  s.tab.playwright.locator=selector=>({...original(selector),count:async()=>2});
  await assert.rejects(helper.options(s.tab,f),/unique_material_locator_required/);assert.deepEqual(s.calls,[]);
});
