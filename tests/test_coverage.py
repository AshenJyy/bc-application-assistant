"""Coverage is read-only and bounded to actual supplied navigation evidence."""
import copy
import io
import json

import pytest

from bc_application.coverage import inventory
from bc_application.profile import ProfileError
from test_uc_courses import setup


def test_coverage_inventory_does_not_persist_plans_or_copy_applicant_answers():
    p,target,page=setup();before=copy.deepcopy(p)
    result=inventory(p,target,[page],[{'url':page['url'],'label':'Synthetic courses'}])
    assert result['complete'] and result['inspected_page_count']==1 and p==before
    assert all('value' not in field for field in result['pages'][0]['fields'])


def test_uninspected_routes_and_record_dialogs_cannot_pass_as_complete():
    p,target,page=setup();url=page['url'];routes=[{'url':url,'label':'Courses'},
        {'url':'https://apply.universityofcalifornia.edu/my-application/accountFamily','label':'Family'}]
    result=inventory(p,target,[page],routes)
    assert not result['complete'] and result['uninspected_pages']==[routes[-1]]
    native={k:v for k,v in page.items() if k not in {'state_metadata','uc_course_editor','uc_course_parent','uc_academic_auxiliary'}}
    native['fields']=[];native['collections']=[{'kind':'editable_table','label':'Schools','row_count':1,'editor_control_count':1}]
    result=inventory(p,target,[native],[routes[0]])
    assert not result['complete'] and result['pages'][0]['record_collections']
    assert any(b['reason']=='repeatable_record_editors_not_supported' for b in result['pages'][0]['blockers'])


def test_missing_canonical_facts_are_not_satisfied_by_existing_website_answers():
    p,target,page=setup();ref=next(iter(p['facts']));p['facts'].pop(ref)
    result=inventory(p,target,[page],[{'url':page['url'],'label':'Courses'}])
    assert not result['complete'] and ref in result['pages'][0]['missing_fact_ids']


@pytest.mark.parametrize('change',['origin','duplicate_route','duplicate_page','unlisted_page','empty_routes','active_journal'])
def test_invalid_inventory_or_pending_recovery_preserves_profile(change):
    p,target,page=setup();routes=[{'url':page['url'],'label':'Courses'}];pages=[page]
    if change=='origin':routes[0]['url']='https://example.org/untrusted'
    elif change=='duplicate_route':routes.append(copy.deepcopy(routes[0]))
    elif change=='duplicate_page':pages.append(copy.deepcopy(page))
    elif change=='unlisted_page':routes[0]['url']='https://apply.universityofcalifornia.edu/my-application/other'
    elif change=='empty_routes':routes=[]
    else:p['checkpoints']['checkpoint:fake']={'state':'prepared','journal':{},'target_id':target}
    before=copy.deepcopy(p)
    with pytest.raises(ProfileError):inventory(p,target,pages,routes)
    assert p==before


def test_cli_inventory_keeps_canonical_file_byte_identical(tmp_path,monkeypatch,capsys):
    from bc_application.cli import main
    from bc_application.store import ProfileStore,ProfileSnapshot
    p,target,page=setup();path=tmp_path/'applicant.json';ProfileStore(path).save(ProfileSnapshot(p,None));before=path.read_bytes()
    payload={'pages':[page],'routes':[{'url':page['url'],'label':'Synthetic courses'}]}
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(payload)))
    assert main(['coverage-inventory','--profile',str(path),'--target',target])==0
    assert json.loads(capsys.readouterr().out)['complete'] and path.read_bytes()==before


def test_one_rejected_option_set_does_not_hide_other_route_gaps_or_authorize_that_page():
    p,target,page=setup();before=copy.deepcopy(p);bad=copy.deepcopy(page)
    bad['url']='https://apply.universityofcalifornia.edu/my-application/rejected'
    for tag in ('uc_course_editor','uc_course_parent','uc_academic_auxiliary','state_metadata'):bad.pop(tag,None)
    native=next(f for f in bad['fields'] if f['control']=='select')
    native['options'].append(copy.deepcopy(native['options'][0]));native['value']='PRIVATE-ANSWER'
    routes=[{'url':page['url'],'label':'Valid course editor'},{'url':bad['url'],'label':'Rejected observation'},
            {'url':'https://apply.universityofcalifornia.edu/my-application/unseen','label':'Unseen'}]
    result=inventory(p,target,[page,bad],routes)
    assert p==before and not result['complete']
    assert result['captured_page_count']==2 and result['inspected_page_count']==1 and result['rejected_page_count']==1
    rejected=result['pages'][1]
    assert not rejected['observation_valid'] and not rejected['ready_to_prepare'] and not rejected['fields']
    assert rejected['blockers']==[{'reason':'observation_requires_review','details':'ambiguous_observed_options'}]
    assert result['uninspected_pages']==routes[-1:]
    assert 'PRIVATE-ANSWER' not in json.dumps(result)


@pytest.mark.parametrize('path',['bioHousehold','campusMap','campusmajor','apply-scholarships','support-programs'])
def test_uncontracted_uc_summary_or_choice_page_is_not_complete_from_an_empty_or_optional_plan(path):
    p,target,page=setup()
    for tag in ('uc_course_editor','uc_course_parent','uc_academic_auxiliary','state_metadata'):page.pop(tag,None)
    page.update(url='https://apply.universityofcalifornia.edu/my-application/'+path,fields=[])
    result=inventory(p,target,[page],[{'url':page['url'],'label':'Unverified public shape'}])
    assert not result['complete'] and not result['pages'][0]['ready_to_prepare']
    assert any(b['reason']=='observed_uc_page_contract_required' for b in result['pages'][0]['blockers'])


@pytest.mark.parametrize('path',['7/250','4/22','4/197','13/54','2/2','5/30'])
def test_uncontracted_common_pages_do_not_pass_from_optional_or_empty_plans(path):
    from test_common_ielts import setup as common_setup
    p,target,page,_,_=common_setup()
    for tag in ('common_ielts','common_ielts_native','choice_observations','state_metadata'):page.pop(tag,None)
    page.update(url='https://apply.commonapp.org/common/'+path,fields=[{'key':'i:unknown','name':'unknown',
        'label':'Uninspected circumstance choice','group':'','control':'checkbox','selector':'[id="unknown"]',
        'value':False,'required':False,'disabled':False,'readonly':False,'invalid':False,'options':[]}])
    result=inventory(p,target,[page],[{'url':page['url'],'label':'Unverified native branch'}])
    assert not result['complete'] and not result['pages'][0]['ready_to_prepare']
    assert any(b['reason']=='observed_common_app_page_contract_required' for b in result['pages'][0]['blockers'])
