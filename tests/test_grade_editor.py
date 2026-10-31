"""Mixed term/scale planning and durable recovery; all applicant data invented."""
import copy
from pathlib import Path

import pytest

from bc_application.browser import digest, structure, values, validate_observation, permission_gate
from bc_application.pages import build_plan, prepare, verify_saved, recovery_bundle
from bc_application.profile import (ProfileError, create_profile, add_statement, set_fact,
    add_target, bind_fact)


def grade_page():
    fields=[]; groups=[]
    def field(key,label,value,control='text',required=False,**extra):
        f=dict(key='i:'+key,selector=f'[id="{key}"]',name='',label=label,group='',value=value,
               control=control,required=required,disabled=False,readonly=False,invalid=False,options=[],**extra)
        fields.append(f); return f['key']
    for t in (1,2):
        for name,label,value in [('schoolName','School Name','Invented Secondary'),('schoolYear','School Year','2024-25'),
            ('gradingScale','Grading Scale','Other' if t==1 else '1-100'),('schedule','Schedule','Semesters')]:
            field(f'{name}Control{t}',f'Transcript {t} {label}',value,'material_select',True)
        prefix=f'Transcript {t}, Course 1, '; row=f'T{t}C1'
        field(f'subjectControl_{row}',prefix+'Subject','Other/Elective','material_select',True)
        field(f'courseNameControl_{row}',prefix+'Course Nameundefined',f'Invented course {t}',required=True)
        field(f'levelControl_{row}',prefix+'Course Level','Regular/Standard','material_select',True)
        for kind in ('grades','credits'):
            keys=[]
            for n,term in enumerate(('Semester 1','Semester 2','Final')):
                key=f'{kind}{n}_{row}'
                label=prefix+term+(' Credits' if kind=='credits' and term=='Final' else ' Credit' if kind=='credits'
                    else ' Grade' if t==2 else 'undefined')
                value=('PRF' if t==1 else '84') if kind=='grades' and n==1 else '4' if kind=='credits' and t==2 and n==1 else ''
                keys.append(field(key,label,value,'material_select' if kind=='grades' and t==2 else 'text',
                    requirement_group={'row':row,'kind':kind}))
            groups.append({'row':row,'kind':kind,'field_keys':keys,
                **({'not_applicable_key':'i:creditNA_'+row+'-input'} if kind=='credits' else {})})
        field(f'creditNA_{row}-input',prefix+'Credits not applicable',t==1,'checkbox')
    state={'schema':'observed-state/1','coverage':'common_app_visible_navigation',
        'current_page_key':'tertiaryNavItem13_55','items':[{'key':'secondaryNavItem13','status':'complete'},
            {'key':'tertiaryNavItem13_55','status':'complete'}]}
    parent={'schema':'grade-parent/1','url':'http://127.0.0.1:8765/common/13/55','heading':'9th Grade',
        'controls_sha256':digest([]),'values_sha256':digest(True),'summary_sha256':digest('Invented summary'),
        'completion_checked':True,'state_metadata':state,
        'reopen_action':{'key':'i:addCG','label':'Edit 9th grade','selector':'[id="addCG"]','disabled':False}}
    return {'schema':'observed-page/1','url':parent['url'],'title':'Synthetic grade editor','frames_present':False,
        'fields':fields,'actions':[{'key':'a:Continue, Closes dialog:0','label':'Continue, Closes dialog',
            'selector':None,'disabled':False}],
        'scope':{'kind':'common_app_grade_dialog','name':'Courses & Grades','heading':'Courses & Grades – 9th grade'},
        'requirement_groups':groups,'editor_state':parent,'state_metadata':state,
        'choice_observations':{'i:grades1_T2C1':[{'label':v,'value':v,'disabled':False} for v in ('84','94')]}}


def planned():
    p=grade_page(); data=create_profile(Path(__file__).parent/'fixtures/synthetic_psr.pdf')
    source=add_statement(data,'Invented student confirms the existing school, course, term and credit choices.')
    target=add_target(data,system='common_app',school='Synthetic general application',program=None,source_id=source)
    for i,f in enumerate(p['fields']):
        if f['value']!='':
            ref=f'education.test.value_{i}'
            set_fact(data,ref,f['value'],source);bind_fact(data,target,f['key'],ref,page_path='/common/13/55')
    return data,target,p


def context(p):
    return {'browser_family':'edge','transport':'extension','origin':'http://127.0.0.1:8765',
        'access_verified':True,'synthetic_test':True,'real_account_test':True,'full_state_restoration_verified':True,
        'restoration_strategy':{'kind':'restore_completed_grade_dialog','current_page_key':'tertiaryNavItem13_55',
            'baseline_state_sha256':digest(p['state_metadata']),'baseline_parent_sha256':digest(p['editor_state'])}}


def test_mixed_scales_partial_terms_and_na_form_one_ready_page():
    data,target,p=planned();validate_observation(p)
    plan=build_plan(data,target,p,reaffirm_keys=['i:grades1_T2C1'])
    assert plan['ready'],plan['blockers']
    assert plan['writes']==[{'field_key':'i:grades1_T2C1','fact_ref':data['targets'][target]['page_field_bindings']['/common/13/55']['i:grades1_T2C1'],'value':'84'}]
    assert not any(w['value']=='' for w in plan['writes'])


@pytest.mark.parametrize('change',['missing_grade','missing_credit','unmapped_existing_grade','changed_header',
    'empty_material_write','no_observed_options','unknown_optional_reaffirm'])
def test_incomplete_evidence_or_layout_changes_stop_whole_page(change):
    data,target,p=planned();reaffirm=['i:grades1_T2C1']
    f=next(f for f in p['fields'] if f['key']=='i:grades1_T2C1')
    if change=='missing_grade': f['value']=''
    if change=='missing_credit': next(f for f in p['fields'] if f['key']=='i:credits1_T2C1')['value']=''
    if change=='unmapped_existing_grade': del data['targets'][target]['page_field_bindings']['/common/13/55'][f['key']]
    if change=='changed_header':
        header=next(f for f in p['fields'] if f['key']=='i:schoolYearControl1');header['value']='2023-24'
        p['choice_observations'][header['key']]=[{'label':'2024-25','value':'2024-25','disabled':False}]
    if change=='empty_material_write':
        f['value']=''
        other=next(v for v in p['fields'] if v['key']=='i:grades2_T2C1');other['value']='84'
        ref=data['targets'][target]['page_field_bindings']['/common/13/55'][f['key']]
        bind_fact(data,target,other['key'],ref,page_path='/common/13/55')
    if change=='no_observed_options': p.pop('choice_observations')
    if change=='unknown_optional_reaffirm': reaffirm=['i:grades0_T2C1']
    plan=build_plan(data,target,p,reaffirm_keys=reaffirm)
    assert not plan['ready']
    expected={'missing_grade':'applicable_course_term_value_required','missing_credit':'applicable_course_term_value_required',
        'unmapped_existing_grade':'unmapped_required_factual_field','changed_header':'existing_course_values_only',
        'empty_material_write':'existing_course_values_only','no_observed_options':'observed_material_reaffirmation_required',
        'unknown_optional_reaffirm':'unmapped_required_factual_field'}[change]
    assert expected in {b['reason'] for b in plan['blockers']}


@pytest.mark.parametrize('change',['foreign_origin','cross_row_credit_na','false_group_label','missing_credit_group','duplicate_choice'])
def test_forged_scope_and_group_contracts_are_rejected(change):
    p=grade_page()
    if change=='foreign_origin':p['url']='https://example.org/common/13/55'
    if change=='cross_row_credit_na':p['requirement_groups'][1]['not_applicable_key']='i:creditNA_T2C1-input'
    if change=='false_group_label':p['fields'][7]['label']='Essay'
    if change=='missing_credit_group':p['requirement_groups'].pop()
    if change=='duplicate_choice':p['choice_observations']['i:grades1_T2C1']*=2
    with pytest.raises(ProfileError):validate_observation(p)


def test_recovery_survives_restart_and_status_drift_never_clears_journal():
    data,target,p=planned();plan=build_plan(data,target,p,reaffirm_keys=['i:grades1_T2C1']);cpid=plan['checkpoint_id']
    prepared=prepare(data,cpid,p,context(p));cp=data['checkpoints'][cpid]
    # Simulates a restarted process reading the one JSON, without in-memory plan/cache.
    import json
    restarted=json.loads(json.dumps(data));bundle=recovery_bundle(restarted,cpid,p)
    assert bundle['plan']==prepared
    assert bundle['context']['journal_persisted'] is True
    assert bundle['plan']['choice_observations']==p['choice_observations']
    after=copy.deepcopy(p);after['editor_state']['completion_checked']=False
    assert not verify_saved(data,cpid,after,revisited_after_save=True,restoration=True)['restored']
    assert cp['journal']==values(p)
    assert verify_saved(data,cpid,p,revisited_after_save=True,restoration=True)['restored']
    assert cp['journal'] is None and 'prepared_plan' not in cp


def test_grade_restoration_permission_bound_to_actual_parent():
    p=grade_page();ctx=context(p);permission_gate(ctx,p,'https://apply.commonapp.org')
    p['editor_state']['summary_sha256']=digest('changed baseline')
    with pytest.raises(ProfileError):permission_gate(ctx,p,'https://apply.commonapp.org')


def test_pdf_course_name_wrap_is_only_a_display_transformation():
    from bc_application.adapters.common_app import CommonAppAdapter
    source='INVENTED PRE-\nCALCULUS 10'
    assert CommonAppAdapter().display_value({'control':'text'},'psr:invented:description',source)=='INVENTED PRE-CALCULUS 10'
    assert source=='INVENTED PRE-\nCALCULUS 10'


def test_reused_grade_ids_cannot_reuse_a_different_pages_bindings():
    data,target,p=planned();t=data['targets'][target]
    # A pre-dev.13 global mapping must also fail closed on every grade page.
    t['field_bindings']=copy.deepcopy(t['page_field_bindings']['/common/13/55'])
    p10=copy.deepcopy(p);p10['url']=p10['editor_state']['url']='http://127.0.0.1:8765/common/13/56'
    p10['scope']['heading']='Courses & Grades – 10th grade';p10['editor_state']['heading']='10th Grade'
    assert not build_plan(data,target,p10)['ready']
    assert build_plan(data,target,p10)['writes']==[]
    source=add_statement(data,'Invented student supplies the separate 10th Grade course name.')
    set_fact(data,'education.test.grade10_name','Invented different course',source)
    t['page_field_bindings']['/common/13/56']=copy.deepcopy(t['page_field_bindings']['/common/13/55'])
    bind_fact(data,target,'i:courseNameControl_T1C1','education.test.grade10_name',page_path='/common/13/56')
    plan10=build_plan(data,target,p10)
    assert plan10['ready'],plan10['blockers']
    assert plan10['writes']==[{'field_key':'i:courseNameControl_T1C1','fact_ref':'education.test.grade10_name','value':'Invented different course'}]
    assert build_plan(data,target,p)['writes']==[]


def test_legacy_scoping_moves_references_without_duplicating_facts_or_changing_psr():
    from bc_application.profile import scope_bindings, validate_profile
    data,target,p=planned();t=data['targets'][target]
    original=copy.deepcopy(data['academic']);fact_count=len(data['facts'])
    legacy=t['page_field_bindings'].pop('/common/13/55');t['field_bindings']=legacy.copy()
    assert not build_plan(data,target,p)['ready']
    scope_bindings(data,target,'/common/13/55',list(legacy))
    validate_profile(data)
    assert t['field_bindings']=={} and t['page_field_bindings']['/common/13/55']==legacy
    assert data['academic']==original and len(data['facts'])==fact_count
    assert build_plan(data,target,p)['ready']


@pytest.mark.parametrize('path',['https://example.org/common/13/55','//other/path','/common/../55','/common/13/55?x=1','/common/13/55#part'])
def test_page_binding_scope_requires_an_observed_path_only(path):
    from bc_application.profile import validate_profile
    data,target,p=planned();t=data['targets'][target]
    t['page_field_bindings'][path]={}
    with pytest.raises(ProfileError,match='observed_page_path_required'):validate_profile(data)
