"""Synthetic UC factual-page requirements and visible-state recovery."""
import copy
import json
from pathlib import Path

import pytest

from bc_application.browser import digest, permission_gate, validate_observation, values
from bc_application.pages import build_plan, prepare, verify_saved, recovery_bundle
from bc_application.profile import ProfileError, create_profile, add_statement, add_target, set_fact

FIXTURES=Path(__file__).parent/'fixtures'


def setup():
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(data,'Fictional student supplies every synthetic UC factual answer below.')
    facts={'personal.legal_given_name':'Synthetic','personal.legal_family_name':'Applicant',
        'personal.has_lived_name':False,'personal.has_previous_legal_name':False,
        'education.attended_california_public_school':False,'personal.birth_date':'2007-03-05',
        'personal.birth_country':'China','personal.birth_city':'Synthetic City'}
    for k,v in facts.items():set_fact(data,k,v,source)
    target=add_target(data,system='uc',school='Synthetic UC',program=None,source_id=source)
    page=json.loads((FIXTURES/'uc_personal_page.json').read_text(encoding='utf-8'))
    page['title']='Personal information - About you - UC application'
    for f in page['fields']:
        f['invalid']=False
        if f['name']=='firstName':f['value']='SYNTHETIC'
        if f['name']=='lastName':f['value']='APPLICANT'
    page['state_metadata']=json.loads((FIXTURES/'uc_review_state.json').read_text(encoding='utf-8'))
    return data,target,page


def context(page):
    return {'browser_family':'edge','transport':'extension','origin':'https://apply.universityofcalifornia.edu',
        'access_verified':True,'real_account_test':True,'full_state_restoration_verified':True,
        'restoration_strategy':{'kind':'restore_uc_personal','page_url':page['url'],
            'baseline_state_sha256':digest(page['state_metadata'])}}


def test_uc_plan_preserves_shared_country_and_formats_only_exact_portal_label():
    data,target,page=setup();plan=build_plan(data,target,page)
    assert plan['ready'],plan['blockers']
    country=next(f for f in page['fields'] if f['name']=='birthCountryCode')
    written=next(w for w in plan['writes'] if w['field_key']==country['key'])
    assert country['options'][next(i for i,o in enumerate(country['options']) if o['value']==written['value'])]['label']=='China, Peoples Republic of'
    assert data['facts']['personal.birth_country']['value']=='China'
    assert all(not w['fact_ref'].startswith('psr:') for w in plan['writes'])


@pytest.mark.parametrize('missing',['personal.has_lived_name','personal.has_previous_legal_name',
    'education.attended_california_public_school'])
def test_current_website_no_or_no_old_name_materials_does_not_supply_personal_history(missing):
    data,target,page=setup();del data['facts'][missing]
    data['facts']['personal.has_materials_under_former_legal_name']=copy.deepcopy(data['facts']['personal.has_lived_name' if missing!='personal.has_lived_name' else 'personal.has_previous_legal_name'])
    for f in page['fields']:
        if f['control']=='radio':f['value']=next(o['value'] for o in f['options'] if o['label']=='No')
    plan=build_plan(data,target,page)
    assert not plan['ready']
    assert missing in next(b['details']['missing_fact_ids'] for b in plan['blockers'] if b['reason']=='page_data_gate_failed')


@pytest.mark.parametrize('case',['missing_section','duplicate_route','external_route','wrong_term','submitted',
    'no_state','boolean_only','wrong_hash','current_incomplete','section_incomplete','other_page'])
def test_uc_test_needs_complete_current_page_and_valid_visible_review_draft_evidence(case):
    _,_,page=setup();ctx=context(page);state=page['state_metadata']
    if case=='missing_section':state['sections'].pop()
    elif case=='duplicate_route':state['sections'][0]['pages'].append(copy.deepcopy(state['sections'][0]['pages'][0]))
    elif case=='external_route':state['sections'][0]['pages'][0]['href']='https://example.invalid/submit'
    elif case=='wrong_term':state['term']='Fall quarter/semester 2028'
    elif case=='submitted':state['draft_marker']='Submitted application'
    elif case=='no_state':page.pop('state_metadata')
    elif case=='boolean_only':ctx.pop('restoration_strategy')
    elif case=='wrong_hash':ctx['restoration_strategy']['baseline_state_sha256']='0'*64
    elif case=='current_incomplete':state['sections'][0]['pages'][0]['label']='To do Personal information'
    elif case=='section_incomplete':state['sections'][0]['completion_text']=''
    else:page['url']=page['url'].replace('accountPersonal','applicationAddress')
    if case not in {'boolean_only','wrong_hash','no_state'}:ctx=context(page)
    with pytest.raises(ProfileError):permission_gate(ctx,page,'https://apply.universityofcalifornia.edu')


@pytest.mark.parametrize('case',['unchanged','other_page_status','section_status','draft_status','one_value'])
def test_uc_recovery_journal_survives_restart_until_every_original_value_and_status_matches(case):
    data,target,page=setup();plan=build_plan(data,target,page);cpid=plan['checkpoint_id']
    prepare(data,cpid,page,context(page));data=json.loads(json.dumps(data));after=copy.deepcopy(page)
    if case=='other_page_status':after['state_metadata']['sections'][-1]['pages'][0]['label']='Edit Introduction'
    elif case=='section_status':after['state_metadata']['sections'][-1]['completion_text']='Section Complete'
    elif case=='draft_status':
        after['state_metadata']['draft_marker']='Submitted application'
        with pytest.raises(ProfileError,match='observed_uc_state_invalid'):verify_saved(data,cpid,after,revisited_after_save=True,restoration=True)
        assert data['checkpoints'][cpid]['journal'] is not None
        return
    elif case=='one_value':after['fields'][0]['value']='Unrestored'
    bundle=recovery_bundle(data,cpid,after)
    assert bundle['plan']['system']=='uc' and bundle['context']['journal_persisted']
    result=verify_saved(data,cpid,after,revisited_after_save=True,restoration=True)
    assert result['restored']==(case=='unchanged')
    assert (data['checkpoints'][cpid]['journal'] is None)==(case=='unchanged')


def test_uc_review_fixture_has_only_public_status_labels_and_all_32_unique_routes():
    _,_,page=setup();validate_observation(page)
    routes=[i['href'] for s in page['state_metadata']['sections'] for i in s['pages']]
    assert len(routes)==len(set(routes))==32


def test_country_and_date_parent_changes_reapply_only_resolved_children_after_parents():
    data,target,page=setup()
    # Put every value at the explicit desired value first, so reapplication
    # cannot depend on a current difference in the child control.
    first=build_plan(data,target,page)
    expected={**values(page),**{w['field_key']:w['value'] for w in first['writes']}}
    for field in page['fields']:field['value']=expected[field['key']]
    parents=[f['key'] for f in page['fields'] if f['name'] in {'birthCountryCode','birthDateMM','birthDateYYYY'}]
    plan=build_plan(data,target,page,reaffirm_keys=parents)
    assert plan['ready'],plan['blockers']
    by_name={f['name']:f['key'] for f in page['fields']}
    keys=[w['field_key'] for w in plan['writes']]
    assert len(keys)==5
    assert keys.index(by_name['birthCountryCode'])<keys.index(by_name['birthCity'])
    assert max(keys.index(by_name[name]) for name in ('birthDateMM','birthDateYYYY'))<keys.index(by_name['birthDateDD'])
    assert next(w for w in plan['writes'] if w['field_key']==by_name['birthCity'])['fact_ref']=='personal.birth_city'


def test_clearing_birth_city_by_country_cannot_be_repaired_from_current_website_without_fact():
    data,target,page=setup();del data['facts']['personal.birth_city']
    plan=build_plan(data,target,page)
    assert not plan['ready']
    assert any(b['reason']=='dependent_factual_value_required' for b in plan['blockers'])
    assert not any(w['field_key']==next(f['key'] for f in page['fields'] if f['name']=='birthCity') for w in plan['writes'])
