"""Current-year drafts use originals and explicit grouping, never completed marks."""
import copy
import json

import pytest

from bc_application import common_current as core
from bc_application.browser import digest
from bc_application.profile import ProfileError,add_statement,add_target
from test_current_studies import scenario,REF


def setup(*,complete=True):
    p,report=scenario();s=add_statement(p,'This fictional student selected a fictional Common App target.')
    target=add_target(p,system='common_app',school='Invented institution',program=None,source_id=s)
    fields=[];rows=[];choices={}
    def field(key,label,control,value,options=None):
        f={'key':key,'label':label,'group':core.SCHEDULE if control=='radio' else '', 'control':control,'value':value,
            'required':True,'disabled':False,'readonly':False,'invalid':not complete,'options':options or [],
            'selector':f'[id="{key[2:]}"]','selector_count':1,'selector_index':0};fields.append(f);return f
    field('i:text_ques_307',core.COUNT,'choice_input','2');choices['i:text_ques_307']=[{'value':str(i),'label':str(i),'disabled':False} for i in range(1,16)]
    opts=[{'value':v,'label':v,'selector':f'[id="option_ques_1803_{i}-input"]','selector_count':1,'selector_index':0,'disabled':False} for i,v in enumerate(['Semester','Trimester','Quarter','Yearly'])]
    radio=field('r:ques_1803',core.SCHEDULE,'radio','Semester',opts);radio.update(selector=opts[0]['selector'],name='mat-radio-group-1')
    c=core.compile_report(p,REF)
    for i,course in enumerate(c['courses'],1):
        row={}
        for j,part in enumerate(['subject','name','level','terms']):
            key=f'i:text_ques_{5000+i*4+j}';row[part]=key;control={'name':'course_name','terms':'term_choices'}.get(part,'choice_input')
            field(key,f'Course {i} '+('schedule' if part=='terms' else part),control,course[part] if complete else [] if part=='terms' else '')
            if part!='name':choices[key]=[{'value':v,'label':v,'disabled':False} for v in (['First Semester','Second Semester','Full Year'] if part=='terms' else [course[part],'Fictional alternative'])]
        rows.append(row)
    page={'schema':'observed-current-page/1','url':core.ORIGIN+core.PATH,'title':core.CONTRACT['title'],'frames_present':False,
        'common_current':{'schema':'common-current-page/1','rows':rows,'content_sha256':digest(core.content(rows))},'fields':fields,
        'choice_observations':choices,'actions':[{'key':'i:sectionContinue24','label':'Continue to next section','selector':'[id="sectionContinue24"]','disabled':False}],
        'state_metadata':{'schema':'observed-state/1','coverage':'common_app_visible_navigation','current_page_key':'tertiaryNavItem4_24',
            'items':[{'key':'secondaryNavItem4','status':'complete' if complete else 'in progress'}, {'key':'tertiaryNavItem4_24','status':'complete' if complete else 'incomplete'},
                {'key':'secondaryNavItem7','status':'in progress'}]}}
    ctx={'browser_family':'edge','transport':'extension','origin':core.ORIGIN,'access_verified':True}
    return p,target,page,ctx


def fill(page,plan):
    page=copy.deepcopy(page)
    for w in plan['writes']:next(f for f in page['fields'] if f['key']==w['field_key'])['value']=w['value']
    for f in page['fields']:f['invalid']=False
    for s in page['state_metadata']['items']:
        if s['key']!='secondaryNavItem7':s['status']='complete'
    return page


def test_blank_observed_rows_fill_whole_page_and_restart_verifies_originals_unchanged():
    p,t,page,ctx=setup(complete=False);academic=copy.deepcopy(p['academic']);before=copy.deepcopy(p)
    preview=core.preview(p,t,REF,page);assert preview['ready'] and p==before and len(preview['next']['writes'])==8
    r=core.prepare(p,t,REF,page,ctx);saved=fill(page,r['plan']);p=json.loads(json.dumps(p))
    assert core.verify(p,r['checkpoint_id'],saved,revisited_after_save=True)['verified']
    assert p['academic']==academic and p['checkpoints'][r['checkpoint_id']]['journal'] is None
    again=core.preview(p,t,REF,saved)
    assert again['next']['stage']=='fields' and again['next']['writes']==[]


def test_site_error_on_multiselect_cannot_be_treated_as_valid_selected_terms():
    p,t,page,ctx=setup();page['fields'][5]['invalid']=True
    ctx.update(real_account_test=True,full_state_restoration_verified=True,restoration_strategy={'kind':'restore_completed_native_page',
        'current_page_key':'tertiaryNavItem4_24','baseline_state_sha256':digest(page['state_metadata'])})
    with pytest.raises(ProfileError,match='shape_change_qa_unverified'):core.prepare(p,t,REF,page,ctx)
    assert not p['checkpoints']


def test_real_same_shape_save_and_exact_original_recovery_include_multiselection_and_status():
    p,t,page,ctx=setup();page['fields'][3]['value']='Original title case name'
    ctx.update(real_account_test=True,full_state_restoration_verified=True,restoration_strategy={'kind':'restore_completed_native_page',
        'current_page_key':'tertiaryNavItem4_24','baseline_state_sha256':digest(page['state_metadata'])})
    r=core.prepare(p,t,REF,page,ctx);saved=fill(page,r['plan']);key=r['checkpoint_id']
    assert core.verify(p,key,saved,revisited_after_save=True)['verified']
    recovery=core.recovery(p,key,saved);restored=fill(saved,recovery['plan'])
    assert core.values(restored)==core.values(page)
    wrong=copy.deepcopy(restored);wrong['state_metadata']['items'][-1]['status']='complete'
    with pytest.raises(ProfileError):core.verify(p,key,wrong,revisited_after_save=True,restoration=True)
    assert p['checkpoints'][key]['journal'] is not None
    assert core.verify(p,key,restored,revisited_after_save=True,restoration=True)['verified']


@pytest.mark.parametrize('change',['missing_fact','changed_source','missing_revisit','wrong_term','unrelated_status','incomplete_recovery'])
def test_interruptions_and_mismatches_keep_journal_until_verified(change):
    p,t,page,ctx=setup(complete=False);r=core.prepare(p,t,REF,page,ctx);key=r['checkpoint_id'];saved=fill(page,r['plan'])
    if change=='missing_fact':del p['facts'][p['facts'][REF]['value']['courses'][0]['terms_ref']]
    if change=='changed_source':p['facts'][p['facts'][REF]['value']['courses'][0]['subject_ref']]['value']='Fictional alternative'
    if change=='wrong_term':saved['fields'][5]['value']=['Second Semester']
    if change=='unrelated_status':saved['state_metadata']['items'][-1]['status']='complete'
    try:
        result=(core.recovery(p,key,saved) if change=='incomplete_recovery' else core.verify(p,key,saved,revisited_after_save=change!='missing_revisit'))
        assert result.get('verified') is False
    except ProfileError:pass
    assert p['checkpoints'][key]['journal'] is not None


@pytest.mark.parametrize('change',['unknown_field','row_gap','new_instructions','bad_terms','duplicate_options','different_origin','populated_count_change','populated_schedule_change'])
def test_unknown_shapes_and_populated_structural_changes_stop_before_input(change):
    p,t,page,ctx=setup();rows=page['common_current']['rows']
    if change=='unknown_field':page['fields'].append({**page['fields'][0],'key':'i:consent'})
    if change=='row_gap':rows[0].pop('subject')
    if change=='new_instructions':page['common_current']['content_sha256']='0'*64
    if change=='bad_terms':page['fields'][5]['value']=['First Semester','First Semester']
    if change=='duplicate_options':page['choice_observations'][rows[0]['subject']]*=2
    if change=='different_origin':page['url']='https://other.invalid'+core.PATH
    if change=='populated_count_change':
        p['facts'][REF]['value']['courses'].pop()
        p['facts'][p['facts'][REF]['value']['enrollment_ref']]['value']=p['facts'][REF]['value']['courses'][0]['record_ids']
    if change=='populated_schedule_change':p['facts'][p['facts'][REF]['value']['scheduling_ref']]['value']='Yearly'
    with pytest.raises(ProfileError):core.preview(p,t,REF,page)
    assert not p['checkpoints']
