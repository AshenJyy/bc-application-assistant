"""Different sites share one source/profile/transaction implementation."""
import copy
import json
from pathlib import Path

import pytest

from bc_application import generic_forms as generic
from bc_application.browser import digest,structure,values
from bc_application.pages import build_plan,prepare,verify_saved,restoration_writes
from bc_application.profile import ProfileError,add_statement,add_target,create_profile,set_fact
from bc_application.store import ProfileStore,ProfileSnapshot,StoreError


def field(label,control,*,group='',value='',required=True,options=None,seed=0):
    f={'label':label,'group':group,'control':control,'required':required,'name':f'input_{seed}',
       'selector':f'[id="field_{seed}"]','selector_count':1,'selector_index':0,'disabled':False,'readonly':False,'invalid':False,
       'value':value,'options':[]}
    f['key']='g:'+digest({k:f[k] for k in ('label','group','control','required')})[:24]
    if options:
        f['options']=[{'value':digest({'label':s,'group':''}),'native_value':str(seed)+'_'+str(i),'label':s,'disabled':False,
            **({'selector':f'[id="option_{seed}_{i}"]','selector_count':1,'selector_index':0} if control=='radio' else {})} for i,s in enumerate(options)]
    return f


def page(variant=0):
    fields=[field('Legal given names' if variant==0 else 'First name on official records','text',seed=variant*100+1),
        field('Country where you live' if variant==0 else 'Current country','select',options=['Canada','China'],seed=variant*100+2),
        field('Name of course' if variant==0 else 'Course title','textarea',group='Secondary course 1',seed=variant*100+3),
        field('Original school percentage','text',group='Secondary course 1',seed=variant*100+4)]
    if variant:fields=fields[::-1]
    instruction='Factual applicant draft. Record original school percentage without conversion.'
    url='https://forms.invented-'+str(variant)+'.invalid/applicant'
    return {'schema':'observed-page/1','url':url,'title':'Invented factual applicant draft','frames_present':False,'fields':fields,
        'actions':[{'key':'a:'+digest('Save draft')[:24],'label':'Save draft','selector':f'[id="save_{variant}"]','disabled':False}],
        'generic_form':{'schema':'generic-form/1','scope':{'selector':f'[id="form_{variant}"]','selector_count':1,'selector_index':0},
            'instructions_sha256':digest(instruction),'destination':{'action':url,'method':'post'}},
        'generic_context':{'instructions':instruction}}


def classify(page,refs):
    return {'schema':'form-semantics/1','observation_sha256':digest(page),'fields':[
        {'key':f['key'],'label':f['label'],'group':f['group'],'control':f['control'],'role':'factual','ref':ref,'purpose':purpose,
         'format':'whitespace' if purpose=='academic_name' else 'identity','reason':'The observed question asks for this explicit canonical fact or original PSR column.'}
        for f,(ref,purpose) in zip(page['fields'],refs,strict=True)]}


def scenario(variant=0):
    p=create_profile(Path(__file__).parent/'fixtures/synthetic_academic_psr.pdf')
    source=add_statement(p,'A fictional student authorizes these invented application URLs and supplies their name and country.')
    set_fact(p,'personal.legal_given_name','Synthetic',source);set_fact(p,'address.current.country','Canada',source)
    t=add_target(p,system='web',school='Invented university '+str(variant),program=None,source_id=source)
    pg=page(variant);generic.bind_site(p,t,pg['url'],source)
    record=next(c for c in p['academic']['courses'] if c['raw_cells']['school_percent'])['record_id']
    refs=[('personal.legal_given_name','name'),('address.current.country','fact'),(f'psr:{record}:description','academic_name'),(f'psr:{record}:school_percent','academic_mark')]
    if variant:refs=refs[::-1]
    analysis=classify(pg,refs)
    ctx={'browser_family':'edge','transport':'extension','origin':generic.origin(pg['url']),'access_verified':True,'application_authorized':True,
         'authorized_origin':generic.origin(pg['url']),'target_id':t}
    return p,t,pg,analysis,ctx


def filled(pg,plan):
    pg=copy.deepcopy(pg)
    for w in plan['writes']:next(f for f in pg['fields'] if f['key']==w['field_key'])['value']=w['value']
    for f in pg['fields']:f['invalid']=False
    return pg


def opt_out_readback(p):
    source=add_statement(p,'After filling each page, save and continue without reopening it for verification.')
    set_fact(p,generic.READBACK_POLICY,False,source)


def save_receipt(plan):
    return {'schema':'generic-draft-save/1','save_performed':True,'revisited_after_save':False,'verification_required':True,
        'target_id':plan['target_id'],'page_url':plan['page_url'],'structure_sha256':plan['structure_sha256'],
        'expected_values_sha256':plan['expected_values_sha256'],'save_action_key':plan['save_action']['key']}


def test_explicit_no_readback_prefers_next_and_records_saved_without_claiming_verification(tmp_path):
    from bc_application.checkpoints import transaction_active
    p,t,pg,a,ctx=scenario();opt_out_readback(p)
    pg['actions'].append({'key':'a:next','label':'Save and Next','selector':'#next','disabled':False});a['observation_sha256']=digest(pg)
    plan=build_plan(p,t,pg,semantic_analysis=a);assert plan['ready'] and plan['save_action']['key']=='a:next' and plan['saved_page_readback'] is False
    key=plan['checkpoint_id'];prepare(p,key,pg,ctx);journal=copy.deepcopy(p['checkpoints'][key]['journal'])
    store=ProfileStore(tmp_path/'applicant.json');store.save(ProfileSnapshot(p,None));snap=store.load()
    result=generic.acknowledge_save(snap.data,key,save_receipt(plan));store.save(snap);stored=store.load().data
    cp=stored['checkpoints'][key]
    assert result['saved'] and not result['verified'] and not result['full_application_complete']
    assert cp['state']=='saved_unverified_user_skipped' and cp['journal']==journal and not transaction_active(cp)
    assert 'verified_source_sha256' not in cp and 'last_verified_at' not in cp
    for operation in (lambda:generic.recovery(stored,key,pg),lambda:generic.cancel(stored,key,pg,revisited_saved_draft=True),
            lambda:generic.resume(stored,key,pg,a)):
        with pytest.raises(ProfileError,match='prepared_generic_checkpoint_required'):operation()
    assert build_plan(stored,t,pg,semantic_analysis=a)['ready']


@pytest.mark.parametrize('change',['no_policy','default_policy','policy_conflict','document_policy','wrong_target','wrong_url','wrong_hash','wrong_action','no_save','revisited','changed_source','changed_directory','stage'])
def test_no_readback_never_bypasses_explicit_preference_ready_sources_or_matching_save_receipt(change):
    p,t,pg,a,ctx=scenario();opt_out_readback(p);plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx);receipt=save_receipt(plan)
    if change=='no_policy':del p['facts'][generic.READBACK_POLICY]
    if change=='default_policy':p['facts'][generic.READBACK_POLICY]['value']=True
    if change=='policy_conflict':
        source=add_statement(p,'Restore saved readback.');set_fact(p,generic.READBACK_POLICY,True,source)
    if change=='document_policy':p['facts'][generic.READBACK_POLICY]['source_refs']=[p['psr_source_id']]
    if change=='wrong_target':receipt['target_id']='target:other'
    if change=='wrong_url':receipt['page_url']='https://another.invalid'
    if change=='wrong_hash':receipt['expected_values_sha256']='0'*64
    if change=='wrong_action':receipt['save_action_key']='a:submit'
    if change=='no_save':receipt['save_performed']=False
    if change=='revisited':receipt['revisited_after_save']=True
    if change=='changed_source':p['facts']['personal.legal_given_name']['value']='Changed name'
    if change=='changed_directory':p['school_directory']={'changed':True}
    if change=='stage':p['checkpoints'][key]['generic_stage_controller']=pg['fields'][0]['key']
    with pytest.raises(ProfileError):generic.acknowledge_save(p,key,receipt)
    assert p['checkpoints'][key]['state']=='prepared' and p['checkpoints'][key]['journal'] is not None


def test_default_keeps_saved_readback_and_stationary_save():
    p,t,pg,a,ctx=scenario();pg['actions'].append({'key':'a:next','label':'Save and Next','selector':'#next','disabled':False});a['observation_sha256']=digest(pg)
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['saved_page_readback'] is True and plan['save_action']['label']=='Save draft'


@pytest.mark.parametrize('value,year,month',[('2027-01-28','2027','January'),('2026-05','2026','May')])
def test_date_components_preserve_supplied_precision(value,year,month):
    assert generic.display_source_value({'format':'date_year'},'education.graduation_date',value)==year
    assert generic.display_source_value({'format':'date_month_name'},'education.graduation_date',value)==month


@pytest.mark.parametrize('value',['2027','2026-13','2026-02-30'])
def test_date_components_reject_missing_month_and_invalid_calendar(value):
    with pytest.raises(ProfileError):generic.display_source_value({'format':'date_year'},'education.graduation_date',value)


def test_record_add_requires_explicit_named_dialog_capability_and_ready_source_fields():
    p,t,pg,a,ctx=record_scenario();pg['actions'][0]['label']='Add';a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    a['record_action']='add_draft';plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['ready'] and plan['record_action']=={'kind':'add_draft','record':a['record']}
    pg['actions'][0]['label']='Submit';a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']


def record_scenario(index=0):
    p,t,pg,a,ctx=scenario();source=add_statement(p,'Two fictional prior school records, with explicit full attendance dates.')
    set_fact(p,'education.prior_schools',[
        {'name':'Invented School A','start':'2020-09-02','end':'2021-06-29'},
        {'name':'Invented School B','start':'2021-09-03','end':'2022-06-28'}],source)
    pg['fields']=[field('Institution name','text',seed=501),field('Date from','text',seed=502),field('Date to','text',seed=503)]
    for f in pg['fields'][1:]:f['widget']={'kind':'calendar','native_readonly':True}
    pg['generic_form']['dialog']={'name':'Prior institution','selector':'#recordDialog','selector_count':1}
    a=classify(pg,[('education.prior_schools','name'),('education.prior_schools','date'),('education.prior_schools','date')])
    a['record']={'ref':'education.prior_schools','path':[index]}
    for item,key in zip(a['fields'],['name','start','end'],strict=True):
        item['source_path']=[index,key];item['format']='identity' if key=='name' else 'date_dmy'
    return p,t,pg,a,ctx


def directory_scenario():
    from test_common_schools import lookup
    from bc_application import schools
    p,t,pg,a,ctx=scenario()
    access={'browser_family':'edge','transport':'extension','access_verified':True,'origin':'http://127.0.0.1:8765','synthetic_test':True}
    for key in ('99990001','99990002'):assert schools.remember_lookup(p,key,lookup(key),access)['ready']
    pg['generic_form']['dialog']={'name':'Prior institution','selector':'#institution','selector_count':1}
    pg['fields']=[field('Institution name','text',seed=801),field('Study country','select',options=['Canada','China'],seed=802),field('Attendance starts','text',seed=803)]
    pg['fields'][-1]['widget']={'kind':'calendar','native_readonly':True}
    a=classify(pg,[('school-directory:99990001:name','name'),('school-directory:99990001:country','fact'),('psr-school:99990001:0:admit_date','date')])
    a['fields'][-1]['format']='date_dmy';a['record']={'ref':'psr-school:99990001'}
    return p,t,pg,a,ctx


def test_verified_directory_metadata_reuses_existing_identity_without_fact_or_school_copies():
    from bc_application.pages import resolve
    p,t,pg,a,ctx=directory_scenario();academic=copy.deepcopy(p['academic']);facts=copy.deepcopy(p['facts']);directory=copy.deepcopy(p['school_directory'])
    for column in ('name','country','city','region','ceeb'):
        assert resolve(p,'school-directory:99990001:'+column)[0]==directory['entries']['99990001']['common_app'][column]
    plan=build_plan(p,t,pg,semantic_analysis=a);assert plan['ready'] and len(plan['writes'])==3
    prepare(p,plan['checkpoint_id'],pg,ctx)
    assert verify_saved(p,plan['checkpoint_id'],filled(pg,plan),revisited_after_save=True)['verified']
    assert p['facts']==facts and p['academic']==academic and p['school_directory']==directory


@pytest.mark.parametrize('change',['wrong_school','missing_entry','unknown_column','wrong_name','unverified_origin','wrong_country'])
def test_directory_sources_cannot_bypass_school_identity_and_origin_evidence(change):
    p,t,pg,a,ctx=directory_scenario();entry=p['school_directory']['entries']['99990001']['common_app']
    if change=='wrong_school':a['fields'][0]['ref']='school-directory:99990002:name'
    if change=='missing_entry':del p['school_directory']['entries']['99990001']
    if change=='unknown_column':a['fields'][1]['ref']='school-directory:99990001:unrecorded'
    if change=='wrong_name':entry['name']='Another invented institution'
    if change=='unverified_origin':entry['evidence']['page_url']='https://unverified.invalid/common/4/18'
    if change=='wrong_country':entry['country']='China'
    try:assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    except ProfileError:pass
    assert all(c.get('journal') is None for c in p['checkpoints'].values())


@pytest.mark.parametrize('operation',['verify','resume','stage_restart','stage_accept'])
def test_directory_changes_stop_persisted_generic_transactions(operation):
    p,t,pg,a,ctx=directory_scenario()
    if operation.startswith('stage'):
        plan=generic.prepare_stage(p,t,pg,a,ctx,pg['fields'][1]['key'])
    else:
        plan=build_plan(p,t,pg,semantic_analysis=a);prepare(p,plan['checkpoint_id'],pg,ctx)
    key=plan['checkpoint_id'];p['school_directory']['entries']['99990001']['common_app']['city']='Another invented city'
    changed=filled(pg,plan);fresh={**a,'observation_sha256':digest(changed)}
    with pytest.raises(ProfileError):
        if operation=='verify':verify_saved(p,key,changed,revisited_after_save=True)
        if operation=='resume':generic.resume(p,key,changed,fresh)
        if operation=='stage_restart':generic.restart_stage(p,key,pg,a,pg['fields'][1]['key'])
        if operation=='stage_accept':generic.accept_stage(p,key,changed,fresh)
    assert p['checkpoints'][key]['journal'] is not None


def parent_record_scenario(*,skip_readback=False):
    p,t,child,analysis,ctx=record_scenario();keys=[]
    if skip_readback:opt_out_readback(p)
    for index in range(2):
        proposed=copy.deepcopy(analysis);proposed['record']['path']=[index]
        for item in proposed['fields']:item['source_path'][0]=index
        plan=build_plan(p,t,child,semantic_analysis=proposed);prepare(p,plan['checkpoint_id'],child,ctx)
        if skip_readback:assert not generic.acknowledge_save(p,plan['checkpoint_id'],save_receipt(plan))['verified']
        else:assert verify_saved(p,plan['checkpoint_id'],filled(child,plan),revisited_after_save=True)['verified']
        keys.append(plan['checkpoint_id'])
    pg=page();a=scenario()[3];headers=['Institution','Attendance','Action'];caption='Prior institutions'
    table={'key':'rc:'+digest({'headers':headers,'caption':caption})[:24],'headers':headers,'caption':caption,
        'rows':[['Invented School A','02-09-2020 to 29-06-2021','Action'],['Invented School B','03-09-2021 to 28-06-2022','Action']],
        'selector':'#records','selector_count':1}
    pg['generic_form']['record_collections']=[table]
    pg['actions'].append({'key':'a:add','label':'Add institution','selector':'#add','disabled':False})
    a['observation_sha256']=digest(pg);a['record_collections']=[{'key':table['key'],'rows':[
        {'row_index':i,'checkpoint_id':key,'identity_field_key':child['fields'][0]['key']} for i,key in enumerate(keys)],
        'action_keys':['a:add'],'reason':'Each independently verified saved record appears exactly once in this summary.'}]
    return p,t,pg,a,ctx,keys


@pytest.mark.parametrize('change',['none','policy_restored','child_source_changed'])
def test_parent_accepts_saved_unverified_children_only_under_current_explicit_skip_policy(change):
    p,t,pg,a,ctx,keys=parent_record_scenario(skip_readback=True)
    if change=='policy_restored':p['facts'][generic.READBACK_POLICY]['value']=True
    if change=='child_source_changed':p['facts']['education.prior_schools']['value'][0]['start']='2020-09-01'
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['ready']==(change=='none')
    assert all(p['checkpoints'][key]['state']=='saved_unverified_user_skipped' and p['checkpoints'][key]['journal'] is not None for key in keys)


def test_parent_record_summary_requires_verified_children_and_preserves_all_rows_on_save():
    p,t,pg,a,ctx,children=parent_record_scenario();before=copy.deepcopy(pg['generic_form']['record_collections'])
    plan=build_plan(p,t,pg,semantic_analysis=a);assert plan['ready'],plan['blockers']
    prepare(p,plan['checkpoint_id'],pg,ctx)
    saved=filled(pg,plan);saved['generic_form']['record_collections'][0]['selector']='#regenerated'
    assert verify_saved(p,plan['checkpoint_id'],saved,revisited_after_save=True)['verified']
    assert [c['state'] for k,c in p['checkpoints'].items() if k in children]==['verified','verified']
    assert pg['generic_form']['record_collections']==before


@pytest.mark.parametrize('change',['no_review','unmapped_row','wrong_identity','source_changed','unverified_child','wrong_target','repeat_checkpoint','wrong_field','manual_action','malformed_row'])
def test_record_table_cannot_hide_unverified_missing_or_different_records(change):
    p,t,pg,a,ctx,children=parent_record_scenario();review=a['record_collections'][0]
    if change=='no_review':del a['record_collections']
    if change=='unmapped_row':pg['generic_form']['record_collections'][0]['rows'].append(['Unreviewed record','Unknown','Action'])
    if change=='wrong_identity':pg['generic_form']['record_collections'][0]['rows'][0][0]='Another institution'
    if change=='source_changed':p['facts']['education.prior_schools']['value'][0]['start']='2020-09-01'
    if change=='unverified_child':p['checkpoints'][children[0]]['state']='blocked'
    if change=='wrong_target':p['checkpoints'][children[0]]['target_id']='target:another'
    if change=='repeat_checkpoint':review['rows'][1]['checkpoint_id']=children[0]
    if change=='wrong_field':review['rows'][0]['identity_field_key']='missing'
    if change=='manual_action':pg['actions'][-1]['label']='Pay institution fee'
    if change=='malformed_row':review['rows'][0]['row_index']=True
    a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    assert all(c.get('journal') is None for c in p['checkpoints'].values())


def test_parent_saved_verification_rechecks_child_receipts_and_summary_cells():
    p,t,pg,a,ctx,children=parent_record_scenario();plan=build_plan(p,t,pg,semantic_analysis=a);prepare(p,plan['checkpoint_id'],pg,ctx)
    p['checkpoints'][children[0]]['verified_source_sha256']='0'*64
    with pytest.raises(ProfileError):verify_saved(p,plan['checkpoint_id'],filled(pg,plan),revisited_after_save=True)
    assert p['checkpoints'][plan['checkpoint_id']]['journal'] is not None


def test_parent_staged_acceptance_and_restart_keep_independently_verified_child_receipts():
    p,t,pg,a,ctx,children=parent_record_scenario();source=add_statement(p,'The fictional applicant supplies six years of schooling.')
    set_fact(p,'education.schooling.primary_years',6,source)
    pg['fields']=[field('Years of regular education','text',value='0',seed=904)]
    a['fields']=classify(pg,[('education.schooling.primary_years','fact')])['fields'];a['observation_sha256']=digest(pg)
    stage=generic.prepare_stage(p,t,pg,a,ctx,pg['fields'][0]['key']);changed=filled(pg,stage)
    changed['generic_context']['instructions']='Total years: 6';changed['generic_form']['instructions_sha256']=digest('Total years: 6')
    a['observation_sha256']=digest(changed);accepted=generic.accept_stage(p,stage['checkpoint_id'],changed,a)
    assert accepted['ready'],accepted['blockers']
    resumed=generic.resume(p,stage['checkpoint_id'],changed,a);assert resumed['ready'] and not resumed['writes']
    assert all(p['checkpoints'][key]['verified_source_sha256'] for key in children)
    assert verify_saved(p,stage['checkpoint_id'],changed,revisited_after_save=True)['verified']


def test_explicit_count_stage_accepts_recomputed_instructions_but_cannot_save_early():
    p,t,pg,a,ctx=scenario();source=add_statement(p,'The fictional student explicitly reports six full-time years.')
    set_fact(p,'education.schooling.primary_years',6,source)
    pg['fields']=[field('Years of regular education','text',value='0',seed=901)]
    a=classify(pg,[('education.schooling.primary_years','fact')])
    stage=generic.prepare_stage(p,t,pg,a,ctx,pg['fields'][0]['key']);assert stage['generic_stage'] and stage['save_action'] is None
    changed=filled(pg,stage);changed['generic_context']['instructions']='Total years: 6'
    changed['generic_form']['instructions_sha256']=digest(changed['generic_context']['instructions']);a['observation_sha256']=digest(changed)
    accepted=generic.accept_stage(p,stage['checkpoint_id'],changed,a);assert accepted['ready'] and not accepted['writes']
    assert verify_saved(p,stage['checkpoint_id'],changed,revisited_after_save=True)['verified']


@pytest.mark.parametrize('count',[-1,1000,1.5,'6',True])
def test_count_branch_requires_a_bounded_explicit_integer(count):
    p,t,pg,a,ctx=scenario();source=add_statement(p,'An invented value used to verify count-source rejection.')
    set_fact(p,'education.example_count',count,source)
    pg['fields']=[field('Number of years','text',value='0',seed=902)];a=classify(pg,[('education.example_count','fact')])
    with pytest.raises(ProfileError):generic.prepare_stage(p,t,pg,a,ctx,pg['fields'][0]['key'])


def test_record_paths_reuse_one_canonical_array_and_keep_each_editor_checkpoint():
    p,t,pg,a,ctx=record_scenario();original=copy.deepcopy(p['facts']['education.prior_schools'])
    plan=build_plan(p,t,pg,semantic_analysis=a);assert plan['ready']
    key_a=plan['checkpoint_id'];prepare(p,key_a,pg,ctx)
    saved=filled(pg,plan);assert verify_saved(p,key_a,saved,revisited_after_save=True)['verified']
    b=copy.deepcopy(a);b['record']['path']=[1]
    for i in b['fields']:i['source_path'][0]=1
    second=build_plan(p,t,pg,semantic_analysis=b);assert second['ready'] and second['checkpoint_id']!=key_a
    key_b=second['checkpoint_id'];prepare(p,key_b,pg,ctx)
    recovered=generic.recovery(p,key_b,pg)
    assert recovered['analysis']['record']==b['record'] and recovered['plan']['checkpoint_id']==key_b
    assert verify_saved(p,key_b,filled(pg,second),revisited_after_save=True)['verified']
    assert p['facts']['education.prior_schools']==original
    assert p['checkpoints'][key_a]['semantic_analysis']['record']['path']==[0]
    assert p['checkpoints'][key_b]['semantic_analysis']['record']['path']==[1]
    assert all(c['journal'] is None for c in p['checkpoints'].values())


@pytest.mark.parametrize('change',['other_record','missing_record','missing_path','bad_path','scalar_record','wrong_dialog','numeric_bool'])
def test_record_semantics_reject_mixed_sources_or_incomplete_paths(change):
    p,t,pg,a,ctx=record_scenario()
    if change=='other_record':a['fields'][0]['source_path'][0]=1
    if change=='missing_record':del a['record']
    if change=='missing_path':a['fields'][0]['source_path']=[0,'not_recorded']
    if change=='bad_path':a['fields'][0]['source_path']=[True,'name']
    if change=='scalar_record':a['record']['path']=[0,'name']
    if change=='wrong_dialog':pg['generic_form']['dialog']['selector_count']=2;a['observation_sha256']=digest(pg)
    if change=='numeric_bool':
        # Python's 0 == False must not permit a boolean label map for numeric data.
        source=add_statement(p,'The synthetic numeric zero.');set_fact(p,'education.numeric_zero',0,source)
        adapter=generic.SemanticAdapter(p,p['targets'][t],pg,a);f=pg['fields'][0]
        adapter.items[f['key']].pop('source_path');adapter.items[f['key']].update(format='observed_label',choice={'source_value':False,'label':'No, none'})
        with pytest.raises(ProfileError):adapter.display_value(f,'education.numeric_zero',0)
        return
    try:assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    except ProfileError:pass
    assert all(c.get('journal') is None for c in p['checkpoints'].values())


def test_original_school_metadata_and_context_are_read_without_new_facts():
    from bc_application.pages import resolve
    from bc_application.source_refs import metadata_value
    p,t,pg,a,ctx=scenario();school=p['academic']['schools'][0];key=school['school_id']
    original=copy.deepcopy(p['academic']);facts=copy.deepcopy(p['facts'])
    assert resolve(p,f'psr-school:{key}:name')[0]==school['district_school_name_raw']
    date_ref=f'psr-school:{key}:0:admit_date';value=metadata_value(p,date_ref)
    assert len(value)==10 and value[4]==value[7]=='-'
    pg['fields']=[field('Attendance started','text',seed=601)]
    pg['fields'][0]['widget']={'kind':'calendar','native_readonly':True}
    a=classify(pg,[(date_ref,'date')]);a['fields'][0]['format']='date_dmy'
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['ready'] and not p['checkpoints'][plan['checkpoint_id']]['required_fact_ids']
    assert p['academic']==original and p['facts']==facts
    for bad in [f'psr-school:{key}:0:unrecorded',f'psr-school:{key}:999:admit_date','psr-context:no-such-context:student_grade_raw']:
        with pytest.raises(ProfileError):resolve(p,bad)


def test_boolean_observed_choice_still_requires_the_exact_source_value():
    p,t,pg,a,ctx=scenario();source=add_statement(p,'The fictional applicant has no bachelor enrollment.')
    set_fact(p,'education.has_enrolled_bachelors',False,source)
    f=pg['fields'][1];f['options'][0].update(label='No, I have not.',value=digest({'label':'No, I have not.','group':''}))
    a['fields'][1].update(ref='education.has_enrolled_bachelors',format='observed_label',choice={'source_value':False,'label':'No, I have not.'})
    a['observation_sha256']=digest(pg)
    assert build_plan(p,t,pg,semantic_analysis=a)['ready']


@pytest.mark.parametrize('ref,value,allowed',[('education.curriculum','普通初中课程',True),('exams.score','97',False),('exams.score',97,False),
    ('psr-context:fixture:student_grade_raw','12',True),('psr-context:fixture:student_grade_raw','13',False)])
def test_observed_label_sources_keep_unicode_and_original_grade_context_bounds(ref,value,allowed):
    assert generic.choice_source_allowed(value,ref)==allowed


def test_record_date_path_change_is_a_source_change_and_cannot_verify_saved_data():
    p,t,pg,a,ctx=record_scenario();plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx)
    p['facts']['education.prior_schools']['value'][0]['start']='2020-09-01'
    with pytest.raises(ProfileError,match='source_changed'):verify_saved(p,key,filled(pg,plan),revisited_after_save=True)
    assert p['checkpoints'][key]['journal'] is not None


@pytest.mark.parametrize('name',['Send invitation','Payment','Sign declaration'])
def test_dialog_caption_cannot_hide_a_forbidden_action_behind_a_save_button(name):
    p,t,pg,a,ctx=record_scenario();pg['generic_form']['dialog']['name']=name;a['observation_sha256']=digest(pg)
    with pytest.raises(ProfileError,match='manual_application_section'):build_plan(p,t,pg,semantic_analysis=a)


def test_record_context_cannot_be_swapped_during_staged_restart():
    p,t,pg,a,ctx=record_scenario();f=field('Country','select',options=['Canada','China'],seed=700)
    pg['fields'].append(f);a['fields'].append({**classify({'fields':[f]},[('address.current.country','fact')])['fields'][0]})
    a['observation_sha256']=digest(pg)
    stage=generic.prepare_stage(p,t,pg,a,ctx,f['key']);key=stage['checkpoint_id']
    changed=copy.deepcopy(a);changed['record']['path']=[1]
    for i in changed['fields']:
        if 'source_path' in i:i['source_path'][0]=1
    with pytest.raises(ProfileError,match='record_context'):generic.restart_stage(p,key,pg,changed,f['key'])


def test_native_change_reaffirmation_is_sourced_matching_owned_select_only():
    p,t,pg,a,ctx=scenario();f=pg['fields'][1];f['widget']={'kind':'owned_native_select'};f['value']=f['options'][0]['value'];a['observation_sha256']=digest(pg)
    stage=generic.prepare_stage(p,t,pg,a,ctx,f['key'],reaffirm_native_select=True)
    assert stage['generic_stage'] and stage['writes'][0]['native_event'] is True and stage['save_action'] is None
    for change in ['not_owned','not_matching','changed_source']:
        p,t,pg,a,ctx=scenario();f=pg['fields'][1];f['widget']={'kind':'owned_native_select'};f['value']=f['options'][0]['value']
        if change=='not_owned':f.pop('widget')
        if change=='not_matching':f['value']=f['options'][1]['value']
        if change=='changed_source':del p['facts']['address.current.country']
        a['observation_sha256']=digest(pg)
        with pytest.raises(ProfileError):generic.prepare_stage(p,t,pg,a,ctx,f['key'],reaffirm_native_select=True)


def test_branch_discovery_keeps_original_journal_and_cannot_verify_as_a_save():
    p,t,pg,a,ctx=scenario()
    controller=pg['fields'][1]
    # The old branch has a field which disappears after the sourced choice.
    controller['value']=controller['options'][1]['value'];a['observation_sha256']=digest(pg)
    original=copy.deepcopy(values(pg))
    stage=generic.prepare_stage(p,t,pg,a,ctx,controller['key'])
    assert stage['generic_stage'] and stage['save_action'] is None and len(stage['writes'])==1
    changed=filled(pg,stage)
    with pytest.raises(ProfileError,match='branch'):
        verify_saved(p,stage['checkpoint_id'],changed,revisited_after_save=True)
    changed['fields'].pop()
    refs=[(i['ref'],i['purpose']) for i in a['fields'][:-1]]
    fresh=classify(changed,refs)
    plan=generic.accept_stage(p,stage['checkpoint_id'],changed,fresh)
    assert plan['ready'] and not plan.get('generic_stage')
    cp=p['checkpoints'][stage['checkpoint_id']]
    assert cp['journal']==original and cp['prepared_plan']['checkpoint_id']==stage['checkpoint_id']
    saved=filled(changed,plan)
    assert verify_saved(p,stage['checkpoint_id'],saved,revisited_after_save=True)['verified']


@pytest.mark.parametrize('change',['missing_fact','wrong_origin','unchanged_choice','changed_controller','changed_source','changed_destination'])
def test_branch_discovery_does_not_bypass_controller_sources_or_destination(change):
    p,t,pg,a,ctx=scenario();controller=pg['fields'][1]
    controller['value']=controller['options'][1]['value'];a['observation_sha256']=digest(pg)
    if change=='missing_fact':
        del p['facts']['address.current.country']
        with pytest.raises(ProfileError):generic.prepare_stage(p,t,pg,a,ctx,controller['key'])
        return
    if change=='wrong_origin':
        ctx['authorized_origin']='https://other.invalid'
        with pytest.raises(ProfileError):generic.prepare_stage(p,t,pg,a,ctx,controller['key'])
        return
    stage=generic.prepare_stage(p,t,pg,a,ctx,controller['key']);changed=filled(pg,stage)
    if change=='unchanged_choice':changed=copy.deepcopy(pg)
    if change=='changed_controller':a['fields'][1]['ref']='address.other.country'
    if change=='changed_source':p['facts']['address.current.country']['value']='China'
    if change=='changed_destination':changed['generic_form']['destination']['action']=changed['url']+'/other'
    fresh={**a,'observation_sha256':digest(changed)}
    with pytest.raises(ProfileError):generic.accept_stage(p,stage['checkpoint_id'],changed,fresh)


def test_matching_readonly_fact_is_source_checked_and_missing_or_changed_value_blocks():
    p,t,pg,a,ctx=scenario();f=pg['fields'][0];f['readonly']=True;f['value']='Synthetic';a['observation_sha256']=digest(pg)
    assert build_plan(p,t,pg,semantic_analysis=a)['ready']
    f['value']='Unconfirmed';a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    del p['facts']['personal.legal_given_name']
    assert build_plan(p,t,pg,semantic_analysis=a)['questions'][0]['fact_id']=='personal.legal_given_name'


def test_observed_label_mapping_is_bound_to_source_and_cannot_convert_grades():
    p,t,pg,a,ctx=scenario();f=pg['fields'][1]
    f['options'][0].update(label='Canada (+ 1)',value=digest({'label':'Canada (+ 1)','group':''}))
    a['fields'][1].update(format='observed_label',choice={'source_value':'Canada','label':'Canada (+ 1)'})
    a['observation_sha256']=digest(pg)
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['ready'] and plan['writes'][1]['value']==f['options'][0]['value']
    p['facts']['address.current.country']['value']='China'
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    a['fields'][-1]['format']='observed_label';a['fields'][-1]['choice']={'source_value':'84','label':'A'}
    with pytest.raises(ProfileError):build_plan(p,t,pg,semantic_analysis=a)


def test_complete_dates_and_nanp_phone_components_are_lossless_display_only():
    p,t,pg,a,ctx=scenario();s=add_statement(p,'Synthetic date and telephone.')
    set_fact(p,'personal.birth_date','2007-11-23',s);set_fact(p,'contact.mobile','+1 2365550199',s)
    adapter=generic.SemanticAdapter(p,p['targets'][t],pg,a)
    for fmt,ref,value,expected in [('date_dmy','personal.birth_date','2007-11-23','23-11-2007'),('phone_nanp_area','contact.mobile','+1 2365550199','236'),('phone_nanp_line','contact.mobile','+1 2365550199','5550199')]:
        adapter.items[pg['fields'][0]['key']]['format']=fmt
        assert adapter.display_value(pg['fields'][0],ref,value)==expected


@pytest.mark.parametrize('value,area,number',[('+86 139 5555 0199','','13955550199'),('+1 (236) 555-0199','236','5550199')])
def test_explicit_mobile_parts_preserve_country_code_and_subscriber(value,area,number):
    p,t,pg,a,ctx=scenario();adapter=generic.SemanticAdapter(p,p['targets'][t],pg,a)
    for fmt,expected in [('phone_e164_area',area),('phone_e164_number',number)]:
        adapter.items[pg['fields'][0]['key']]['format']=fmt
        assert adapter.display_value(pg['fields'][0],'contact.primary_phone',value)==expected
        for ref,bad in [('personal.legal_given_name',value),('contact.mobile','13955550199'),('contact.primary_phone','+44 7700 900123')]:
            with pytest.raises(ProfileError):adapter.display_value(pg['fields'][0],ref,bad)


@pytest.mark.parametrize('policy',[['address.application_address_policy'],[],['address.unknown'],[{}],['address.application_address_policy']*2])
def test_policy_references_are_validated_and_source_gated(policy):
    p,t,pg,a,ctx=scenario();a['policy_refs']=policy
    if policy not in ([],['address.application_address_policy']):
        with pytest.raises(ProfileError,match='policy_reference'):build_plan(p,t,pg,semantic_analysis=a)
    else:
        plan=build_plan(p,t,pg,semantic_analysis=a)
        assert plan['ready']==(not policy)
        if policy:
            assert [q['fact_id'] for q in plan['questions']]==policy
            source=add_statement(p,'The fictional applicant chooses permanent address except explicit temporary mailing.')
            set_fact(p,policy[0],'permanent_except_explicit_temporary_mailing',source)
            assert build_plan(p,t,pg,semantic_analysis=a)['ready']


def test_stationary_save_is_unique_and_preferred_without_hiding_next_action():
    p,t,pg,a,ctx=scenario()
    pg['actions'].append({'key':'a:'+digest('Save and Next')[:24],'label':'Save and Next','selector':'#next','disabled':False})
    a['observation_sha256']=digest(pg)
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['ready'] and plan['save_action']['label']=='Save draft' and len(pg['actions'])==2
    pg['actions'].append({'key':'a:'+digest('Save')[:24],'label':'Save','selector':'#save','disabled':False})
    a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']


def test_branch_restart_keeps_original_journal_and_cancel_clears_controller():
    p,t,pg,a,ctx=scenario();f=pg['fields'][1]
    f['value']=f['options'][1]['value'];a['observation_sha256']=digest(pg)
    stage=generic.prepare_stage(p,t,pg,a,ctx,f['key']);key=stage['checkpoint_id']
    original=copy.deepcopy(p['checkpoints'][key]['journal'])
    restarted=generic.restart_stage(p,key,pg,a,f['key'])
    assert restarted['checkpoint_id']==key and p['checkpoints'][key]['journal']==original
    assert generic.cancel(p,key,pg,revisited_saved_draft=True)['restored']
    assert p['checkpoints'][key]['journal'] is None and 'generic_stage_controller' not in p['checkpoints'][key]


def test_restart_collects_only_the_new_controller_answer_and_still_requires_psr():
    p,t,pg,a,ctx=scenario();f=pg['fields'][1]
    f['value']=f['options'][1]['value'];a['observation_sha256']=digest(pg)
    stage=generic.prepare_stage(p,t,pg,a,ctx,f['key']);key=stage['checkpoint_id']
    fresh=copy.deepcopy(a);fresh['fields'][1]['ref']='address.mailing.country'
    waiting=generic.restart_stage(p,key,pg,fresh,f['key'])
    assert not waiting['ready'] and [q['fact_id'] for q in waiting['questions']]==['address.mailing.country']
    assert p['checkpoints'][key]['generic_pending_fact_ids']==['address.mailing.country']
    p['sources'][p['psr_source_id']]['path']='missing-fixture.pdf'
    with pytest.raises(ProfileError):generic.restart_stage(p,key,pg,a,f['key'])


@pytest.mark.parametrize('variant',[0,1])
def test_unregistered_sites_use_agent_proposals_and_exact_original_marks(variant):
    p,t,pg,a,ctx=scenario(variant);original=copy.deepcopy(p['academic']);before=copy.deepcopy(p)
    agenda=generic.preview(p,[{'target_id':t,'page':pg,'analysis':a}]);assert agenda['ready'] and p==before
    plan=build_plan(p,t,pg,semantic_analysis=a);assert plan['ready'],plan['blockers']
    marks=[w for w in plan['writes'] if w['fact_ref'].endswith(':school_percent')];assert len(marks)==1
    original_record=next(c for c in p['academic']['courses'] if c['record_id']==marks[0]['fact_ref'][4:].rsplit(':',1)[0])
    assert marks[0]['value']==original_record['raw_cells']['school_percent']
    prepare(p,plan['checkpoint_id'],pg,ctx);saved=filled(pg,plan)
    # All implementation IDs, names and native option values change on load.
    for i,f in enumerate(saved['fields']):
        f['selector']=f'[id="regenerated_{i}"]';f['name']='new_'+str(i)
        for o in f['options']:
            o['native_value']='new_'+o['native_value']
            if 'selector' in o:o['selector']='[id="new_option"]'
    saved['actions'][0]['selector']='[id="different_save"]';saved['generic_form']['scope']['selector']='[id="different_form"]'
    assert verify_saved(p,plan['checkpoint_id'],saved,revisited_after_save=True)['verified']
    assert p['academic']==original and p['checkpoints'][plan['checkpoint_id']]['journal'] is None


def test_missing_fact_is_asked_once_across_sites_and_never_copied_from_prefilled_answer():
    p,t,pg,a,ctx=scenario();p2,t2,pg2,a2,_=scenario(1)
    p['targets'].update(p2['targets']);p['sources'].update(p2['sources']);del p['facts']['personal.legal_given_name']
    pg['fields'][0]['value']='Unverified existing website answer';a['observation_sha256']=digest(pg)
    before=copy.deepcopy(p);result=generic.preview(p,[{'target_id':t,'page':pg,'analysis':a},{'target_id':t2,'page':pg2,'analysis':a2}])
    assert not result['ready'] and len(result['questions'])==1 and len(result['questions'][0]['uses'])==2 and p==before
    assert result['questions'][0]['fact_id']=='personal.legal_given_name'


def test_semantically_selected_facts_are_not_skipped_when_native_required_flags_are_missing():
    p,t,pg,a,ctx=scenario()
    for f in pg['fields']:
        f['required']=False;f['key']='g:'+digest({k:f[k] for k in ('label','group','control','required')})[:24]
    refs=[(i['ref'],i['purpose']) for i in a['fields']];a=classify(pg,refs)
    plan=build_plan(p,t,pg,semantic_analysis=a);assert plan['ready'] and len(plan['writes'])==4
    del p['facts']['personal.legal_given_name'];plan=build_plan(p,t,pg,semantic_analysis=a)
    assert not plan['ready'] and plan['questions'][0]['fact_id']=='personal.legal_given_name'


def test_explicitly_selected_optional_fact_does_not_fabricate_required_signals():
    p,t,pg,a,ctx=scenario();f=pg['fields'][0];f['required']=False;f['label']='Legal given name (optional)'
    f['key']='g:'+digest({k:f[k] for k in ('label','group','control','required')})[:24]
    a=classify(pg,[(i['ref'],i['purpose']) for i in a['fields']])
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert plan['ready'] and any(w['field_key']==f['key'] for w in plan['writes'])


@pytest.mark.parametrize('change',['stale','missing_field','unknown_field','wrong_label','wrong_group','bad_purpose','convert_grade','manual_binding','skip_required','unscoped_mark','unknown_custom'])
def test_semantic_proposals_cannot_bypass_evidence_or_capability_gates(change):
    p,t,pg,a,ctx=scenario();item=a['fields'][-1]
    if change=='stale':a['observation_sha256']='0'*64
    if change=='missing_field':a['fields'].pop()
    if change=='unknown_field':a['fields'].append({**item,'key':'unknown'})
    if change=='wrong_label':item['label']='Another question'
    if change=='wrong_group':item['group']='Another course'
    if change=='bad_purpose':item['purpose']='academic_name'
    if change=='convert_grade':item['format']='whitespace'
    if change=='manual_binding':
        pg['fields'][0]['label']='Describe your leadership';pg['fields'][0]['key']='g:'+digest({k:pg['fields'][0][k] for k in ('label','group','control','required')})[:24]
        a['fields'][0].update(key=pg['fields'][0]['key'],label=pg['fields'][0]['label']);a['observation_sha256']=digest(pg)
    if change=='skip_required':item.update(role='skip_optional',ref=None,purpose=None,format='identity')
    if change=='unscoped_mark':
        pg['fields'][-1]['group']='Different course';f=pg['fields'][-1];f['key']='g:'+digest({k:f[k] for k in ('label','group','control','required')})[:24]
        item.update(key=f['key'],group=f['group']);a['observation_sha256']=digest(pg)
    if change=='unknown_custom':
        f=pg['fields'][1];f['control']='unsupported';f['key']='g:'+digest({k:f[k] for k in ('label','group','control','required')})[:24]
        a['fields'][1].update(key=f['key'],control=f['control']);a['observation_sha256']=digest(pg)
    try:assert not build_plan(p,t,pg,semantic_analysis=a)['ready']
    except ProfileError:pass
    assert all(c.get('journal') is None for c in p['checkpoints'].values())


@pytest.mark.parametrize('change',['target','origin','authorization','real_test','restore_test'])
def test_permission_is_bound_to_selected_target_and_origin(change):
    p,t,pg,a,ctx=scenario();plan=build_plan(p,t,pg,semantic_analysis=a)
    if change=='target':ctx['target_id']='some_other_target'
    if change=='origin':ctx['authorized_origin']='https://other.invalid'
    if change=='authorization':ctx['application_authorized']=False
    if change=='real_test':ctx['real_account_test']=True;ctx['full_state_restoration_verified']=True
    if change=='restore_test':ctx['restore_after_test']=True
    with pytest.raises(ProfileError):prepare(p,plan['checkpoint_id'],pg,ctx)
    assert p['checkpoints'][plan['checkpoint_id']]['journal'] is None


def test_conditional_new_question_keeps_one_journal_and_collects_only_missing_fact():
    p,t,pg,a,ctx=scenario();plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx)
    original=copy.deepcopy(p['checkpoints'][key]['journal']);expanded=filled(pg,plan)
    new=field('Contact telephone','tel',seed=200);expanded['fields'].append(new)
    refs=[(i['ref'],i['purpose']) for i in a['fields']]+[('contact.phone','fact')];new_analysis=classify(expanded,refs)
    waiting=generic.resume(p,key,expanded,new_analysis)
    assert not waiting['ready'] and [q['fact_id'] for q in waiting['questions']]==['contact.phone']
    assert waiting['checkpoint_id']==key
    assert p['checkpoints'][key]['journal']==original
    source=add_statement(p,'Fictional student provides the newly required contact telephone.');set_fact(p,'contact.phone','+1 555 010 0200',source)
    p=json.loads(json.dumps(p));next_plan=generic.resume(p,key,expanded,new_analysis)
    assert next_plan['ready'] and len(next_plan['writes'])==1 and p['checkpoints'][key]['journal']==original
    saved=filled(expanded,next_plan);assert verify_saved(p,key,saved,revisited_after_save=True)['verified']


@pytest.mark.parametrize('change',['changed_fact','changed_binding','removed_field','changed_instructions','changed_options'])
def test_restart_cannot_silently_change_original_meaning_or_source(change):
    p,t,pg,a,ctx=scenario();plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx);saved=filled(pg,plan)
    proposed={**copy.deepcopy(a),'observation_sha256':digest(saved)}
    if change=='changed_fact':p['facts']['personal.legal_given_name']['value']='A different name'
    if change=='changed_binding':proposed['fields'][0]['ref']='personal.legal_family_name'
    if change=='removed_field':saved['fields'].pop()
    if change=='changed_instructions':saved['generic_context']['instructions']='Convert grades to GPA';saved['generic_form']['instructions_sha256']=digest(saved['generic_context']['instructions'])
    if change=='changed_options':saved['fields'][1]['options'][0]['label']='Other country'
    proposed['observation_sha256']=digest(saved)
    with pytest.raises(ProfileError):generic.resume(p,key,saved,proposed)
    assert p['checkpoints'][key]['journal'] is not None


def test_interrupted_saved_read_resumes_and_unsaved_cancel_verifies_originals():
    p,t,pg,a,ctx=scenario();plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx)
    saved=filled(pg,plan);p=json.loads(json.dumps(p));resumed=generic.resume(p,key,saved)
    assert resumed['ready'] and resumed['writes']==[]
    assert verify_saved(p,key,saved,revisited_after_save=True)['verified']
    plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx)
    recovery=generic.recovery(p,key,pg)
    assert recovery['plan']['checkpoint_id']==key and recovery['context']['journal_persisted']
    pending=generic.preview(p,[{'target_id':t,'page':pg,'analysis':a}]);assert pending['recovery_required'][0]['checkpoint_id']==key and not pending['questions']
    assert not generic.cancel(p,key,saved,revisited_saved_draft=True)['restored']
    assert generic.cancel(p,key,pg,revisited_saved_draft=True)['restored']


def test_saved_verification_rechecks_sources_and_never_exposes_generic_restoration_writes():
    p,t,pg,a,ctx=scenario();plan=build_plan(p,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(p,key,pg,ctx)
    with pytest.raises(ProfileError,match='unsaved_cancel'):restoration_writes(p,key,pg)
    saved=filled(pg,plan);p['facts']['personal.legal_given_name']['value']='Changed after save'
    with pytest.raises(ProfileError,match='source_changed'):verify_saved(p,key,saved,revisited_after_save=True)
    assert p['checkpoints'][key]['journal'] is not None


def test_already_matching_generic_draft_requires_independent_source_ready_saved_values():
    p,t,pg,a,ctx=scenario();plan=build_plan(p,t,pg,semantic_analysis=a);saved=filled(pg,plan)
    a['observation_sha256']=digest(saved)
    before=copy.deepcopy(p);wrong=copy.deepcopy(saved);wrong['fields'][0]['value']='Unsaved different name'
    assert not generic.verify_matching(p,t,saved,wrong,ctx,revisited_saved_draft=True,analysis=a)['verified'] and p==before
    assert generic.verify_matching(p,t,saved,saved,ctx,revisited_saved_draft=True,analysis=a)['verified']
    assert all(c.get('journal') is None for c in p['checkpoints'].values())
    del p['facts']['personal.legal_given_name'];a['observation_sha256']=digest(saved)
    assert not generic.verify_matching(p,t,saved,saved,ctx,revisited_saved_draft=True,analysis=a)['verified']


@pytest.mark.parametrize('kind',['empty','add_records','optional_consent','optional_narrative'])
def test_unobserved_record_work_and_excluded_optional_content_never_become_empty_success(kind):
    p,t,pg,a,ctx=scenario()
    if kind=='empty':pg['fields']=[];a['fields']=[]
    if kind=='add_records':pg['actions'].append({'key':'a:add','label':'Add school','selector':'[id="add"]','disabled':False})
    if kind in {'optional_consent','optional_narrative'}:
        f=field('I agree to the declaration' if kind=='optional_consent' else 'Additional comments','checkbox' if kind=='optional_consent' else 'textarea',required=False,value=False if kind=='optional_consent' else '',seed=600)
        pg['fields'].append(f);a['fields'].append({k:f[k] for k in ('label','group','control')}|{'key':f['key'],'role':'skip_optional','ref':None,'purpose':None,'format':'identity','reason':'Optional field is not requested.'})
    a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']


@pytest.mark.parametrize('edit',['pending_answer','known_fact','unasked_fact','unused_source','journal_change','target_change'])
def test_atomic_store_accepts_only_new_answers_to_recorded_conditional_questions(tmp_path,edit):
    p,t,pg,a,ctx=scenario();store=ProfileStore(tmp_path/'applicant.json');snap=ProfileSnapshot(p,None);store.save(snap)
    plan=build_plan(snap.data,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(snap.data,key,pg,ctx);store.save(snap)
    expanded=filled(pg,plan);expanded['fields'].append(field('Contact telephone','tel',seed=300))
    refs=[(i['ref'],i['purpose']) for i in a['fields']]+[('contact.phone','fact')]
    assert not generic.resume(snap.data,key,expanded,classify(expanded,refs))['ready'];store.save(snap)
    before=store.path.read_bytes();snap=store.load();original=copy.deepcopy(snap.data['checkpoints'][key]['journal'])
    source=add_statement(snap.data,'Fictional student supplies a phone number in response to the pending question.')
    set_fact(snap.data,'contact.phone','+1 555 010 0300',source)
    if edit=='known_fact':snap.data['facts']['personal.legal_given_name']['value']='Changed existing name'
    if edit=='unasked_fact':set_fact(snap.data,'contact.unasked','Unrequested information',source)
    if edit=='unused_source':add_statement(snap.data,'Unrelated unasked new source.')
    if edit=='journal_change':snap.data['checkpoints'][key]['journal']={}
    if edit=='target_change':snap.data['targets'][t]['program']='Different program'
    if edit=='pending_answer':
        store.save(snap);assert store.load().data['checkpoints'][key]['journal']==original
        assert generic.resume(snap.data,key,expanded,classify(expanded,refs))['ready'];store.save(snap)
    else:
        with pytest.raises(StoreError,match='active_recover_before_fact'):store.save(snap)
        assert store.path.read_bytes()==before


def test_explicit_spontaneous_fact_intake_survives_cli_restart_without_touching_journal(tmp_path,monkeypatch,capsys):
    from bc_application.cli import main
    from io import StringIO
    p,t,pg,a,ctx=record_scenario();store=ProfileStore(tmp_path/'applicant.json');snap=ProfileSnapshot(p,None);store.save(snap)
    plan=build_plan(snap.data,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(snap.data,key,pg,ctx);store.save(snap)
    original=copy.deepcopy(store.load().data);before=store.path.read_bytes()
    operations=[{'op':'statement','id':'answer','text':'A fictional applicant studied the curriculum but did not take its examination.'},
        {'op':'fact','field':'education.example_exam_taken','value':False,'source':'answer'}]
    args=['profile-update','--profile',str(store.path),'--stdin']
    monkeypatch.setattr('sys.stdin',StringIO(json.dumps(operations)))
    assert main(args)!=0;capsys.readouterr();assert store.path.read_bytes()==before
    monkeypatch.setattr('sys.stdin',StringIO(json.dumps(operations)))
    assert main(args+['--append-new-student-facts'])==0
    assert json.loads(capsys.readouterr().out)['ok']
    stored=store.load().data
    assert stored['facts']['education.example_exam_taken']['value'] is False
    assert stored['checkpoints']==original['checkpoints'] and stored['academic']==original['academic'] and stored['exams']==original['exams']
    for ref,fact in original['facts'].items():assert stored['facts'][ref]==fact
    assert generic.recovery(stored,key,pg)['plan']['checkpoint_id']==key
    saved=filled(pg,plan)
    assert verify_saved(stored,key,saved,revisited_after_save=True)['verified']


@pytest.mark.parametrize('edit',['known_fact','old_source','extra_source','checkpoint','target','review','exam','non_statement','extra_id','stale_writer'])
def test_explicit_new_fact_opt_in_never_unlocks_existing_browser_sources_or_state(tmp_path,edit):
    p,t,pg,a,ctx=scenario();store=ProfileStore(tmp_path/'applicant.json');snap=ProfileSnapshot(p,None);store.save(snap)
    plan=build_plan(snap.data,t,pg,semantic_analysis=a);key=plan['checkpoint_id'];prepare(snap.data,key,pg,ctx);store.save(snap)
    old=store.load();source=add_statement(snap.data,'The fictional student explicitly reports no curriculum examination.')
    ref='education.example_exam_taken';set_fact(snap.data,ref,False,source);ids=[ref]
    if edit=='known_fact':snap.data['facts']['personal.legal_given_name']['value']='Changed'
    if edit=='old_source':snap.data['sources'][p['facts']['personal.legal_given_name']['source_refs'][0]]['text']='Changed statement'
    if edit=='extra_source':add_statement(snap.data,'Unused fictional source')
    if edit=='checkpoint':snap.data['checkpoints'][key]['journal'][pg['fields'][0]['key']]='Changed original'
    if edit=='target':snap.data['targets'][t]['program']='Changed program'
    if edit=='review':snap.data['reviews']['new']={'state':'resolved'}
    if edit=='exam':
        from bc_application.profile import add_exam
        add_exam(snap.data,name='Invented exam',system='Invented',score='5',scale='1-5',source_id=source)
    if edit=='non_statement':snap.data['facts'][ref]['source_refs']=[p['psr_source_id']]
    if edit=='extra_id':ids.append('education.unmentioned')
    if edit=='stale_writer':store.save(old)
    before=store.path.read_bytes()
    with pytest.raises((StoreError,ProfileError)):
        store.save(snap,explicit_new_fact_ids=ids)
    assert store.path.read_bytes()==before
