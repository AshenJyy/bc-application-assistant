import copy
import json
from pathlib import Path

import pytest

from bc_application.adapters import get_adapter
from bc_application.pages import build_plan
from bc_application.profile import add_statement,add_target,create_profile,set_fact

FIXTURES=Path(__file__).parent/'fixtures'


@pytest.fixture
def applicant():
    profile=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(profile,'Invented applicant explicitly confirms each synthetic fact below.')
    facts={'personal.legal_given_name':'Synthetic','personal.legal_family_name':'Applicant',
        'personal.preferred_family_name':'Applicant','personal.birth_date':'2007-03-05',
        'personal.has_lived_name':False,'personal.has_previous_legal_name':False,
        'personal.has_materials_under_former_legal_name':False,
        'education.attended_california_public_school':False,'personal.birth_country':'Canada',
        'personal.birth_city':'Victoria','personal.birth_region':'British Columbia','personal.citizenship':'Canada',
        'personal.legal_sex':'X','personal.communication_name_choice':'First name',
        'contact.email':'student@example.invalid','contact.mobile':'+1 555 010 1234',
        'address.permanent.country':'China','address.permanent.street':'123 Synthetic Street',
        'address.permanent.city':'Synthetic City','address.permanent.region':'Jiangsu Sheng',
        'address.permanent.postal_code':'000000'}
    for key,value in facts.items(): set_fact(profile,key,value,source)
    targets={system:add_target(profile,system=system,school=f'Synthetic {system}',program=None,source_id=source)
             for system in ('uc','mit','common_app')}
    return profile,source,targets


def test_former_name_history_and_former_name_materials_are_distinct(applicant):
    profile,_,targets=applicant
    uc={'key':'n:otherNames','name':'otherNames','label':'Have you ever had a different legal name?','control':'radio'}
    common={'key':'n:former','name':'former','label':'Do you have any materials under a former legal name?',
        'group':'Do you have any materials under a former legal name?','control':'radio'}
    assert get_adapter('uc').binding(uc,profile['targets'][targets['uc']],profile)=='personal.has_previous_legal_name'
    assert get_adapter('common_app').binding(common,profile['targets'][targets['common_app']],profile)=='personal.has_materials_under_former_legal_name'


def test_student_identity_is_not_automatically_reused_for_family_questions(applicant):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    page['url']='https://apply.commonapp.org/common/5/42'
    page['actions']=[{'key':'i:sectionContinue42','label':'Continue to next section','selector':'[id="sectionContinue42"]','disabled':False}]
    plan=build_plan(profile,targets['common_app'],page)
    assert not plan['ready'] and not plan['writes']
    assert any(b.get('reason')=='unmapped_required_factual_field' for b in plan['blockers'])


@pytest.mark.parametrize('system,fixture', [('uc','uc_personal_page.json'),('mit','mit_personal_page.json'),('common_app','common_app_personal_page.json')])
def test_three_observed_personal_pages_share_one_name_and_birthdate(applicant,system,fixture):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/fixture).read_text(encoding='utf-8'))
    plan=build_plan(profile,targets[system],page)
    if system=='mit':
        # The captured MIT page marks a preferred surname optional while its
        # native control is required. Shared bindings still resolve, but this
        # real-site contradiction must prevent every write/save.
        assert not plan['ready']
        assert [b['reason'] for b in plan['blockers']]==['conflicting_required_signals']
    else:
        assert plan['ready'],plan['blockers']
    refs={w['fact_ref'] for w in plan['writes']}
    assert 'personal.legal_given_name' in refs and 'personal.legal_family_name' in refs
    assert 'personal.birth_date' in refs
    assert not any(f'personal.birth_{part}' in profile['facts'] for part in ('month','day','year'))
    assert len(profile['targets'])==3


def test_shared_date_is_losslessly_formatted_per_observed_controls(applicant):
    profile,_,targets=applicant
    results={}
    for system,fixture in [('uc','uc_personal_page.json'),('mit','mit_personal_page.json'),('common_app','common_app_personal_page.json')]:
        page=json.loads((FIXTURES/fixture).read_text(encoding='utf-8'))
        plan=build_plan(profile,targets[system],page)
        results[system]=[w['value'] for w in plan['writes'] if w['fact_ref']=='personal.birth_date']
    # UC rebuilds date children, so day is written after both month and year.
    assert results=={'uc':['03','2007','05'],'mit':['03','05','2007'],'common_app':['March 5, 2007']}
    assert profile['facts']['personal.birth_date']['value']=='2007-03-05'


def test_mit_permanent_and_mailing_addresses_have_distinct_visible_contexts(applicant):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'mit_personal_page.json').read_text(encoding='utf-8'))
    plan=build_plan(profile,targets['mit'],page)
    assert next(w for w in plan['writes'] if w['fact_ref']=='address.permanent.street')['value']=='123 Synthetic Street'
    assert not any(w['fact_ref'].startswith('address.mailing.') for w in plan['writes'])
    assert get_adapter('mit').save_action(page)['label']=='Save and Continue'


@pytest.mark.parametrize('system', ['mit','common_app'])
def test_narrative_textarea_and_certification_remain_blocked(applicant,system):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/f'{system}_personal_page.json').read_text(encoding='utf-8'))
    field=copy.deepcopy(page['fields'][0]); field.update(key='i:essay',selector='[id="essay"]',label='Describe a challenge you faced',control='textarea',required=True)
    page['fields'].append(field)
    assert not build_plan(profile,targets[system],page)['ready']
    page['fields'].pop(); page['title']='Certification'
    assert not build_plan(profile,targets[system],page)['ready']


@pytest.mark.parametrize('path', ['/mycolleges/123/questions','/common/6/55','/submit','/account/register'])
def test_common_app_supplements_writing_submission_and_registration_excluded(applicant,path):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    page['url']='https://apply.commonapp.org'+path
    plan=build_plan(profile,targets['common_app'],page)
    assert not plan['ready'] and plan['save_action'] is None


def test_common_continue_must_match_current_section_id(applicant):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    action=next(a for a in page['actions'] if a['key']=='i:sectionContinue11')
    action['key']='i:sectionContinue99'
    assert not build_plan(profile,targets['common_app'],page)['ready']


def test_optional_custom_suffix_is_untouched_until_explicit_choice(applicant):
    profile,source,targets=applicant
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    suffix=next(f for f in page['fields'] if f['label']=='Suffix')
    set_fact(profile,'personal.suffix','Jr.',source)
    assert build_plan(profile,targets['common_app'],page)['ready']
    assert not build_plan(profile,targets['common_app'],page,optional_keys=[suffix['key']])['ready']


def test_unknown_birthdate_is_not_reconstructed_from_browser_or_grades(applicant):
    profile,_,targets=applicant
    del profile['facts']['personal.birth_date']
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    # A filled website field does not become a source of confirmed applicant facts.
    next(f for f in page['fields'] if f['label']=='Date of birth')['value']='March 5, 2007'
    assert not build_plan(profile,targets['common_app'],page)['ready']


def test_invalid_date_errors_never_echo_personal_input(applicant):
    profile,source,targets=applicant
    profile['facts']['personal.birth_date']['value']='PRIVATE-INVALID-INPUT'
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    blockers=build_plan(profile,targets['common_app'],page)['blockers']
    assert 'PRIVATE-INVALID-INPUT' not in json.dumps(blockers)
    assert 'explicit_iso_birth_date_required' in json.dumps(blockers)


def test_conflicting_legacy_date_parts_cannot_be_silently_overridden(applicant):
    profile,source,targets=applicant
    set_fact(profile,'personal.birth_month','December',source)
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    plan=build_plan(profile,targets['common_app'],page)
    assert not plan['ready'] and 'contradictory_birth_date_facts' in json.dumps(plan['blockers'])


@pytest.mark.parametrize('label', ['I have reported all of my courses for this grade',
    'I confirm this information is accurate', 'I affirm all answers', 'I acknowledge the declaration'])
def test_course_completion_attestations_block_even_optional_explicit_bindings(applicant,label):
    from bc_application.profile import bind_fact
    profile,source,targets=applicant
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    page['url']='https://apply.commonapp.org/common/13/55'
    page['actions']=[{'key':'i:sectionContinue55','label':'Continue to next section','selector':'[id="sectionContinue55"]','disabled':False}]
    field={'key':'i:completion','name':'completion','label':label,'group':'','control':'checkbox',
        'selector':'[id="completion"]','required':False,'disabled':False,'readonly':False,'value':False,'options':[],'invalid':False}
    page['fields']=[field]
    set_fact(profile,'education.course_completion',True,source)
    bind_fact(profile,targets['common_app'],field['key'],'education.course_completion')
    plan=build_plan(profile,targets['common_app'],page,optional_keys=[field['key']])
    assert not plan['ready'] and not plan['writes']
    assert plan['blockers'][-1]['details']['manual_fields_remaining']==[field['key']]


def test_observed_mit_coursework_page_requires_explicit_answers_without_inferring_from_psr(applicant):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'mit_coursework_page.json').read_text(encoding='utf-8'))
    plan=build_plan(profile,targets['mit'],page)
    assert not plan['ready'] and not plan['writes']
    assert len([f for f in page['fields'] if f['required']])==4
    gate=plan['blockers'][-1]['details']
    assert gate['manual_fields_remaining']==[]
    assert set(gate['missing_fact_ids'])=={f'education.subjects.{s}.{part}' for s in ('calculus','physics','biology','chemistry') for part in ('status','year')}


def coursework_answers(applicant):
    profile,source,targets=applicant
    answers={'calculus':'taken','physics':'in_progress_or_planned','biology':'will_not_take','chemistry':'taken'}
    for subject,value in answers.items():
        set_fact(profile,f'education.subjects.{subject}.status',value,source)
        set_fact(profile,f'education.subjects.{subject}.year','not_listed_or_not_taken' if value=='will_not_take' else '11th',source)
    return profile,targets,json.loads((FIXTURES/'mit_coursework_page.json').read_text(encoding='utf-8'))


def test_explicit_subject_answers_and_years_use_actual_options_without_filling_notes(applicant):
    profile,targets,page=coursework_answers(applicant)
    plan=build_plan(profile,targets['mit'],page)
    assert plan['ready'],plan['blockers']
    assert len(plan['writes'])==7
    for write in plan['writes']:
        field=next(f for f in page['fields'] if f['key']==write['field_key'])
        assert field['control']=='select'
        assert write['value'] in {o['value'] for o in field['options'] if o['value']}
    assert all(f['value']=='' for f in page['fields'] if f['control']=='textarea')
    assert profile['facts']['education.subjects.biology.year']['value']=='not_listed_or_not_taken'


@pytest.mark.parametrize('case', ['nonempty','required','selected','unknown','other_page','invalid'])
def test_optional_coursework_note_exception_is_strictly_limited(applicant,case):
    profile,targets,page=coursework_answers(applicant)
    field=page['fields'][0]; optional=None
    if case=='nonempty': field['value']='Existing private narrative'
    elif case=='required': field['required']=True
    elif case=='selected': optional=[field['key']]
    elif case=='unknown': field['label']='Additional statement'
    elif case=='other_page':
        page['title']='Personal information';page.pop('mit_coursework')
    elif case=='invalid': field['invalid']=True
    plan=build_plan(profile,targets['mit'],page,optional_keys=optional)
    assert not plan['ready']
    assert field['key'] in plan['blockers'][-1]['details']['manual_fields_remaining']
    assert not any(w['field_key']==field['key'] for w in plan['writes'])


@pytest.mark.parametrize('status', ['Taken','completed',True,7])
def test_subject_status_needs_explicit_canonical_meaning(applicant,status):
    profile,source,targets=applicant
    page=json.loads((FIXTURES/'mit_coursework_page.json').read_text(encoding='utf-8'))
    for subject in ('physics','biology','chemistry'):
        set_fact(profile,f'education.subjects.{subject}.status','taken',source)
    set_fact(profile,'education.subjects.calculus.status',status,source)
    plan=build_plan(profile,targets['mit'],page)
    assert not plan['ready']
    assert any(b.get('reason')=='explicit_subject_coursework_status_required' for b in plan['blockers'])


@pytest.mark.parametrize('system', ['uc','mit','common_app'])
@pytest.mark.parametrize('label', ['I understand the declaration','I have read the terms','I agree',
    'Consent to release records',"I've finished adding high schools"])
def test_attestations_and_consent_always_require_the_applicant(applicant,system,label):
    profile,_,targets=applicant
    page=json.loads((FIXTURES/f'{system}_personal_page.json').read_text(encoding='utf-8'))
    field=copy.deepcopy(page['fields'][0]); field.update(key='i:consent',selector='[id="consent"]',
        label=label,control='checkbox',value=False,required=False,options=[])
    page['fields'].append(field)
    plan=build_plan(profile,targets[system],page)
    assert not plan['ready'] and not any(w['field_key']=='i:consent' for w in plan['writes'])


@pytest.mark.parametrize('identity', [{'selector_count':3,'selector_index':3},
    {'selector_count':3,'selector_index':-1}, {'selector_count':3,'selector_index':True}])
def test_invalid_repeated_control_identity_stops_before_checkpoint_mutation(applicant,identity):
    from bc_application.profile import ProfileError
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    page['fields'][0].update(identity)
    before=copy.deepcopy(profile)
    with pytest.raises(ProfileError,match='observed_selector_identity_invalid'):
        build_plan(profile,targets['common_app'],page)
    assert profile==before


def test_repeated_native_grade_controls_keep_distinct_original_course_percentages(applicant):
    from bc_application.profile import bind_record_column
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'native_repeated_grade_page.json').read_text(encoding='utf-8'))
    for index,code in enumerate(('MTEST10---','MSPLT10---','MWRAP11---')):
        record=next(c for c in profile['academic']['courses'] if c['raw_cells']['course_code']==code)
        bind_record_column(profile,targets['common_app'],f'i:repeatedGrade@{index}',record['record_id'],'school_percent',page_path='/common/13/55')
    plan=build_plan(profile,targets['common_app'],page)
    assert plan['ready'],plan['blockers']
    assert [w['value'] for w in plan['writes']]==['84','78','92']
    assert len({w['fact_ref'] for w in plan['writes']})==3
    assert len(profile['checkpoints'][plan['checkpoint_id']]['required_course_ids'])==3
    assert [f['selector_index'] for f in page['fields']]==[0,1,2]


def test_distinct_field_keys_cannot_bind_the_same_selector_position(applicant):
    from bc_application.profile import ProfileError
    profile,_,targets=applicant
    page=json.loads((FIXTURES/'native_repeated_grade_page.json').read_text(encoding='utf-8'))
    page['fields'][1]['selector_index']=0
    with pytest.raises(ProfileError,match='ambiguous_observed_controls'):
        build_plan(profile,targets['common_app'],page)
