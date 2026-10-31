"""Fictional values; the public contract was observed in the actual Edge portal."""
import copy
import json
from pathlib import Path

import pytest

from bc_application.browser import digest, values, validate_observation
from bc_application.common_ielts import CONTRACT, resume
from bc_application.pages import build_plan, prepare, recovery_bundle, verify_saved
from bc_application.profile import (ProfileError, create_profile, add_statement,
                                    add_target, add_exam, set_fact)


def setup(*, incomplete=True):
    data=create_profile(Path(__file__).parent/'fixtures/synthetic_psr.pdf')
    source=add_statement(data,'Fictional complete IELTS facts, actual sitting count and highest scores explicitly confirmed.')
    target=add_target(data,system='common_app',school='Synthetic college',program=None,source_id=source)
    eid=add_exam(data,name='IELTS Academic',system='IELTS',score=7,scale='IELTS_0_to_9',
                 date='2025-04-12',source_id=source)
    for key,value in {'exams.ielts.taken_count':3,'exams.ielts.retake_planned':False,
            'exams.ielts.highest_scores_confirmed':True,
            **{f'exams.{eid}.{k}':v for k,v in {'listening':7.5,'reading':7,'writing':6,'speaking':7}.items()}}.items():
        set_fact(data,key,value,source)
    page={'schema':'observed-page/1','url':'https://apply.commonapp.org'+CONTRACT['path'],
        'title':CONTRACT['title'],'frames_present':False,'fields':[],
        'actions':[{'key':'i:sectionContinue10','label':'Continue to next section',
                    'selector':'[id="sectionContinue10"]','disabled':False}],
        'common_ielts':{'schema':'common-ielts-page/1','content_sha256':CONTRACT['content_sha256']},
        'common_ielts_native':{'schema':'common-ielts-native/1','heading':'IELTS','controls':[],'auxiliary':[]},
        'choice_observations':{},'state_metadata':{'schema':'observed-state/1',
            'coverage':'common_app_visible_navigation','current_page_key':'tertiaryNavItem2_10',
            'items':[{'key':k,'status':'in progress' if incomplete and k in {'secondaryNavItem2','tertiaryNavItem2_10'} else 'complete'}
                     for k in ['secondaryNavItem2','secondaryNavItem3','tertiaryNavItem2_2','tertiaryNavItem2_6','tertiaryNavItem2_10']]}}
    for spec in CONTRACT['fields']:
        f={k:spec[k] for k in ('key','label','group','control','required')}
        f.update(name=f['key'][2:],selector=f'[id="{f["key"][2:]}"]',disabled=False,readonly=False,
                 invalid=incomplete,value='' if incomplete else '1',options=[])
        if f['control']=='choice_input':
            labels=[str(i) for i in range(6)] if f['key']=='i:text_ques_159' else [format(i/2,'g').removeprefix('0') if i==1 else format(i/2,'g') for i in range(18,-1,-1)]
            page['choice_observations'][f['key']]=[{'value':s,'label':s,'disabled':False} for s in labels]
            page['common_ielts_native']['controls'].append({'key':f['key'],'tag':'INPUT','type':'text',
                'role':'combobox','popup':'listbox','expanded':'false','wrapper':'NG-SELECT'})
            if f['key']=='i:text_ques_159':f.update(value='1',invalid=False)
        elif f['control']=='radio':
            f.update(name='mat-radio-group-0',identity_kind='common_app_question_radio')
            f['options']=[{'value':str(i+15),'label':str(i),'disabled':False,
                           'selector':f'[id="option_ques_160_{i+15}-input"]'} for i in range(4)]
            f['selector']=f['options'][0]['selector']
            if not incomplete:f['value']='15'
        else:
            if not incomplete:f['value']='January 1, 2024'
            page['common_ielts_native']['auxiliary'].append({'kind':'calendar','field_key':f['key']})
        page['fields'].append(f)
    context={'browser_family':'edge','transport':'extension','origin':'https://apply.commonapp.org','access_verified':True}
    return data,target,page,context,eid


def filled(page,plan):
    result=copy.deepcopy(page)
    for w in plan['writes']:next(f for f in result['fields'] if f['key']==w['field_key'])['value']=w['value']
    for f in result['fields']:f['invalid']=False
    for item in result['state_metadata']['items']:
        if item['key'] in {'secondaryNavItem2','tertiaryNavItem2_10'}:item['status']='complete'
    return result


def test_latest_only_never_supplies_actual_sitting_count_even_with_existing_one():
    data,target,page,context,_=setup()
    del data['facts']['exams.ielts.taken_count']
    add_statement(data,'Report only the latest result. All five scores are my highest.')
    plan=build_plan(data,target,page)
    assert not plan['ready']
    assert any(b.get('field_key')=='i:text_ques_159' for b in plan['blockers'])
    with pytest.raises(ProfileError):prepare(data,plan['checkpoint_id'],page,context)
    assert data['checkpoints'][plan['checkpoint_id']]['journal'] is None


@pytest.mark.parametrize('value',[True,0,6,2.0,'2'])
def test_count_requires_explicit_supported_integer(value):
    data,target,page,_,_=setup();data['facts']['exams.ielts.taken_count']['value']=value
    plan=build_plan(data,target,page)
    assert not plan['ready']
    assert any(b['reason']=='explicit_supported_ielts_taken_count_required' for b in plan['blockers'])


@pytest.mark.parametrize('case',['highest_missing','highest_false','retake_missing','retake_true','date_month','ambiguous_exam','missing_component'])
def test_required_source_configuration_is_never_inferred(case):
    data,target,page,_,eid=setup()
    if case=='highest_missing':del data['facts']['exams.ielts.highest_scores_confirmed']
    if case=='highest_false':data['facts']['exams.ielts.highest_scores_confirmed']['value']=False
    if case=='retake_missing':del data['facts']['exams.ielts.retake_planned']
    if case=='retake_true':data['facts']['exams.ielts.retake_planned']['value']=True
    if case=='date_month':data['facts'][f'exams.{eid}.date']['value']='2025-04'
    if case=='ambiguous_exam':data['exams']['exam:other']={**data['exams'][eid],'exam_id':'exam:other'}
    if case=='missing_component':del data['facts'][f'exams.{eid}.speaking']
    assert not build_plan(data,target,page)['ready']


def test_all_twelve_fields_use_current_exam_sources_and_complete_saved_status():
    data,target,page,context,eid=setup();plan=build_plan(data,target,page)
    assert plan['ready'],plan['blockers']
    assert len(plan['writes'])==12
    mapped={w['field_key']:w['value'] for w in plan['writes']}
    assert mapped['i:text_ques_159']=='3' and mapped['r:ques_160']=='15'
    assert mapped['i:text_ques_164']=='7.5' and mapped['i:text_ques_1794']=='7'
    assert {mapped[f['key']] for f in page['fields'] if f['control']=='text'}=={'April 12, 2025'}
    original=copy.deepcopy(page);prepare(data,plan['checkpoint_id'],page,context)
    data=json.loads(json.dumps(data));after=filled(page,plan)
    assert verify_saved(data,plan['checkpoint_id'],after,revisited_after_save=True)['verified']
    cp=data['checkpoints'][plan['checkpoint_id']]
    assert cp['journal'] is None and 'prepared_plan' not in cp
    assert data['facts'][f'exams.{eid}.date']['value']=='2025-04-12'
    assert data['facts'][f'exams.{eid}.score']['scale']=='IELTS_0_to_9'
    assert original==page and len(data['exams'])==1


@pytest.mark.parametrize('case',['new_field','label','control','popup','wrapper','calendar','clear_owner','choices','choice_disabled','save','content','state'])
def test_contract_drift_blocks_before_journal(case):
    data,target,page,_,_=setup()
    if case=='new_field':page['fields'].append({**page['fields'][0],'key':'i:unknown'})
    if case=='label':page['fields'][0]['label']='Different question'
    if case=='control':page['fields'][0]['control']='text'
    if case=='popup':page['common_ielts_native']['controls'][0]['expanded']='true'
    if case=='wrapper':page['common_ielts_native']['controls'][0]['wrapper']='UNKNOWN'
    if case=='calendar':page['common_ielts_native']['auxiliary'].pop()
    if case=='clear_owner':page['common_ielts_native']['auxiliary'].append({'kind':'clear','field_key':'unknown'})
    if case=='choices':page['choice_observations']['i:text_ques_159'].append(page['choice_observations']['i:text_ques_159'][0])
    if case=='choice_disabled':page['choice_observations']['i:text_ques_159'][0]['disabled']='false'
    if case=='save':page['actions'][0]['label']='Submit application'
    if case=='content':page['common_ielts']['content_sha256']='0'*64
    if case=='state':del page['state_metadata']
    with pytest.raises(ProfileError):build_plan(data,target,page)
    assert not data['checkpoints']


@pytest.mark.parametrize('case',['field','status','unrelated_status','not_revisited'])
def test_failed_saved_readback_retains_whole_original(case):
    data,target,page,context,_=setup();plan=build_plan(data,target,page)
    prepare(data,plan['checkpoint_id'],page,context);after=filled(page,plan)
    if case=='field':after['fields'][-1]['value']='April 13, 2025'
    if case=='status':after['state_metadata']['items'][-1]['status']='in progress'
    if case=='unrelated_status':after['state_metadata']['items'][1]['status']='in progress'
    assert not verify_saved(data,plan['checkpoint_id'],after,revisited_after_save=case!='not_revisited')['verified']
    assert data['checkpoints'][plan['checkpoint_id']]['journal']==values(page)


def test_incomplete_original_cancel_is_verified_without_a_blank_draft_save():
    data,target,page,context,_=setup();plan=build_plan(data,target,page)
    prepare(data,plan['checkpoint_id'],page,context)
    restored=json.loads(json.dumps(page))
    assert verify_saved(data,plan['checkpoint_id'],restored,revisited_after_save=True,restoration=True)['restored']
    assert data['checkpoints'][plan['checkpoint_id']]['journal'] is None


def test_original_invalid_flags_and_unchanged_choice_values_are_checked_exactly():
    data,target,page,context,_=setup();plan=build_plan(data,target,page)
    prepare(data,plan['checkpoint_id'],page,context);wrong=copy.deepcopy(page)
    for f in wrong['fields']:f['invalid']=False
    assert not verify_saved(data,plan['checkpoint_id'],wrong,revisited_after_save=True,restoration=True)['restored']
    assert data['checkpoints'][plan['checkpoint_id']]['journal']
    data,target,page,_,_=setup()
    page['fields'][0]['value']='3'
    next(o for o in page['choice_observations']['i:text_ques_159'] if o['value']=='3')['disabled']=True
    assert not build_plan(data,target,page)['ready']


def test_restart_resume_uses_sources_and_preserves_original_journal():
    data,target,page,context,_=setup();plan=build_plan(data,target,page)
    prepare(data,plan['checkpoint_id'],page,context)
    data=json.loads(json.dumps(data));original=copy.deepcopy(data['checkpoints'][plan['checkpoint_id']]['journal'])
    after=filled(page,plan);after['fields'][2]['value']='7'
    again=resume(data,plan['checkpoint_id'],after)
    assert again['ready'] and len(again['writes'])==1
    assert again['writes'][0]['field_key']=='i:text_ques_164'
    assert data['checkpoints'][plan['checkpoint_id']]['journal']==original
    bundle=recovery_bundle(data,plan['checkpoint_id'],after)
    assert bundle['original_invalid_fields'] and bundle['original_values_sha256']==digest(original)
    assert bundle['original_state_metadata']==page['state_metadata']
    assert verify_saved(data,plan['checkpoint_id'],filled(after,again),revisited_after_save=True)['verified']


@pytest.mark.parametrize('case',['unrelated_state','source','shape','test_context'])
def test_resume_rejects_changes_without_replacing_original(case):
    data,target,page,context,_=setup();plan=build_plan(data,target,page)
    prepare(data,plan['checkpoint_id'],page,context)
    original=copy.deepcopy(data['checkpoints'][plan['checkpoint_id']]);after=filled(page,plan)
    if case=='unrelated_state':after['state_metadata']['items'][1]['status']='in progress'
    if case=='source':data['facts']['exams.ielts.taken_count']['value']=4
    if case=='shape':after['actions'].append({'key':'i:unknown','label':'Unknown','selector':'[id="unknown"]','disabled':False})
    if case=='test_context':data['checkpoints'][plan['checkpoint_id']]['context']['real_account_test']=True
    with pytest.raises(ProfileError):resume(data,plan['checkpoint_id'],after)
    assert data['checkpoints'][plan['checkpoint_id']]['journal']==original['journal']


def test_completed_original_recovery_preserves_all_visible_statuses():
    data,target,page,context,_=setup(incomplete=False);plan=build_plan(data,target,page)
    context.update(real_account_test=True,full_state_restoration_verified=True,
        restoration_strategy={'kind':'restore_completed_native_page','current_page_key':'tertiaryNavItem2_10',
                              'baseline_state_sha256':digest(page['state_metadata'])})
    prepare(data,plan['checkpoint_id'],page,context)
    assert verify_saved(data,plan['checkpoint_id'],filled(page,plan),revisited_after_save=True)['verified']
    data=json.loads(json.dumps(data));bundle=recovery_bundle(data,plan['checkpoint_id'],filled(page,plan))
    assert bundle['writes'] and not bundle['original_invalid_fields']
    assert verify_saved(data,plan['checkpoint_id'],page,revisited_after_save=True,restoration=True)['restored']
