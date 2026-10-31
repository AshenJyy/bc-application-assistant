"""Collection questions are shared facts, never guesses from existing answers."""
import copy
import io
import json
from pathlib import Path

import pytest

from bc_application.intake import agenda
from bc_application.profile import ProfileError,add_statement,set_fact,bind_record_column
from bc_application.pages import build_plan,prepare
from test_adapters import applicant
from test_common_factual import setup as factual_setup,filled

FIXTURES=Path(__file__).parent/'fixtures'


def requests(applicant):
    p,_,targets=applicant;result=[]
    for system in ('uc','mit','common_app'):
        page=json.loads((FIXTURES/f'{system}_personal_page.json').read_text(encoding='utf-8'))
        for f in page['fields']:f['invalid']=False
        result.append({'target_id':targets[system],'pages':[page],'routes':[{'url':page['url'],'label':'Personal Information'}]})
    return result


def request(target,page):
    return [{'target_id':target,'pages':[page],'routes':[{'url':page['url'],'label':'Fictional current page'}]}]


def test_one_missing_name_is_asked_once_across_three_targets_and_known_facts_are_omitted(applicant):
    p,_,_=applicant;incoming=requests(applicant);del p['facts']['personal.legal_given_name'];before=copy.deepcopy(p)
    report=agenda(p,incoming)
    assert p==before and report['profile_changed'] is False
    question=next(q for q in report['questions'] if q['fact_id']=='personal.legal_given_name')
    assert len([q for q in report['questions'] if q['fact_id']=='personal.legal_given_name'])==1
    assert {u['system'] for u in question['uses']}=={'uc','mit','common_app'}
    assert 'personal.legal_family_name' in report['known_fact_ids']
    assert not any(q['fact_id']=='personal.legal_family_name' for q in report['questions'])
    assert report['required_uses_count']>report['required_fact_count']
    assert all('value' not in q for q in report['questions'])


def test_one_explicit_answer_removes_the_question_from_all_targets(applicant):
    p,source,_=applicant;incoming=requests(applicant);del p['facts']['personal.legal_given_name']
    assert any(q['fact_id']=='personal.legal_given_name' for q in agenda(p,incoming)['questions'])
    set_fact(p,'personal.legal_given_name','New fictional student',source)
    report=agenda(p,incoming)
    assert not any(q['fact_id']=='personal.legal_given_name' for q in report['questions'])
    assert 'personal.legal_given_name' in report['known_fact_ids']


def test_conflicting_existing_fact_is_one_resolution_question_and_not_a_reusable_answer(applicant):
    p,_,_=applicant;other=add_statement(p,'A conflicting fictional spelling.')
    set_fact(p,'personal.legal_given_name','Different',other)
    report=agenda(p,requests(applicant));q=next(q for q in report['questions'] if q['fact_id']=='personal.legal_given_name')
    assert q['reason']=='conflict' and len(q['uses'])==3
    assert 'personal.legal_given_name' not in report['known_fact_ids']
    assert all('Different' not in json.dumps(q) for q in report['questions'])


def test_unmapped_required_family_fields_are_implementation_gaps_not_guessed_student_questions(applicant):
    p,_,targets=applicant;item=requests(applicant)[-1];page=item['pages'][0]
    page['url']='https://apply.commonapp.org/common/5/42';item['routes'][0]['url']=page['url']
    report=agenda(p,[item])
    assert not report['questions'] and report['implementation_gaps']
    assert not report['complete'] and not report['ready_pages']


def test_known_answers_with_a_missing_psr_need_source_review_not_repeat_questions(applicant,tmp_path):
    p,_,_=applicant;p['sources'][p['psr_source_id']]['path']=str(tmp_path/'missing.pdf')
    report=agenda(p,requests(applicant))
    assert not report['questions'] and report['source_reviews']
    assert not report['ready_pages'] and not report['already_matching_pages']


def test_unclear_original_grade_stays_an_academic_review_without_fabricated_grade_question(applicant):
    p,_,targets=applicant;course=next(c for c in p['academic']['courses'] if c['raw_cells']['equivalency_marker'])
    bind_record_column(p,targets['uc'],'i:grade',course['record_id'],'school_percent')
    page={'schema':'observed-page/1','url':'https://apply.universityofcalifornia.edu/my-application/accountPersonal',
        'title':'Synthetic original grade','frames_present':False,'fields':[{'key':'i:grade','label':'Grade','group':'',
        'control':'text','required':True,'selector':'[id="grade"]','disabled':False,'readonly':False,'invalid':False,
        'value':course['raw_cells']['school_percent'],'options':[]}],
        'actions':[{'key':'i:save','label':'Save & continue','selector':'[id="save"]','disabled':False}]}
    report=agenda(p,request(targets['uc'],page))
    assert report['academic_reviews'] and not report['questions']


def test_uninspected_navigation_and_manual_narrative_remain_explicit(applicant):
    p,_,_=applicant;item=requests(applicant)[-1];page=item['pages'][0]
    page['fields'].append({'key':'i:story','label':'Describe your circumstances','group':'','control':'textarea',
        'required':True,'selector':'[id="story"]','value':'Existing fictional narrative','options':[],
        'invalid':False,'disabled':False,'readonly':False})
    item['routes'].append({'url':'https://apply.commonapp.org/common/5/26','label':'Uninspected household'})
    report=agenda(p,[item])
    assert report['manual_pages'] and report['uninspected_pages'] and not report['complete']
    assert not report['questions']
    assert 'Existing fictional narrative' not in json.dumps(report)


def test_matching_completed_page_is_skipped_but_incomplete_page_remains_in_queue():
    p,t,page,_=factual_setup();plan=build_plan(p,t,page);page=filled(page,plan)
    report=agenda(p,request(t,page))
    assert not report['questions'] and len(report['already_matching_pages'])==1 and not report['ready_pages']
    page['state_metadata']['items'][1]['status']='in progress';page['state_metadata']['items'][0]['status']='in progress'
    report=agenda(p,request(t,page))
    assert not report['already_matching_pages'] and len(report['ready_pages'])==1
    assert report['ready_pages'][0]['planned_write_count']==0


def test_matching_local_values_cannot_be_claimed_saved_without_an_independent_revisit():
    p,t,page,_=factual_setup();page=filled(page,build_plan(p,t,page))
    report=agenda(p,request(t,page))
    assert report['complete'] and report['already_matching_pages']
    assert report['already_matching_pages'][0]['saved_revisit_required'] is True
    assert report['execution_verified'] is False and report['website_actions_performed'] is False


def test_active_recovery_is_reported_before_any_more_collection_or_planning():
    p,t,page,ctx=factual_setup();plan=build_plan(p,t,page);prepare(p,plan['checkpoint_id'],page,ctx);before=copy.deepcopy(p)
    report=agenda(p,request(t,page))
    assert report['recovery_required'][0]['checkpoint_id']==plan['checkpoint_id']
    assert report['inspection_deferred'] and not report['questions'] and p==before


def test_agenda_is_bound_to_profile_and_observations_and_contains_no_answer_copy(applicant):
    p,_,_=applicant;incoming=requests(applicant);first=agenda(p,incoming);same=agenda(p,incoming)
    assert first==same and first['profile_revision']==p['revision']
    p['facts']['personal.birth_city']['value']='Fictional second city';second=agenda(p,incoming)
    assert first['profile_sha256']!=second['profile_sha256']
    assert 'Fictional second city' not in json.dumps(second)
    incoming[0]['pages'][0]['fields'][0]['value']='Fictional changed browser value'
    assert agenda(p,incoming)['observation_set_sha256']!=second['observation_set_sha256']


def test_cli_agenda_keeps_the_single_canonical_file_byte_identical(tmp_path,monkeypatch,capsys):
    from bc_application.cli import main
    from bc_application.store import ProfileStore,ProfileSnapshot
    p,t,page,_=factual_setup();path=tmp_path/'applicant.json';ProfileStore(path).save(ProfileSnapshot(p,None));before=path.read_bytes()
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps({'requests':request(t,page)})))
    assert main(['collection-agenda','--profile',str(path)])==0
    assert json.loads(capsys.readouterr().out)['schema']=='collection-agenda/1'
    assert path.read_bytes()==before and len(list(tmp_path.glob('*.json')))==1


@pytest.mark.parametrize('case',['empty','too_many','duplicate_target','invalid_page','invalid_shape','unlisted_target'])
def test_invalid_collection_inputs_do_not_change_profile(applicant,case):
    p,_,_=applicant;items=requests(applicant);before=copy.deepcopy(p)
    if case=='empty':items=[]
    if case=='too_many':items=items*9
    if case=='duplicate_target':items.append(items[0])
    if case=='invalid_page':items[0]['pages']=[1]
    if case=='invalid_shape':items[0]['extra']='unsupported'
    if case=='unlisted_target':items[0]['target_id']='target:missing'
    with pytest.raises(ProfileError):agenda(p,items)
    assert p==before
