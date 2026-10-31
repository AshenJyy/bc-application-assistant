"""Joined academic source gates, shared target pages and canonical persistence."""
import copy
import io
import json

import pytest

from test_common_schools import scenario as school_scenario,page as school_page
from test_common_academic import scenario as academic_scenario
from bc_application import common_schools,workflow
from bc_application.profile import ProfileError,add_statement,add_target,set_fact
from bc_application.store import ProfileStore,ProfileSnapshot


def scenario():
    p,t,ref,ctx=school_scenario(early=True)
    other=school_scenario('other')[0]['facts']['education.school_reports.other']
    p['facts']['education.school_reports.other']=other
    academic,_,_=academic_scenario();p['sources'].update(academic['sources']);p['facts'].update(academic['facts'])
    steps=[{'target_id':t,'kind':kind,'report_ref':ref,'page_url':ctx['origin']+path} for kind,ref,path in (
        ('common_school','education.school_reports.current','/common/4/18'),
        ('common_school','education.school_reports.other','/common/4/19'),
        ('common_academic','education.reporting.grade_9','/common/13/55'))]
    routes=[{'url':s['page_url'],'label':label} for s,label in zip(steps,['Current school','Other schools','9th Grade'])]
    return p,t,steps,routes,ctx


def test_school_and_course_workflow_has_one_source_set_and_orders_dependencies():
    p,t,steps,routes,ctx=scenario();raw=copy.deepcopy(p);result=workflow.agenda(p,list(reversed(steps)),routes)
    assert result['ready'] and not result['questions'] and not result['directory_discovery']
    assert [j['page_url'] for j in result['jobs']]==[s['page_url'] for s in steps]
    assert not result['full_application_complete'] and not result['website_actions_performed'] and p==raw


def test_shared_physical_common_app_pages_are_not_duplicated_for_another_university():
    p,t,steps,routes,ctx=scenario();source=add_statement(p,'Fictional student selects another university.')
    other=add_target(p,system='common_app',school='Second fictional university',program=None,source_id=source)
    extra=[{**s,'target_id':other} for s in steps];result=workflow.agenda(p,steps+extra,routes)
    assert result['ready'] and len(result['jobs'])==3
    assert all(j['target_ids']==[t,other] for j in result['jobs']) and not result['questions']


def test_missing_shared_fact_is_collected_once_and_one_answer_clears_every_use():
    p,t,steps,routes,ctx=scenario()
    for report in ('education.school_reports.current','education.school_reports.other'):
        p['facts'][report]['value']['current_school_ref']='education.shared_current_school'
    result=workflow.agenda(p,steps,routes);question=result['questions']
    assert len(question)==1 and question[0]['fact_id']=='education.shared_current_school' and len(question[0]['job_ids'])==2
    set_fact(p,'education.shared_current_school','99990002',add_statement(p,'The fictional current school is Secondary 2.'))
    assert workflow.agenda(p,steps,routes)['ready']


def test_missing_report_is_implementation_work_and_never_a_student_json_question():
    p,t,steps,routes,ctx=scenario();del p['facts']['education.reporting.grade_9']
    result=workflow.agenda(p,steps,routes)
    assert not result['ready'] and not result['questions']
    assert any(g['reason']=='source_reference_report_needs_implementation' for g in result['implementation_gaps'])


def test_directory_discovery_is_deduplicated_source_work_not_a_personal_question():
    p,t,steps,routes,ctx=scenario();p.pop('school_directory');result=workflow.agenda(p,steps,routes)
    assert result['ready'] and not result['questions']
    assert {r['psr_school_id'] for r in result['directory_discovery']}=={'99990001','99990002'}


@pytest.mark.parametrize('change',['missing_route','foreign_origin','query','kind','report_kind','duplicate_report','missing_school_dependency','school_name','missing_psr','different_origin'])
def test_invalid_routes_reports_and_sources_never_become_a_runnable_workflow(change,tmp_path):
    p,t,steps,routes,ctx=scenario()
    if change=='missing_route':routes.pop()
    if change=='foreign_origin':routes[0]['url']=steps[0]['page_url']='https://example.org/common/4/18'
    if change=='query':routes[0]['url']=steps[0]['page_url']=steps[0]['page_url']+'?submit=true'
    if change=='kind':steps[0]['kind']='essay'
    if change=='report_kind':steps[0]['report_ref']='education.school_reports.other'
    if change=='duplicate_report':steps.append({**steps[0],'report_ref':'education.other_report'})
    if change=='missing_school_dependency':steps=steps[2:]
    if change=='school_name':p['facts']['education.reporting.t1.school_name']['value']='A different fictional school'
    if change=='missing_psr':p['sources'][p['psr_source_id']]['path']=str(tmp_path/'missing.pdf')
    if change=='different_origin':routes[0]['url']=steps[0]['page_url']=steps[0]['page_url'].replace('127.0.0.1','localhost')
    before=copy.deepcopy(p)
    try:assert not workflow.agenda(p,steps,routes)['ready']
    except ProfileError:pass
    assert p==before


def test_active_page_requires_recovery_before_other_pages_or_new_questions():
    p,t,steps,routes,ctx=scenario();first=common_schools.prepare(p,t,steps[0]['report_ref'],school_page(),ctx)
    del p['facts']['education.boarding'];result=workflow.agenda(p,steps,routes)
    assert result['inspection_deferred'] and not result['questions'] and not result['ready']
    assert result['recovery_required'][0]['checkpoint_id']==first['checkpoint_id']
    assert result['recovery_required'][0]['job_id']==result['jobs'][0]['job_id']


def test_source_fingerprint_survives_checkpoint_events_but_changes_with_answers():
    p,t,steps,routes,ctx=scenario();before=workflow.agenda(p,steps,routes)['source_set_sha256']
    p['revision']+=1;p['events'].append({'kind':'fictional_event'})
    assert workflow.agenda(p,steps,routes)['source_set_sha256']==before
    p['facts']['education.graduation_date']['value']='2027-02'
    assert workflow.agenda(p,steps,routes)['source_set_sha256']!=before


def test_cli_workflow_preview_leaves_the_single_profile_byte_identical(tmp_path,monkeypatch,capsys):
    from bc_application.cli import main
    p,t,steps,routes,ctx=scenario();path=tmp_path/'applicant.json';ProfileStore(path).save(ProfileSnapshot(p,None));before=path.read_bytes()
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps({'steps':steps,'routes':routes})))
    assert main(['workflow-preview','--profile',str(path)])==0
    assert json.loads(capsys.readouterr().out)['ready'] and path.read_bytes()==before
    assert len(list(tmp_path.glob('*.json')))==1
