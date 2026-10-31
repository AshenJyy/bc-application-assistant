"""School-term preflight only; no browser input or applicant journal creation."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bc_application.profile import ProfileError,create_profile,add_statement,add_target,set_fact
from bc_application.browser import digest
from bc_application.uc_term_setup import (preview_term_availability,school_form_blockers,
    prepare_term_test,verify_term_test,recover_term_test,annotated_school)

FIXTURES=Path(__file__).parent/'fixtures'


def setup():
    page=json.loads((FIXTURES/'uc_school_terms_page.json').read_text())
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(data,'Fictional student confirms all APs Full year and retains other UC choices.')
    target=add_target(data,system='uc',school='Synthetic UC',program=None,source_id=source)
    set_fact(data,'education.uc_ap_reporting_term','Full year',source)
    set_fact(data,'education.uc_other_settings_retained',True,source)
    return data,target,page


def test_unused_attendance_slots_are_not_invented_missing_school_years():
    data,target,page=setup();before=copy.deepcopy(data)
    assert len(page['fields'])==59 and school_form_blockers(page)==[]
    result=preview_term_availability(data,target,page)
    assert result['data_ready'],result['blockers']
    assert result['proposed_writes']==[{'field_key':'i:onefinal','value':True,'fact_ref':'education.uc_ap_reporting_term'}]
    assert result['automatic_execution_available'] is False
    assert result['schema']!='page-plan/1' and 'ready' not in result
    assert data==before and not data['checkpoints']


@pytest.mark.parametrize('change',['half_pair','summer_without_grade','no_attendance','empty_date','unknown_field',
    'required_essay','declaration','term_label','duplicate_term_selector','wrong_school_route','no_save','special_curriculum'])
def test_unknown_requirements_or_changed_shapes_block_before_any_execution(change):
    data,target,p=setup();fields={f['key']:f for f in p['fields']}
    if change=='half_pair':fields['i:attendsyear1']['value']=''
    elif change=='summer_without_grade':fields['i:attendsummer3']['value']=True
    elif change=='no_attendance':
        for key,f in fields.items():
            if key.startswith(('i:attendgrade','i:attendsyear')):f['value']=''
    elif change=='empty_date':fields['i:startYear']['value']=''
    elif change=='unknown_field':p['fields'].append({**p['fields'][0],'key':'i:unknown','selector':'[id="unknown"]'})
    elif change=='required_essay':fields['i:hsDegreeSelect']['control']='textarea'
    elif change=='declaration':fields['i:specialCurr-ib']['label']='I certify this application is correct'
    elif change=='term_label':fields['i:onefinal']['label']='I agree to a year of tuition payments'
    elif change=='duplicate_term_selector':fields['i:onefinal']['selector_count']=2
    elif change=='wrong_school_route':p['url']=p['url'].replace('action=edit','action=add')
    elif change=='no_save':p['actions']=p['actions'][1:]
    else:fields['i:specialCurr-ib']['value']=True
    assert not preview_term_availability(data,target,p)['data_ready']
    assert not data['checkpoints']


@pytest.mark.parametrize('missing',['education.uc_ap_reporting_term','education.uc_other_settings_retained'])
def test_populated_website_does_not_replace_student_term_or_retention_confirmation(missing):
    data,target,page=setup();del data['facts'][missing]
    assert not preview_term_availability(data,target,page)['data_ready']


def test_existing_recovery_cannot_be_bypassed_by_a_term_preview():
    data,target,page=setup();data['checkpoints']['test']={'state':'prepared','target_id':target,'journal':{}}
    with pytest.raises(ProfileError,match='pending_transaction_requires_recovery'):
        preview_term_availability(data,target,page)


def test_already_available_full_year_does_not_generate_a_new_toggle():
    data,target,page=setup();next(f for f in page['fields'] if f['key']=='i:onefinal')['value']=True
    result=preview_term_availability(data,target,page)
    assert result['data_ready'] and result['proposed_writes']==[]


def test_cli_preview_is_read_only_and_never_creates_a_second_applicant_file(tmp_path):
    from bc_application.store import ProfileStore,ProfileSnapshot
    data,target,page=setup();path=tmp_path/'applicant.json'
    ProfileStore(path).save(ProfileSnapshot(data,None));original=path.read_bytes()
    runner=FIXTURES.parents[1]/'skills/bc-application/scripts/run.py'
    result=subprocess.run([sys.executable,'-B',str(runner),'uc-term-preview','--profile',str(path),'--target',target],
        input=json.dumps({'page':page}),capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['data_ready'] and not json.loads(result.stdout)['automatic_execution_available']
    assert path.read_bytes()==original and list(tmp_path.glob('*.json'))==[path]


def bundle_for(school):
    fixture=json.loads((FIXTURES/'uc_courses_page.json').read_text())
    state=json.loads((FIXTURES/'uc_review_state.json').read_text());state['page_url']=school['url']
    bundle={'schema':'uc-school-term-bundle/1','school_identity_sha256':'a'*64,
        'school':copy.deepcopy(school),'state_metadata':state,'courses':[],
        'auxiliary':copy.deepcopy(fixture['uc_academic_auxiliary'])}
    base='https://apply.universityofcalifornia.edu'
    for grade in ['09','10','11','12']:
        page={k:v for k,v in copy.deepcopy(fixture).items() if not k.startswith('uc_')}
        page['url']=base+'/my-application/acadHistFrHighSchoolClasses/editClasses/'+grade+'/123456'
        context=copy.deepcopy(fixture['uc_course_editor']);context['grade']=grade
        context['summary_url']=base+'/my-application/acadHistFrGrades/'+grade
        parent=copy.deepcopy(fixture['uc_course_parent']);parent['url']=context['summary_url']
        bundle['courses'].append({'page':page,'summary':{'context':context,'parent':parent,'rows_sha256':'b'*64}})
    return bundle


def school_context(bundle):
    return {'browser_family':'edge','transport':'extension','origin':'https://apply.universityofcalifornia.edu',
        'access_verified':True,'real_account_test':True,'full_state_restoration_verified':True,
        'restoration_strategy':{'kind':'restore_uc_school_terms','page_url':bundle['school']['url'],
            'baseline_state_sha256':digest(bundle['state_metadata']),'baseline_related_sha256':digest(bundle['courses'])}}


def enabled_school(bundle):
    result=copy.deepcopy(bundle)
    next(f for f in result['school']['fields'] if f['key']=='i:onefinal')['value']=True
    return result


def test_school_and_all_four_course_journals_survive_restart_in_the_same_canonical_file(tmp_path):
    from bc_application.store import ProfileStore,ProfileSnapshot
    from bc_application.pages import verify_saved,build_plan
    data,target,school=setup();bundle=bundle_for(school)
    plan=prepare_term_test(data,target,bundle,school_context(bundle));cpid=plan['checkpoint_id']
    assert len(data['checkpoints'][cpid]['journal'])==59
    assert len(data['checkpoints'][cpid]['related_journal'])==4
    store=ProfileStore(tmp_path/'applicant.json');store.save(ProfileSnapshot(data,None));snapshot=store.load()
    after=enabled_school(bundle)
    # A hypothetical newly exposed native term selector is read-only discovery,
    # not a claimed UC selector and never an item in this plan's writes.
    extra=copy.deepcopy(after['courses'][2]['page']['fields'][0])
    extra.update(key='i:synthetic_new_term',selector='[id="synthetic_new_term"]',label='Synthetic term availability')
    after['courses'][2]['page']['fields'].append(extra)
    assert verify_term_test(snapshot.data,cpid,after,revisited_after_save=True)['verified']
    assert snapshot.data['checkpoints'][cpid]['journal'] is not None
    with pytest.raises(ProfileError,match='dedicated_verification'):
        verify_saved(snapshot.data,cpid,annotated_school(bundle),revisited_after_save=True,restoration=True)
    with pytest.raises(ProfileError,match='pending_transaction'):
        build_plan(snapshot.data,target,annotated_school(bundle))
    recovery=recover_term_test(snapshot.data,cpid,after)
    assert recovery['writes']==[{'field_key':'i:onefinal','value':False}]
    assert verify_term_test(snapshot.data,cpid,bundle,revisited_after_save=True,restoration=True)['restored']
    assert snapshot.data['checkpoints'][cpid]['journal'] is None
    assert 'related_journal' not in snapshot.data['checkpoints'][cpid]
    store.save(snapshot);assert list(tmp_path.glob('*.json'))==[tmp_path/'applicant.json']


@pytest.mark.parametrize('change',['only_three_courses','wrong_course','state_hash','related_hash','boolean_only',
    'nonreal_context','incomplete_academic','incomplete_comments','missing_retention','semester_choice'])
def test_school_term_test_needs_complete_sources_and_all_original_recovery_evidence(change):
    data,target,school=setup();bundle=bundle_for(school);ctx=school_context(bundle)
    if change=='only_three_courses':bundle['courses'].pop()
    elif change=='wrong_course':bundle['courses'][2]['page']['url']='https://example.invalid/course'
    elif change=='state_hash':ctx['restoration_strategy']['baseline_state_sha256']='0'*64
    elif change=='related_hash':ctx['restoration_strategy']['baseline_related_sha256']='0'*64
    elif change=='boolean_only':ctx.pop('restoration_strategy')
    elif change=='nonreal_context':ctx['real_account_test']=False
    elif change=='incomplete_academic':
        next(s for s in bundle['state_metadata']['sections'] if s['label']=='Academic history')['completion_text']='';ctx=school_context(bundle)
    elif change=='incomplete_comments':
        next(i for s in bundle['state_metadata']['sections'] for i in s['pages'] if i['href'].endswith('acadHistAddInformation'))['label']='To do Additional information';ctx=school_context(bundle)
    elif change=='missing_retention':data['facts'].pop('education.uc_other_settings_retained')
    else:data['facts']['education.uc_ap_reporting_term']['value']='Semester'
    with pytest.raises(ProfileError):prepare_term_test(data,target,bundle,ctx)
    assert not data['checkpoints']


@pytest.mark.parametrize('change',['course_value','course_rows','school_value','status','auxiliary','summary'])
def test_original_school_course_and_status_drift_never_clears_recovery(change):
    data,target,school=setup();bundle=bundle_for(school)
    plan=prepare_term_test(data,target,bundle,school_context(bundle));cpid=plan['checkpoint_id'];after=copy.deepcopy(bundle)
    if change=='course_value':after['courses'][1]['page']['fields'][1]['value']='Unrestored fictional course'
    elif change=='course_rows':after['courses'][1]['summary']['rows_sha256']='c'*64
    elif change=='school_value':next(f for f in after['school']['fields'] if f['key']=='i:onefinal')['value']=True
    elif change=='status':after['state_metadata']['sections'][-1]['pages'][0]['label']='Edit Introduction'
    elif change=='auxiliary':after['auxiliary']['structure_sha256']='d'*64
    else:after['courses'][2]['summary']['parent']['summary_sha256']='e'*64
    assert not verify_term_test(data,cpid,after,revisited_after_save=True,restoration=True)['restored']
    assert data['checkpoints'][cpid]['journal'] is not None and data['checkpoints'][cpid]['related_journal']


def test_cli_school_journal_preparation_verification_and_recovery_use_one_profile(tmp_path):
    from bc_application.store import ProfileStore,ProfileSnapshot
    data,target,school=setup();bundle=bundle_for(school);path=tmp_path/'applicant.json'
    ProfileStore(path).save(ProfileSnapshot(data,None));runner=FIXTURES.parents[1]/'skills/bc-application/scripts/run.py'
    def run(command,payload,*args):
        result=subprocess.run([sys.executable,'-B',str(runner),command,'--profile',str(path),*args],
            input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stdout+result.stderr
        return json.loads(result.stdout)
    plan=run('uc-term-prepare',{'bundle':bundle,'context':school_context(bundle)},'--target',target)
    before_warning_kit=path.read_bytes()
    warning_kit=run('uc-term-recover',{'post_warning_cancel':True},'--checkpoint',plan['checkpoint_id'])
    assert warning_kit['post_warning_cancel'] and warning_kit['requires_fresh_ui_identity_verification']
    assert warning_kit['plan']==plan and path.read_bytes()==before_warning_kit
    after=enabled_school(bundle);checkpoint=plan['checkpoint_id']
    assert run('uc-term-verify',{'bundle':after,'revisited_after_save':True},'--checkpoint',checkpoint)['verified']
    before_recovery=path.read_bytes()
    recovery=run('uc-term-recover',{'bundle':after},'--checkpoint',checkpoint)
    assert recovery['writes']==[{'field_key':'i:onefinal','value':False}] and path.read_bytes()==before_recovery
    assert run('uc-term-verify',{'bundle':bundle,'revisited_after_save':True},'--checkpoint',checkpoint,'--restoration')['restored']
    assert list(tmp_path.glob('*.json'))==[path]
