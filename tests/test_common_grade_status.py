"""Explicit grade-12 official-mark answer; no inference from missing PSR results."""
import copy

import pytest

from test_common_factual import setup,filled
from bc_application.pages import build_plan,prepare,verify_saved
from bc_application.profile import ProfileError,add_statement,set_fact
from bc_application.common_pages import resume

FACT='education.common_app.grade12.has_official_grades'


def scenario(answer=False):
    p,t,page,ctx=setup('grade12_status')
    set_fact(p,FACT,answer,add_statement(p,'Fictional student explicitly confirms whether official grade-12 marks are available.'))
    return p,t,page,ctx


def test_blank_to_confirmed_no_verifies_saved_page_and_keeps_original_psr():
    p,t,page,ctx=scenario();original=copy.deepcopy(p['academic']);plan=build_plan(p,t,page)
    assert plan['ready'] and plan['writes'][0]['value']=='1' and plan['writes'][0]['fact_ref']==FACT
    prepare(p,plan['checkpoint_id'],page,ctx)
    assert verify_saved(p,plan['checkpoint_id'],filled(page,plan),revisited_after_save=True)['verified']
    assert p['academic']==original and p['checkpoints'][plan['checkpoint_id']]['journal'] is None


def test_current_no_is_not_a_fact_or_inferred_from_psr_blank_marks():
    p,t,page,ctx=setup('grade12_status');page['fields'][0]['value']='1';page['fields'][0]['invalid']=False
    plan=build_plan(p,t,page)
    assert not plan['ready'] and FACT in p['checkpoints'][plan['checkpoint_id']]['source_gate']['missing_fact_ids']
    assert FACT not in p['facts']


@pytest.mark.parametrize('answer',[True,'No',0,None])
def test_only_explicit_boolean_false_uses_the_no_branch(answer):
    if answer is None:
        with pytest.raises(ProfileError,match='explicit_nonempty_fact'):scenario(answer)
        return
    p,t,page,ctx=scenario(answer);assert not build_plan(p,t,page)['ready']


def test_observed_yes_never_switches_to_no_and_risks_erasing_grade_records():
    p,t,page,ctx=scenario();page['fields'][0]['value']='0'
    with pytest.raises(ProfileError,match='grade12_official_grade_layout'):build_plan(p,t,page)


def test_grade_status_restart_retains_journal_and_other_navigation_states():
    p,t,page,ctx=scenario();plan=build_plan(p,t,page);key=plan['checkpoint_id'];prepare(p,key,page,ctx)
    journal=copy.deepcopy(p['checkpoints'][key]['journal']);updated=filled(page,plan)
    assert resume(p,key,updated)['ready'] and p['checkpoints'][key]['journal']==journal
    changed=copy.deepcopy(updated);changed['state_metadata']['items'][-1]['status']='complete'
    assert not verify_saved(p,key,changed,revisited_after_save=True)['verified']
    assert p['checkpoints'][key]['journal']==journal
