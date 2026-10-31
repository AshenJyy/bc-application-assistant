import copy
import json
from pathlib import Path

import pytest

from bc_application.browser import digest, structure, values, validate_observation, permission_gate
from bc_application.pages import build_plan, execute, prepare, verify_saved, restoration_writes
from bc_application.profile import (ProfileError, add_statement, add_target, bind_fact,
    bind_record_column, create_profile, set_fact)
from bc_application.store import ProfileStore, ProfileSnapshot

FIXTURES=Path(__file__).parent/'fixtures'


def text_field(key='i:firstname', name='firstName', label='First/Given name *', value='Before'):
    return {'key':key,'name':name,'label':label,'group':'What is your name?', 'control':'text',
            'selector':f'[id="{key[2:]}"]','required':True,'disabled':False,'readonly':False,
            'value':value,'options':[],'invalid':False}


def page(fields=None):
    return {'schema':'observed-page/1','url':'http://127.0.0.1:8765/uc','title':'Synthetic UC',
            'frames_present':False,'fields':fields or [text_field()],
            'actions':[{'key':'i:save','label':'Save&continue','selector':'[id="save"]','disabled':False}]}


@pytest.fixture
def prepared(tmp_path):
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    source=add_statement(data,'Invented student confirms their name and selects a UC test target.')
    set_fact(data,'personal.legal_given_name','Synthetic',source)
    target=add_target(data,system='uc',school='Invented UC target',program=None,source_id=source)
    store=ProfileStore(tmp_path/'applicant.json')
    snapshot=ProfileSnapshot(data,None)
    store.save(snapshot)
    return snapshot,store,target


CONTEXT={'browser_family':'edge','transport':'extension','origin':'http://127.0.0.1:8765',
         'access_verified':True,'synthetic_test':True}


def completed_state():
    return {'schema':'observed-state/1','coverage':'common_app_visible_navigation',
        'current_page_key':'tertiaryNavItem3_11','items':[{'key':'secondaryNavItem3','status':'complete'},
            {'key':'tertiaryNavItem3_11','status':'complete'},{'key':'secondaryNavItem2','status':'in progress'}]}


def real_context(p):
    return {**CONTEXT,'real_account_test':True,'full_state_restoration_verified':True,
        'restoration_strategy':{'kind':'restore_completed_native_page',
            'current_page_key':p['state_metadata']['current_page_key'],
            'baseline_state_sha256':digest(p['state_metadata'])}}


def common_radio_page():
    p=json.loads((FIXTURES/'common_app_personal_page.json').read_text(encoding='utf-8'))
    p['url']='https://apply.commonapp.org/common/3/11'
    for field in p['fields']:
        field['invalid']=False
        if field['control']=='radio':
            question=field['selector'].split('option_ques_')[1].split('_')[0]
            field.update(key=f'r:ques_{question}',identity_kind='common_app_question_radio')
    return p


def test_common_radio_saved_state_and_recovery_survive_generated_group_names():
    p=common_radio_page();p['state_metadata']=completed_state()
    data=create_profile(FIXTURES/'synthetic_psr.pdf')
    cp={'state':'prepared','page_key':p['url'],'observed_structure':structure(p),
        'context':{'real_account_test':True},'original_state_metadata':copy.deepcopy(p['state_metadata']),
        'journal':values(p),'original_values_sha256':digest(values(p)),'expected_values_sha256':digest(values(p))}
    data['checkpoints']['synthetic-radio']=cp
    after=copy.deepcopy(p)
    for i,f in enumerate(after['fields']):
        if f['control']=='radio':f['name']=f'mat-radio-group-{i+12}'
    validate_observation(after)
    assert digest(after)!=digest(p)
    assert structure(after)==structure(p)
    assert restoration_writes(data,'synthetic-radio',after)==[]
    assert verify_saved(data,'synthetic-radio',after,revisited_after_save=True)['verified']
    assert verify_saved(data,'synthetic-radio',after,revisited_after_save=True,restoration=True)['restored']
    assert cp['journal'] is None


@pytest.mark.parametrize('change',['question_id','option_label','option_value','multiplicity','different_page','identity_kind'])
def test_common_radio_identity_does_not_hide_form_changes(change):
    p=common_radio_page();before=digest(structure(p))
    f=next(f for f in p['fields'] if f['control']=='radio')
    if change=='question_id':f['options'][1]['selector']='[id="option_ques_99_2372-input"]'
    if change=='option_label':f['options'][1]['label']='Changed choice'
    if change=='option_value':f['options'][1]['value']='999'
    if change=='multiplicity':f['options'][1]['selector_count']=2;f['options'][1]['selector_index']=0
    if change=='different_page':p['url']='https://apply.commonapp.org/common/5/1'
    if change=='identity_kind':f['identity_kind']='ignore_any_metadata'
    if change in {'option_label','option_value'}:
        validate_observation(p)
        assert digest(structure(p))!=before
    else:
        with pytest.raises(ProfileError,match='observed_radio_identity_invalid'):validate_observation(p)


def test_synthetic_flag_cannot_enable_real_mit_restoration():
    p=page();p['url']='https://apply.mitadmissions.org/personal';p['state_metadata']=completed_state()
    context={**real_context(p),'origin':'https://apply.mitadmissions.org'}
    with pytest.raises(ProfileError,match='observed_completed_page_restoration_evidence_required'):
        permission_gate(context,p,'https://apply.mitadmissions.org')


class SavedPort:
    """Models draft typing separately from persisted state; not implementation mirroring."""
    def __init__(self,current,store,checkpoint,*,discard=False,fail=False,new_field=False,normalize_other=False):
        self.current=copy.deepcopy(current); self.saved=copy.deepcopy(current)
        self.store=store; self.cp=checkpoint; self.discard=discard; self.fail=fail
        self.new_field=new_field; self.calls=[]
        self.normalize_other=normalize_other

    def observe(self): return copy.deepcopy(self.current)

    def write(self,writes):
        self.calls.append('write')
        # Inspect the actual saved file: rollback must survive a process failure.
        persisted=self.store.load().data['checkpoints'][self.cp]
        assert persisted['state'] in {'prepared','needs_restore','verified'}
        assert persisted['journal'] is not None
        for w in writes:
            next(f for f in self.current['fields'] if f['key']==w['field_key'])['value']=w['value']
        if self.fail:
            self.fail=False
            raise RuntimeError('simulated browser interruption after typing')
        if self.new_field:
            self.current['fields'].append(text_field('i:new','new','Conditional required *',''))
        if self.normalize_other:
            self.normalize_other=False
            self.current['fields'][1]['value']='Unexpected browser normalization'

    def save_draft(self,action):
        self.calls.append('save')
        if not self.discard: self.saved=copy.deepcopy(self.current)
        self.discard=False

    def revisit(self,url):
        self.calls.append('revisit'); self.current=copy.deepcopy(self.saved)


def test_page_plan_requires_known_facts_even_if_existing_browser_values(prepared):
    snapshot,_,target=prepared
    plan=build_plan(snapshot.data,target,page([text_field(name='lastName')]))
    assert not plan['ready']
    assert plan['blockers'][-1]['details']['missing_fact_ids']==['personal.legal_family_name']


def test_conflicting_optional_label_and_native_required_does_not_request_an_invented_fact(prepared):
    snapshot,_,target=prepared
    f=text_field(name='lastName',label='Preferred Last Nameoptional',value='')
    f['invalid']=True
    plan=build_plan(snapshot.data,target,page([f]))
    assert not plan['ready']
    assert plan['blockers']==[{'field_key':f['key'],'label':f['label'],'reason':'conflicting_required_signals'}]
    assert not plan['writes']


def test_summary_record_tables_cannot_be_mistaken_for_a_complete_empty_page(prepared):
    snapshot,_,target=prepared
    p=page();p['fields']=[]
    p['collections']=[{'kind':'editable_table','label':'School Name | School Country',
        'row_count':2,'editor_control_count':3}]
    plan=build_plan(snapshot.data,target,p)
    assert not plan['ready'] and not plan['writes']
    assert plan['blockers']==[{'reason':'repeatable_record_editors_not_supported','collection_count':1}]


@pytest.mark.parametrize('change',['negative_rows','zero_editors','bad_kind','bad_label'])
def test_invalid_collection_evidence_is_rejected(change):
    p=page();p['collections']=[{'kind':'editable_table','label':'Invented school list','row_count':2,'editor_control_count':3}]
    c=p['collections'][0]
    if change=='negative_rows':c['row_count']=-1
    if change=='zero_editors':c['editor_control_count']=0
    if change=='bad_kind':c['kind']='automatic_school_import'
    if change=='bad_label':c['label']=None
    with pytest.raises(ProfileError,match='observed_collections_invalid'):validate_observation(p)


def test_actual_uc_radio_question_required_without_html_required(prepared):
    snapshot,_,target=prepared
    f=text_field(name='hasLivedName',label='Do you have a lived name?',value='N')
    f.update(control='radio',required=False,options=[{'label':'No','value':'N'},{'label':'Yes','value':'Y'}])
    assert not build_plan(snapshot.data,target,page([f]))['ready']
    source=add_statement(snapshot.data,'Synthetic student explicitly reports no lived name.')
    set_fact(snapshot.data,'personal.has_lived_name',False,source)
    assert build_plan(snapshot.data,target,page([f]))['ready']


def test_subjective_essay_declaration_invitation_and_payment_pages_block(prepared):
    snapshot,_,target=prepared
    for label in ('Essay *','Describe your leadership *','I certify this application','Send invitation','Payment'):
        f=text_field(label=label)
        assert not build_plan(snapshot.data,target,page([f]))['ready']
    p=page(); p['actions'][0]['label']='Submit application'
    assert not build_plan(snapshot.data,target,p)['ready']


def test_duplicate_category_labels_require_an_explicit_observed_option_value():
    from bc_application.pages import encode
    field=text_field(label='Subject Area/Course Category',value='science-cs')
    field.update(control='select',options=[{'label':'Computer Science','value':'math-cs','group':'Mathematics'},
        {'label':'Computer Science','value':'science-cs','group':'Science'}])
    with pytest.raises(ProfileError,match='observed_option_exact_match_required'):
        encode(field,'Computer Science')
    assert encode(field,'math-cs')=='math-cs'


def test_real_test_boolean_cannot_replace_observed_completion_evidence(prepared):
    snapshot,_,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p)
    with pytest.raises(ProfileError,match='observed_completed_page_restoration_evidence_required'):
        prepare(snapshot.data,plan['checkpoint_id'],p,{**CONTEXT,'real_account_test':True,
            'full_state_restoration_verified':True})


@pytest.mark.parametrize('change', ['current_incomplete','other_status_changed','missing_metadata','wrong_baseline_hash'])
def test_real_restoration_requires_original_values_and_all_captured_statuses(prepared,change):
    from bc_application.pages import restoration_writes
    snapshot,store,target=prepared
    p=page(); p['state_metadata']=completed_state()
    plan=build_plan(snapshot.data,target,p); context=real_context(p)
    if change=='wrong_baseline_hash':
        context['restoration_strategy']['baseline_state_sha256']='0'*64
        with pytest.raises(ProfileError,match='observed_completed_page_restoration_evidence_required'):
            prepare(snapshot.data,plan['checkpoint_id'],p,context)
        return
    prepare(snapshot.data,plan['checkpoint_id'],p,context); store.save(snapshot)
    original=copy.deepcopy(p)
    p['fields'][0]['value']='Synthetic'
    if change=='current_incomplete': p['state_metadata']['items'][1]['status']='incomplete'
    elif change=='other_status_changed': p['state_metadata']['items'][2]['status']='complete'
    else: del p['state_metadata']
    result=verify_saved(snapshot.data,plan['checkpoint_id'],p,revisited_after_save=True)
    assert not result['verified']
    cp=snapshot.data['checkpoints'][plan['checkpoint_id']]
    assert cp['journal'] and cp['original_state_metadata']==original['state_metadata']
    # Metadata drift must not prevent generating value recovery writes.
    assert restoration_writes(snapshot.data,plan['checkpoint_id'],p)==[{'field_key':'i:firstname','value':'Before'}]
    p['fields'][0]['value']='Before'
    p['state_metadata']=copy.deepcopy(original['state_metadata'])
    assert verify_saved(snapshot.data,plan['checkpoint_id'],p,revisited_after_save=True,restoration=True)['restored']
    store.save(snapshot)
    assert cp['journal'] is None and 'original_state_metadata' not in cp


@pytest.mark.parametrize('bad', [None,{'schema':'other'}, {'schema':'observed-state/1','coverage':'common_app_visible_navigation',
    'current_page_key':'missing','items':[{'key':'other','status':'complete'}]}])
def test_bad_state_metadata_cannot_reach_planning(prepared,bad):
    snapshot,_,target=prepared; p=page();p['state_metadata']=bad
    with pytest.raises(ProfileError,match='observed_state_metadata_invalid'):
        build_plan(snapshot.data,target,p)


def test_unmapped_required_unknown_controls_and_duplicate_save_block(prepared):
    snapshot,_,target=prepared
    assert not build_plan(snapshot.data,target,page([text_field(name='unknown')]))['ready']
    p=page(); p['actions'].append({**p['actions'][0],'key':'i:save2'})
    assert not build_plan(snapshot.data,target,p)['ready']
    p=page(); p['frames_present']=True
    assert not build_plan(snapshot.data,target,p)['ready']


def test_original_grade_binding_no_conversion_and_unclear_course_gate(prepared):
    snapshot,_,target=prepared
    course=next(c for c in snapshot.data['academic']['courses'] if c['raw_cells']['equivalency_marker'])
    bind_record_column(snapshot.data,target,'i:grade',course['record_id'],'school_percent')
    f=text_field('i:grade','grade','Grade *','')
    plan=build_plan(snapshot.data,target,page([f]))
    assert plan['writes'][0]['value']=='93'
    assert not plan['ready'] and plan['blockers'][-1]['details']['academic_reviews']
    f.update(control='select',options=[{'label':'A','value':'A'}])
    assert 'observed_option_exact_match_required' in str(build_plan(snapshot.data,target,page([f]))['blockers'])


def test_scoped_marker_explanation_does_not_require_revalidating_clear_psr_grade(prepared):
    from bc_application.profile import clarify_marker,review_requirements,set_course_schedule
    snapshot,_,target=prepared
    record=next(c for c in snapshot.data['academic']['courses'] if c['raw_cells']['equivalency_marker'])
    source=add_statement(snapshot.data,'This synthetic E means equivalency credit for this record only.',scope=[record['record_id']])
    clarify_marker(snapshot.data,[record['record_id']],meaning='equivalency_credit',statement_source_id=source)
    bind_record_column(snapshot.data,target,'i:grade',record['record_id'],'school_percent')
    plan=build_plan(snapshot.data,target,page([text_field('i:grade','grade','Grade *','')]))
    assert plan['ready'] and plan['writes'][0]['value']=='93'
    assert review_requirements(snapshot.data,record['record_id'])[0]['transcript_or_report_card_review_required']
    # Original credits are also explicit PSR values; missing periods are different.
    bind_record_column(snapshot.data,target,'i:grade',record['record_id'],'credits')
    assert build_plan(snapshot.data,target,page([text_field('i:grade','credits','Credits *','')]))['ready']
    schedule_source=add_statement(snapshot.data,'The invented student confirms this course lasted a semester.',scope=[record['record_id']])
    set_course_schedule(snapshot.data,record['record_id'],duration='semester',source_id=schedule_source)
    assert build_plan(snapshot.data,target,page([text_field('i:grade','credits','Credits *','')]))['ready']
    bind_fact(snapshot.data,target,'i:grade',f"schedules.{record['record_id']}.duration")
    assert not build_plan(snapshot.data,target,page([text_field('i:grade','duration','Course duration *','')]))['ready']


@pytest.mark.parametrize('column',['description','course_description'])
def test_original_course_name_uses_the_actual_raw_psr_column(prepared,column):
    snapshot,_,target=prepared
    record=next(c for c in snapshot.data['academic']['courses'] if not c['review_issues'])
    bind_record_column(snapshot.data,target,'i:course',record['record_id'],column)
    plan=build_plan(snapshot.data,target,page([text_field('i:course','course','Course name *','')]))
    assert plan['ready']
    assert plan['writes'][0]['value']==record['raw_cells']['course_description']
    assert not snapshot.data['facts'].get('education.course_name')


def test_missing_unneeded_supplement_does_not_block_an_authoritative_psr_grade(prepared,tmp_path):
    from bc_application.profile import clarify_marker,register_document,review_requirements,review_with_document
    snapshot,_,target=prepared
    record=next(c for c in snapshot.data['academic']['courses'] if c['raw_cells']['equivalency_marker'])
    statement=add_statement(snapshot.data,'This invented record uses equivalency credit.',scope=[record['record_id']])
    clarify_marker(snapshot.data,[record['record_id']],meaning='equivalency_credit',statement_source_id=statement)
    source=tmp_path/'report.pdf'; source.write_bytes((FIXTURES/'synthetic_transcript.pdf').read_bytes())
    document=register_document(snapshot.data,source,kind='report_card')
    review=review_requirements(snapshot.data,record['record_id'])[0]['review_id']
    review_with_document(snapshot.data,review,document,page=2,quote='AP CALCULUS BC 12A 29-May-2026 A 93 93 E 4')
    source.unlink()
    bind_record_column(snapshot.data,target,'i:grade',record['record_id'],'school_percent')
    assert build_plan(snapshot.data,target,page([text_field('i:grade','grade','Grade *','')]))['ready']


def test_optional_fields_require_explicit_choice_with_sourced_reason(prepared):
    snapshot,_,target=prepared
    source=add_statement(snapshot.data,'Synthetic student confirms a middle name.')
    set_fact(snapshot.data,'personal.middle_name','Invented',source)
    f=text_field(name='middleName',label='Middle name',value=''); f['required']=False
    plan=build_plan(snapshot.data,target,page([f]))
    assert not plan['writes'] and plan['recommendations'][0]['source'].startswith('https://admission.')
    assert build_plan(snapshot.data,target,page([f]),optional_keys=[f['key']])['writes']


@pytest.mark.parametrize('change', ['permission','origin','built_in','real_test','stale_page'])
def test_permission_origin_restoration_and_staleness_checked_before_writes(prepared,change):
    snapshot,store,target=prepared
    p=page(); context=copy.deepcopy(CONTEXT)
    plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    if change=='permission': context['access_verified']=False
    if change=='origin': context['origin']='https://example.org'
    if change=='built_in': context['transport']='iab'
    if change=='real_test': context['real_account_test']=True
    if change=='stale_page': p['fields'][0]['value']='Student edited meanwhile'
    with pytest.raises(ProfileError): prepare(snapshot.data,plan['checkpoint_id'],p,context)
    assert store.load().data['checkpoints'][plan['checkpoint_id']]['journal'] is None


def test_all_page_write_save_revisit_then_restore_only_one_json(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    port=SavedPort(p,store,plan['checkpoint_id'])
    result=execute(snapshot,store,plan['checkpoint_id'],port,CONTEXT,restore_test=True)
    assert result=={'fill_verified':True,'restored':True,'state':'restored'}
    assert port.saved==p
    assert port.calls==['write','save','revisit','revisit','write','save','revisit']
    cp=store.load().data['checkpoints'][plan['checkpoint_id']]
    assert cp['state']=='restored' and cp['journal'] is None
    assert len(list(store.path.parent.glob('*.json')))==1


def test_typed_values_are_not_proof_of_persistence(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    port=SavedPort(p,store,plan['checkpoint_id'],discard=True)
    result=execute(snapshot,store,plan['checkpoint_id'],port,CONTEXT,restore_test=True)
    assert not result['fill_verified'] and result['restored']
    assert port.saved==p


def test_interrupted_partial_fill_restores_and_journal_survives(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    port=SavedPort(p,store,plan['checkpoint_id'],fail=True)
    assert execute(snapshot,store,plan['checkpoint_id'],port,CONTEXT,restore_test=True)['restored']
    assert port.saved==p


def test_conditional_required_fields_stop_before_save(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    port=SavedPort(p,store,plan['checkpoint_id'],new_field=True)
    with pytest.raises(ProfileError,match='conditional_page_changed'):
        execute(snapshot,store,plan['checkpoint_id'],port,CONTEXT)
    assert 'save' not in port.calls
    assert store.load().data['checkpoints'][plan['checkpoint_id']]['state']=='needs_restore'


def test_verification_requires_revisit_and_detects_normalized_values(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); prepare(snapshot.data,plan['checkpoint_id'],p,CONTEXT)
    p['fields'][0]['value']='Synthetic'
    assert not verify_saved(snapshot.data,plan['checkpoint_id'],p,revisited_after_save=False)['verified']
    p['fields'][0]['value']='SYNTHETIC'
    assert not verify_saved(snapshot.data,plan['checkpoint_id'],p,revisited_after_save=True)['verified']


def test_actual_observed_uc_structure_with_only_synthetic_values(prepared):
    snapshot,_,target=prepared
    p=json.loads((FIXTURES/'uc_personal_page.json').read_text(encoding='utf-8'))
    plan=build_plan(snapshot.data,target,p)
    assert not plan['ready'] and len(p['fields'])==12
    assert len(plan['blockers'][-1]['details']['missing_fact_ids'])==9
    assert len({a['key'] for a in p['actions']})==3


def test_pending_browser_transaction_prevents_fact_edits_and_lost_journal(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    prepare(snapshot.data,plan['checkpoint_id'],p,CONTEXT); store.save(snapshot)
    original_journal=copy.deepcopy(snapshot.data['checkpoints'][plan['checkpoint_id']]['journal'])
    with pytest.raises(ProfileError,match='pending_transaction'):
        build_plan(snapshot.data,target,p)
    assert snapshot.data['checkpoints'][plan['checkpoint_id']]['journal']==original_journal
    source=add_statement(snapshot.data,'A concurrent factual edit during browser filling.')
    set_fact(snapshot.data,'personal.middle_name','Concurrent',source)
    with pytest.raises(ProfileError,match='browser_transaction_active'):
        store.save(snapshot)
    assert 'personal.middle_name' not in store.load().data['facts']


@pytest.mark.parametrize('state', ['prepared', 'saved_unverified', 'needs_restore', 'verified'])
@pytest.mark.parametrize('change', ['conditional_required', 'manual_field', 'optional_choice', 'different_page'])
def test_replanning_cannot_replace_pending_recovery_even_when_requirements_change(prepared,state,change):
    from bc_application.checkpoints import create_checkpoint
    snapshot,store,target=prepared
    p=page(); p['state_metadata']=completed_state(); plan=build_plan(snapshot.data,target,p)
    prepare(snapshot.data,plan['checkpoint_id'],p,real_context(p))
    cp=snapshot.data['checkpoints'][plan['checkpoint_id']]
    cp['state']=state
    store.save(snapshot)
    original=copy.deepcopy(snapshot.data)
    changed=copy.deepcopy(p); optional=[]
    if change=='conditional_required':
        changed['fields'].append(text_field('i:last','lastName','Family name *',''))
    elif change=='manual_field':
        changed['fields'].append(text_field('i:essay','essay','Describe your interests *',''))
    elif change=='optional_choice':
        f=text_field('i:middle','middleName','Middle name',''); f['required']=False
        changed['fields'].append(f); optional=[f['key']]
    else:
        changed['url']='http://127.0.0.1:8765/other-page'
    with pytest.raises(ProfileError,match='pending_transaction_requires_recovery'):
        build_plan(snapshot.data,target,changed,optional_keys=optional)
    assert snapshot.data==original
    # The standalone checkpoint API must not provide a route around the guard.
    with pytest.raises(ProfileError,match='pending_transaction_requires_recovery'):
        create_checkpoint(snapshot.data,target,p['url'],fact_ids=['personal.new_required'])
    assert snapshot.data==original
    assert store.load().data==original


def test_real_account_test_cannot_disable_restoration(prepared):
    snapshot,store,target=prepared
    p=page(); plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    context={**CONTEXT,'real_account_test':True,'full_state_restoration_verified':True}
    port=SavedPort(p,store,plan['checkpoint_id'])
    with pytest.raises(ProfileError,match='requires_restoration'):
        execute(snapshot,store,plan['checkpoint_id'],port,context)
    assert not port.calls


def test_browser_side_effects_on_untouched_fields_stop_before_save_and_restore(prepared):
    snapshot,store,target=prepared
    middle=text_field('i:middle','middleName','Middle name','Original middle'); middle['required']=False
    p=page([text_field(),middle])
    plan=build_plan(snapshot.data,target,p); store.save(snapshot)
    port=SavedPort(p,store,plan['checkpoint_id'],normalize_other=True)
    result=execute(snapshot,store,plan['checkpoint_id'],port,CONTEXT,restore_test=True)
    assert not result['fill_verified'] and result['restored']
    assert port.saved==p
    # The only save is restoration; the unexpected changed field never gets a draft save.
    assert port.calls.count('save')==1
