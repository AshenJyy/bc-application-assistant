"""Invented BC records: first-use academic rows, source gates and one-file recovery."""
import copy
import io
import json
from pathlib import Path

import pytest

from bc_application import common_academic as ca
from bc_application.academic import compile_report
from bc_application.browser import digest,values,validate_observation
from bc_application.profile import ProfileError,create_profile,add_statement,set_fact,add_target
from bc_application.store import ProfileStore,ProfileSnapshot

REF='education.reporting.grade_9'


def scenario():
    p=create_profile(Path(__file__).parent/'fixtures/synthetic_academic_psr.pdf')
    s=add_statement(p,'Fictional student supplied the exact schools, schedule and classifications.')
    target=add_target(p,system='common_app',school='Fictional target',program=None,source_id=s)
    report={'schema':'academic-report/1','grade':'9','transcripts':[]}
    for n,(record,scale,schedule,term,na) in enumerate([
        (p['academic']['courses'][0],'Other','Semesters','semester_2',True),
        (next(c for c in p['academic']['courses'] if c['raw_cells']['course_code']=='MTEST10---'),'1-100','Yearly','final',False)],1):
        base=f'education.reporting.t{n}'
        refs={}
        for key,value in {'school_name':f'Fictional Secondary {n}','school_year':'2023-24','grading_scale':scale,'schedule':schedule}.items():
            refs[key]=base+'.'+key;set_fact(p,refs[key],value,s)
        for key,value in {'subject':'Other/Elective','level':'Regular/Standard','credits_na':na}.items():set_fact(p,base+'.'+key,value,s)
        rid=record['record_id']
        course={'record_id':rid,'subject_ref':base+'.subject','level_ref':base+'.level','credits_na_ref':base+'.credits_na',
            'grade_terms':{term:f'psr:{rid}:{ca.CONTRACT["scales"][scale]}'},
            'credit_terms':{} if na else {term:f'psr:{rid}:credits'}}
        report['transcripts'].append({'key':f'transcript_{n}','psr_school_id':f'9999000{n}','header_refs':refs,'courses':[course]})
    set_fact(p,REF,report,s)
    context={'browser_family':'edge','transport':'extension','origin':'http://127.0.0.1:8765','access_verified':True,'synthetic_test':True}
    return p,target,context


def page(config=None,old=None,*,saved=False):
    config=config or [{'headers':{},'rows':2}];old=old or {};fields=[];groups=[];pending=[];native=[];choices={}
    def field(key,label,value='',control='text',required=False,**extra):
        selector_key=key.split('@')[0]
        f=dict(key='i:'+key,selector=f'[id="{selector_key}"]',selector_count=1,selector_index=0,name='',label=label,group='',
            control=control,value=old.get('i:'+key,value),required=required,disabled=False,readonly=False,invalid=False,options=[])
        f.update(extra)
        fields.append(f)
        if control=='material_select':
            options=list(dict.fromkeys(['Select','Fictional Secondary 1','Fictional Secondary 2','2023-24','Other','1-100',
                'Semesters','Yearly','Other/Elective','Regular/Standard','84','78','92',str(f['value'])]))
            choices[f['key']]=[{'label':v,'value':v,'disabled':False} for v in options]
        return f
    for n,item in enumerate(config,1):
        for key,label in ca.CONTRACT['headers'].items():
            field(f'{ca.HEADER_IDS[key]}Control{n}',f'Transcript {n} {label}',item['headers'].get(key,'Select'),'material_select',True)
        headers={key:fields[-4+i]['value'] for i,key in enumerate(ca.CONTRACT['headers'])}
        terms=ca.CONTRACT['schedules'].get(headers['schedule'],[]) if headers['grading_scale']!='Select' else []
        native.append({'number':n,'selector':f'ca-cng-transcript:has([id="schoolNameControl{n}"])','selector_count':1,'rows':[]})
        for index in range(1,item['rows']+1):
            row=f'T{n}C{index}';prefix=f'Transcript {n}, Course {index}, '
            field(f'subjectControl_{row}',prefix+'Subject','Select','material_select',True)
            field(f'courseNameControl_{row}',prefix+'Course Nameundefined',required=True)
            field(f'levelControl_{row}',prefix+'Course Level','Select','material_select',True)
            native[-1]['rows'].append({'number':index,'selector':f'ca-cng-course:has([id="courseNameControl_{row}"])','selector_count':1,
                'remove_label':f'Remove transcript {n}, course {index} of {item["rows"]}, Opens dialog' if index>1 else None})
            if not terms:pending.append(row);continue
            for kind in ['grades','credits']:
                keys=[]
                for offset,term in enumerate(terms):
                    label=ca.CONTRACT['terms'][term];other=kind=='grades' and headers['grading_scale']=='Other'
                    if other:key=f'gradeControl_{row}'+(f'@{offset}' if len(terms)>1 else '')
                    else:key=('grade' if kind=='grades' else 'credit')+{'semester_1':'1','semester_2':'2','final':'Final'}[term]+f'Control_{row}'
                    extra={'requirement_group':{'row':row,'kind':kind}}
                    if other:extra.update(selector_count=len(terms),selector_index=offset)
                    f=field(key,prefix+label+('undefined' if other else ' Grade' if kind=='grades' else ' Credits' if term=='final' else ' Credit'),
                        control='material_select' if kind=='grades' and not other else 'text',**extra)
                    if kind=='credits':f['readonly']=old.get(f'i:creditNA_{row}-input',False)
                    keys.append(f['key'])
                groups.append({'row':row,'kind':kind,'field_keys':keys,**({'not_applicable_key':f'i:creditNA_{row}-input'} if kind=='credits' else {})})
            field(f'creditNA_{row}-input',prefix+'Credits not applicable',False,'checkbox')
    state={'schema':'observed-state/1','coverage':'common_app_visible_navigation','current_page_key':'tertiaryNavItem13_55',
        'items':[{'key':'secondaryNavItem13','status':'incomplete'},{'key':'tertiaryNavItem13_55','status':'incomplete'},
            {'key':'secondaryNavItem3','status':'complete'}]}
    parent={'schema':'grade-parent/1','url':'http://127.0.0.1:8765/common/13/55','heading':'9th Grade',
        'controls_sha256':digest([]),'values_sha256':digest(False),'summary_sha256':digest(config if saved else 'Original blank'),
        'completion_checked':False,'state_metadata':state,'counts':[{'complete':c['rows'],'incomplete':0} for c in config] if saved else [],
        'reopen_action':{'key':'i:addCG','label':'Edit 9th grade','selector':'[id="addCG"]','disabled':False}}
    return {'schema':'observed-page/1','url':parent['url'],'title':ca.CONTRACT['title'],'frames_present':False,'fields':fields,
        'actions':[{'key':'i:changePreferencesClose','label':'Close dialog','selector':'[id="changePreferencesClose"]','disabled':False},
            {'key':'a:Continue, Closes dialog:1','label':'Continue, Closes dialog','selector':None,'disabled':False}],
        'scope':{'kind':'common_app_grade_creation','name':'Courses & Grades','heading':'Courses & Grades – 9th grade'},
        'common_academic':{'schema':'common-academic-page/1','pending_rows':pending,'instructions':ca.CONTRACT['instructions']},
        'academic_layout':{'schema':'common-academic-layout/1','transcripts':native},'requirement_groups':groups,
        'editor_state':parent,'state_metadata':state,'choice_observations':choices}


def transition(current,plan):
    config=[{'headers':{key:f['value'] for key,f in group['headers'].items()},'rows':len(group['rows'])} for group in ca.layout(current).values()]
    original=values(current);stage=plan['stage']
    if stage=='add_transcript':config.append({'headers':{},'rows':2})
    elif stage=='add_course':config[plan['transcript']-1]['rows']+=1
    elif stage=='remove_placeholder':config[plan['transcript']-1]['rows']-=1
    else:
        for write in plan['writes']:original[write['field_key']]=write['value']
    return page(config,original)


def complete(p,t,ctx,start=None):
    current=start or page();first=ca.prepare(p,t,REF,current,ctx);key=first['checkpoint_id'];stages=[]
    for _ in range(40):
        result=ca.advance(p,key,current);assert result['ready'],result
        plan=result['plan'];stages.append(plan['stage']);current=transition(current,plan)
        if plan['stage']=='fields':
            config=[{'headers':{k:f['value'] for k,f in v['headers'].items()},'rows':len(v['rows'])} for v in ca.layout(current).values()]
            return key,page(config,values(current),saved=True),stages
    raise AssertionError('Creation did not terminate')


def test_empty_to_two_schools_mixed_scale_semester_yearly_saved_without_attestation():
    p,t,ctx=scenario();original=copy.deepcopy(p['academic']);key,saved,stages=complete(p,t,ctx)
    assert {'header','remove_placeholder','add_transcript','credit_mode','fields'}<=set(stages)
    result=ca.verify(p,key,saved,revisited_after_save=True)
    assert result['verified'] and result['courses']==2 and result['student_completion_action_required']
    assert p['academic']==original and p['checkpoints'][key]['journal'] is None
    assert [f['value'] for f in saved['fields'] if f['value'] in {'PRF','84'}]==['PRF','84']


@pytest.mark.parametrize('stage',['initial','header','add_transcript','credit_mode','fields'])
def test_restart_keeps_original_journal_and_adds_only_missing_rows(stage,tmp_path):
    p,t,ctx=scenario();original=page();key=ca.prepare(p,t,REF,original,ctx)['checkpoint_id'];current=original
    for _ in range(40):
        plan=ca.advance(p,key,current)['plan']
        if stage=='initial':break
        current=transition(current,plan)
        if plan['stage']==stage:break
    store=ProfileStore(tmp_path/'applicant.json');snapshot=ProfileSnapshot(p,None);store.save(snapshot)
    loaded=store.load();journal=copy.deepcopy(loaded.data['checkpoints'][key]['journal'])
    for _ in range(40):
        result=ca.advance(loaded.data,key,current);assert result['ready']
        plan=result['plan'];current=transition(current,plan)
        if plan['stage']=='fields':break
    assert loaded.data['checkpoints'][key]['journal']==journal==values(original)
    config=[{'headers':{k:f['value'] for k,f in v['headers'].items()},'rows':len(v['rows'])} for v in ca.layout(current).values()]
    assert ca.verify(loaded.data,key,page(config,values(current),saved=True),revisited_after_save=True)['verified']
    store.save(loaded);assert len(list(tmp_path.glob('*.json')))==1


@pytest.mark.parametrize('change',['missing_psr','missing_fact','conflict','exam_grade','foreign_record','missing_mark','wrong_scale','unknown_schedule'])
def test_no_row_creation_without_all_original_sources(change,tmp_path):
    p,t,ctx=scenario();report=p['facts'][REF]['value'];course=report['transcripts'][0]['courses'][0]
    if change=='missing_psr':p['sources'][p['psr_source_id']]['path']=str(tmp_path/'absent.pdf')
    if change=='missing_fact':del p['facts'][course['subject_ref']]
    if change=='conflict':set_fact(p,course['subject_ref'],'Science',add_statement(p,'Conflicting invented answer.'))
    if change=='exam_grade':course['grade_terms']={'semester_2':'exams.ap.score'}
    if change=='foreign_record':course['grade_terms']={'semester_2':f'psr:{p["academic"]["courses"][1]["record_id"]}:school_percent'}
    if change=='missing_mark':course['grade_terms']={'semester_2':f'psr:{course["record_id"]}:school_percent'}
    if change=='wrong_scale':p['facts'][report['transcripts'][0]['header_refs']['grading_scale']]['value']='1-100'
    if change=='unknown_schedule':p['facts'][report['transcripts'][0]['header_refs']['schedule']]['value']='Quarters'
    before=copy.deepcopy(p)
    try:assert not ca.prepare(p,t,REF,page(),ctx)['ready']
    except ProfileError:pass
    assert p==before and not p['checkpoints']


@pytest.mark.parametrize('change',['instructions','term_identity','extra_field','missing_owner','wrong_path','attest_field'])
def test_changed_public_contract_stops_before_input(change):
    p,t,ctx=scenario();configured=[{'headers':{'school_name':'Fictional Secondary 1','school_year':'2023-24','grading_scale':'Other','schedule':'Semesters'},'rows':1}]
    current=page(configured)
    if change=='instructions':current['common_academic']['instructions']=['Unknown instruction']
    if change=='term_identity':current['fields'][7]['key']='i:gradeControl_T2C1@0'
    if change=='extra_field':current['fields'].append({**current['fields'][4],'key':'i:new','label':'Unknown'})
    if change=='missing_owner':current['academic_layout']['transcripts'][0]['selector_count']=2
    if change=='wrong_path':current['url']='http://127.0.0.1:8765/common/13/58'
    if change=='attest_field':current['fields'].append({**current['fields'][4],'key':'i:attest','label':'I certify'})
    with pytest.raises(ProfileError):ca.prepare(p,t,REF,current,ctx)
    assert not p['checkpoints']


@pytest.mark.parametrize('change',['name','extra_populated','header'])
def test_existing_conflict_blocks_before_earlier_add_or_header(change):
    p,t,ctx=scenario();current=page()
    f=next(f for f in current['fields'] if f['key']==('i:courseNameControl_T1C2' if change=='extra_populated' else 'i:courseNameControl_T1C1' if change=='name' else 'i:schoolYearControl1'))
    f['value']='Unrelated existing record'
    with pytest.raises(ProfileError,match='conflicting|populated'):ca.prepare(p,t,REF,current,ctx)
    assert not p['checkpoints']


@pytest.mark.parametrize('change',['invalid','counts','not_revisited','attestation','other_status','source'])
def test_saved_mismatch_keeps_recovery_journal(change):
    p,t,ctx=scenario();key,saved,_=complete(p,t,ctx);journal=copy.deepcopy(p['checkpoints'][key]['journal'])
    if change=='invalid':saved['fields'][4]['invalid']=True
    if change=='counts':saved['editor_state']['counts'][0]['complete']=5
    if change=='attestation':saved['editor_state']['completion_checked']=True
    if change=='other_status':saved['state_metadata']['items'][-1]['status']='incomplete'
    if change=='source':p['facts']['education.reporting.t1.level']['value']='Honors'
    try:assert not ca.verify(p,key,saved,revisited_after_save=change!='not_revisited')['verified']
    except ProfileError:pass
    assert p['checkpoints'][key]['journal']==journal


def test_unsaved_cancel_requires_exact_independent_saved_original():
    p,t,ctx=scenario();original=page();key=ca.prepare(p,t,REF,original,ctx)['checkpoint_id']
    assert not ca.cancel(p,key,original,revisited_saved_draft=False)['restored']
    assert ca.cancel(p,key,original,revisited_saved_draft=True)=={'restored':True,'restore_save_performed':False}
    assert p['checkpoints'][key]['journal'] is None


@pytest.mark.parametrize('flag',['real_account_test','restore_after_test'])
def test_real_account_new_record_qa_is_not_an_intended_update(flag):
    p,t,ctx=scenario();ctx[flag]=True
    with pytest.raises(ProfileError,match='intended_update_only|restoration_not_established'):ca.prepare(p,t,REF,page(),ctx)
    assert not p['checkpoints']


def test_report_stores_references_not_duplicate_marks_or_course_names():
    p,_,_=scenario();report=p['facts'][REF]['value'];compiled=compile_report(p,REF)
    assert compiled['ready']
    assert 'SYNTHETIC COURSE 9' not in json.dumps(report) and 'PRF' not in json.dumps(report)


def test_more_than_default_two_rows_creates_only_the_missing_course():
    p,t,ctx=scenario();report=p['facts'][REF]['value'];report['transcripts']=report['transcripts'][:1]
    template=report['transcripts'][0]['courses'][0]
    for record in p['academic']['courses'][1:3]:
        course=copy.deepcopy(template);course['record_id']=record['record_id']
        course['grade_terms']={'semester_1':f'psr:{record["record_id"]}:school_grade_symbol'}
        report['transcripts'][0]['courses'].append(course)
    key,saved,stages=complete(p,t,ctx)
    assert stages.count('add_course')==1 and 'remove_placeholder' not in stages
    assert ca.verify(p,key,saved,revisited_after_save=True)['courses']==3


def test_existing_original_header_is_protected_during_resume():
    p,t,ctx=scenario();original=page();original['fields'][0]['value']='Fictional Secondary 1'
    key=ca.prepare(p,t,REF,original,ctx)['checkpoint_id'];current=copy.deepcopy(original)
    current['fields'][0]['value']='Select';before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='original_academic_record_changed'):ca.advance(p,key,current)
    assert p==before


def test_preview_missing_choices_does_not_create_a_checkpoint():
    p,t,ctx=scenario();original=page();original['choice_observations']={};before=copy.deepcopy(p)
    result=ca.prepare(p,t,REF,original,ctx)
    assert not result['ready'] and result['source_ready'] and result['next']['stage']=='choices' and p==before


def test_duplicate_report_record_is_rejected_before_any_creation():
    p,t,ctx=scenario();report=p['facts'][REF]['value'];report['transcripts'][0]['courses']*=2
    with pytest.raises(ProfileError,match='unique_original_academic_record'):ca.prepare(p,t,REF,page(),ctx)
    assert not p['checkpoints']


@pytest.mark.parametrize('change',['school','grade','year'])
def test_original_psr_school_grade_and_year_attribution_are_required(change):
    p,t,ctx=scenario();report=p['facts'][REF]['value']
    if change=='school':report['transcripts'][0]['psr_school_id']='99990002'
    if change=='grade':report['grade']='10'
    if change=='year':
        # A source-preserving reporting API may never merge original contexts.
        course=copy.deepcopy(report['transcripts'][0]['courses'][0]);course['record_id']=p['academic']['courses'][-1]['record_id']
        course['grade_terms']={'semester_2':f'psr:{course["record_id"]}:school_grade_symbol'}
        report['transcripts'][0]['courses'].append(course)
        report['transcripts']=report['transcripts'][:1]
    with pytest.raises(ProfileError,match='attribution_conflict|school_year_conflict'):ca.prepare(p,t,REF,page(),ctx)
    assert not p['checkpoints']


def test_cli_preview_is_byte_identical_and_staged_restart_cancel_uses_one_json(tmp_path,monkeypatch,capsys):
    from bc_application.cli import main
    p,t,ctx=scenario();store=ProfileStore(tmp_path/'applicant.json');store.save(ProfileSnapshot(p,None));before=store.path.read_bytes()
    def call(command,payload,*extra):
        monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(payload)))
        code=main([command,'--profile',str(store.path),*extra]);result=json.loads(capsys.readouterr().out)
        assert code==0,result
        return result
    assert call('common-academic-preview',{'page':page()},'--target',t,'--report-ref',REF)['ready']
    assert store.path.read_bytes()==before
    result=call('common-academic-prepare',{'page':page(),'context':ctx},'--target',t,'--report-ref',REF)
    key=result['checkpoint_id'];current=transition(page(),result['plan'])
    call('common-academic-advance',{'page':current},'--checkpoint',key)
    assert call('common-academic-cancel',{'page':page(),'revisited_saved_draft':True},'--checkpoint',key)['restored']
    assert store.load().data['checkpoints'][key]['journal'] is None
