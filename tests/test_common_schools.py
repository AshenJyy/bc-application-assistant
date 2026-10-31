"""Invented school identities, PSR enrollment references, statements and restart."""
import copy
import io
import json
from pathlib import Path

import pytest

from bc_application import common_schools as ca,schools
from bc_application.browser import digest
from bc_application.profile import ProfileError,create_profile,add_statement,set_fact,add_target
from bc_application.store import ProfileStore,ProfileSnapshot,StoreError

REF='education.school_reports.current'


def lookup(school_id='99990002',*,base='http://127.0.0.1:8765',other=False):
    n=school_id[-1];name='Fictional Secondary '+n;question='256' if other else '245'
    return {'schema':'observed-school-lookup/1','title':'High School Lookup','page_url':base+('/common/4/19' if other else '/common/4/18'),
        'question_id':question,'search_by':'High School Name','query':name,'query_key':'searchTermControl'+question,'total':1,'loading':False,
        'options':[{'kind':'school','name':name,'city':'Invented City','region':'BC','country':'Canada','ceeb':'12345'+n,
            'label':name+' Invented City, BC, Canada | CEEB: 12345'+n,'selector':f'[id="selectionListResult100{n}-"]','selector_count':1,'selected':False},
            {'kind':'manual','label':'Homeschooled'},{'kind':'manual','label':"I don't see my high school in this list"}]}


def scenario(kind='current',*,early=False):
    p=create_profile(Path(__file__).parent/'fixtures/synthetic_academic_psr.pdf');s=add_statement(p,'Fictional student supplied a complete school list, boarding/graduation/progression facts and these factual explanations.')
    t=add_target(p,system='common_app',school='Fictional university',program=None,source_id=s)
    context={'browser_family':'edge','transport':'extension','access_verified':True,'origin':'http://127.0.0.1:8765','synthetic_test':True}
    for key in ('99990001','99990002'):assert schools.remember_lookup(p,key,lookup(key),context)['ready']
    facts={'education.current_school_id':'99990002','education.boarding':False,'education.will_graduate':True,
        'education.graduation_date':'2027-01' if early else '2027-06','education.progression':['early'] if early else ['unchanged'],
        'education.explanations.school_progression':'I expect to graduate in January 2027 after completing the requirements. I plan to begin university in fall 2027.',
        'education.explanations.school_transfer':'I transferred to access courses that were not offered at my previous school.'}
    for ref,value in facts.items():set_fact(p,ref,value,s)
    report={'schema':'school-report/1','kind':kind,'current_school_ref':'education.current_school_id',
        'schools':[{'psr_school_id':'99990002' if kind=='current' else '99990001',
            'entry_ref':'psr-school:'+('99990002' if kind=='current' else '99990001')+':0:admit_date',
            'exit_ref':None if kind=='current' else 'psr-school:99990001:0:withdrawal_date'}],
        'boarding_ref':'education.boarding' if kind=='current' else None,'graduate_ref':'education.will_graduate' if kind=='current' else None,
        'graduation_ref':'education.graduation_date' if kind=='current' else None,'progression_ref':'education.progression' if kind=='current' else None,
        'explanation_ref':schools.STATEMENTS[kind] if kind=='other' or early else None}
    ref='education.school_reports.'+kind;set_fact(p,ref,report,s)
    return p,t,ref,context


def page(kind='current',*,old=None,cards=None,count='',saved=False,all_complete=False):
    old=old or {};s=ca.CONTRACT[kind];fields=[]
    def field(key,label,control,value='',required=True,group='',**extra):
        f={'key':key,'label':label,'control':control,'value':old.get(key,value),'required':required,'group':group,'name':'',
            'selector':f'[id="{key[2:]}"]' if key.startswith('i:') else None,'selector_count':1,'selector_index':0,
            'options':[],'disabled':False,'readonly':False,'invalid':False,**extra}
        fields.append(f);return f
    def radio(item,labels,default=''):
        f=field(item['key'],item['label'],'radio',default,group=item['label'],name='mat-radio-group-100')
        q=item['key'].removeprefix('r:ques_')
        f['options']=[{'label':label,'value':str(index),'selector':f'[id="option_ques_{q}_{1000+index}-input"]','selector_count':1,'selector_index':0,'disabled':False} for index,label in enumerate(labels)]
        f['selector']=f['options'][0]['selector'];return f
    if kind=='current':
        n=1;radio(s['boarding'],['Yes','No']);grad=radio(s['graduate'],['Yes','No'])
        if grad['value']=='0':field(s['graduation']['key'],s['graduation']['label'],'text')
        for p in ca.CONTRACT['progression']:
            field('g:265:'+p['part'],p['label'],'checkbox',False,False,ca.CONTRACT['progression_label'],
                selector=f'fieldset:has([id="title_ques_265"]) input[type="checkbox"][value="{p["value"]}"]')
        note=any(old.get('g:265:'+p['part'],False) for p in ca.CONTRACT['progression'] if p['part']!='unchanged')
    else:
        chosen=radio(s['count'],[str(i) for i in range(4)],count)['value'];n=int(chosen or 0);note=n>0
    for r in s['records'][:n]:
        field(r['entry_key'],r['entry_label'],'text')
        if kind=='other':field(r['exit_key'],r['exit_label'],'text')
    if note:
        q=s['statement']['question_id'];key='statement:'+q;value=old.get(key,'')
        field(key,s['statement']['label'],'school_statement',selector=f'[role="textbox"][contenteditable="true"][aria-labelledby="title_ques_{q}"]',
            statement_format=old.get('@statement_formats',{}).get(key,'plain_paragraph' if value else 'empty'))
    num=s['path'].split('/')[-1];current='tertiaryNavItem4_'+num
    state={'schema':'observed-state/1','coverage':'common_app_visible_navigation','current_page_key':current,
        'items':[{'key':'secondaryNavItem4','status':'complete' if all_complete else 'in progress'},
            {'key':current,'status':'complete' if saved or all_complete else 'incomplete'},
            {'key':'tertiaryNavItem4_'+('19' if kind=='current' else '18'),'status':'complete' if all_complete else 'not started'},
            {'key':'secondaryNavItem3','status':'complete'}]}
    records=[{k:r[k] for k in ('question_id','label')} for r in s['records'][:n]]
    return {'schema':'observed-school-page/1','url':'http://127.0.0.1:8765'+s['path'],'title':ca.CONTRACT['title'],'heading':s['heading'],
        'frames_present':False,'fields':fields,'actions':[{'key':'i:sectionContinue'+num,'selector':f'[id="sectionContinue{num}"]','label':'Continue to next section','disabled':False}],
        'common_school':{'schema':'common-school-page/1','kind':kind,'records':records},
        'school_values':{r['question_id']:copy.deepcopy((cards or {}).get(r['question_id'])) for r in records},'state_metadata':state}


def card(identity):
    return {'name':identity['name'],'ceeb':identity['ceeb'],'text':identity['name']+'\n1 Invented Street\nInvented City, BC\nCAN\nIndependent\nCEEB Code : '+identity['ceeb']}


def transition(current,plan,*,saved=False,all_complete=False):
    v=ca.values(current);cards=copy.deepcopy(current['school_values'])
    if plan['stage']=='school':cards[plan['question_id']]=card(plan['identity'])
    else:
        for w in plan['writes']:
            v[w['field_key']]=w['value']
            if w['field_key'].startswith('statement:'):v['@statement_formats'][w['field_key']]='plain_paragraph'
    kind=current['common_school']['kind']
    return page(kind,old=v,cards=cards,count=v.get('r:ques_255',''),saved=saved,all_complete=all_complete)


def complete(p,t,ref,ctx,current):
    first=ca.prepare(p,t,ref,current,ctx);key=first['checkpoint_id'];stages=[]
    for _ in range(15):
        result=ca.advance(p,key,current);plan=result['plan'];stages.append(plan['stage']);current=transition(current,plan)
        if plan['stage']=='fields':return key,transition(current,plan,saved=True),stages
    raise AssertionError('school_stages_did_not_terminate')


@pytest.mark.parametrize('kind,early',[('current',False),('current',True),('other',False)])
def test_empty_school_to_whole_saved_page_uses_psr_and_student_statements(kind,early):
    p,t,ref,ctx=scenario(kind,early=early);raw=copy.deepcopy(p['academic']);key,saved,stages=complete(p,t,ref,ctx,page(kind))
    assert 'school' in stages and stages[-1]=='fields'
    assert ca.verify(p,key,saved,revisited_after_save=True)['verified']
    assert p['academic']==raw and p['checkpoints'][key]['journal'] is None
    assert saved['fields'] and next(f['value'] for f in saved['fields'] if f['key']==ca.CONTRACT[kind]['records'][0]['entry_key'])==('February 2024' if kind=='current' else 'September 2023')


@pytest.mark.parametrize('stage',['initial','school','graduation_mode','progression_mode','fields'])
def test_single_json_restart_preserves_original_and_does_not_duplicate_school(stage,tmp_path):
    p,t,ref,ctx=scenario(early=True);current=page();original=ca.values(current);key=ca.prepare(p,t,ref,current,ctx)['checkpoint_id']
    for _ in range(15):
        plan=ca.advance(p,key,current)['plan']
        if stage=='initial':break
        current=transition(current,plan)
        if plan['stage']==stage:break
    store=ProfileStore(tmp_path/'applicant.json');store.save(ProfileSnapshot(p,None));snapshot=store.load()
    for _ in range(15):
        plan=ca.advance(snapshot.data,key,current)['plan'];current=transition(current,plan)
        assert snapshot.data['checkpoints'][key]['journal']==original
        if plan['stage']=='fields':break
    assert ca.verify(snapshot.data,key,transition(current,plan,saved=True),revisited_after_save=True)['verified']
    store.save(snapshot);assert len(list(tmp_path.glob('*.json')))==1


@pytest.mark.parametrize('change',['missing_psr','missing_fact','conflict','bad_progression','bad_date','missing_statement','wrong_statement_scope','wrong_current_school','foreign_date_reference','directory_missing'])
def test_all_required_school_sources_precede_any_record_creation(change,tmp_path):
    p,t,ref,ctx=scenario(early=True);report=p['facts'][ref]['value']
    if change=='missing_psr':p['sources'][p['psr_source_id']]['path']=str(tmp_path/'missing.pdf')
    if change=='missing_fact':del p['facts']['education.boarding']
    if change=='conflict':set_fact(p,'education.boarding',True,add_statement(p,'Conflicting fictional answer.'))
    if change=='bad_progression':p['facts']['education.progression']['value']=['early','unchanged']
    if change=='bad_date':p['facts']['education.graduation_date']['value']='2027-99'
    if change=='missing_statement':del p['facts']['education.explanations.school_progression']
    if change=='wrong_statement_scope':report['explanation_ref']='education.unrelated_note'
    if change=='wrong_current_school':p['facts']['education.current_school_id']['value']='99990001'
    if change=='foreign_date_reference':report['schools'][0]['entry_ref']='psr-school:99990001:0:admit_date'
    if change=='directory_missing':p.pop('school_directory')
    before=copy.deepcopy(p)
    try:assert not ca.prepare(p,t,ref,page(),ctx)['ready']
    except ProfileError:pass
    assert p==before and not p['checkpoints']


@pytest.mark.parametrize('change',['incomplete','ambiguous','wrong_region','name_mismatch','duplicate_code','special_option','wrong_origin','missing_psr'])
def test_directory_requires_complete_unique_source_name_bc_match(change,tmp_path):
    p,t,ref,ctx=scenario();result=lookup()
    if change=='incomplete':result['total']=10
    if change=='ambiguous':result['options'].insert(1,{**result['options'][0],'ceeb':'654321','label':'Another exact-name BC match','selector':'[id="selectionListResult1008-"]'});result['total']=2
    if change=='wrong_region':result['options'][0]['region']='ON'
    if change=='name_mismatch':result['options'][0]['name']='A different school'
    if change=='duplicate_code':result['options'].insert(1,copy.deepcopy(result['options'][0]));result['total']=2
    if change=='special_option':result['options']=[{'kind':'manual','label':"I don't see my high school in this list"}];result['total']=0
    if change=='wrong_origin':result['page_url']='https://example.org/common/4/18'
    if change=='missing_psr':p['sources'][p['psr_source_id']]['path']=str(tmp_path/'gone.pdf')
    before=copy.deepcopy(p)
    try:assert not schools.resolve_lookup(p,'99990002',result)['ready']
    except ProfileError:pass
    assert p==before


def test_one_directory_identity_is_reused_across_common_app_targets():
    p,t,ref,ctx=scenario();before=copy.deepcopy(p['school_directory'])
    source=add_statement(p,'Fictional student adds another university.');add_target(p,system='common_app',school='Another fictional university',program=None,source_id=source)
    result=schools.remember_lookup(p,'99990002',lookup(),ctx)
    assert result['reused'] and not result['profile_changed'] and p['school_directory']==before


@pytest.mark.parametrize('change',['extra_field','statement_prompt','statement_owner','school_owner','radio_option','date_selector','checkbox_selector','frame'])
def test_new_or_cross_question_controls_never_get_a_school_plan(change):
    p,t,ref,ctx=scenario(early=True);_,saved,_=complete(p,t,ref,ctx,page());p['checkpoints']={}
    if change=='extra_field':saved['fields'].append({**saved['fields'][0],'key':'i:unknown'})
    if change=='statement_prompt':saved['fields'][-1]['label']='Why do you want to attend this college?'
    if change=='statement_owner':saved['fields'][-1]['selector']='[id="essay"]'
    if change=='school_owner':saved['common_school']['records'][0]['question_id']='256'
    if change=='radio_option':saved['fields'][0]['options'][0]['label']='I agree'
    if change=='date_selector':next(f for f in saved['fields'] if f['control']=='text')['selector']='[id="wrong"]'
    if change=='checkbox_selector':next(f for f in saved['fields'] if f['control']=='checkbox')['selector']='[id="wrong"]'
    if change=='frame':saved['frames_present']=True
    with pytest.raises(ProfileError):ca.prepare(p,t,ref,saved,ctx)
    assert not p['checkpoints']


def test_existing_school_identity_conflict_stops_without_replacement():
    p,t,ref,ctx=scenario();current=page(cards={'245':card(p['school_directory']['entries']['99990001']['common_app'])})
    with pytest.raises(ProfileError,match='conflicting_existing_school'):ca.prepare(p,t,ref,current,ctx)
    assert not p['checkpoints']


@pytest.mark.parametrize('change',['not_revisited','wrong_value','wrong_school','other_status','source','format'])
def test_saved_mismatch_keeps_the_original_journal(change):
    p,t,ref,ctx=scenario(early=True);key,saved,_=complete(p,t,ref,ctx,page());original=copy.deepcopy(p['checkpoints'][key]['journal'])
    if change=='wrong_value':saved['fields'][0]['value']='0'
    if change=='wrong_school':saved['school_values']['245']['ceeb']='111111'
    if change=='other_status':saved['state_metadata']['items'][-1]['status']='incomplete'
    if change=='source':p['facts']['education.graduation_date']['value']='2028-01'
    if change=='format':saved['fields'][-1]['statement_format']='rich'
    try:assert not ca.verify(p,key,saved,revisited_after_save=change!='not_revisited')['verified']
    except ProfileError:pass
    assert p['checkpoints'][key]['journal']==original


def test_unsaved_cancel_checks_original_including_school_and_statement_format():
    p,t,ref,ctx=scenario();original=page();key=ca.prepare(p,t,ref,original,ctx)['checkpoint_id']
    changed=transition(original,ca.advance(p,key,original)['plan'])
    assert not ca.cancel(p,key,changed,revisited_saved_draft=True)['restored']
    assert ca.cancel(p,key,original,revisited_saved_draft=True)['restored']


def test_real_account_existing_statement_polish_then_full_saved_restoration():
    p,t,ref,ctx=scenario(early=True);key,original,_=complete(p,t,ref,ctx,page());ca.verify(p,key,original,revisited_after_save=True)
    original['state_metadata']=page(saved=True,all_complete=True)['state_metadata']
    original['fields'][-1]['value']='A longer fictional original explanation with the same facts.'
    ctx.update(real_account_test=True,full_state_restoration_verified=True,restoration_strategy={'kind':'restore_completed_native_page',
        'current_page_key':original['state_metadata']['current_page_key'],'baseline_state_sha256':digest(original['state_metadata'])})
    key=ca.prepare(p,t,ref,original,ctx)['checkpoint_id'];plan=ca.advance(p,key,original)['plan'];saved=transition(original,plan,saved=True,all_complete=True)
    assert ca.verify(p,key,saved,revisited_after_save=True)['verified'] and p['checkpoints'][key]['journal'] is not None
    recover=ca.recovery(p,key,saved);restored=transition(saved,recover['plan'],saved=True,all_complete=True)
    assert ca.verify(p,key,restored,revisited_after_save=True,restoration=True)['verified'] and p['checkpoints'][key]['journal'] is None


def test_real_account_new_school_qa_stops_before_persisting():
    p,t,ref,ctx=scenario();original=page(saved=True,all_complete=True)
    ctx.update(real_account_test=True,full_state_restoration_verified=True,restoration_strategy={'kind':'restore_completed_native_page',
        'current_page_key':original['state_metadata']['current_page_key'],'baseline_state_sha256':digest(original['state_metadata'])})
    with pytest.raises(ProfileError,match='creation_or_shape_change'):ca.prepare(p,t,ref,original,ctx)
    assert not p['checkpoints']


def test_directory_cannot_change_while_a_browser_journal_is_active(tmp_path):
    p,t,ref,ctx=scenario();key=ca.prepare(p,t,ref,page(),ctx)['checkpoint_id'];store=ProfileStore(tmp_path/'applicant.json');snapshot=ProfileSnapshot(p,None);store.save(snapshot)
    snapshot.data['school_directory']['entries']['99990002']['common_app']['city']='Different city'
    with pytest.raises(StoreError,match='browser_transaction_active'):store.save(snapshot)
    assert store.load().data['checkpoints'][key]['journal'] is not None


def test_cli_preview_byte_identity_and_persisted_school_restart_cancel(tmp_path,monkeypatch,capsys):
    from bc_application.cli import main
    p,t,ref,ctx=scenario();store=ProfileStore(tmp_path/'applicant.json');store.save(ProfileSnapshot(p,None));original=store.path.read_bytes()
    def call(command,payload,*args):
        monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(payload)));code=main([command,'--profile',str(store.path),*args]);result=json.loads(capsys.readouterr().out)
        assert code==0,result;return result
    assert call('common-school-preview',{'page':page()},'--target',t,'--report-ref',ref)['ready']
    assert store.path.read_bytes()==original
    result=call('common-school-prepare',{'page':page(),'context':ctx},'--target',t,'--report-ref',ref);key=result['checkpoint_id']
    call('common-school-advance',{'page':transition(page(),result['plan'])},'--checkpoint',key)
    assert call('common-school-cancel',{'page':page(),'revisited_saved_draft':True},'--checkpoint',key)['restored']
    assert len(list(tmp_path.glob('*.json')))==1


def test_dynamic_checkbox_group_names_and_earlier_recorded_structure_allow_exact_recovery():
    p,t,ref,ctx=scenario(early=True);key,original,_=complete(p,t,ref,ctx,page());ca.verify(p,key,original,revisited_after_save=True)
    original['state_metadata']=page(saved=True,all_complete=True)['state_metadata']
    original['fields'][-1]['value']='A fictional original explanation.'
    ctx.update(real_account_test=True,full_state_restoration_verified=True,restoration_strategy={'kind':'restore_completed_native_page',
        'current_page_key':original['state_metadata']['current_page_key'],'baseline_state_sha256':digest(original['state_metadata'])})
    key=ca.prepare(p,t,ref,original,ctx)['checkpoint_id'];plan=ca.advance(p,key,original)['plan']
    # Retain a pre-normalization journal during an interrupted development upgrade.
    for f in p['checkpoints'][key]['original_structure']['fields']:
        if f['control']=='checkbox':f['name']='ca-checkboxList-5_group'
    saved=transition(original,plan,saved=True,all_complete=True)
    for f in saved['fields']:
        if f['control']=='checkbox':f['name']='ca-checkboxList-1_group'
    assert ca.verify(p,key,saved,revisited_after_save=True)['verified']
    restored=transition(saved,ca.recovery(p,key,saved)['plan'],saved=True,all_complete=True)
    assert ca.verify(p,key,restored,revisited_after_save=True,restoration=True)['verified']


@pytest.mark.parametrize('value,expected',[('24-Aug-2023','August 2023'),('25-aug-2025','August 2025'),('2027-01','January 2027'),('2024-02-29','February 2024')])
def test_school_month_formatting_preserves_explicit_dates(value,expected):
    assert schools.month(value)==expected


@pytest.mark.parametrize('value',['2023-02-29','31-Apr-2024','2027-13','Sep 2024','2024','01-XYZ-2024'])
def test_school_dates_never_guess_missing_or_invalid_components(value):
    with pytest.raises(ProfileError,match='explicit_school_month'):schools.month(value)


def test_missing_psr_enrollment_needs_transcript_and_student_clarification():
    from bc_application.profile import academic_digest
    p,t,ref,ctx=scenario();p['academic']['schools'][1]['enrollments'][0]['raw_cells']['admit_date']=''
    p['academic_sha256']=academic_digest(p['academic'])
    report=p['facts'][ref]['value'];report['schools'][0]['entry_ref']='education.school_entry_date'
    set_fact(p,'education.school_entry_date','2024-02',add_statement(p,'Fictional student supplies an otherwise missing school date.'))
    result=ca.preview(p,t,ref,page());assert not result['ready']
    assert any(b['reason']=='missing_school_date_requires_transcript_and_clarification' for b in result['blockers'])


def test_explicit_school_date_cannot_disagree_with_original_psr_month():
    p,t,ref,ctx=scenario();p['facts'][ref]['value']['schools'][0]['entry_ref']='education.school_entry_date'
    set_fact(p,'education.school_entry_date','2024-09',add_statement(p,'A conflicting fictional date.'))
    with pytest.raises(ProfileError,match='original_school_date_conflict'):ca.preview(p,t,ref,page())


def test_rich_statement_original_requires_a_separate_restoration_method():
    p,t,ref,ctx=scenario(early=True);key,original,_=complete(p,t,ref,ctx,page());ca.verify(p,key,original,revisited_after_save=True)
    original['fields'][-1]['value']='An original rich explanation.';original['fields'][-1]['statement_format']='rich'
    key=ca.prepare(p,t,ref,original,ctx)['checkpoint_id']
    with pytest.raises(ProfileError,match='rich_school_statement_rollback'):ca.recovery(p,key,original)
