"""Whole current-year page; source references, public widgets and saved recovery."""
import copy
import json
import re
from importlib.resources import files
from urllib.parse import urlsplit

from .browser import digest,permission_gate,validate_common_state
from .checkpoints import create_checkpoint,transaction_active
from .common_pages import state_matches
from .current_studies import compile_report
from .profile import ProfileError,_event,now

CONTRACT=json.loads(files('bc_application').joinpath('data/common_current.json').read_text(encoding='utf-8'))
ORIGIN=CONTRACT['origin'];PATH=CONTRACT['path'];HEADING=CONTRACT['heading'];COUNT=CONTRACT['count_label'];SCHEDULE=CONTRACT['scheduling_label']


def content(rows):return CONTRACT['content_base']+(' '+CONTRACT['course_content'] if rows else '')+' '+CONTRACT['content_end']


def values(page):return {f['key']:f['value'] for f in page['fields']}


def structure(page):
    return {k:page[k] for k in ('schema','url','title','common_current','actions')}|{'fields':[
        {k:v for k,v in f.items() if k not in {'value','invalid'} and not(k=='name' and f['control']=='radio')}
        for f in page['fields']]}


def validate(page):
    try:
        u=urlsplit(page['url']);tag=page['common_current'];rows=tag['rows'];fields={f['key']:f for f in page['fields']}
        if (page['schema']!='observed-current-page/1' or page['title']!='My Common Application | Common App'
                or u.scheme+'://'+u.netloc not in {ORIGIN,'http://127.0.0.1:8765','http://localhost:8765'}
                or u.path!=PATH or u.query or u.fragment or page.get('frames_present')
                or tag.get('schema')!='common-current-page/1' or set(tag)!={'schema','rows','content_sha256'}
                or not isinstance(rows,list) or len(rows)>25 or tag['content_sha256']!=digest(content(rows))
                or len(fields)!=len(page['fields'])):raise ProfileError('observed_current_course_contract_required')
        validate_common_state(page['state_metadata'])
        if (page['state_metadata']['current_page_key']!='tertiaryNavItem4_24'
                or 'secondaryNavItem4' not in {s['key'] for s in page['state_metadata']['items']}):raise ProfileError('observed_current_status_required')
        expected={'i:text_ques_307':(COUNT,'choice_input')}
        if rows:expected['r:ques_1803']=(SCHEDULE,'radio')
        for index,row in enumerate(rows,1):
            if set(row)!={'subject','name','level','terms'}:raise ProfileError('observed_current_course_row_required')
            for part,control in [('subject','choice_input'),('name','course_name'),('level','choice_input'),('terms','term_choices')]:
                key=row[part]
                if not re.fullmatch(r'i:text_ques_\d+',key) or key in expected:raise ProfileError('unique_current_course_control_required')
                expected[key]=(f'Course {index} '+('schedule' if part=='terms' else part),control)
        if set(fields)!=set(expected):raise ProfileError('unknown_current_course_field')
        selectors=set()
        for key,f in fields.items():
            label,control=expected[key]
            if (f['label']!=label or f['control']!=control or f['required'] is not True or f['disabled'] or f['readonly']
                    or f['selector_count']!=1 or f['selector_index']!=0 or f['selector'] in selectors):raise ProfileError('observed_current_control_required')
            selectors.add(f['selector'])
            if control=='radio':
                if (f['group']!=SCHEDULE or [o['label'] for o in f['options']]!=['Semester','Trimester','Quarter','Yearly']
                        or any(o['value']!=o['label'] or o['disabled'] or o['selector_count']!=1
                            or not re.fullmatch(r'\[id="option_ques_1803_\d+-input"\]',o['selector']) for o in f['options'])
                        or f['value'] not in ['',*[o['value'] for o in f['options']]]):raise ProfileError('observed_current_scheduling_required')
            elif f['group'] or f['selector']!=f'[id="{key[2:]}"]':raise ProfileError('observed_current_owner_required')
            if control=='term_choices':
                if (not isinstance(f['value'],list) or any(not isinstance(v,str) or not v for v in f['value'])
                        or f['value']!=sorted(set(f['value']))):raise ProfileError('observed_current_selected_terms_required')
            elif not isinstance(f['value'],str):raise ProfileError('observed_current_value_required')
        count=fields['i:text_ques_307']['value']
        if (not re.fullmatch(r'\d*',count) or int(count or 0)!=len(rows)):raise ProfileError('observed_current_count_rows_required')
        choices=page['choice_observations'];choice_keys={k for k,f in fields.items() if f['control'] in {'choice_input','term_choices'}}
        if set(choices)!=choice_keys:raise ProfileError('fresh_current_choice_options_required')
        for key,options in choices.items():
            if (not isinstance(options,list) or not 1<=len(options)<=100 or len({o['label'] for o in options})!=len(options)
                    or any(set(o)!={'value','label','disabled'} or not isinstance(o['label'],str) or not o['label']
                        or o['value']!=o['label'] or type(o['disabled']) is not bool for o in options)):
                raise ProfileError('distinct_current_choice_options_required')
            selected=fields[key]['value'];selected=selected if isinstance(selected,list) else [selected] if selected else []
            if any(sum(o['label']==v and not o['disabled'] for o in options)!=1 for v in selected):
                raise ProfileError('current_selection_absent_from_fresh_options')
        if page['actions']!=[{'key':'i:sectionContinue24','label':'Continue to next section','selector':'[id="sectionContinue24"]','disabled':False}]:
            raise ProfileError('observed_current_draft_save_required')
    except (KeyError,TypeError,AttributeError) as exc:raise ProfileError('observed_current_page_incomplete') from exc


def _compile(profile,target,ref,page):
    validate(page)
    if profile['targets'].get(target,{}).get('system')!='common_app':raise ProfileError('student_selected_common_target_required')
    return compile_report(profile,ref)


def _step(page,c):
    fields={f['key']:f for f in page['fields']};rows=page['common_current']['rows'];writes=[];desired=values(page)
    def put(key,value):
        f=fields[key]
        if f['control'] in {'choice_input','term_choices'}:
            choices=page['choice_observations'][key]
            for v in value if isinstance(value,list) else [value]:
                if sum(o['label']==v and not o['disabled'] for o in choices)!=1:raise ProfileError('explicit_value_not_in_current_options')
        desired[key]=value
        if f['value']!=value:writes.append({'field_key':key,'value':value})
    def populated():return any(fields[key]['value'] for r in rows for key in r.values())
    if str(len(c['courses']))!=fields['i:text_ques_307']['value']:
        if populated():raise ProfileError('populated_current_course_count_change_requires_review')
        put('i:text_ques_307',str(len(c['courses'])));stage='count'
    elif fields['r:ques_1803']['value']!=c['scheduling_system']:
        if populated():raise ProfileError('populated_current_scheduling_change_requires_review')
        put('r:ques_1803',c['scheduling_system']);stage='scheduling'
    else:
        stage='fields'
        for row,course in zip(rows,c['courses'],strict=True):
            for part in ('subject','name','level','terms'):put(row[part],sorted(course[part]) if part=='terms' else course[part])
    return {'stage':stage,'writes':writes,**({'structure_sha256':digest(structure(page)),
        'expected_values_sha256':digest(desired)} if stage=='fields' else {})}


def preview(profile,target,ref,page):
    if any(transaction_active(c) for c in profile['checkpoints'].values()):raise ProfileError('pending_transaction_requires_recovery')
    c=_compile(profile,target,ref,page)
    return {**c,**({'next':_step(page,c)} if c['ready'] else {}),'profile_changed':False,'website_actions_performed':False}


def prepare(profile,target,ref,page,context):
    result=preview(profile,target,ref,page);permission_gate(context,page,ORIGIN)
    if not result['ready']:return result
    if context.get('real_account_test') and (result['next']['stage']!='fields' or any(f['invalid'] for f in page['fields'])):
        raise ProfileError('real_current_course_shape_change_qa_unverified')
    key=create_checkpoint(profile,target,page['url'],fact_ids=result['required_fact_ids'],course_ids=result['required_course_ids'],record_columns=result['required_record_columns'])
    profile['checkpoints'][key].update(kind='common_current',state='prepared',journal=copy.deepcopy(values(page)),context=copy.deepcopy(context),
        report_ref=ref,source_fingerprint=result['source_fingerprint'],original_structure=copy.deepcopy(structure(page)),
        original_state_metadata=copy.deepcopy(page['state_metadata']),original_invalid_fields=sorted(f['key'] for f in page['fields'] if f['invalid']))
    _event(profile,'current_course_page_prepared',[key]);return advance(profile,key,page)


def _active(profile,key,page):
    cp=profile['checkpoints'].get(key)
    if not cp or cp.get('kind')!='common_current' or cp.get('journal') is None:raise ProfileError('prepared_current_course_page_required')
    if any(k!=key and transaction_active(c) for k,c in profile['checkpoints'].items()):raise ProfileError('pending_transaction_requires_recovery')
    c=_compile(profile,cp['target_id'],cp['report_ref'],page);permission_gate(cp['context'],page,ORIGIN)
    if not state_matches(cp['original_state_metadata'],page['state_metadata'],'tertiaryNavItem4_24','secondaryNavItem4',resume=True):
        raise ProfileError('unrelated_current_course_status_changed')
    if not c['ready'] or c['source_fingerprint']!=cp['source_fingerprint']:raise ProfileError('current_course_resume_source_gate_failed')
    return cp,c


def advance(profile,key,page):
    cp,c=_active(profile,key,page);step=_step(page,c)
    plan={'schema':'common-current-plan/1','system':'common_app','ready':True,'checkpoint_id':key,'page_url':page['url'],
        'observation_sha256':digest(page),'choice_observations':page['choice_observations'],**step}
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan));return {'ready':True,'checkpoint_id':key,'stage':step['stage'],'plan':plan}


def verify(profile,key,page,*,revisited_after_save,restoration=False):
    cp,c=_active(profile,key,page);plan=cp.get('prepared_plan',{})
    okay=(revisited_after_save is True and ((values(page)==cp['journal'] and structure(page)==cp['original_structure']
        and page['state_metadata']==cp['original_state_metadata'] and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['original_invalid_fields']) if restoration else
        (plan.get('stage')=='fields' and digest(values(page))==plan['expected_values_sha256'] and digest(structure(page))==plan['structure_sha256']
        and not any(f['invalid'] for f in page['fields']) and state_matches(cp['original_state_metadata'],page['state_metadata'],'tertiaryNavItem4_24','secondaryNavItem4'))))
    if not okay:cp['state']='needs_restore';return {'verified':False,'state':'needs_restore','reason':'current_saved_page_mismatch'}
    cp.update(state='restored' if restoration else 'verified',last_verified_at=now())
    if restoration or not(cp['context'].get('real_account_test') or cp['context'].get('restore_after_test')):
        cp['journal']=None
        for item in ('prepared_plan','original_structure','original_state_metadata','original_invalid_fields'):cp.pop(item,None)
    _event(profile,'current_course_original_verified' if restoration else 'current_course_saved_verified',[key])
    return {'verified':True,'restoration':restoration,'courses':len(c['courses']),'source_records':c['source_record_count'],'fields':len(page['fields'])}


def recovery(profile,key,page):
    cp,_=_active(profile,key,page)
    if structure(page)!=cp['original_structure'] or cp['original_invalid_fields']:raise ProfileError('current_unsaved_cancel_or_intended_resume_required')
    plan={'schema':'common-current-plan/1','system':'common_app','ready':True,'checkpoint_id':key,'page_url':page['url'],'stage':'fields','restoration':True,
        'observation_sha256':digest(page),'structure_sha256':digest(cp['original_structure']),'expected_values_sha256':digest(cp['journal']),
        'choice_observations':page['choice_observations'],'writes':[{'field_key':f['key'],'value':cp['journal'][f['key']]} for f in page['fields'] if f['value']!=cp['journal'][f['key']]]}
    return {'plan':plan,'context':cp['context']}


def cancel(profile,key,page,*,revisited_saved_draft):
    cp,_=_active(profile,key,page)
    okay=(revisited_saved_draft is True and values(page)==cp['journal'] and structure(page)==cp['original_structure']
        and page['state_metadata']==cp['original_state_metadata'] and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['original_invalid_fields'])
    if not okay:cp['state']='needs_restore';return {'restored':False,'state':'needs_restore'}
    cp.update(state='restored',journal=None)
    for item in ('prepared_plan','original_structure','original_state_metadata','original_invalid_fields'):cp.pop(item,None)
    _event(profile,'current_course_unsaved_canceled',[key]);return {'restored':True,'restore_save_performed':False}
