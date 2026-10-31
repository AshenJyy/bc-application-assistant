"""Source-gated school choice/count stages and scoped factual school statements."""
import copy
import json
import re
from importlib.resources import files
from urllib.parse import urlsplit

from .browser import digest,permission_gate,validate_common_state
from .checkpoints import create_checkpoint,transaction_active
from .common_pages import state_matches
from .profile import ProfileError,_event,now
from .schools import compile_report,ORIGIN

CONTRACT=json.loads(files('bc_application').joinpath('data/common_schools.json').read_text(encoding='utf-8'))


def spec(page):
    kind=page.get('common_school',{}).get('kind');s=CONTRACT.get(kind)
    if kind not in {'current','other'} or urlsplit(page['url']).path!=s['path']:raise ProfileError('observed_school_page_contract_required')
    return s


def structure(page):
    return stable_structure({k:page[k] for k in ('schema','url','title','common_school','actions')}|{'fields':page['fields']})


def stable_structure(recorded):
    # Radio/checkbox names contain a render generation; public owners, option
    # values, labels and semantic selectors remain part of the identity.
    return {**recorded,'fields':[
        {k:v for k,v in f.items() if k not in {'value','invalid','statement_format'} and not(k=='name' and f['control'] in {'radio','checkbox'})}
        for f in recorded['fields']]}


def values(page):
    return {f['key']:f['value'] for f in page['fields']}|{'@schools':page['school_values'],
        '@statement_formats':{f['key']:f['statement_format'] for f in page['fields'] if f['control']=='school_statement'}}


def validate_lookup(page):
    u=urlsplit(page.get('page_url',''));question=page.get('question_id','')
    if (page.get('schema')!='observed-school-lookup/1' or u.scheme+'://'+u.netloc not in {ORIGIN,'http://127.0.0.1:8765','http://localhost:8765'}
            or u.path not in {CONTRACT['current']['path'],CONTRACT['other']['path']} or u.query or u.fragment
            or page.get('title')!=CONTRACT['lookup_title'] or question not in {r['question_id'] for s in ('current','other') for r in CONTRACT[s]['records']}
            or (u.path==CONTRACT['current']['path'])!=(question=='245')
            or page.get('search_by')!=CONTRACT['lookup_search'] or not isinstance(page.get('query'),str) or not page['query'].strip()
            or page.get('query_key')!='searchTermControl'+question or page.get('loading') is not False
            or type(page.get('total')) is not int or page['total']<0
            or not isinstance(page.get('options'),list) or not 1<=len(page['options'])<=50):
        raise ProfileError('observed_public_school_lookup_required')
    codes=[];labels=[]
    for option in page['options']:
        if option.get('kind')=='school':
            if (set(option)!={'kind','name','city','region','country','ceeb','label','selector','selector_count','selected'}
                    or any(not isinstance(option[k],str) or not option[k].strip() for k in ('name','city','region','country','label'))
                    or not re.fullmatch(r'\d{6}',option['ceeb']) or not re.fullmatch(r'\[id="selectionListResult\d+-"\]',option['selector'])
                    or option['selector_count']!=1 or type(option['selected']) is not bool):
                raise ProfileError('observed_school_candidate_required')
            codes.append(option['ceeb']);labels.append(option['label'])
        elif option.get('kind')!='manual' or option.get('label') not in {'Homeschooled',"I don't see my high school in this list"}:
            raise ProfileError('unknown_school_lookup_option')
    if len(codes)!=len(set(codes)) or len(labels)!=len(set(labels)):raise ProfileError('ambiguous_school_lookup_candidates')


def validate(page):
    try:
        s=spec(page);u=urlsplit(page['url']);tag=page['common_school'];fields={f['key']:f for f in page['fields']}
        if (page['schema']!='observed-school-page/1' or page['title']!=CONTRACT['title'] or page.get('frames_present')
                or u.scheme+'://'+u.netloc not in {ORIGIN,'http://localhost:8765','http://127.0.0.1:8765'} or u.query or u.fragment
                or set(tag)!={'schema','kind','records'} or tag['schema']!='common-school-page/1'
                or len(fields)!=len(page['fields']) or not isinstance(tag['records'],list) or len(tag['records'])>len(s['records'])
                or page.get('heading')!=s['heading']):raise ProfileError('observed_school_page_shape_required')
        validate_common_state(page['state_metadata'])
        if (page['state_metadata']['current_page_key']!='tertiaryNavItem4_'+u.path.split('/')[-1]
                or 'secondaryNavItem4' not in {i['key'] for i in page['state_metadata']['items']}):raise ProfileError('observed_school_status_required')
        expected={};selected_count=len(tag['records'])
        def add(key,label,control,required=True):expected[key]={'label':label,'control':control,'required':required}
        if tag['kind']=='current':
            if selected_count!=1:raise ProfileError('one_current_school_slot_required')
            for name in ('boarding','graduate'):add(s[name]['key'],s[name]['label'],'radio')
            graduate=fields.get(s['graduate']['key'],{}).get('value')
            if graduate=='0':add(s['graduation']['key'],s['graduation']['label'],'text')
            for part in CONTRACT['progression']:add('g:265:'+part['part'],part['label'],'checkbox',False)
            changed=any(fields.get('g:265:'+part['part'],{}).get('value') is True for part in CONTRACT['progression'] if part['part']!='unchanged')
            note_needed=changed
        else:
            add(s['count']['key'],s['count']['label'],'radio');count=fields.get(s['count']['key'],{}).get('value','')
            if count not in {'','0','1','2','3'} or (int(count or 0)!=selected_count):raise ProfileError('observed_school_count_slots_required')
            note_needed=selected_count>0
        if note_needed:add('statement:'+s['statement']['question_id'],s['statement']['label'],'school_statement')
        if set(page['school_values'])!={r['question_id'] for r in tag['records']}:raise ProfileError('observed_school_card_values_required')
        for index,record in enumerate(tag['records']):
            wanted=s['records'][index]
            if record!={k:wanted[k] for k in ('question_id','label')}:raise ProfileError('observed_school_slot_identity_required')
            card=page['school_values'][record['question_id']]
            if card is not None and (set(card)!={'name','ceeb','text'} or not re.fullmatch(r'\d{6}',card['ceeb']) or not card['name'] or not card['text']):
                raise ProfileError('observed_selected_school_identity_required')
            for part in ('entry','exit'):
                if part+'_key' in wanted:add(wanted[part+'_key'],wanted[part+'_label'],'text')
        if set(fields)!=set(expected):raise ProfileError('unknown_or_missing_school_question')
        for key,f in fields.items():
            e=expected[key]
            if (any(f[k]!=v for k,v in e.items()) or f['disabled'] or f['readonly'] or f['selector_count']!=1 or f['selector_index']!=0):
                raise ProfileError('observed_school_control_identity_required')
            if f['control']=='radio':
                q=key.removeprefix('r:ques_');expected_labels=['0','1','2','3'] if tag['kind']=='other' else ['Yes','No']
                if (f['group']!=f['label'] or [o['label'] for o in f['options']]!=expected_labels
                        or [o['value'] for o in f['options']]!=(['0','1','2','3'] if tag['kind']=='other' else ['0','1'])
                        or any(not re.fullmatch(r'\[id="option_ques_'+q+r'_\d+-input"\]',o['selector']) or o['selector_count']!=1 or o['disabled'] for o in f['options'])):
                    raise ProfileError('observed_school_radio_options_required')
            elif f['control']=='checkbox':
                part=next(p for p in CONTRACT['progression'] if key=='g:265:'+p['part'])
                if (f['group']!=CONTRACT['progression_label'] or f['selector']!=f'fieldset:has([id="title_ques_265"]) input[type="checkbox"][value="{part["value"]}"]'
                        or type(f['value']) is not bool):raise ProfileError('observed_school_progression_required')
            elif f['control']=='school_statement':
                if (f['selector']!=f'[role="textbox"][contenteditable="true"][aria-labelledby="title_ques_{s["statement"]["question_id"]}"]'
                        or f.get('statement_format') not in {'empty','plain_paragraph','rich'} or f['group']):raise ProfileError('scoped_factual_school_statement_required')
            elif f['selector']!=f'[id="{key.removeprefix("i:")}"]' or f['group']:raise ProfileError('observed_school_date_identity_required')
        action=page['actions']
        if action!=[{'key':'i:sectionContinue'+u.path.split('/')[-1],'selector':f'[id="sectionContinue{u.path.split("/")[-1]}"]','label':'Continue to next section','disabled':False}]:
            raise ProfileError('observed_school_draft_save_required')
    except (KeyError,TypeError,AttributeError) as exc:raise ProfileError('observed_school_contract_incomplete') from exc


def _compile(profile,target,report_ref,page):
    validate(page)
    if profile['targets'].get(target,{}).get('system')!='common_app':raise ProfileError('student_selected_common_target_required')
    compiled=compile_report(profile,report_ref)
    if compiled.get('kind') and compiled['kind']!=page['common_school']['kind']:raise ProfileError('school_report_page_kind_mismatch')
    if compiled['ready']:
        origin=urlsplit(page['url']).scheme+'://'+urlsplit(page['url']).netloc
        if any(urlsplit(r['identity']['evidence']['page_url']).netloc!=urlsplit(origin).netloc for r in compiled['schools']):
            raise ProfileError('school_identity_environment_mismatch')
    return compiled


def _step(page,compiled):
    s=spec(page);fields={f['key']:f for f in page['fields']};kind=compiled['kind'];rows=compiled['schools']
    if kind=='other':
        current=fields[s['count']['key']]['value']
        if current!=str(len(rows)):
            if any(page['school_values'].values()):raise ProfileError('populated_school_count_change_requires_review')
            return {'stage':'count','writes':[{'field_key':s['count']['key'],'value':str(len(rows))}]}
    # Check every existing school before an earlier empty lookup is filled.
    for index,record in enumerate(page['common_school']['records']):
        if index>=len(rows):raise ProfileError('unexpected_existing_school_slot')
        card=page['school_values'][record['question_id']];identity=rows[index]['identity']
        if card and (card['name']!=identity['name'] or card['ceeb']!=identity['ceeb']):raise ProfileError('conflicting_existing_school_identity')
    for index,record in enumerate(page['common_school']['records']):
        if page['school_values'][record['question_id']] is None:
            return {'stage':'school','question_id':record['question_id'],'identity':rows[index]['identity']}
    if kind=='current':
        graduate=fields[s['graduate']['key']]
        if graduate['value']!='0':return {'stage':'graduation_mode','writes':[{'field_key':graduate['key'],'value':'0'}]}
        changes=[{'field_key':'g:265:'+p['part'],'value':p['part'] in compiled['progression']} for p in CONTRACT['progression']]
        if any(fields[w['field_key']]['value']!=w['value'] for w in changes):return {'stage':'progression_mode','writes':changes}
    desired=values(page);writes=[]
    def put(key,value):
        desired[key]=value
        if fields[key]['value']!=value:writes.append({'field_key':key,'value':value})
    for index,row in enumerate(rows):
        slot=s['records'][index];put(slot['entry_key'],row['entry'])
        if kind=='other':put(slot['exit_key'],row['exit'])
    if kind=='current':
        put(s['boarding']['key'],'0' if compiled['boarding'] else '1');put(s['graduation']['key'],compiled['graduation'])
    if compiled['explanation'] is not None:
        key='statement:'+s['statement']['question_id'];put(key,compiled['explanation'])
        if any(w['field_key']==key for w in writes):desired['@statement_formats'][key]='plain_paragraph'
    return {'stage':'fields','writes':writes,'structure_sha256':digest(structure(page)),'expected_values_sha256':digest(desired)}


def preview(profile,target,report_ref,page):
    if any(transaction_active(c) for c in profile['checkpoints'].values()):raise ProfileError('pending_transaction_requires_recovery')
    c=_compile(profile,target,report_ref,page)
    return {**c,**({'next':_step(page,c)} if c['ready'] else {}),'profile_changed':False,'website_actions_performed':False}


def prepare(profile,target,report_ref,page,context):
    report=preview(profile,target,report_ref,page);permission_gate(context,page,ORIGIN)
    if not report['ready']:return report
    first=report['next']
    if context.get('real_account_test') and (first['stage']!='fields' or any(f['invalid'] for f in page['fields'])
            or any(f['control']=='school_statement' and f['statement_format']!='plain_paragraph' for f in page['fields'])):
        raise ProfileError('real_school_creation_or_shape_change_qa_unverified')
    key=create_checkpoint(profile,target,page['url'],fact_ids=report['required_fact_ids'])
    cp=profile['checkpoints'][key]
    cp.update(kind='common_school',state='prepared',journal=copy.deepcopy(values(page)),context=copy.deepcopy(context),
        report_ref=report_ref,source_fingerprint=report['source_fingerprint'],original_structure=structure(page),
        original_state_metadata=copy.deepcopy(page['state_metadata']),original_invalid_fields=sorted(f['key'] for f in page['fields'] if f['invalid']))
    _event(profile,'school_page_prepared',[key]);return advance(profile,key,page)


def _active(profile,key,page):
    cp=profile['checkpoints'].get(key)
    if not cp or cp.get('kind')!='common_school' or cp.get('journal') is None:raise ProfileError('prepared_school_page_required')
    if any(k!=key and transaction_active(c) for k,c in profile['checkpoints'].items()):raise ProfileError('pending_transaction_requires_recovery')
    validate(page);permission_gate(cp['context'],page,ORIGIN)
    if not state_matches(cp['original_state_metadata'],page['state_metadata'],page['state_metadata']['current_page_key'],'secondaryNavItem4',resume=True):
        raise ProfileError('unrelated_school_status_changed')
    c=_compile(profile,cp['target_id'],cp['report_ref'],page)
    if not c['ready'] or c['source_fingerprint']!=cp['source_fingerprint']:raise ProfileError('school_resume_source_gate_failed')
    return cp,c


def advance(profile,key,page):
    cp,c=_active(profile,key,page);step=_step(page,c)
    plan={'schema':'common-school-plan/1','system':'common_app','ready':True,'checkpoint_id':key,'page_url':page['url'],
        'observation_sha256':digest(page),**step}
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan));return {'ready':True,'checkpoint_id':key,'stage':step['stage'],'plan':plan}


def verify(profile,key,page,*,revisited_after_save,restoration=False):
    cp,c=_active(profile,key,page)
    if restoration:
        okay=(revisited_after_save is True and values(page)==cp['journal'] and structure(page)==stable_structure(cp['original_structure'])
            and page['state_metadata']==cp['original_state_metadata'] and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['original_invalid_fields'])
    else:
        plan=cp.get('prepared_plan',{})
        okay=(revisited_after_save is True and plan.get('stage')=='fields' and digest(values(page))==plan['expected_values_sha256']
            and digest(structure(page))==plan['structure_sha256'] and not any(f['invalid'] for f in page['fields'])
            and state_matches(cp['original_state_metadata'],page['state_metadata'],page['state_metadata']['current_page_key'],'secondaryNavItem4'))
    if not okay:
        cp['state']='needs_restore';return {'verified':False,'state':'needs_restore','reason':'school_saved_page_mismatch'}
    cp.update(state='restored' if restoration else 'verified',last_verified_at=now())
    if restoration or not(cp['context'].get('real_account_test') or cp['context'].get('restore_after_test')):
        cp['journal']=None
        for item in ('prepared_plan','original_structure','original_state_metadata','original_invalid_fields'):cp.pop(item,None)
    _event(profile,'school_original_verified' if restoration else 'school_saved_verified',[key])
    return {'verified':True,'restoration':restoration,'schools':len(c['schools']),'fields':len(page['fields'])}


def recovery(profile,key,page):
    cp,c=_active(profile,key,page)
    original_structure=stable_structure(cp['original_structure'])
    if structure(page)!=original_structure or cp['original_invalid_fields']:raise ProfileError('school_unsaved_cancel_or_intended_resume_required')
    if values(page)['@schools']!=cp['journal']['@schools']:raise ProfileError('school_record_rollback_not_established')
    if any(v=='rich' for v in cp['journal']['@statement_formats'].values()):raise ProfileError('rich_school_statement_rollback_not_established')
    writes=[{'field_key':f['key'],'value':cp['journal'][f['key']]} for f in page['fields'] if f['value']!=cp['journal'][f['key']]]
    plan={'schema':'common-school-plan/1','system':'common_app','ready':True,'checkpoint_id':key,'page_url':page['url'],'stage':'fields',
        'restoration':True,'observation_sha256':digest(page),'structure_sha256':digest(original_structure),
        'expected_values_sha256':digest(cp['journal']),'writes':writes}
    return {'plan':plan,'context':cp['context']}


def cancel(profile,key,page,*,revisited_saved_draft):
    cp,c=_active(profile,key,page)
    okay=(revisited_saved_draft is True and values(page)==cp['journal'] and structure(page)==stable_structure(cp['original_structure'])
        and page['state_metadata']==cp['original_state_metadata'] and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['original_invalid_fields'])
    if not okay:cp['state']='needs_restore';return {'restored':False,'state':'needs_restore'}
    cp.update(state='restored',journal=None)
    for item in ('prepared_plan','original_structure','original_state_metadata','original_invalid_fields'):cp.pop(item,None)
    _event(profile,'school_unsaved_canceled',[key]);return {'restored':True,'restore_save_performed':False}
