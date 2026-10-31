"""Fictional answers against public observed native UC field contracts."""
import copy
import json
from pathlib import Path

import pytest

from bc_application.browser import digest, values, validate_observation
from bc_application.pages import build_plan, prepare, verify_saved
from bc_application.profile import (ProfileError, create_profile, add_statement, add_target,
                                    add_exam, set_fact, set_exam_date, validate_profile)
from bc_application.uc_factual import CONTRACTS, BASE

FIXTURES=Path(__file__).parent/'fixtures'


def setup(kind):
    spec=next(s for s in CONTRACTS if s['kind']==kind)
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(data,'Fictional applicant explicitly supplies all factual answers for these tests.')
    target=add_target(data,system='uc',school='Synthetic UC',program=None,source_id=source)
    eid=add_exam(data,name='IELTS Academic',system='IELTS',score=7,scale='IELTS_0_to_9',date='2025-04-12',source_id=source)
    facts={'personal.citizenship':'China','personal.uc_citizenship_category':'Non-immigrant',
        'personal.has_current_us_visa':True,'personal.current_us_visa':'B2','personal.plans_different_us_visa':True,
        'personal.planned_us_visa':'F1','personal.has_us_ssn_or_itin':False,'education.first_language':'Chinese',
        'education.middle_school.high_school_math':False,'education.middle_school.other_language_courses':False,
        'education.middle_school.outside_us':True,'education.middle_school.instruction_language':'Chinese',
        'education.application_level':'First-year','exams.ielts.completed':'Completed',
        'exams.ielts.score_received':True,'exams.ielts.retake_planned':False,
        **{f'exams.{eid}.{k}':v for k,v in {'listening':7.5,'reading':7,'writing':6,'speaking':7,'report_number':'SYNTHETIC-REPORT'}.items()}}
    for key,value in facts.items():set_fact(data,key,value,source)
    page={'schema':'observed-page/1','url':BASE+spec['path'],'title':spec['title'],'frames_present':False,
        'fields':[],'actions':[{'key':'i:save','label':'Save & continue','selector':'[id="save"]','disabled':False}],
        'uc_factual':{'schema':'uc-factual-page/1','kind':kind}}
    for expected in spec['fields']:
        key=expected['key'];control=expected['control'];options=[]
        if control=='radio':labels=['Completed','Planned'] if key.endswith('.isCompleted') else ['First-year','Transfer'] if kind=='level' else ['Non-immigrant','Other'] if key=='n:citizenshipStatus' else ['Yes','No']
        elif control=='select':labels=['China, Peoples Republic of','B2 - Visitor','F1 - Student','Other language','Chinese','April','2025','6.0','7.0','7.5']
        else:labels=[]
        for i,label in enumerate(labels):
            opt={'label':label,'value':str(i),'disabled':False}
            if control=='radio':opt['selector']=f'[id="synthetic-{key[2:]}-{i}"]'
            options.append(opt)
        page['fields'].append({k:expected[k] for k in ('key','label','group','control','required')}|{
            'name':key[2:],'selector':options[0]['selector'] if control=='radio' else f'[id="{key[2:]}"]',
            'value':False if control=='checkbox' else '0' if options else 'SYNTHETIC-OLD',
            'disabled':False,'readonly':False,'invalid':False,'options':options})
    state=json.loads((FIXTURES/'uc_review_state.json').read_text())
    state['page_url']=page['url'];section=next(s for s in state['sections'] if s['label']==spec['section'])
    section['completion_text']='Section Complete'
    next(p for p in section['pages'] if p['href']==spec['path'])['label']=spec['review_label']
    page['state_metadata']=state
    return data,target,page,spec,eid


@pytest.mark.parametrize('kind',[s['kind'] for s in CONTRACTS])
def test_whole_factual_page_save_revisit_and_durable_original_recovery(kind):
    data,target,page,spec,eid=setup(kind)
    optional=['i:ieltsFormNumber'] if kind=='ielts' else []
    plan=build_plan(data,target,page,optional_keys=optional)
    assert plan['ready'],plan['blockers']
    context={'browser_family':'edge','transport':'extension','origin':BASE,'access_verified':True,
        'real_account_test':True,'full_state_restoration_verified':True,'restoration_strategy':{
            'kind':'restore_uc_factual','page_url':page['url'],'baseline_state_sha256':digest(page['state_metadata']),
            'review_label':spec['review_label'],'section':spec['section']}}
    prepare(data,plan['checkpoint_id'],page,context)
    after=copy.deepcopy(page)
    expected={**values(page),**{w['field_key']:w['value'] for w in plan['writes']}}
    for f in after['fields']:f['value']=expected[f['key']]
    assert verify_saved(data,plan['checkpoint_id'],after,revisited_after_save=True)['verified']
    assert data['checkpoints'][plan['checkpoint_id']]['journal'] is not None
    resumed=json.loads(json.dumps(data))
    assert verify_saved(resumed,plan['checkpoint_id'],page,revisited_after_save=True,restoration=True)['restored']
    assert resumed['checkpoints'][plan['checkpoint_id']]['journal'] is None
    if kind=='background':assert all(w['field_key'].startswith('i:lang_') for w in plan['writes'])
    if kind=='ielts':
        assert expected['i:takenMonth']=='5' and expected['i:takenYear']=='6'
        assert data['facts'][f'exams.{eid}.date']['value']=='2025-04-12'
        assert next(w for w in plan['writes'] if w['field_key']=='i:ieltsOverallScore')['value']=='8'


@pytest.mark.parametrize('case',['new_field','wrong_label','wrong_route','unknown_kind','new_collection','duplicate_selector'])
def test_changed_shape_stops_before_planning(case):
    data,target,page,_,_=setup('grade78')
    if case=='new_field':page['fields'].append({**page['fields'][0],'key':'i:unexpected'})
    elif case=='wrong_label':page['fields'][0]['label']='New question'
    elif case=='wrong_route':page['url']+='Changed'
    elif case=='unknown_kind':page['uc_factual']['kind']='other'
    elif case=='new_collection':page['collections']=[{'kind':'editable_table'}]
    else:page['fields'][0]['selector_count']=2
    with pytest.raises(ProfileError):build_plan(data,target,page)
    assert not data['checkpoints']


def test_missing_retaking_fact_and_ambiguous_exam_both_block_even_if_page_has_answers():
    for case in ('missing','ambiguous'):
        data,target,page,_,eid=setup('ielts')
        if case=='missing':del data['facts']['exams.ielts.retake_planned']
        else:data['exams']['exam:synthetic-other']={**data['exams'][eid],'exam_id':'exam:synthetic-other'}
        assert not build_plan(data,target,page)['ready']


def test_successful_requested_update_discards_temporary_old_values_but_failed_verification_keeps_them():
    data,target,page,_,_=setup('ielts');ctx={'browser_family':'edge','transport':'extension','origin':BASE,'access_verified':True}
    plan=build_plan(data,target,page);prepare(data,plan['checkpoint_id'],page,ctx)
    assert not verify_saved(data,plan['checkpoint_id'],page,revisited_after_save=True)['verified']
    assert data['checkpoints'][plan['checkpoint_id']]['journal']
    expected={**values(page),**{w['field_key']:w['value'] for w in plan['writes']}}
    for f in page['fields']:f['value']=expected[f['key']]
    assert verify_saved(data,plan['checkpoint_id'],page,revisited_after_save=True)['verified']
    assert data['checkpoints'][plan['checkpoint_id']]['journal'] is None
    with pytest.raises(ProfileError,match='rollback_journal_required'):
        verify_saved(data,plan['checkpoint_id'],page,revisited_after_save=True,restoration=True)


@pytest.mark.parametrize('value',['2025-04','2024-02-29'])
def test_exam_date_preserves_original_precision_and_score_scale(value):
    data,_,_,_,eid=setup('ielts');source=add_statement(data,'Synthetic exact date clarification.')
    # A separate fictional exam starts without a date; no hidden migration of the original.
    other=add_exam(data,name='Synthetic AP',system='AP',score=3,scale='AP_1_to_5',source_id=source,date=value)
    assert data['facts'][data['exams'][other]['date_fact_id']]['value']==value
    assert data['facts'][data['exams'][other]['score_fact_id']]['scale']=='AP_1_to_5'
    validate_profile(data)


@pytest.mark.parametrize('value',['2025-02-29','2025-13','2025','04/2025',None])
def test_invalid_exam_date_does_not_change_profile(value):
    data,_,_,_,eid=setup('ielts');before=copy.deepcopy(data)
    with pytest.raises(ProfileError):set_exam_date(data,eid,value,next(iter(data['sources'])))
    assert before==data
