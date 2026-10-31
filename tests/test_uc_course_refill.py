"""Fictional PSR-backed conditional term/grade transactions and restart recovery."""
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from bc_application.browser import digest, values, structure
from bc_application.profile import create_profile, add_statement, add_target, set_fact, bind_fact, bind_record_column, ProfileError
from bc_application.uc_course_refill import prepare_refill, prepare_grades, recover_refill, verify_refill, validate_bundle

FIXTURES=Path(__file__).parent/'fixtures'
URL='https://apply.universityofcalifornia.edu/my-application/acadHistFrHighSchoolClasses/editClasses/11/123456'


def field(i,suffix,value,options=None):
    labels={'subject':'Subject Area/Course Category','class_title':'Course Name','honors':'Honor Type','term':'Term System','grade1':'Grade 1','grade2':'Grade 2'}
    key=f'academics_hs_classes_add_{i}_{suffix}'
    return {'key':'i:'+key,'selector':'[id="'+key+'"]','selector_count':1,'selector_index':0,'name':key,
        'label':labels[suffix],'group':'','control':'text' if suffix=='class_title' else 'select','value':value,
        'required':True,'disabled':False,'readonly':False,'invalid':False,
        'options':[{'value':v,'label':label,'disabled':False} for v,label in (options or [])]}


def refresh(bundle):
    p=bundle['page'];rows=[];terms=[];fields={f['key']:f for f in p['fields']}
    for i in range(2):
        pre=f'i:academics_hs_classes_add_{i}_'
        def display(suffix):
            f=fields.get(pre+suffix)
            return '' if f is None else f['value'] if f['control']=='text' else next(o['label'] for o in f['options'] if o['value']==f['value'])
        term=display('term');terms.append('Full year' if term=='Full' else '' if term=='--' else term)
        rows.append(['B-English',display('class_title'),display('honors'),'' if term=='--' else term,display('grade1'),display('grade2'),'','',''])
    summary=bundle['summary'];summary['context']['row_terms']=terms
    summary['cells']={'columns':summary['context']['columns'],'rows':rows}
    summary['rows_sha256']=digest(summary['cells']);summary['parent']['summary_sha256']=digest(summary['cells'])
    return bundle


def setup(*,blank=False,real=False):
    p=create_profile(FIXTURES/'synthetic_psr.pdf');source=add_statement(p,'Fictional student confirms Full AP and retains the supplied other reporting choices.')
    target=add_target(p,system='uc',school='Synthetic UC',program=None,source_id=source)
    set_fact(p,'education.uc_ap_reporting_term','Full year',source);set_fact(p,'education.uc_other_settings_retained',True,source)
    courses=[p['academic']['courses'][1],p['academic']['courses'][2]]
    page={'schema':'observed-page/1','url':URL,'title':'Enter HS classes - Academic history - UC application','frames_present':False,'fields':[],
        'actions':[{'key':'i:save','label':'Save & continue','selector':'[id="save"]','disabled':False},
                   {'key':'i:cancel-btn','label':'Cancel','selector':'[id="cancel-btn"]','disabled':False}]}
    for i,c in enumerate(courses):
        page['fields'] += [field(i,'subject','4',[('4','English')]),field(i,'class_title',c['raw_cells']['course_description']),
            field(i,'honors','AP' if i==0 else 'NH',[('AP','AP'),('NH','NH')]),
            field(i,'term','' if blank else 'S',[('','--'),('F','Full'),('S','Semester')])]
        if not blank:page['fields'] += [field(i,'grade1','Z',[('','--'),('084','84'),('078','78'),('Z','NO')]),
                                       field(i,'grade2','078' if i else '084',[('','--'),('084','84'),('078','78'),('Z','NO')])]
        for suffix,value in [('subject','English'),('honors','AP' if i==0 else 'NH'),('term','Full' if i==0 else 'Semester')]:
            ref=f'education.refill.row{i}.{suffix}';set_fact(p,ref,value,source)
            bind_fact(p,target,f'i:academics_hs_classes_add_{i}_{suffix}',ref,page_path=urlsplit(URL).path)
        bind_record_column(p,target,f'i:academics_hs_classes_add_{i}_class_title',c['record_id'],'description',page_path=urlsplit(URL).path)
        bind_record_column(p,target,f'i:academics_hs_classes_add_{i}_grade{1 if i==0 else 2}',c['record_id'],'school_percent',page_path=urlsplit(URL).path)
        if i:
            ref='education.refill.row1.offterm';set_fact(p,ref,'NO',source)
            bind_fact(p,target,'i:academics_hs_classes_add_1_grade1',ref,page_path=urlsplit(URL).path)
    state=json.loads((FIXTURES/'uc_review_state.json').read_text());state['page_url']=URL
    context={'schema':'uc-course-editor/1','grade':'11','summary_url':'https://apply.universityofcalifornia.edu/my-application/acadHistFrGrades/11',
        'year':'2025 - 2026 academic year','row_count':2,'context_sha256':'a'*64,
        'columns':['Subject area/Course category','Course name','Hnrs','Term','G1','G2','G3','G4','Language name']}
    bundle={'schema':'uc-course-refill-bundle/1','page':page,'summary':{'context':context,
        'parent':{'schema':'uc-course-parent/1','url':context['summary_url'],'context_sha256':'a'*64,'row_count':2}},
        'auxiliary':json.loads((FIXTURES/'uc_courses_page.json').read_text())['uc_academic_auxiliary'],'state_metadata':state}
    refresh(bundle)
    ctx={'browser_family':'edge','transport':'extension','origin':'https://apply.universityofcalifornia.edu','access_verified':True,'real_account_test':real}
    if real:ctx.update(full_state_restoration_verified=True,restoration_strategy={'kind':'restore_uc_course_refill','page_url':URL,
        'baseline_state_sha256':digest(state),'baseline_parent_sha256':digest(bundle['summary']['parent'])})
    return p,target,bundle,ctx


def selected_page(bundle,plan,*,restore=False):
    page=copy.deepcopy(bundle['page']);base=[f for f in page['fields'] if not f['key'].endswith(('_grade1','_grade2'))]
    for f in base:
        if f['key'].endswith('_term'):f['value']=('S' if restore else next(r['value'] for r in plan['rows'] if r['field_key']==f['key']))
    page['fields']=[]
    for i in range(2):
        page['fields'].extend(f for f in base if f['key'].startswith(f'i:academics_hs_classes_add_{i}_'))
        term=next(f for f in base if f['key']==f'i:academics_hs_classes_add_{i}_term')['value']
        for j in range(1,2 if term=='F' else 3):page['fields'].append(field(i,f'grade{j}','',[('','--'),('084','84'),('078','78'),('Z','NO')]))
    return page


def apply(page,plan):
    page=copy.deepcopy(page)
    for w in plan['writes']:next(f for f in page['fields'] if f['key']==w['field_key'])['value']=w['value']
    return page


def test_blank_terms_discover_only_actual_grades_save_and_clear_intended_refill():
    p,target,b,ctx=setup(blank=True);before=copy.deepcopy(p['academic']);plan=prepare_refill(p,target,b,ctx)
    assert len(plan['writes'])==2 and p['checkpoints'][plan['checkpoint_id']]['journal']==b
    p=json.loads(json.dumps(p));page=selected_page(b,plan);grade=prepare_grades(p,plan['checkpoint_id'],page)
    assert len(grade['writes'])==3
    after=refresh({**copy.deepcopy(b),'page':apply(page,grade)})
    assert verify_refill(p,plan['checkpoint_id'],after,revisited_after_save=True)['verified']
    assert p['checkpoints'][plan['checkpoint_id']]['journal'] is None and p['academic']==before


def test_changed_terms_and_scores_restore_after_restart_from_same_journal():
    p,target,b,ctx=setup(real=True);plan=prepare_refill(p,target,b,ctx);page=selected_page(b,plan)
    grade=prepare_grades(p,plan['checkpoint_id'],page);after=refresh({**copy.deepcopy(b),'page':apply(page,grade)})
    assert verify_refill(p,plan['checkpoint_id'],after,revisited_after_save=True)['verified']
    p=json.loads(json.dumps(p));recovery=recover_refill(p,plan['checkpoint_id'])
    assert len(recovery['term_writes'])==2 and recovery['original']==b
    original_shape=selected_page(b,plan,restore=True);restore=prepare_grades(p,plan['checkpoint_id'],original_shape,restoration=True)
    final=refresh({**copy.deepcopy(b),'page':apply(original_shape,restore)})
    assert verify_refill(p,plan['checkpoint_id'],final,revisited_after_save=True,restoration=True)['restored']


@pytest.mark.parametrize('change',['unbound','term_unconfirmed','ap_semester','different_record','guessed_grade','unknown_field','ambiguous','wrong_origin','comments','submitted','parent_hash'])
def test_source_native_permission_and_recovery_boundaries(change):
    p,target,b,ctx=setup(real=True);bindings=p['targets'][target]['page_field_bindings'][urlsplit(URL).path]
    if change=='unbound':bindings.pop('i:academics_hs_classes_add_0_term')
    elif change=='term_unconfirmed':p['facts'].pop('education.uc_ap_reporting_term')
    elif change=='ap_semester':p['facts']['education.refill.row0.term']['value']='Semester'
    elif change=='different_record':bindings['i:academics_hs_classes_add_0_grade1']=bindings['i:academics_hs_classes_add_1_grade2']
    elif change=='guessed_grade':p['facts']['education.refill.row1.offterm']['value']='97'
    elif change=='unknown_field':b['page']['fields'][0]['key']='i:unknown'
    elif change=='ambiguous':b['page']['fields'][0]['selector_count']=2
    elif change=='wrong_origin':ctx['origin']='https://example.org'
    elif change=='comments':b['auxiliary']['values_sha256']=digest({'i:additional_comments':'Unrelated narrative'})
    elif change=='submitted':b['state_metadata']['draft_marker']='Submitted'
    else:ctx['restoration_strategy']['baseline_parent_sha256']='c'*64
    with pytest.raises(ProfileError):prepare_refill(p,target,b,ctx)
    assert not any(cp.get('journal') for cp in p['checkpoints'].values())


@pytest.mark.parametrize('change',['new_field','changed_subject','missing_grade','wrong_term','changed_option'])
def test_conditional_stage_refuses_drift_without_discarding_original(change):
    p,target,b,ctx=setup(blank=True);plan=prepare_refill(p,target,b,ctx);page=selected_page(b,plan)
    if change=='new_field':page['fields'].append(field(2,'class_title','Unknown row'))
    elif change=='changed_subject':page['fields'][0]['value']='19'
    elif change=='missing_grade':page['fields'].pop()
    elif change=='wrong_term':next(f for f in page['fields'] if f['key'].endswith('_0_term'))['value']='S'
    else:next(f for f in page['fields'] if f['key'].endswith('_0_grade1'))['options']=[{'value':'0','label':'Other','disabled':False}]
    with pytest.raises(ProfileError):prepare_grades(p,plan['checkpoint_id'],page)
    assert recover_refill(p,plan['checkpoint_id'])['original']==b


@pytest.mark.parametrize('change',['no_revisit','saved_grade','summary_grade','other_status','summary_context','auxiliary'])
def test_saved_readback_cannot_clear_wrong_value_summary_or_other_state(change):
    p,target,b,ctx=setup(blank=True);plan=prepare_refill(p,target,b,ctx);page=selected_page(b,plan)
    grade=prepare_grades(p,plan['checkpoint_id'],page);after=refresh({**copy.deepcopy(b),'page':apply(page,grade)})
    if change=='saved_grade':after['page']['fields'][-1]['value']='084'
    elif change=='summary_grade':
        after['summary']['cells']['rows'][0][4]='78';after['summary']['rows_sha256']=digest(after['summary']['cells'])
    elif change=='other_status':after['state_metadata']['sections'][-1]['completion_text']='Section Complete'
    elif change=='summary_context':after['summary']['context']['context_sha256']='c'*64;after['summary']['parent']['context_sha256']='c'*64
    elif change=='auxiliary':after['auxiliary']['structure_sha256']='d'*64
    assert not verify_refill(p,plan['checkpoint_id'],after,revisited_after_save=change!='no_revisit')['verified']
    assert recover_refill(p,plan['checkpoint_id'])['original']==b


def test_generic_verification_cannot_clear_refill_journal_and_facts_cannot_change_mid_transaction(tmp_path):
    from bc_application.pages import verify_saved
    from bc_application.store import ProfileStore,ProfileSnapshot,StoreError
    p,target,b,ctx=setup(blank=True);plan=prepare_refill(p,target,b,ctx)
    with pytest.raises(ProfileError,match='dedicated_verification'):verify_saved(p,plan['checkpoint_id'],b['page'],revisited_after_save=True)
    store=ProfileStore(tmp_path/'applicant.json');snapshot=ProfileSnapshot(p,None);store.save(snapshot)
    snapshot.data['facts']['education.refill.row0.term']['value']='Semester'
    with pytest.raises(StoreError,match='transaction_active'):store.save(snapshot)


def test_exact_unsaved_cancel_can_restore_an_original_reset_draft_with_existing_errors():
    p,target,b,ctx=setup(blank=True)
    for f in b['page']['fields']:
        if f['key'].endswith('_term'):f['invalid']=True
    plan=prepare_refill(p,target,b,ctx)
    assert verify_refill(p,plan['checkpoint_id'],copy.deepcopy(b),revisited_after_save=True,restoration=True)['restored']


def test_duplicate_subject_labels_require_explicit_group_without_changing_classification():
    p,target,b,ctx=setup(blank=True);f=b['page']['fields'][0]
    f['options']=[{'value':'4','label':'Computer Science','group':'Mathematics','disabled':False},
        {'value':'50','label':'Computer Science','group':'Science','disabled':False}]
    p['facts']['education.refill.row0.subject']['value']='Computer Science'
    with pytest.raises(ProfileError,match='exact_match'):prepare_refill(p,target,b,ctx)
    p['facts']['education.refill.row0.subject']['value']={'label':'Computer Science','group':'Mathematics'}
    plan=prepare_refill(p,target,b,ctx)
    assert not any(w['field_key']==f['key'] for w in plan['writes'])
    assert p['checkpoints'][plan['checkpoint_id']]['journal']['page']['fields'][0]['value']=='4'


def test_name_only_psr_reference_does_not_infer_or_resolve_missing_results():
    from bc_application.checkpoints import page_requirements
    p,_,_,_=setup();record=p['academic']['courses'][-1];rid=record['record_id']
    assert page_requirements(p,fact_ids=[],course_ids=[rid],record_columns={rid:['description']})['data_ready']
    assert not page_requirements(p,fact_ids=[],course_ids=[rid],record_columns={rid:['description','final_result']})['data_ready']
    assert not page_requirements(p,fact_ids=[],course_ids=[rid])['data_ready']
    assert p['reviews'][rid+':result_and_completion_status_require_confirmation']['status']=='unresolved'


def test_native_reaffirmation_still_requires_observed_bound_term_and_second_grade_plan():
    p,target,b,ctx=setup();key='i:academics_hs_classes_add_1_term'
    with pytest.raises(ProfileError,match='reaffirmation'):prepare_refill(p,target,b,ctx,reaffirm_term_keys=['i:unknown'])
    plan=prepare_refill(p,target,b,ctx,reaffirm_term_keys=[key])
    assert any(w['field_key']==key and w['value']=='S' for w in plan['writes'])
    grades=prepare_grades(p,plan['checkpoint_id'],selected_page(b,plan))
    assert len(grades['writes'])==3


def test_cli_refill_roundtrip_uses_one_json_and_read_only_restart_bundle(tmp_path,monkeypatch,capsys):
    import io
    from bc_application.cli import main
    from bc_application.store import ProfileStore,ProfileSnapshot
    p,target,b,ctx=setup(blank=True);path=tmp_path/'applicant.json';store=ProfileStore(path);store.save(ProfileSnapshot(p,None))
    def call(command,payload,*args):
        monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(payload)))
        assert main([command,'--profile',str(path),*args])==0
        return json.loads(capsys.readouterr().out)
    plan=call('uc-refill-prepare',{'bundle':b,'context':ctx},'--target',target);checkpoint=plan['checkpoint_id']
    before=path.read_bytes();recovery=call('uc-refill-recover',{},'--checkpoint',checkpoint)
    assert path.read_bytes()==before and recovery['original']==b
    page=selected_page(b,plan);grades=call('uc-refill-grades',{'page':page},'--checkpoint',checkpoint)
    after=refresh({**copy.deepcopy(b),'page':apply(page,grades)})
    assert call('uc-refill-verify',{'bundle':after,'revisited_after_save':True},'--checkpoint',checkpoint)['verified']
    assert list(tmp_path.glob('*.json'))==[path] and store.load().data['checkpoints'][checkpoint]['journal'] is None
