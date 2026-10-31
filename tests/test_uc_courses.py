"""Fictional UC course-page planning, term boundaries and restart restoration."""
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from bc_application.browser import digest, structure, values, validate_observation, permission_gate
from bc_application.pages import build_plan, prepare, verify_saved, recovery_bundle
from bc_application.profile import ProfileError, create_profile, add_statement, add_target, set_fact, bind_fact

FIXTURES=Path(__file__).parent/'fixtures'


def setup():
    p=json.loads((FIXTURES/'uc_courses_page.json').read_text())
    state=json.loads((FIXTURES/'uc_review_state.json').read_text())
    state['page_url']=p['url'];p['state_metadata']=state
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(data,'Fictional student explicitly retains these synthetic UC choices and marks.')
    target=add_target(data,system='uc',school='Synthetic UC',program=None,source_id=source)
    for i,f in enumerate(p['fields']):
        ref=f'education.uc_test.value_{i}'
        set_fact(data,ref,f['value'],source)
        bind_fact(data,target,f['key'],ref,page_path=urlsplit(p['url']).path)
    return data,target,p


def context(p):
    return {'browser_family':'edge','transport':'extension','origin':'https://apply.universityofcalifornia.edu',
        'access_verified':True,'real_account_test':True,'full_state_restoration_verified':True,
        'restoration_strategy':{'kind':'restore_uc_courses','page_url':p['url'],
            'baseline_state_sha256':digest(p['state_metadata']),'baseline_parent_sha256':digest(p['uc_course_parent'])}}


def test_whole_native_course_page_has_explicit_scoped_choices_and_original_values():
    data,target,p=setup();validate_observation(p);permission_gate(context(p),p,context(p)['origin'])
    plan=build_plan(data,target,p,reaffirm_keys=[p['fields'][-1]['key']])
    assert plan['ready'],plan['blockers']
    assert len(plan['writes'])==1 and plan['writes'][0]['value']=='Z'
    assert values(p)['i:academics_hs_classes_add_0_grade1Other']=='EXT'


def test_reused_native_row_ids_never_fall_back_to_global_or_another_grade():
    data,target,p=setup()
    bindings=data['targets'][target].pop('page_field_bindings')
    data['targets'][target]['field_bindings']=next(iter(bindings.values()))
    assert not build_plan(data,target,p)['ready']


@pytest.mark.parametrize('change',['unknown','wrong_label','ambiguous','missing_grade','new_row','wrong_school',
    'wrong_grade','wrong_columns','wrong_parent','frame','wrong_term','essay','missing_auxiliary','nonempty_auxiliary'])
def test_unobserved_or_changed_course_shapes_fail_closed(change):
    _,_,p=setup()
    if change=='unknown':p['fields'][0]['key']='i:unknown'
    elif change=='wrong_label':p['fields'][0]['label']='Choose your preferred major'
    elif change=='ambiguous':p['fields'][0]['selector_count']=2
    elif change=='missing_grade':p['fields'].pop()
    elif change=='new_row':p['uc_course_editor']['row_count']=3
    elif change=='wrong_school':p['url']=p['url'].replace('123456','other')
    elif change=='wrong_grade':p['uc_course_editor']['grade']='10'
    elif change=='wrong_columns':p['uc_course_editor']['columns'].remove('GRDG System')
    elif change=='wrong_parent':p['uc_course_parent']['row_count']=4
    elif change=='frame':p['frames_present']=True
    elif change=='wrong_term':p['uc_course_editor']['row_terms'][0]='Quarter'
    elif change=='missing_auxiliary':p.pop('uc_academic_auxiliary')
    elif change=='nonempty_auxiliary':p['uc_academic_auxiliary']['values_sha256']=digest({'i:additional_comments':'Synthetic existing text'})
    else:p['fields'][1]['control']='textarea'
    with pytest.raises(ProfileError):validate_observation(p)


def test_missing_confirmation_blocks_even_when_current_answer_is_populated():
    data,target,p=setup();key=p['fields'][0]['key']
    del data['targets'][target]['page_field_bindings'][urlsplit(p['url']).path][key]
    assert any(b.get('field_key')==key for b in build_plan(data,target,p)['blockers'])


def test_course_reclassification_requires_another_workflow_before_a_ready_plan():
    data,target,p=setup();key=p['fields'][0]['key']
    ref=data['targets'][target]['page_field_bindings'][urlsplit(p['url']).path][key]
    data['facts'][ref]['value']='Physics'
    plan=build_plan(data,target,p)
    assert not plan['ready']
    assert any(b['reason']=='uc_course_reconfiguration_requires_workflow' for b in plan['blockers'])


def test_explicit_yearly_ap_choice_blocks_existing_semester_ap_configuration():
    data,target,p=setup();source=add_statement(data,'All fictional AP courses are Full year for UC.')
    set_fact(data,'education.uc_ap_reporting_term','Full year',source)
    next(f for f in p['fields'] if f['key'].endswith('_0_honors'))['value']='AP'
    plan=build_plan(data,target,p)
    assert not plan['ready']
    assert any(b['reason']=='uc_ap_yearly_school_and_course_setup_required' for b in plan['blockers'])


def test_existing_mixed_term_controls_are_readable_but_changes_require_staged_refill():
    data,target,p=setup();source=add_statement(data,'Fictional AP Full and other Semester reporting choices.')
    set_fact(data,'education.uc_ap_reporting_term','Full year',source)
    p['fields']=[f for f in p['fields'] if f['key']!='i:academics_hs_classes_add_1_grade2']
    p['uc_course_editor']['row_terms'][1]='Full year'
    for i in range(2):
        f=copy.deepcopy(p['fields'][0]);f.update(key=f'i:academics_hs_classes_add_{i}_term',label='Term System',
            name=f'term{i}',selector=f'[id="academics_hs_classes_add_{i}_term"]',value='F' if i else 'S',
            options=[{'value':v,'label':label,'disabled':False} for v,label in [('','--'),('F','Full'),('S','Semester')]])
        p['fields'].append(f);ref=f'education.mixed.term{i}';set_fact(data,ref,'Full' if i else 'Semester',source)
        bind_fact(data,target,f['key'],ref,page_path=urlsplit(p['url']).path)
    plan=build_plan(data,target,p);assert plan['ready'],plan['blockers']
    p['fields'][-1]['value']='S'
    with pytest.raises(ProfileError,match='course_terms'):validate_observation(p)


@pytest.mark.parametrize('change',['none','summary','value','other_status','school_context'])
def test_restart_recovery_clears_journal_only_after_original_summary_values_and_statuses_match(change):
    data,target,p=setup();plan=build_plan(data,target,p);cpid=plan['checkpoint_id']
    prepare(data,cpid,p,context(p));data=json.loads(json.dumps(data));after=copy.deepcopy(p)
    if change=='summary':after['uc_course_parent']['summary_sha256']='c'*64
    elif change=='value':after['fields'][1]['value']='Not restored'
    elif change=='other_status':after['state_metadata']['sections'][-1]['pages'][0]['label']='Edit Introduction'
    elif change=='school_context':
        after['uc_course_editor']['context_sha256']='d'*64;after['uc_course_parent']['context_sha256']='d'*64
    if change=='school_context':
        with pytest.raises(ProfileError,match='restoration_structure_changed'):recovery_bundle(data,cpid,after)
    else:
        bundle=recovery_bundle(data,cpid,after)
        assert bundle['plan']['uc_course_parent']==p['uc_course_parent']
    result=verify_saved(data,cpid,after,revisited_after_save=True,restoration=True)
    assert result['restored']==(change=='none')
    assert (data['checkpoints'][cpid]['journal'] is None)==(change=='none')


def test_normal_saved_summary_may_reflect_factual_name_change_but_restoration_must_match_original():
    data,target,p=setup();key=p['fields'][1]['key'];ref=data['targets'][target]['page_field_bindings'][urlsplit(p['url']).path][key]
    data['facts'][ref]['value']='Synthetic corrected course'
    plan=build_plan(data,target,p);cpid=plan['checkpoint_id'];prepare(data,cpid,p,context(p))
    after=copy.deepcopy(p);after['fields'][1]['value']='Synthetic corrected course'
    after['uc_course_parent']['summary_sha256']='f'*64
    assert verify_saved(data,cpid,after,revisited_after_save=True)['verified']
    assert data['checkpoints'][cpid]['journal'] is not None
    assert not verify_saved(data,cpid,after,revisited_after_save=True,restoration=True)['restored']


@pytest.mark.parametrize('change',['no_parent_hash','incomplete_grade','incomplete_academic','wrong_strategy'])
def test_real_course_test_needs_complete_page_and_exact_parent_evidence(change):
    _,_,p=setup();ctx=context(p)
    if change=='no_parent_hash':ctx['restoration_strategy'].pop('baseline_parent_sha256')
    elif change=='incomplete_grade':
        next(i for s in p['state_metadata']['sections'] for i in s['pages'] if i['href'].endswith('/09'))['label']='To do 9th grade'
        ctx=context(p)
    elif change=='incomplete_academic':
        next(s for s in p['state_metadata']['sections'] if s['label']=='Academic history')['completion_text']='';ctx=context(p)
    else:ctx['restoration_strategy']['kind']='restore_uc_personal'
    with pytest.raises(ProfileError):permission_gate(ctx,p,ctx['origin'])
