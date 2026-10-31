"""Clean extracted-plugin/offline-runtime smoke test; synthetic input only."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
import runpy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.validate_plugin import validate_archive

ROOT = Path(__file__).resolve().parents[1]


def verify(archive: Path, node: Path) -> dict:
    report = validate_archive(archive)
    workspace = ROOT / "work"
    workspace.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-check-", dir=workspace) as temporary:
        isolated = Path(temporary).resolve()
        if not isolated.is_relative_to(workspace.resolve()):
            raise ValueError("Unexpected verification target")
        plugin = isolated / "plugin"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(plugin)
        if not (plugin / "plugin.json").exists():
            plugin = next(p.parent for p in plugin.glob("*/plugin.json"))
        skill = plugin / "skills/bc-application"
        modules=sorted((skill/'scripts').glob('*.mjs'))
        js_smoke="const {pathToFileURL}=await import('node:url');for(const file of JSON.parse(process.argv[1]))await import(pathToFileURL(file).href);"
        js_check=subprocess.run([str(node.resolve()),'--input-type=module','-e',js_smoke,
            json.dumps([str(p.resolve()) for p in modules])],capture_output=True,text=True,cwd=isolated)
        if not modules or js_check.returncode:
            raise RuntimeError('Clean extracted host module import failed: '+js_check.stderr)
        report['extracted_host_module_imports']=len(modules)
        setup = subprocess.run([sys.executable, str(skill / "scripts/bootstrap.py"), "--runtime-dir",
                                str(isolated / "runtime")], capture_output=True, text=True, cwd=isolated)
        if setup.returncode:
            raise RuntimeError("Offline runtime setup failed: " + setup.stderr)
        python = isolated / "runtime/Scripts/python.exe"
        version_check=subprocess.run([str(python),str(skill/'scripts/run.py'),'--version'],
            capture_output=True,text=True,cwd=isolated)
        if version_check.returncode or version_check.stdout.strip()!=report['version'].replace('-dev.','.dev'):
            raise RuntimeError('Extracted manifest/runtime version mismatch')
        output = isolated / "applicant.json"
        run = subprocess.run([str(python), str(skill / "scripts/run.py"), "profile-init", "--psr",
                              str(ROOT / "tests/fixtures/synthetic_psr.pdf"), "--profile", str(output)],
                             capture_output=True, text=True, cwd=isolated)
        if run.returncode:
            raise RuntimeError("Extracted parser failed: " + run.stdout + run.stderr)
        extracted = json.loads(output.read_text(encoding="utf-8"))
        if len(extracted["academic"]["courses"]) != 7 or len(extracted["academic"]["schools"]) != 2:
            raise RuntimeError("Synthetic release result differs from fixture")
        resumed = subprocess.run([str(python), str(skill / "scripts/run.py"), "profile-summary", "--profile",str(output)],
                                 capture_output=True,text=True,cwd=isolated)
        if resumed.returncode or json.loads(resumed.stdout)["revision"] != 1:
            raise RuntimeError("Canonical profile resume failed")
        if len(list(isolated.glob("*.json"))) != 1:
            raise RuntimeError("Unexpected duplicate applicant profile")
        # Exercise the installed adapter/checkpoint module in the clean runtime,
        # not the editable development package. No browser driver is imported.
        relay_smoke = '''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.profile import ProfileError,add_statement,add_target,set_fact,register_document,clarify_marker,review_with_document
from bc_application.evidence import render_preview
from bc_application.pages import build_plan,prepare,verify_saved
store=ProfileStore(Path(sys.argv[2])); snapshot=store.load()
source=add_statement(snapshot.data,'Invented clean-release browser test.')
set_fact(snapshot.data,'personal.legal_given_name','Synthetic',source)
target=add_target(snapshot.data,system='uc',school='Synthetic UC',program=None,source_id=source)
page={'schema':'observed-page/1','url':'http://127.0.0.1:8765/uc','title':'Synthetic','frames_present':False,
'fields':[{'key':'i:first','name':'firstName','label':'First name *','group':'','control':'text','selector':'[id="first"]',
'required':True,'disabled':False,'readonly':False,'value':'Before','options':[],'invalid':False}],
'actions':[{'key':'i:save','label':'Save draft','selector':'[id="save"]','disabled':False}]}
plan=build_plan(snapshot.data,target,page); assert plan['ready']
prepare(snapshot.data,plan['checkpoint_id'],page,{'browser_family':'edge','transport':'extension',
'origin':'http://127.0.0.1:8765','access_verified':True,'synthetic_test':True,'restore_after_test':True}); store.save(snapshot)
original_journal=dict(snapshot.data['checkpoints'][plan['checkpoint_id']]['journal'])
changed=dict(page); changed['fields']=page['fields']+[dict(page['fields'][0],key='i:new',name='lastName',selector='[id="new"]')]
try:
    build_plan(snapshot.data,target,changed)
except ProfileError as exc:
    assert str(exc)=='pending_transaction_requires_recovery'
else:
    raise AssertionError('Recovery journal can be overwritten')
assert snapshot.data['checkpoints'][plan['checkpoint_id']]['journal']==original_journal
page['fields'][0]['value']='Synthetic'
assert verify_saved(snapshot.data,plan['checkpoint_id'],page,revisited_after_save=True)['verified']
store.save(snapshot)
page['fields'][0]['value']='Before'
assert verify_saved(snapshot.data,plan['checkpoint_id'],page,revisited_after_save=True,restoration=True)['restored']
store.save(snapshot)
document=register_document(snapshot.data,Path(sys.argv[3]),kind='transcript')
try:
    set_fact(snapshot.data,'education.synthetic_document_fact','Invented',document,evidence={'page':1,'quote':'Invented nonexistent evidence'})
except ProfileError as exc:
    assert str(exc)=='evidence_quote_not_found_on_page'
else:
    raise AssertionError('Unsupported evidence was accepted')
set_fact(snapshot.data,'education.synthetic_document_fact','AP CALCULUS BC 12A',document,
    evidence={'page':2,'quote':'AP CALCULUS BC 12A 29-May-2026 A 93 93 E 4'})
store.save(snapshot)
preview=render_preview(snapshot.data,document,page=2,output=Path(sys.argv[2]).parent/'synthetic-review.png',profile_path=Path(sys.argv[2]))
assert preview['manual_review_required'] and not preview['text_extraction_performed']
record=next(c for c in snapshot.data['academic']['courses'] if c['raw_cells']['equivalency_marker'])
statement=add_statement(snapshot.data,'For this synthetic record only the marker denotes equivalency credit.',scope=[record['record_id']])
clarify_marker(snapshot.data,[record['record_id']],meaning='equivalency_credit',statement_source_id=statement)
review=record['record_id']+':equivalency_marker_requires_explanation'
review_with_document(snapshot.data,review,document,page=2,quote='AP CALCULUS BC 12A 29-May-2026 A 93 93 E 4',
    method='visual_review',bbox=[0,0,595,841])
assert snapshot.data['reviews'][review]['document_evidence']['method']=='visual_review'
store.save(snapshot)
from bc_application.adapters.mit import COURSEWORK_NOTES,STEM_STATUS_LABELS,CLASSES_INSTRUCTION,STEM_INSTRUCTION,CLASSES_HEADER
mit_target=add_target(snapshot.data,system='mit',school='Synthetic MIT',program=None,source_id=source)
mit_page={'schema':'observed-page/1','url':'http://127.0.0.1:8765/apply/frm?00000000-0000-4000-8000-000000000000',
    'title':'Synthetic MIT self-reported coursework','frames_present':False,'fields':[],
    'actions':[{'key':'i:save','label':'Save and Continue','selector':'[id="save"]','disabled':False}]}
mit_page['mit_coursework']={'schema':'mit-coursework/1','classes_instruction':CLASSES_INSTRUCTION,
    'stem_instruction':STEM_INSTRUCTION,'subject_year_pairs':[]}
mit_page['collections']=[{'kind':'editable_table','label':CLASSES_HEADER,'row_count':0,'editor_control_count':1}]
set_fact(snapshot.data,'education.current_school_country','Canada',source)
set_fact(snapshot.data,'education.us_based_school_system',False,source)
for subject in ('calculus','physics','biology','chemistry'):
    set_fact(snapshot.data,f'education.subjects.{subject}.status','taken',source)
    set_fact(snapshot.data,f'education.subjects.{subject}.year','11th',source)
    mit_page['fields'].append({'key':'i:'+subject,'name':subject,'label':subject.title()+'*','group':'',
        'control':'select','selector':'[id="'+subject+'"]','required':True,'disabled':False,'readonly':False,
        'value':'','invalid':False,'options':[{'value':value,'label':label,'disabled':False} for value,label in STEM_STATUS_LABELS.items()]})
    mit_page['fields'].append({'key':'i:'+subject+'_year','name':subject+'_year','label':'Year','group':'Year',
        'control':'select','selector':'[id="'+subject+'_year"]','required':False,'disabled':False,'readonly':False,
        'value':'','invalid':False,'options':[{'value':year,'label':year,'disabled':False} for year in ('','9th','10th','11th','12th')]})
    mit_page['mit_coursework']['subject_year_pairs'].append({'subject':subject,'status_key':'i:'+subject,'year_key':'i:'+subject+'_year'})
for index,label in enumerate(COURSEWORK_NOTES):
    mit_page['fields'].append({'key':f'i:note{index}','name':f'note{index}','label':label,'group':label,
        'control':'textarea','selector':f'[id="note{index}"]','required':False,'disabled':False,'readonly':False,
        'value':'','invalid':False,'options':[]})
mit_plan=build_plan(snapshot.data,mit_target,mit_page)
assert mit_plan['ready'] and len(mit_plan['writes'])==8
mit_page['fields'][-1]['value']='Existing synthetic note'
assert not build_plan(snapshot.data,mit_target,mit_page)['ready']
store.save(snapshot)
from bc_application.pages import recovery_bundle
from bc_application.browser import digest
uc_page=json.loads(Path(sys.argv[4]).read_text(encoding='utf-8'))
uc_page['title']='Personal information - About you - UC application'
uc_page['state_metadata']=json.loads(Path(sys.argv[5]).read_text(encoding='utf-8'))
for field,value in {'personal.legal_family_name':'Fixture','personal.has_lived_name':False,
    'personal.has_previous_legal_name':False,'education.attended_california_public_school':False,
    'personal.birth_date':'2007-03-05','personal.birth_country':'China','personal.birth_city':'Synthetic City'}.items():
    set_fact(snapshot.data,field,value,source)
for field in uc_page['fields']:field['invalid']=False
uc_initial=build_plan(snapshot.data,target,uc_page)
assert uc_initial['ready']
desired={w['field_key']:w['value'] for w in uc_initial['writes']}
for field in uc_page['fields']:field['value']=desired.get(field['key'],field['value'])
uc_page['fields'][0]['value']='SYNTHETIC'
uc_original=json.loads(json.dumps(uc_page))
uc_plan=build_plan(snapshot.data,target,uc_page,reaffirm_keys=[f['key'] for f in uc_page['fields'] if f['control']=='select' and f['required']])
assert uc_plan['ready'] and any(w['fact_ref']=='personal.birth_city' for w in uc_plan['writes'])
uc_context={'browser_family':'edge','transport':'extension','origin':'https://apply.universityofcalifornia.edu',
    'access_verified':True,'real_account_test':True,'full_state_restoration_verified':True,
    'restoration_strategy':{'kind':'restore_uc_personal','page_url':uc_page['url'],
        'baseline_state_sha256':digest(uc_page['state_metadata'])}}
prepare(snapshot.data,uc_plan['checkpoint_id'],uc_page,uc_context);store.save(snapshot)
for field in uc_page['fields']:
    field['value']=next((w['value'] for w in uc_plan['writes'] if w['field_key']==field['key']),field['value'])
assert verify_saved(snapshot.data,uc_plan['checkpoint_id'],uc_page,revisited_after_save=True)['verified']
store.save(snapshot)
bundle=recovery_bundle(snapshot.data,uc_plan['checkpoint_id'],uc_page)
assert bundle['plan']['system']=='uc' and bundle['original_state_metadata']==uc_original['state_metadata']
assert verify_saved(snapshot.data,uc_plan['checkpoint_id'],uc_original,revisited_after_save=True,restoration=True)['restored']
store.save(snapshot)
from bc_application.profile import bind_fact
from urllib.parse import urlsplit
courses=json.loads(Path(sys.argv[6]).read_text(encoding='utf-8'))
courses['state_metadata']=json.loads(Path(sys.argv[5]).read_text(encoding='utf-8'))
courses['state_metadata']['page_url']=courses['url']
for index,field in enumerate(courses['fields']):
    ref=f'education.uc_release.value_{index}'
    set_fact(snapshot.data,ref,field['value'],source)
    bind_fact(snapshot.data,target,field['key'],ref,page_path=urlsplit(courses['url']).path)
snapshot.data['facts']['education.uc_release.value_1']['value']='Synthetic corrected course'
course_original=json.loads(json.dumps(courses))
course_plan=build_plan(snapshot.data,target,courses)
assert course_plan['ready'] and len(course_plan['writes'])==1
course_context={**uc_context,'restoration_strategy':{'kind':'restore_uc_courses','page_url':courses['url'],
    'baseline_state_sha256':digest(courses['state_metadata']),'baseline_parent_sha256':digest(courses['uc_course_parent'])}}
prepare(snapshot.data,course_plan['checkpoint_id'],courses,course_context);store.save(snapshot)
snapshot=store.load()
courses['fields'][1]['value']='Synthetic corrected course'
courses['uc_course_parent']['summary_sha256']='c'*64
assert verify_saved(snapshot.data,course_plan['checkpoint_id'],courses,revisited_after_save=True)['verified']
store.save(snapshot)
bundle=recovery_bundle(snapshot.data,course_plan['checkpoint_id'],courses)
assert bundle['plan']['uc_academic_auxiliary']==course_original['uc_academic_auxiliary'] and len(bundle['writes'])==1
assert not verify_saved(snapshot.data,course_plan['checkpoint_id'],courses,revisited_after_save=True,restoration=True)['restored']
assert snapshot.data['checkpoints'][course_plan['checkpoint_id']]['journal'] is not None
assert verify_saved(snapshot.data,course_plan['checkpoint_id'],course_original,revisited_after_save=True,restoration=True)['restored']
store.save(snapshot)
print('Clean installed page contract passed')
'''
        page_check = subprocess.run([str(python),"-c",relay_smoke,str(skill/"scripts"),str(output),str(ROOT/'tests/fixtures/synthetic_transcript.pdf'),
            str(ROOT/'tests/fixtures/uc_personal_page.json'),str(ROOT/'tests/fixtures/uc_review_state.json'),
            str(ROOT/'tests/fixtures/uc_courses_page.json')],
            capture_output=True,text=True,cwd=isolated)
        if page_check.returncode:
            raise RuntimeError("Clean page contract failed: "+page_check.stdout+page_check.stderr)
        # Reuse only fictional fixture construction in the development process.
        # The transaction itself executes exclusively from the extracted package
        # in the clean runtime, with the same single synthetic canonical JSON.
        sys.path.insert(0,str(ROOT/'skills/bc-application/scripts'))
        fixture_helpers=runpy.run_path(str(ROOT/'tests/test_uc_course_refill.py'))
        fake,target_id,baseline,context=fixture_helpers['setup'](blank=True)
        exposed=fixture_helpers['selected_page'](baseline,{'rows':[
            {'field_key':'i:academics_hs_classes_add_0_term','value':'F'},
            {'field_key':'i:academics_hs_classes_add_1_term','value':'S'}]})
        refill_input={'sources':fake['sources'],'facts':fake['facts'],'targets':fake['targets'],
            'target_id':target_id,'bundle':baseline,'context':context,'exposed':exposed}
        refill_smoke='''import copy,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.browser import digest,values
from bc_application.uc_course_refill import prepare_refill,prepare_grades,recover_refill,verify_refill
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for key in ('sources','facts','targets'):snapshot.data[key].update(data[key])
store.save(snapshot)
plan=prepare_refill(snapshot.data,data['target_id'],data['bundle'],data['context']);store.save(snapshot)
snapshot=store.load();assert recover_refill(snapshot.data,plan['checkpoint_id'])['original']==data['bundle']
grade=prepare_grades(snapshot.data,plan['checkpoint_id'],data['exposed']);store.save(snapshot)
after=copy.deepcopy(data['bundle']);after['page']=copy.deepcopy(data['exposed'])
for w in grade['writes']:next(f for f in after['page']['fields'] if f['key']==w['field_key'])['value']=w['value']
fields={f['key']:f for f in after['page']['fields']};rows=[]
for i in range(2):
    def display(suffix):
        field=fields.get(f'i:academics_hs_classes_add_{i}_'+suffix)
        return '' if field is None else field['value'] if field['control']=='text' else next(o['label'] for o in field['options'] if o['value']==field['value'])
    rows.append(['B-English',display('class_title'),display('honors'),display('term'),display('grade1'),display('grade2'),'','',''])
after['summary']['cells']['rows']=rows
after['summary']['context']['row_terms']=['Full year','Semester']
after['summary']['rows_sha256']=digest(after['summary']['cells'])
after['summary']['parent']['summary_sha256']=digest(after['summary']['cells'])
assert verify_refill(snapshot.data,plan['checkpoint_id'],after,revisited_after_save=True)['verified'];store.save(snapshot)
assert store.load().data['checkpoints'][plan['checkpoint_id']]['journal'] is None
assert snapshot.data['academic']==raw and len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean installed conditional UC refill passed')
'''
        refill_check=subprocess.run([str(python),'-c',refill_smoke,str(skill/'scripts'),str(output)],
            input=json.dumps(refill_input),capture_output=True,text=True,cwd=isolated)
        if refill_check.returncode:
            raise RuntimeError('Clean UC refill contract failed: '+refill_check.stdout+refill_check.stderr)
        factual_helpers=runpy.run_path(str(ROOT/'tests/test_uc_factual.py'))
        fake,factual_target,factual_page,_,_=factual_helpers['setup']('ielts')
        factual_input={key:fake[key] for key in ('sources','facts','targets','exams')}
        factual_input.update(target=factual_target,page=factual_page)
        factual_smoke='''import copy,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.uc_factual import CONTRACTS
from bc_application.pages import build_plan,prepare,verify_saved
assert len(CONTRACTS)==5 and any(c['kind']=='ielts' for c in CONTRACTS)
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for key in ('sources','facts','targets','exams'):snapshot.data[key].update(data[key])
store.save(snapshot);page=data['page']
plan=build_plan(snapshot.data,data['target'],page,optional_keys=['i:ieltsFormNumber']);assert plan['ready']
prepare(snapshot.data,plan['checkpoint_id'],page,{'browser_family':'edge','transport':'extension',
    'origin':'https://apply.universityofcalifornia.edu','access_verified':True});store.save(snapshot)
snapshot=store.load()
for w in plan['writes']:next(f for f in page['fields'] if f['key']==w['field_key'])['value']=w['value']
assert verify_saved(snapshot.data,plan['checkpoint_id'],page,revisited_after_save=True)['verified'];store.save(snapshot)
assert snapshot.data['checkpoints'][plan['checkpoint_id']]['journal'] is None
assert snapshot.data['academic']==raw and len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean installed UC factual resource and requested-update contract passed')
'''
        factual_check=subprocess.run([str(python),'-c',factual_smoke,str(skill/'scripts'),str(output)],
            input=json.dumps(factual_input),capture_output=True,text=True,cwd=isolated)
        if factual_check.returncode:
            raise RuntimeError('Clean UC factual contract failed: '+factual_check.stdout+factual_check.stderr)
        common_helpers=runpy.run_path(str(ROOT/'tests/test_common_ielts.py'))
        fake,common_target,common_page,common_context,_=common_helpers['setup']()
        common_input={key:fake[key] for key in ('sources','facts','targets','exams')}
        common_input.update(target=common_target,page=common_page,context=common_context)
        common_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.common_ielts import CONTRACT,resume
from bc_application.pages import build_plan,prepare,verify_saved
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for key in ('sources','facts','targets'):snapshot.data[key].update(data[key])
snapshot.data['exams']=data['exams'];store.save(snapshot)
page=data['page'];assert len(CONTRACT['fields'])==12
count=snapshot.data['facts'].pop('exams.ielts.taken_count')
assert not build_plan(snapshot.data,data['target'],page)['ready']
snapshot.data['facts']['exams.ielts.taken_count']=count
plan=build_plan(snapshot.data,data['target'],page);assert plan['ready']
prepare(snapshot.data,plan['checkpoint_id'],page,data['context']);store.save(snapshot)
snapshot=store.load();original=copy.deepcopy(snapshot.data['checkpoints'][plan['checkpoint_id']]['journal'])
for w in plan['writes']:next(f for f in page['fields'] if f['key']==w['field_key'])['value']=w['value']
for field in page['fields']:field['invalid']=False
for item in page['state_metadata']['items']:
    if item['key'] in {'secondaryNavItem2','tertiaryNavItem2_10'}:item['status']='complete'
relay=subprocess.run([sys.executable,str(Path(sys.argv[1])/'run.py'),'common-ielts-resume',
    '--profile',sys.argv[2],'--checkpoint',plan['checkpoint_id']],input=json.dumps({'page':page}),
    capture_output=True,text=True)
assert relay.returncode==0,relay.stdout+relay.stderr
again=json.loads(relay.stdout);snapshot=store.load()
assert again['ready'] and not again['writes']
assert snapshot.data['checkpoints'][plan['checkpoint_id']]['journal']==original
assert verify_saved(snapshot.data,plan['checkpoint_id'],page,revisited_after_save=True)['verified'];store.save(snapshot)
assert store.load().data['checkpoints'][plan['checkpoint_id']]['journal'] is None
assert snapshot.data['academic']==raw and len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean installed Common App IELTS source gate and restart passed')
'''
        common_check=subprocess.run([str(python),'-c',common_smoke,str(skill/'scripts'),str(output)],
            input=json.dumps(common_input),capture_output=True,text=True,cwd=isolated)
        if common_check.returncode:
            raise RuntimeError('Clean Common App IELTS contract failed: '+common_check.stdout+common_check.stderr)
        common_factual_helpers=runpy.run_path(str(ROOT/'tests/test_common_factual.py'))
        for kind in ('language','household','grade12_status'):
            fake,factual_target,factual_page,factual_context=common_factual_helpers['setup'](kind,complete=True)
            if kind=='grade12_status':
                from bc_application.profile import add_statement,set_fact
                set_fact(fake,'education.common_app.grade12.has_official_grades',False,add_statement(fake,'Fictional student confirms no official grade-12 marks on transcript.'))
                factual_page['fields'][0]['value']='1'
            factual_input={key:fake[key] for key in ('sources','facts','targets')}
            factual_input.update(target=factual_target,page=factual_page,context=factual_context)
            common_factual_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.pages import build_plan,prepare,verify_saved,recovery_bundle
from bc_application.common_factual import CONTRACTS
from bc_application.intake import agenda
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for key in ('sources','facts','targets'):snapshot.data[key].update(data[key])
page=data['page'];original=copy.deepcopy(page)
assert {s['kind'] for s in CONTRACTS}=={'language','household','grade12_status'}
plan=build_plan(snapshot.data,data['target'],page);assert plan['ready'],plan['blockers']
context={**data['context'],'restore_after_test':True}
prepare(snapshot.data,plan['checkpoint_id'],page,context);store.save(snapshot)
for w in plan['writes']:next(f for f in page['fields'] if f['key']==w['field_key'])['value']=w['value']
for field in page['fields']:field['invalid']=False
relay=subprocess.run([sys.executable,str(Path(sys.argv[1])/'run.py'),'common-page-resume',
    '--profile',sys.argv[2],'--checkpoint',plan['checkpoint_id']],input=json.dumps({'page':page}),capture_output=True,text=True)
assert relay.returncode==0,relay.stdout+relay.stderr
assert json.loads(relay.stdout)['ready'];snapshot=store.load()
assert verify_saved(snapshot.data,plan['checkpoint_id'],page,revisited_after_save=True)['verified'];store.save(snapshot)
assert recovery_bundle(store.load().data,plan['checkpoint_id'],page)['original_values_sha256']
assert verify_saved(snapshot.data,plan['checkpoint_id'],original,revisited_after_save=True,restoration=True)['restored'];store.save(snapshot)
before=Path(sys.argv[2]).read_bytes()
request={'target_id':data['target'],'pages':[page],'routes':[{'url':page['url'],'label':'Synthetic observed page'}]}
relay=subprocess.run([sys.executable,str(Path(sys.argv[1])/'run.py'),'collection-agenda','--profile',sys.argv[2]],
    input=json.dumps({'requests':[request]}),capture_output=True,text=True)
assert relay.returncode==0,relay.stdout+relay.stderr
report=json.loads(relay.stdout)
assert not report['questions'] and len(report['already_matching_pages'])==1
assert Path(sys.argv[2]).read_bytes()==before
assert report['execution_verified'] is False and report['already_matching_pages'][0]['saved_revisit_required']
relay=subprocess.run([sys.executable,str(Path(sys.argv[1])/'run.py'),'page-verify-matching','--profile',sys.argv[2],
    '--target',data['target']],input=json.dumps({'baseline':page,'page':page,'context':data['context'],
    'revisited_saved_draft':True}),capture_output=True,text=True)
assert relay.returncode==0,relay.stdout+relay.stderr
assert json.loads(relay.stdout)['verification_kind']=='read_only_saved_match'
assert store.load().data['checkpoints'][plan['checkpoint_id']]['journal'] is None
assert snapshot.data['academic']==raw and len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean installed Common App factual restart, recovery and no-repeat agenda passed')
'''
            factual_check=subprocess.run([str(python),'-c',common_factual_smoke,str(skill/'scripts'),str(output)],
                input=json.dumps(factual_input),capture_output=True,text=True,cwd=isolated)
            if factual_check.returncode:
                raise RuntimeError('Clean Common factual/agenda contract failed: '+factual_check.stdout+factual_check.stderr)
        fake,language_target,language_rows,language_context=common_factual_helpers['setup']('language',n=3)
        _,_,language_original,_=common_factual_helpers['setup']('language',n=0)
        language_input={key:fake[key] for key in ('sources','facts','targets')}
        language_input.update(target=language_target,original=language_original,rows=language_rows,context=language_context)
        language_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.browser import values
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for key in ('sources','facts','targets'):snapshot.data[key].update(data[key])
store.save(snapshot)
def relay(operation,payload,key=None):
    result=subprocess.run([sys.executable,str(Path(sys.argv[1])/'run.py'),'common-language-'+operation,'--profile',sys.argv[2],
        '--target' if operation in {'preview','prepare'} else '--checkpoint',key or data['target']],
        input=json.dumps(payload),capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)
before=Path(sys.argv[2]).read_bytes()
assert relay('preview',{'page':data['original']})['ready']
assert Path(sys.argv[2]).read_bytes()==before
first=relay('prepare',{'page':data['original'],'context':data['context']});key=first['checkpoint_id']
assert first['stage']=='count' and first['plan']['desired_count']==3
assert store.load().data['checkpoints'][key]['journal']==values(data['original'])
second=relay('resume',{'page':data['rows']},key);assert second['stage']=='fields'
page=copy.deepcopy(data['rows'])
for w in second['plan']['writes']:next(f for f in page['fields'] if f['key']==w['field_key'])['value']=w['value']
for field in page['fields']:field['invalid']=False
for item in page['state_metadata']['items']:
    if item['key'] in {'secondaryNavItem3','tertiaryNavItem3_16'}:item['status']='complete'
assert relay('verify',{'page':page,'revisited_after_save':True},key)['verified']
first=relay('prepare',{'page':data['original'],'context':data['context']});key=first['checkpoint_id']
relay('rows',{'page':data['rows']},key)
assert relay('cancel',{'page':data['original'],'revisited_saved_draft':True},key)['restored']
result=store.load().data
assert result['academic']==raw and all(cp.get('journal') is None for cp in result['checkpoints'].values())
assert len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean installed staged language creation, restart and unsaved cancellation passed')
'''
        language_check=subprocess.run([str(python),'-c',language_smoke,str(skill/'scripts'),str(output)],
            input=json.dumps(language_input),capture_output=True,text=True,cwd=isolated)
        if language_check.returncode:
            raise RuntimeError('Clean staged language contract failed: '+language_check.stdout+language_check.stderr)
        academic_helpers=runpy.run_path(str(ROOT/'tests/test_common_academic.py'))
        academic_data,academic_target,academic_context=academic_helpers['scenario']()
        academic_original=academic_helpers['page']()
        from bc_application import common_academic
        first=common_academic.prepare(academic_data,academic_target,academic_helpers['REF'],academic_original,academic_context)
        current=academic_original;academic_pages=[]
        for _ in range(40):
            step=common_academic.advance(academic_data,first['checkpoint_id'],current)
            academic_pages.append(current)
            current=academic_helpers['transition'](current,step['plan'])
            if step['stage']=='fields':break
        config=[{'headers':{k:f['value'] for k,f in v['headers'].items()},'rows':len(v['rows'])}
            for v in common_academic.layout(current).values()]
        academic_input={k:academic_data[k] for k in ('sources','facts','targets')}
        academic_input.update(target=academic_target,report_ref=academic_helpers['REF'],pages=academic_pages,
            saved=academic_helpers['page'](config,{f['key']:f['value'] for f in current['fields']},saved=True),context=academic_context)
        academic_output=isolated/'academic-student'/'applicant.json'
        academic_output.parent.mkdir()
        academic_init=subprocess.run([str(python),str(skill/'scripts/run.py'),'profile-init','--psr',
            str(ROOT/'tests/fixtures/synthetic_academic_psr.pdf'),'--profile',str(academic_output)],capture_output=True,text=True,cwd=isolated)
        if academic_init.returncode:raise RuntimeError('Independent fictional academic student init failed')
        academic_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.browser import values
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for k in ('sources','facts','targets'):snapshot.data[k].update(data[k])
store.save(snapshot)
def relay(operation,payload,key=None):
    args=[sys.executable,str(Path(sys.argv[1])/'run.py'),'common-academic-'+operation,'--profile',sys.argv[2]]
    args+=['--target',data['target'],'--report-ref',data['report_ref']] if operation in {'preview','prepare'} else ['--checkpoint',key]
    result=subprocess.run(args,input=json.dumps(payload),capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)
before=Path(sys.argv[2]).read_bytes()
assert relay('preview',{'page':data['pages'][0]})['ready']
assert Path(sys.argv[2]).read_bytes()==before
first=relay('prepare',{'page':data['pages'][0],'context':data['context']});key=first['checkpoint_id']
original=values(data['pages'][0])
for page in data['pages'][1:]:
    assert relay('advance',{'page':page},key)['ready']
    assert store.load().data['checkpoints'][key]['journal']==original
assert relay('verify',{'page':data['saved'],'revisited_after_save':True},key)['verified']
first=relay('prepare',{'page':data['pages'][0],'context':data['context']});key=first['checkpoint_id']
relay('advance',{'page':data['pages'][1]},key)
assert relay('cancel',{'page':data['pages'][0],'revisited_saved_draft':True},key)['restored']
result=store.load().data
assert result['academic']==raw and all(cp.get('journal') is None for cp in result['checkpoints'].values())
assert len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean installed academic first-use, persisted restart, saved verification and cancel passed')
'''
        academic_check=subprocess.run([str(python),'-c',academic_smoke,str(skill/'scripts'),str(academic_output)],
            input=json.dumps(academic_input),capture_output=True,text=True,cwd=isolated)
        if academic_check.returncode:
            raise RuntimeError('Clean academic creation contract failed: '+academic_check.stdout+academic_check.stderr)
        school_helpers=runpy.run_path(str(ROOT/'tests/test_common_schools.py'))
        school_data,school_target,school_ref,school_context=school_helpers['scenario'](early=True)
        school_other=school_helpers['scenario']('other')[0]['facts']['education.school_reports.other']
        school_data['facts']['education.school_reports.other']=school_other
        from bc_application import common_schools
        school_cases=[]
        for kind in ('current','other'):
            report_ref='education.school_reports.'+kind
            current=school_helpers['page'](kind);school_pages=[]
            first=common_schools.prepare(school_data,school_target,report_ref,current,school_context)
            for _ in range(15):
                step=common_schools.advance(school_data,first['checkpoint_id'],current)
                school_pages.append(current);current=school_helpers['transition'](current,step['plan'])
                if step['stage']=='fields':break
            saved=school_helpers['transition'](current,step['plan'],saved=True)
            assert common_schools.verify(school_data,first['checkpoint_id'],saved,revisited_after_save=True)['verified']
            school_cases.append({'report_ref':report_ref,'pages':school_pages,'saved':saved})
        school_input={k:school_data[k] for k in ('sources','facts','targets')}
        school_input.update(target=school_target,context=school_context,cases=school_cases,
            lookups=[{'school_id':key,'lookup':school_helpers['lookup'](key)} for key in ('99990001','99990002')])
        school_output=isolated/'school-student'/'applicant.json';school_output.parent.mkdir()
        school_init=subprocess.run([str(python),str(skill/'scripts/run.py'),'profile-init','--psr',
            str(ROOT/'tests/fixtures/synthetic_academic_psr.pdf'),'--profile',str(school_output)],capture_output=True,text=True,cwd=isolated)
        if school_init.returncode:raise RuntimeError('Independent fictional school student init failed')
        school_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.common_schools import values
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load()
raw=copy.deepcopy(snapshot.data['academic'])
for k in ('sources','facts','targets'):snapshot.data[k].update(data[k])
store.save(snapshot)
def call(command,payload,*extra):
    args=[sys.executable,str(Path(sys.argv[1])/'run.py'),command,'--profile',sys.argv[2],*extra]
    result=subprocess.run(args,input=json.dumps(payload),capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)
for item in data['lookups']:
    payload={'lookup':item['lookup'],'context':data['context']}
    before=Path(sys.argv[2]).read_bytes()
    assert call('school-lookup-resolve',payload,'--school',item['school_id'])['ready']
    assert Path(sys.argv[2]).read_bytes()==before
    assert call('school-lookup-remember',payload,'--school',item['school_id'])['profile_changed']
    before=Path(sys.argv[2]).read_bytes()
    assert call('school-lookup-remember',payload,'--school',item['school_id'])['reused']
    assert Path(sys.argv[2]).read_bytes()==before
for case in data['cases']:
    args=['--target',data['target'],'--report-ref',case['report_ref']]
    before=Path(sys.argv[2]).read_bytes()
    assert call('common-school-preview',{'page':case['pages'][0]},*args)['ready']
    assert Path(sys.argv[2]).read_bytes()==before
    first=call('common-school-prepare',{'page':case['pages'][0],'context':data['context']},*args);key=first['checkpoint_id']
    for page in case['pages'][1:]:
        assert call('common-school-advance',{'page':page},'--checkpoint',key)['ready']
        assert store.load().data['checkpoints'][key]['journal']==values(case['pages'][0])
    assert call('common-school-verify',{'page':case['saved'],'revisited_after_save':True},'--checkpoint',key)['verified']
    first=call('common-school-prepare',{'page':case['pages'][0],'context':data['context']},*args);key=first['checkpoint_id']
    call('common-school-advance',{'page':case['pages'][1]},'--checkpoint',key)
    assert call('common-school-cancel',{'page':case['pages'][0],'revisited_saved_draft':True},'--checkpoint',key)['restored']
result=store.load().data
assert result['academic']==raw and all(cp.get('journal') is None for cp in result['checkpoints'].values())
assert len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean school lookup reuse, first-use persisted restart, saved verification and cancellation passed')
'''
        school_check=subprocess.run([str(python),'-c',school_smoke,str(skill/'scripts'),str(school_output)],
            input=json.dumps(school_input),capture_output=True,text=True,cwd=isolated)
        if school_check.returncode:raise RuntimeError('Clean school contract failed: '+school_check.stdout+school_check.stderr)
        workflow_input={'sources':academic_input['sources'],'facts':academic_input['facts'],
            'steps':[{'target_id':school_target,'kind':kind,'report_ref':ref,'page_url':url} for kind,ref,url in (
                ('common_school','education.school_reports.current',school_cases[0]['pages'][0]['url']),
                ('common_school','education.school_reports.other',school_cases[1]['pages'][0]['url']),
                ('common_academic',academic_input['report_ref'],academic_input['pages'][0]['url']))]}
        workflow_input['routes']=[{'url':s['page_url'],'label':'Fictional observed route'} for s in workflow_input['steps']]
        workflow_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore
from bc_application.profile import add_statement,add_target
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));snapshot=store.load();raw=copy.deepcopy(snapshot.data['academic'])
for key in ('sources','facts'):snapshot.data[key].update(data[key])
store.save(snapshot)
def preview():
    result=subprocess.run([sys.executable,str(Path(sys.argv[1])/'run.py'),'workflow-preview','--profile',sys.argv[2]],
        input=json.dumps({'steps':data['steps'],'routes':data['routes']}),capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)
before=Path(sys.argv[2]).read_bytes();first=preview()
assert first['ready'] and not first['questions'] and len(first['jobs'])==3
assert Path(sys.argv[2]).read_bytes()==before and not first['full_application_complete']
snapshot=store.load();original=snapshot.data['facts'].pop('education.boarding');store.save(snapshot)
before=Path(sys.argv[2]).read_bytes();missing=preview()
assert not missing['ready'] and len(missing['questions'])==1 and missing['questions'][0]['fact_id']=='education.boarding'
assert Path(sys.argv[2]).read_bytes()==before
snapshot=store.load();snapshot.data['facts']['education.boarding']=original
source=add_statement(snapshot.data,'Fictional student chooses a second university for the shared workflow.')
other=add_target(snapshot.data,system='common_app',school='Second fictional workflow university',program=None,source_id=source);store.save(snapshot)
data['steps']+=[{**step,'target_id':other} for step in list(data['steps'])]
before=Path(sys.argv[2]).read_bytes();reused=preview()
assert reused['ready'] and not reused['questions'] and len(reused['jobs'])==3
assert all(len(j['target_ids'])==2 for j in reused['jobs']) and Path(sys.argv[2]).read_bytes()==before
result=store.load().data
assert result['academic']==raw and all(cp.get('journal') is None for cp in result['checkpoints'].values())
assert len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean joined workflow agenda, shared answer collection and university reuse passed')
'''
        workflow_check=subprocess.run([str(python),'-c',workflow_smoke,str(skill/'scripts'),str(school_output)],
            input=json.dumps(workflow_input),capture_output=True,text=True,cwd=isolated)
        if workflow_check.returncode:raise RuntimeError('Clean workflow contract failed: '+workflow_check.stdout+workflow_check.stderr)
        sys.path.insert(0,str(ROOT/'tests'))
        current_helpers=runpy.run_path(str(ROOT/'tests/test_common_current.py'))
        current_data,current_target,current_page,current_context=current_helpers['setup'](complete=False)
        current_input={'profile':current_data,'target':current_target,'page':current_page,'context':current_context}
        current_output=isolated/'current-year-student'/'applicant.json';current_output.parent.mkdir()
        current_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore,ProfileSnapshot
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));store.save(ProfileSnapshot(data['profile'],None))
raw=copy.deepcopy(data['profile']['academic'])
def call(op,page,key=None,**extra):
    args=[sys.executable,str(Path(sys.argv[1])/'run.py'),'common-current-'+op,'--profile',sys.argv[2]]
    args+=['--target',data['target'],'--report-ref','education.current_year.report'] if op in {'preview','prepare'} else ['--checkpoint',key]
    r=subprocess.run(args,input=json.dumps({'page':page,**extra}),capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
    return json.loads(r.stdout)
before=Path(sys.argv[2]).read_bytes();assert call('preview',data['page'])['ready'];assert Path(sys.argv[2]).read_bytes()==before
prepared=call('prepare',data['page'],context=data['context']);key=prepared['checkpoint_id']
resumed=call('advance',data['page'],key);saved=copy.deepcopy(data['page'])
for write in resumed['plan']['writes']:next(f for f in saved['fields'] if f['key']==write['field_key'])['value']=write['value']
for f in saved['fields']:f['invalid']=False
for s in saved['state_metadata']['items']:
    if s['key']!='secondaryNavItem7':s['status']='complete'
assert call('verify',saved,key,revisited_after_save=True)['verified']
assert call('preview',saved)['next']['writes']==[]
prepared=call('prepare',data['page'],context=data['context'])
assert call('cancel',data['page'],prepared['checkpoint_id'],revisited_saved_draft=True)['restored']
result=store.load().data
assert result['academic']==raw and all(c.get('journal') is None for c in result['checkpoints'].values())
assert len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
print('Clean current-year reference/grouping, persisted restart, verify and cancel passed')
'''
        current_check=subprocess.run([str(python),'-c',current_smoke,str(skill/'scripts'),str(current_output)],
            input=json.dumps(current_input),capture_output=True,text=True,cwd=isolated)
        if current_check.returncode:raise RuntimeError('Clean current-year contract failed: '+current_check.stdout+current_check.stderr)
        generic_helpers=runpy.run_path(str(ROOT/'tests/test_generic_forms.py'))
        generic_data,generic_target,generic_page,generic_analysis,generic_context=generic_helpers['scenario']()
        generic_data['school_directory']=generic_helpers['directory_scenario']()[0]['school_directory']
        generic_plan=generic_helpers['build_plan'](generic_data,generic_target,generic_page,semantic_analysis=generic_analysis)
        expanded=generic_helpers['filled'](generic_page,generic_plan)
        expanded['fields'].append(generic_helpers['field']('Contact telephone','tel',seed=900))
        expanded_analysis=generic_helpers['classify'](expanded,[(i['ref'],i['purpose']) for i in generic_analysis['fields']]+[('contact.phone','fact')])
        generic_data['checkpoints']={}
        generic_input={'profile':generic_data,'target':generic_target,'page':generic_page,'analysis':generic_analysis,
            'context':generic_context,'expanded':expanded,'expanded_analysis':expanded_analysis}
        generic_input['record_cases']=[{'page':case[2],'analysis':case[3]} for case in
            (generic_helpers['record_scenario'](0),generic_helpers['record_scenario'](1))]
        parent_case=generic_helpers['parent_record_scenario']()
        generic_input['parent_case']={'page':parent_case[2],'analysis':parent_case[3]}
        generic_input['count_field']=generic_helpers['field']('Years of regular education','number',value='0',seed=990)
        generic_output=isolated/'generic-student'/'applicant.json';generic_output.parent.mkdir()
        generic_smoke='''import copy,json,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from bc_application.store import ProfileStore,ProfileSnapshot
data=json.load(sys.stdin);store=ProfileStore(Path(sys.argv[2]));store.save(ProfileSnapshot(data['profile'],None));raw=copy.deepcopy(data['profile']['academic'])
def call(command,payload,*,target=False,key=None,append_new=False):
    args=[sys.executable,str(Path(sys.argv[1])/'run.py'),command,'--profile',sys.argv[2]]
    if target:args+=['--target',data['target']]
    if key:args+=['--checkpoint',key]
    if command=='profile-update':args+=['--stdin']
    if append_new:args+=['--append-new-student-facts']
    r=subprocess.run(args,input=json.dumps(payload),capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
    return json.loads(r.stdout)
before=Path(sys.argv[2]).read_bytes()
assert call('generic-preview',{'requests':[{'target_id':data['target'],'page':data['page'],'analysis':data['analysis']}]})['ready']
assert Path(sys.argv[2]).read_bytes()==before
plan=call('page-plan',{'page':data['page'],'analysis':data['analysis']},target=True);key=plan['checkpoint_id']
call('page-prepare',{'page':data['page'],'context':data['context']},key=key)
journal=copy.deepcopy(store.load().data['checkpoints'][key]['journal'])
call('profile-update',[{'op':'statement','id':'spontaneous','text':'The fictional student volunteers that no curriculum examination was taken.'},
    {'op':'fact','field':'education.curriculum_exam_taken','value':False,'source':'spontaneous'}],append_new=True)
assert store.load().data['checkpoints'][key]['journal']==journal
assert store.load().data['facts']['education.curriculum_exam_taken']['value'] is False
waiting=call('generic-resume',{'page':data['expanded'],'analysis':data['expanded_analysis']},key=key)
assert not waiting['ready'] and [q['fact_id'] for q in waiting['questions']]==['contact.phone']
call('profile-update',[{'op':'statement','id':'answer','text':'Fictional student supplies the newly requested telephone.'},
    {'op':'fact','field':'contact.phone','value':'+1 555 010 0900','source':'answer'}])
assert store.load().data['checkpoints'][key]['journal']==journal
resumed=call('generic-resume',{'page':data['expanded'],'analysis':data['expanded_analysis']},key=key)
assert resumed['ready'] and len(resumed['writes'])==1
saved=copy.deepcopy(data['expanded'])
for w in resumed['writes']:next(f for f in saved['fields'] if f['key']==w['field_key'])['value']=w['value']
assert call('page-verify',{'page':saved,'revisited_after_save':True},key=key)['verified']
assert call('page-verify-matching',{'baseline':saved,'page':saved,'context':data['context'],'revisited_saved_draft':True},target=True)['verified']
plan=call('page-plan',{'page':data['page'],'analysis':data['analysis']},target=True);key=plan['checkpoint_id']
call('page-prepare',{'page':data['page'],'context':data['context']},key=key)
assert call('generic-recover',{'page':data['page']},key=key)['context']['journal_persisted']
assert call('generic-cancel',{'page':data['page'],'revisited_saved_draft':True},key=key)['restored']
# A persisted branch may deliberately remove an inapplicable question. It must
# retain the original journal and cannot be verified before whole-page acceptance.
branch=copy.deepcopy(data['page']);controller=branch['fields'][1]
controller['value']=controller['options'][1]['value']
from bc_application.browser import digest
analysis=copy.deepcopy(data['analysis']);analysis['observation_sha256']=digest(branch)
stage=call('generic-stage',{'page':branch,'analysis':analysis,'context':data['context'],'controller_key':controller['key']},target=True)
key=stage['checkpoint_id'];original=copy.deepcopy(store.load().data['checkpoints'][key]['journal'])
assert stage['generic_stage'] and stage['save_action'] is None
restart=call('generic-stage-restart',{'page':branch,'analysis':analysis,'controller_key':controller['key']},key=key)
assert restart['checkpoint_id']==key and store.load().data['checkpoints'][key]['journal']==original
changed=copy.deepcopy(branch)
for w in stage['writes']:next(f for f in changed['fields'] if f['key']==w['field_key'])['value']=w['value']
changed['fields'].pop();proposal=copy.deepcopy(analysis);proposal['fields'].pop();proposal['observation_sha256']=digest(changed)
whole=call('generic-stage-accept',{'page':changed,'analysis':proposal},key=key)
assert whole['ready'] and not whole.get('generic_stage')
for w in whole['writes']:next(f for f in changed['fields'] if f['key']==w['field_key'])['value']=w['value']
assert call('page-verify',{'page':changed,'revisited_after_save':True},key=key)['verified']
call('profile-update',[{'op':'statement','id':'school_answer','text':'Explicit fictional institution names and full dates.'},
    {'op':'fact','field':'education.prior_schools','value':[
        {'name':'Invented School A','start':'2020-09-02','end':'2021-06-29'},
        {'name':'Invented School B','start':'2021-09-03','end':'2022-06-28'}],'source':'school_answer'}])
record_keys=[]
for case in data['record_cases']:
    page=case['page'];proposal=case['analysis']
    plan=call('page-plan',{'page':page,'analysis':proposal},target=True);assert plan['ready'];key=plan['checkpoint_id'];record_keys.append(key)
    call('page-prepare',{'page':page,'context':data['context']},key=key)
    recovery=call('generic-recover',{'page':page},key=key);assert recovery['analysis']['record']==proposal['record']
    saved=copy.deepcopy(page)
    for w in plan['writes']:next(f for f in saved['fields'] if f['key']==w['field_key'])['value']=w['value']
    proposed={**proposal,'observation_sha256':digest(saved)}
    resume=call('generic-resume',{'page':saved,'analysis':proposed},key=key);assert resume['ready'] and not resume['writes']
    assert call('page-verify',{'page':saved,'revisited_after_save':True},key=key)['verified']
assert len(set(record_keys))==2
parent=data['parent_case']['page'];proposal=data['parent_case']['analysis']
for row,key in zip(proposal['record_collections'][0]['rows'],record_keys):row['checkpoint_id']=key
plan=call('page-plan',{'page':parent,'analysis':proposal},target=True);assert plan['ready'];key=plan['checkpoint_id']
call('page-prepare',{'page':parent,'context':data['context']},key=key)
for w in plan['writes']:next(f for f in parent['fields'] if f['key']==w['field_key'])['value']=w['value']
assert call('page-verify',{'page':parent,'revisited_after_save':True},key=key)['verified']
call('profile-update',[{'op':'statement','id':'policy','text':'Fictional student provides six years and requests saving without independent readback.'},
    {'op':'fact','field':'education.primary_years','value':6,'source':'policy'},
    {'op':'fact','field':'workflow.saved_page_readback','value':False,'source':'policy'}])
parent['fields'].append(data['count_field']);proposal['fields'].append({
    **{k:data['count_field'][k] for k in ('key','label','group','control')},'role':'factual','ref':'education.primary_years',
    'purpose':'fact','format':'identity','reason':'Explicit fictional count from the applicant.'})
proposal['observation_sha256']=digest(parent)
stage=call('generic-stage',{'page':parent,'analysis':proposal,'context':data['context'],'controller_key':data['count_field']['key']},target=True)
key=stage['checkpoint_id'];assert stage['writes'][0]['count_input'] is True
restart=call('generic-stage-restart',{'page':parent,'analysis':proposal,'controller_key':data['count_field']['key']},key=key)
assert restart['checkpoint_id']==key
for w in stage['writes']:next(f for f in parent['fields'] if f['key']==w['field_key'])['value']=w['value']
proposal['observation_sha256']=digest(parent)
whole=call('generic-stage-accept',{'page':parent,'analysis':proposal},key=key)
assert whole['ready'] and not whole['writes'] and whole['saved_page_readback'] is False
receipt={'schema':'generic-draft-save/1','save_performed':True,'revisited_after_save':False,'verification_required':True,
    'target_id':whole['target_id'],'page_url':whole['page_url'],'structure_sha256':whole['structure_sha256'],
    'expected_values_sha256':whole['expected_values_sha256'],'save_action_key':whole['save_action']['key']}
ack=call('generic-acknowledge-save',{'receipt':receipt},key=key)
assert ack['saved'] and not ack['verified'] and ack['state']=='saved_unverified_user_skipped'
assert store.load().data['checkpoints'][key]['journal'] is not None
from bc_application.source_refs import metadata_value
stored=store.load().data;school=stored['academic']['schools'][0]
assert metadata_value(stored,'psr-school:'+school['school_id']+':name')==school['district_school_name_raw']
assert len(metadata_value(stored,'psr-school:'+school['school_id']+':0:admit_date'))==10
assert metadata_value(stored,'school-directory:99990001:country')=='Canada'
from bc_application.generic_forms import display_source_value
assert display_source_value({'format':'date_year'},'education.graduation_date','2027-02-17')=='2027'
assert display_source_value({'format':'date_month_name'},'exams.exam:fictional.date','2026-05')=='May'
case=data['record_cases'][0];page=copy.deepcopy(case['page']);proposal=copy.deepcopy(case['analysis'])
page['actions'][0]['label']='Add';proposal.update(record_action='add_draft',observation_sha256=digest(page))
plan=call('page-plan',{'page':page,'analysis':proposal},target=True);assert plan['ready'] and plan['record_action']['kind']=='add_draft'
key=plan['checkpoint_id'];call('page-prepare',{'page':page,'context':data['context']},key=key)
receipt.update(target_id=plan['target_id'],page_url=plan['page_url'],structure_sha256=plan['structure_sha256'],
    expected_values_sha256=plan['expected_values_sha256'],save_action_key=plan['save_action']['key'])
assert call('generic-acknowledge-save',{'receipt':receipt},key=key)['state']=='saved_unverified_user_skipped'
result=store.load().data
from bc_application.checkpoints import transaction_active
assert result['academic']==raw and not any(transaction_active(c) for c in result['checkpoints'].values())
assert len(list(Path(sys.argv[2]).parent.glob('*.json')))==1
from bc_application.profile import add_statement,set_fact,ProfileError
from bc_application.source_refs import average_details
calculation=copy.deepcopy(result);template=copy.deepcopy(calculation['academic']['courses'][0]);rows=[]
for level,scores in [('11',[83,91,93,95,97,99]),('12',[82,90,92,94,96,98])]:
    for index,score in enumerate(scores):
        row=copy.deepcopy(template);row['record_id']='fictional:'+level+':'+str(index)
        row['raw_cells'].update(course_description='FICTIONAL COURSE '+str(index)+' '+level,school_percent=str(score),completion_date='17-Feb-2028')
        rows.append(row)
calculation['academic']['courses']=rows
source=add_statement(calculation,'This fictional applicant requests separate course-level Best 5 means.')
set_fact(calculation,'education.psr_average_policies',{f'course-level-{level}':{
    'method':'arithmetic_mean_best_percentages_by_course_suffix','course_level':level,'count':5,'decimals':2,'rounding':'half_up'}
    for level in ('11','12')},source)
assert metadata_value(calculation,'psr-average:course-level-11:percent')=='95.00'
assert metadata_value(calculation,'psr-average:course-level-12:percent')=='94.00'
assert len(average_details(calculation,'course-level-11')['record_ids'])==5
rows[0]['raw_cells']['school_percent']=''
try:metadata_value(calculation,'psr-average:course-level-11:percent')
except ProfileError:pass
else:raise AssertionError('Incomplete achieved candidate cannot be silently omitted')
from bc_application.profile import add_exam,register_exam_release_schedule
evidence_case=copy.deepcopy(result)
permission=add_statement(evidence_case,'This fictional applicant permits use of an observed official AP schedule.')
exam=add_exam(evidence_case,name='AP Calculus BC',system='AP',score=5,scale='1-5',source_id=permission,date='2028-05')
schedule=register_exam_release_schedule(evidence_case,system='AP',year=2028,release_date='2028-07-17',
    url='https://apstudents.collegeboard.org/view-scores',title='Fictional unit-test schedule',
    excerpt='2028 AP Exam scores will be available starting July 17.',observation_method='official_search_excerpt')
set_fact(evidence_case,'exams.ap_result_release_policy',{'rule':'exam_board_public_schedule','exam_ids':[exam],'schedule_source_id':schedule},permission)
assert metadata_value(evidence_case,'exam-record:'+exam+':result_release_date')=='2028-07-17'
component=evidence_case['exams'][exam]['score_fact_id'].rsplit('.',1)[0]+'.ab_subscore'
set_fact(evidence_case,component,4,permission,scale='1-5')
assert metadata_value(evidence_case,'exam-record:'+exam+':ab_subscore')==4
assert metadata_value(evidence_case,'exam-record:'+exam+':score')==5
from bc_application.generic_forms import validate_exam_component,switch_view
validate_exam_component(evidence_case,{'ref':'exam-record:'+exam,'component':component})
assert callable(switch_view) and evidence_case['academic']==raw
print('Clean generic semantics, records, parent receipts, count restart, public exam evidence and saved-unverified continuation passed')
'''
        generic_check=subprocess.run([str(python),'-c',generic_smoke,str(skill/'scripts'),str(generic_output)],
            input=json.dumps(generic_input),capture_output=True,text=True,cwd=isolated)
        if generic_check.returncode:raise RuntimeError('Clean generic form contract failed: '+generic_check.stdout+generic_check.stderr)
        blocked = subprocess.run([str(python), str(skill / "scripts/run.py"), "preflight", "--profile-dir",
                                  str(isolated), "--browser", "chrome"], capture_output=True, text=True, cwd=isolated)
        if blocked.returncode != 2 or "psr_pdf_readable" not in json.loads(blocked.stdout)["blockers"]:
            raise RuntimeError("Missing-PSR gate failed")
        report.update({"offline_runtime_setup": "passed", "outside_checkout_execution": "passed",
                       "synthetic_courses": 7, "synthetic_schools": 2, "missing_psr_gate": "passed",
                       "canonical_profile_resume":"passed", "single_applicant_json":"passed",
                       "installed_page_contract":"passed", "installed_recovery_guard":"passed",
                       "installed_document_quote_check":"passed", "validation_scope":"offline_extracted_package",
                       "live_application_writes": "not_performed_by_offline_verifier",
                       "installed_visual_review_contract":"passed",
                       "installed_mit_coursework_status_contract":"passed",
                       "installed_uc_personal_status_contract":"passed",
                       "installed_uc_dependent_fields_contract":"passed",
                       "installed_uc_course_summary_recovery_contract":"passed",
                       "installed_uc_conditional_term_refill_contract":"passed",
                       "installed_uc_factual_resource_and_update_contract":"passed",
                       "installed_common_ielts_source_gate_and_restart_contract":"passed",
                       "installed_common_factual_restart_and_recovery_contract":"passed",
                       "installed_collection_agenda_reuse_and_byte_identity":"passed",
                       "installed_independent_saved_match_verification":"passed",
                       "installed_staged_language_creation_restart_cancel":"passed",
                       "installed_academic_creation_restart_verify_cancel":"passed",
                       "installed_school_lookup_reuse_creation_restart_verify_cancel":"passed",
                       "installed_joined_workflow_agenda_and_university_reuse":"passed",
                       "installed_current_year_grouping_restart_verify_cancel":"passed",
                       "installed_generic_semantics_conditional_answers_restart_match_cancel":"passed",
                       "installed_generic_record_paths_modal_restart_metadata":"passed",
                       "installed_generic_parent_receipts_count_restart_skip_readback":"passed",
                       "installed_generic_explicit_record_add_date_components":"passed",
                       "installed_course_suffix_best_five_source_gate":"passed",
                       "installed_official_ap_release_schedule_evidence":"passed",
                       "installed_parent_exam_ab_subscore_component":"passed",
                       "chrome_edge_page_filling": "requires_documented_host_relay"})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--node", type=Path, required=True, help="Existing host Node.js executable for clean module imports")
    args = parser.parse_args()
    report = verify(args.archive,args.node)
    serialized = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized)
