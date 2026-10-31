"""Different fictional applicants against repeated public language semantics."""
import copy
import json
from pathlib import Path

import pytest

from bc_application.browser import digest,values,structure
from bc_application.common_factual import CONTRACTS,field_specs
from bc_application.common_pages import resume
from bc_application.pages import build_plan,prepare,verify_saved,recovery_bundle
from bc_application.profile import ProfileError,create_profile,add_statement,add_target,set_fact


def setup(kind='language',*,n=2,complete=False):
    profile=create_profile(Path(__file__).parent/'fixtures/synthetic_psr.pdf')
    source=add_statement(profile,'Invented applicant explicitly supplies all language abilities and household answers.')
    target=add_target(profile,system='common_app',school='Fictional college',program=None,source_id=source)
    spec=next(s for s in CONTRACTS if s['kind']==kind);path=spec['path'];section=path.split('/')[2];number=path.split('/')[-1]
    facts={'family.independence_statuses_apply':False,'family.parents.marital_status':'Married','family.permanent_home':'Parent 1',
        'personal.languages.order':[f'language_{i}' for i in range(n)]}
    labels=['French','Spanish','German','Mandarin','English']
    for i in range(n):
        prefix=f'personal.languages.language_{i}.';facts[prefix+'label']=labels[i]
        facts.update({prefix+s['part']:s['part']=='speak' or i==0 and s['part']=='first_language' for s in CONTRACTS[1]['proficiencies']})
    for key,value in facts.items():set_fact(profile,key,value,source)
    page={'schema':'observed-page/1','url':'https://apply.commonapp.org'+path,'title':spec['title'],'frames_present':False,
        'common_factual':{'schema':'common-factual-page/1','kind':kind,'content_sha256':spec['content_sha256'],
            **({'rows':[{'language_key':f'i:text_ques_{4000+2*i}','proficiency_id':str(4001+2*i)} for i in range(n)]} if kind=='language' else {})},
        'common_factual_native':{'schema':'common-factual-native/1','heading':spec['heading'],'controls':[]},
        'fields':[],'actions':[{'key':'i:sectionContinue'+number,'label':'Continue to next section','selector':f'[id="sectionContinue{number}"]','disabled':False}],
        'choice_observations':{},'state_metadata':{'schema':'observed-state/1','coverage':'common_app_visible_navigation',
            'current_page_key':spec['current_key'],'items':[{'key':key,'status':'complete' if complete else 'in progress'}
                for key in [spec['parent_key'],spec['current_key']]]+[{'key':'secondaryNavItem7','status':'in progress'}]}}
    if kind=='language' and n==0:page['common_factual']['content_sha256']=spec['empty_content_sha256']
    for i,wanted in enumerate(field_specs(page)):
        f={k:wanted[k] for k in ('key','label','group','control','required')}
        f.update(selector=wanted.get('selector',f'[id="{f["key"][2:]}"]'),value=False if f['control']=='checkbox' else '',
            disabled=False,readonly=False,invalid=not complete and f['required'],options=[])
        if f['control']=='radio':
            question=f['key'].split('_')[-1];labels=[str(i) for i in range(1,6)] if question=='223' else ['Married','Separated'] if question=='364' else ['Both Parents','Parent 1','Parent 2','Other'] if question=='366' else ['Yes','No']
            f['options']=[{'value':str(j),'label':label,'disabled':False,'selector':f'[id="option_ques_{question}_{j}-input"]'} for j,label in enumerate(labels)]
            f.update(selector=f['options'][0]['selector'],name=f'mat-radio-group-{i}',identity_kind='common_app_question_radio')
            if complete:f['value']=str(n-1) if question=='223' else '0' if question in {'364','366'} else '1' if question=='3033' else ''
            if question=='223':f.update(value=str(n-1) if n else '',invalid=not bool(n))
        elif f['control']=='choice_input':
            page['choice_observations'][f['key']]=[{'label':label,'value':label,'disabled':False} for label in ['English','French','Spanish','German','Mandarin']]
            page['common_factual_native']['controls'].append({'key':f['key'],'tag':'INPUT','type':'text','role':'combobox','popup':'listbox','expanded':'false','wrapper':'NG-SELECT'})
            if complete:f['value']='English'
        page['fields'].append(f)
    context={'browser_family':'edge','transport':'extension','origin':'https://apply.commonapp.org','access_verified':True}
    return profile,target,page,context


def filled(page,plan):
    result=copy.deepcopy(page)
    for w in plan['writes']:next(f for f in result['fields'] if f['key']==w['field_key'])['value']=w['value']
    for f in result['fields']:f['invalid']=False
    for item in result['state_metadata']['items']:
        if item['key']!='secondaryNavItem7':item['status']='complete'
    return result


@pytest.mark.parametrize('n',[1,2,3,4,5])
def test_existing_language_rows_map_different_students_without_student_specific_ids(n):
    p,t,page,context=setup(n=n);plan=build_plan(p,t,page)
    assert plan['ready'],plan['blockers']
    assert len(page['fields'])==1+6*n
    refs=[w['fact_ref'] for w in plan['writes']]
    assert all(f'personal.languages.language_{i}.label' in refs for i in range(n))
    prepare(p,plan['checkpoint_id'],page,context)
    assert verify_saved(p,plan['checkpoint_id'],filled(page,plan),revisited_after_save=True)['verified']
    assert p['checkpoints'][plan['checkpoint_id']]['journal'] is None


@pytest.mark.parametrize('kind',['language','household'])
def test_whole_original_survives_restart_and_requires_exact_status_recovery(kind):
    p,t,page,ctx=setup(kind,complete=True);plan=build_plan(p,t,page)
    assert plan['ready'],plan['blockers']
    ctx.update(real_account_test=True,full_state_restoration_verified=True,restoration_strategy={
        'kind':'restore_completed_native_page','current_page_key':page['state_metadata']['current_page_key'],
        'baseline_state_sha256':digest(page['state_metadata'])})
    prepare(p,plan['checkpoint_id'],page,ctx);after=filled(page,plan)
    assert verify_saved(p,plan['checkpoint_id'],after,revisited_after_save=True)['verified']
    p=json.loads(json.dumps(p));recovery=recovery_bundle(p,plan['checkpoint_id'],after)
    assert recovery['original_values_sha256']==digest(values(page))
    wrong=copy.deepcopy(page);wrong['state_metadata']['items'][-1]['status']='complete'
    assert not verify_saved(p,plan['checkpoint_id'],wrong,revisited_after_save=True,restoration=True)['restored']
    assert p['checkpoints'][plan['checkpoint_id']]['journal'] is not None
    assert verify_saved(p,plan['checkpoint_id'],page,revisited_after_save=True,restoration=True)['restored']


def test_blank_proficiency_is_not_inferred_from_an_exam_or_existing_checkbox():
    p,t,page,_=setup(complete=True);del p['facts']['personal.languages.language_0.write']
    plan=build_plan(p,t,page)
    assert not plan['ready']
    assert 'personal.languages.language_0.write' in p['checkpoints'][plan['checkpoint_id']]['source_gate']['missing_fact_ids']


@pytest.mark.parametrize('case',['count_change','duplicate_language','bad_order','bad_boolean','no_proficiency','independence_yes','other_language'])
def test_source_configuration_stops_before_preparation(case):
    p,t,page,_=setup('household' if case=='independence_yes' else 'language')
    if case=='count_change':p['facts']['personal.languages.order']['value'].pop()
    if case=='duplicate_language':p['facts']['personal.languages.language_1.label']['value']='French'
    if case=='bad_order':p['facts']['personal.languages.order']['value']=['language_0',{}]
    if case=='bad_boolean':p['facts']['personal.languages.language_0.speak']['value']='Yes'
    if case=='no_proficiency':
        for part in CONTRACTS[1]['proficiencies']:p['facts']['personal.languages.language_0.'+part['part']]['value']=False
    if case=='independence_yes':p['facts']['family.independence_statuses_apply']['value']=True
    if case=='other_language':p['facts']['personal.languages.language_0.label']['value']='Other'
    assert not build_plan(p,t,page)['ready']


@pytest.mark.parametrize('case',['new_field','pair','cross_question','selector','label','widget','choice','state','both_tags'])
def test_changed_semantics_cannot_authorize_a_page(case):
    p,t,page,_=setup()
    if case=='new_field':page['fields'].append({**page['fields'][1],'key':'i:unknown'})
    if case=='pair':page['common_factual']['rows'][0]['proficiency_id']=page['common_factual']['rows'][1]['proficiency_id']
    if case=='cross_question':page['common_factual']['rows'][0]['proficiency_id']='4000'
    if case=='selector':page['fields'][2]['selector']='input[type="checkbox"]'
    if case=='label':page['fields'][2]['label']='Different question'
    if case=='widget':page['common_factual_native']['controls'][0]['wrapper']='OTHER'
    if case=='choice':del page['choice_observations'][page['fields'][1]['key']]
    if case=='state':page.pop('state_metadata')
    if case=='both_tags':page['common_ielts']={'schema':'common-ielts-page/1'}
    with pytest.raises(ProfileError):build_plan(p,t,page)
    assert not p['checkpoints']


def test_language_reselection_reapplies_only_explicit_abilities_after_each_label():
    p,t,page,_=setup(complete=True);label=page['common_factual']['rows'][0]['language_key']
    plan=build_plan(p,t,page,reaffirm_keys=[label])
    assert plan['ready'],plan['blockers']
    following=plan['writes'][plan['writes'].index(next(w for w in plan['writes'] if w['field_key']==label))+1:]
    assert {w['fact_ref'] for w in following if w['field_key'].startswith('g:4001:')}=={
        'personal.languages.language_0.'+s['part'] for s in CONTRACTS[1]['proficiencies']}


def test_native_radio_reaffirmation_uses_an_existing_enabled_exact_option():
    p,t,page,_=setup('household',complete=True)
    plan=build_plan(p,t,page,reaffirm_keys=['r:ques_3033','r:ques_364','r:ques_366'])
    assert plan['ready'] and len(plan['writes'])==3
    assert not any(w['field_key']=='r:ques_369' for w in plan['writes'])


def test_interrupted_intended_language_update_resumes_without_overwriting_original():
    p,t,page,ctx=setup();plan=build_plan(p,t,page);prepare(p,plan['checkpoint_id'],page,ctx)
    p=json.loads(json.dumps(p));before=copy.deepcopy(p['checkpoints'][plan['checkpoint_id']]['journal'])
    after=filled(page,plan);after['fields'][1]['value']='English'
    remaining=resume(p,plan['checkpoint_id'],after)
    assert remaining['ready'] and p['checkpoints'][plan['checkpoint_id']]['journal']==before
    assert verify_saved(p,plan['checkpoint_id'],filled(after,remaining),revisited_after_save=True)['verified']


def test_restoring_a_language_reapplies_all_original_flags_even_when_only_its_label_differs():
    p,t,page,ctx=setup(complete=True);plan=build_plan(p,t,page)
    ctx['restore_after_test']=True;prepare(p,plan['checkpoint_id'],page,ctx)
    after=copy.deepcopy(page);after['fields'][1]['value']='French'
    recovered=recovery_bundle(p,plan['checkpoint_id'],after)
    assert recovered['writes'][0]['field_key']==page['fields'][1]['key']
    assert {w['field_key'] for w in recovered['writes'][1:]}=={f'g:4001:{s["part"]}' for s in CONTRACTS[1]['proficiencies']}


def test_restart_does_not_bypass_another_active_journal():
    p,t,page,ctx=setup();plan=build_plan(p,t,page);prepare(p,plan['checkpoint_id'],page,ctx)
    p['checkpoints']['checkpoint:another']={'target_id':t,'page_key':'other','state':'needs_restore','journal':{'field':'old'}}
    before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='pending_transaction_requires_recovery'):resume(p,plan['checkpoint_id'],page)
    assert p==before
