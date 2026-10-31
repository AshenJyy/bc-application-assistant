"""Synthetic factual coursework, source gates and persistent recovery."""
import copy
import json
from pathlib import Path

import pytest

from bc_application.adapters.mit import CLASSES_HEADER
from bc_application.browser import digest, permission_gate, validate_observation, values
from bc_application.pages import build_plan, prepare, verify_saved, recovery_bundle
from bc_application.profile import ProfileError, create_profile, add_statement, add_target, set_fact

FIXTURES=Path(__file__).parent/'fixtures'


def setup():
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(data,'Fictional student confirms all synthetic factual answers below.')
    facts={'education.current_school_country':'Canada','education.us_based_school_system':False}
    for s in ('calculus','physics','biology','chemistry'):
        facts.update({f'education.subjects.{s}.status':'taken',f'education.subjects.{s}.year':'11th'})
    for key,value in facts.items():set_fact(data,key,value,source)
    target=add_target(data,system='mit',school='Synthetic MIT',program=None,source_id=source)
    page=json.loads((FIXTURES/'mit_coursework_page.json').read_text(encoding='utf-8'))
    page['collections']=[dict(kind='editable_table',label=CLASSES_HEADER,row_count=0,editor_control_count=1)]
    for f in page['fields']:
        if f['control']=='select':f['value']=next(o['value'] for o in f['options'] if o['label'] in {'Taken','11th'})
    page['state_metadata']={'schema':'observed-state/1','coverage':'mit_visible_review_and_draft',
        'page_url':page['url'],'review_url':'https://apply.mitadmissions.org/apply/review',
        'portal_url':'https://apply.mitadmissions.org/portal/apply','application_status':'In Progress',
        'errors':[{'section':'Essays','message':'Missing essay response(s)',
            'href':'frm?00000000-0000-4000-8000-000000000000'}],'warnings':[]}
    return data,source,target,page


def context(page):
    return {'browser_family':'edge','transport':'extension','origin':'https://apply.mitadmissions.org',
        'access_verified':True,'real_account_test':True,'full_state_restoration_verified':True,
        'restoration_strategy':{'kind':'restore_mit_coursework','page_url':page['url'],
            'baseline_state_sha256':digest(page['state_metadata'])}}


def test_explicit_eight_answers_allow_empty_us_only_table_without_inference():
    data,_,target,page=setup()
    keys=[f['key'] for f in page['fields'] if f['control']=='select']
    plan=build_plan(data,target,page,reaffirm_keys=keys)
    assert plan['ready'],plan['blockers']
    assert len(plan['writes'])==8
    assert all(w['value']==values(page)[w['field_key']] for w in plan['writes'])
    assert plan['collection_policy']['kind']=='mit_non_us_empty_classes'
    cp=data['checkpoints'][plan['checkpoint_id']]
    assert len(cp['required_fact_ids'])==10
    assert len(data['academic']['courses'])>0


@pytest.mark.parametrize('case',['country_missing','us_system_missing','us_system_true','other_country','nonempty',
    'another_table','wrong_header','extra_editor','conflicting_fact','missing_year','unexplained_blank_year'])
def test_narrow_table_exception_and_all_required_facts(case):
    data,source,target,page=setup()
    if case=='country_missing':del data['facts']['education.current_school_country']
    elif case=='us_system_missing':del data['facts']['education.us_based_school_system']
    elif case=='us_system_true':data['facts']['education.us_based_school_system']['value']=True
    elif case=='other_country':data['facts']['education.current_school_country']['value']='United States'
    elif case=='nonempty':page['collections'][0]['row_count']=1
    elif case=='another_table':page['collections'].append(copy.deepcopy(page['collections'][0]))
    elif case=='wrong_header':page['collections'][0]['label']='School Name'
    elif case=='extra_editor':page['collections'][0]['editor_control_count']=2
    elif case=='conflicting_fact':
        newer=add_statement(data,'Fictional contradictory system statement')
        set_fact(data,'education.us_based_school_system',True,newer)
    elif case=='missing_year':del data['facts']['education.subjects.physics.year']
    else:data['facts']['education.subjects.calculus.year']['value']=''
    plan=build_plan(data,target,page)
    assert not plan['ready'],case


@pytest.mark.parametrize('case',['wrong_title','wrong_origin','instruction_drift','missing_subject','swapped_year',
    'duplicate_year','changed_year_options'])
def test_forged_or_stale_semantic_context_stops_before_checkpoint_mutation(case):
    data,_,target,page=setup();page.pop('state_metadata')
    ctx=page['mit_coursework']
    if case=='wrong_title':page['title']='Schools attended'
    elif case=='wrong_origin':page['url']='https://example.invalid/apply/frm'
    elif case=='instruction_drift':ctx['classes_instruction']='Everyone must fill this table'
    elif case=='missing_subject':ctx['subject_year_pairs'].pop()
    elif case=='swapped_year':ctx['subject_year_pairs'][0]['year_key']=ctx['subject_year_pairs'][0]['status_key']
    elif case=='duplicate_year':ctx['subject_year_pairs'][0]['year_key']=ctx['subject_year_pairs'][1]['year_key']
    else:page['fields'][2]['options'][1]['label']='8th'
    before=copy.deepcopy(data)
    with pytest.raises(ProfileError,match='observed_mit_'):build_plan(data,target,page)
    assert data==before


def test_missing_public_association_blocks_the_page_instead_of_ignoring_years():
    data,_,target,page=setup();page.pop('mit_coursework');page.pop('state_metadata')
    plan=build_plan(data,target,page)
    assert not plan['ready']
    assert any(b['reason']=='mit_coursework_semantic_context_required' for b in plan['blockers'])


def test_will_not_take_requires_explicit_reason_for_blank_year():
    data,_,target,page=setup()
    data['facts']['education.subjects.biology.status']['value']='will_not_take'
    assert any(b['reason']=='contradictory_subject_status_and_year' for b in build_plan(data,target,page)['blockers'])
    data['facts']['education.subjects.biology.year']['value']='not_listed_or_not_taken'
    plan=build_plan(data,target,page)
    assert plan['ready']
    pair=next(p for p in page['mit_coursework']['subject_year_pairs'] if p['subject']=='biology')
    assert next(w for w in plan['writes'] if w['field_key']==pair['year_key'])['value']==''


@pytest.mark.parametrize('case',['no_state','boolean_only','different_page','state_hash','coursework_error','submitted'])
def test_real_test_permission_needs_full_review_and_draft_evidence(case):
    _,_,_,page=setup();ctx=context(page)
    if case=='no_state':page.pop('state_metadata')
    elif case=='boolean_only':ctx.pop('restoration_strategy')
    elif case=='different_page':ctx['restoration_strategy']['page_url']+='0'
    elif case=='state_hash':ctx['restoration_strategy']['baseline_state_sha256']='0'*64
    elif case=='coursework_error':
        page['state_metadata']['errors'][0]['section']='Self-reported coursework';ctx=context(page)
    else:page['state_metadata']['application_status']='Submitted';ctx=context(page)
    with pytest.raises(ProfileError):permission_gate(ctx,page,'https://apply.mitadmissions.org')


@pytest.mark.parametrize('case',['unchanged','warning_drift','error_drift','value_drift'])
def test_recovery_survives_restart_and_clears_only_after_whole_state_comparison(case):
    data,_,target,page=setup();plan=build_plan(data,target,page)
    cpid=plan['checkpoint_id'];prepare(data,cpid,page,context(page))
    # A serialized restart retains one complete original-value journal.
    restored=json.loads(json.dumps(data));after=copy.deepcopy(page)
    if case=='warning_drift':after['state_metadata']['warnings']=copy.deepcopy(after['state_metadata']['errors'])
    elif case=='error_drift':after['state_metadata']['errors'][0]['message']='Changed missing response'
    elif case=='value_drift':after['fields'][2]['value']=''
    bundle=recovery_bundle(restored,cpid,after)
    assert bundle['plan']['checkpoint_id']==cpid
    assert bundle['context']['journal_persisted']
    verified=verify_saved(restored,cpid,after,revisited_after_save=True,restoration=True)
    assert verified['restored']==(case=='unchanged')
    assert (restored['checkpoints'][cpid]['journal'] is None)==(case=='unchanged')


def test_status_collections_are_validated_as_actual_section_routes():
    _,_,_,page=setup()
    page['state_metadata']['errors'][0]['href']='https://example.invalid/collect'
    with pytest.raises(ProfileError,match='observed_mit_state_invalid'):validate_observation(page)
