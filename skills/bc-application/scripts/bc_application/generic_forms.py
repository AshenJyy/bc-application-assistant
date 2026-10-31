"""Agent-proposed semantic bindings over the shared factual page transaction core.

There is no site label dictionary or model client here. The conversational agent
reads the actual observation; this module checks its proposal and source gates.
"""
import copy
import re
from decimal import Decimal,InvalidOperation
from datetime import date
from urllib.parse import urlsplit

from .adapters.uc import MANUAL
from .browser import digest,origin,structure,values
from .checkpoints import transaction_active
from .profile import FACT_ID,ProfileError,_event,now
from .source_refs import is_metadata,metadata_value,validate_path,select_path,dependencies

DRAFT=re.compile(r'save(?:\s+draft|\s+changes|\s*(?:&|and)\s*(?:continue|next))?',re.I)
MANUAL_EXTRA=re.compile(r'personal statement|motivation|tell us about|terms of|i accept|i agree',re.I)
PURPOSES={'fact','name','address','date','academic_name','academic_mark','academic_credit'}
FORMATS={'identity','whitespace','iso_date','english_date','date_dmy','date_year','date_month_name','decimal_fixed_2','phone_nanp_area','phone_nanp_line','phone_e164_area','phone_e164_number','observed_label','catalogue_label'}


READBACK_POLICY='workflow.saved_page_readback'


def readback_skipped(profile):
    """Only an explicit applicant statement can opt out of saved-page readback."""
    fact=profile['facts'].get(READBACK_POLICY,{})
    refs=fact.get('source_refs',[])
    from .checkpoints import page_requirements
    return (fact.get('value') is False and bool(refs)
        and all(profile['sources'].get(ref,{}).get('kind')=='student_statement' for ref in refs)
        and page_requirements(profile,fact_ids=[READBACK_POLICY])['data_ready'])


def choice_source_allowed(value,ref):
    if type(value) is bool:return True
    if not isinstance(value,str):return False
    if any(c.isalpha() for c in value):return True
    return ref.startswith('psr-context:') and ref.endswith(':student_grade_raw') and value.isdecimal() and 1<=int(value)<=12


def directory_unchanged(profile,checkpoint):
    current=digest(profile.get('school_directory'))
    return checkpoint.get('generic_directory_sha256',current)==current


def source_fingerprint(profile,analysis):
    refs={i['ref'] for i in analysis['fields'] if i['role']=='factual'}|set(analysis.get('policy_refs',[]))
    if analysis.get('record'):refs.add(analysis['record']['ref'])
    if analysis.get('record',{}).get('component'):refs.add(analysis['record']['component'])
    refs.update(r['ref'] for r in analysis.get('child_records',[]))
    refs.update(r['component'] for r in analysis.get('child_records',[]) if r.get('component'))
    refs|={d for ref in list(refs) for d in dependencies(ref,profile)}
    facts={r:profile['facts'].get(r) for r in refs if not r.startswith('psr:') and not is_metadata(r)}
    sources={s for f in facts.values() if f for s in f['source_refs']}|{profile['psr_source_id']}
    release_policy=(facts.get('exams.ap_result_release_policy') or {}).get('value',{})
    if isinstance(release_policy,dict) and release_policy.get('schedule_source_id'):
        sources.add(release_policy['schedule_source_id'])
    exams={}
    for ref in refs:
        if ref.startswith('exam-record:'):
            key=ref[len('exam-record:'):]
            if key not in profile['exams']:key=key.rsplit(':',1)[0]
            exams[key]=profile['exams'].get(key)
    return digest({'academic':profile['academic_sha256'],'directory':profile.get('school_directory'),
        **({'exam_records':exams} if exams else {}),
        'facts':facts,'sources':{s:profile['sources'].get(s) for s in sources}})


def collection_actions(profile,target_id,page,analysis):
    """Read-only parent witnesses: every visible row belongs to a verified child."""
    observed=page['generic_form'].get('record_collections',[]);proposed=analysis.get('record_collections',[])
    if not observed and not proposed:return set()
    if (not isinstance(proposed,list) or len(proposed)!=len(observed) or any(not isinstance(c,dict) or not isinstance(c.get('key'),str) for c in proposed)
            or {c.get('key') for c in proposed}!={c['key'] for c in observed}):
        raise ProfileError('complete_record_collection_review_required')
    allowed=set();seen_checkpoints=set()
    from .pages import resolve,encode
    for review in proposed:
        if set(review)!={'key','rows','action_keys','reason'} or not isinstance(review['reason'],str) or not review['reason'].strip():
            raise ProfileError('explicit_record_collection_review_required')
        table=next(c for c in observed if c['key']==review['key']);rows=review['rows']
        if (not isinstance(rows,list) or len(rows)!=len(table['rows']) or not rows or any(not isinstance(r,dict) or type(r.get('row_index')) is not int for r in rows)
                or sorted(r.get('row_index',-1) for r in rows)!=list(range(len(rows)))):
            raise ProfileError('every_record_summary_row_requires_verification')
        identities=[]
        for row in rows:
            if (set(row)!={'row_index','checkpoint_id','identity_field_key'} or not isinstance(row['checkpoint_id'],str)
                    or not isinstance(row['identity_field_key'],str)):raise ProfileError('verified_record_row_reference_required')
            key=row['checkpoint_id'];cp=profile['checkpoints'].get(key,{})
            verified=(cp.get('state')=='verified' and cp.get('journal') is None
                and cp.get('verified_source_sha256')==source_fingerprint(profile,cp['semantic_analysis'])) if cp.get('semantic_analysis') else False
            acknowledged=(readback_skipped(profile) and cp.get('state')=='saved_unverified_user_skipped'
                and cp.get('save_receipt',{}).get('save_performed') is True
                and cp.get('acknowledged_source_sha256')==source_fingerprint(profile,cp['semantic_analysis'])) if cp.get('semantic_analysis') else False
            if (key in seen_checkpoints or not (verified or acknowledged)
                    or cp.get('target_id')!=target_id or cp.get('page_key')!=page['url'] or not cp.get('semantic_analysis',{}).get('record')
                    ):
                raise ProfileError('current_source_verified_child_record_required')
            seen_checkpoints.add(key)
            item=next((i for i in cp['semantic_analysis']['fields'] if i['key']==row['identity_field_key'] and i['role']=='factual'),None)
            field=next((f for f in cp['observed_structure']['fields'] if f['key']==row['identity_field_key']),None)
            if not item or not field:raise ProfileError('verified_child_identity_field_required')
            raw,_=resolve(profile,item['ref']);rendered=display_source_value(item,item['ref'],raw);encoded=encode(field,rendered)
            identity=next((o['label'] for o in field['options'] if o['value']==encoded),None) if field['control']=='select' else str(rendered)
            if not identity or table['rows'][row['row_index']].count(identity)!=1:raise ProfileError('exact_child_identity_cell_required')
            identities.append(identity)
        if len(set(identities))!=len(identities):raise ProfileError('ambiguous_record_summary_identity')
        if not isinstance(review['action_keys'],list) or len(set(review['action_keys']))!=len(review['action_keys']):raise ProfileError('explicit_record_collection_actions_required')
        for key in review['action_keys']:
            action=next((a for a in page['actions'] if a['key']==key),None)
            inert_remove=bool(action and action['label'].strip()=='Remove Qualification' and page['generic_form'].get('view'))
            if (key in allowed or not action or action['disabled'] or MANUAL.search(action['label']) or DRAFT.fullmatch(action['label'])
                    or re.search(r'\b(?:pay|fee|fees|sign|send|delete|remove|submit|purchase)\b',action['label'],re.I) and not inert_remove
                    or not re.search(r'\b(?:add|institution|school|record|course|subject|qualification)\b',action['label'],re.I)):
                raise ProfileError('read_only_record_management_action_required')
            allowed.add(key)
    return allowed


def bind_site(profile,target_id,url,source_id):
    """Record an explicitly authorized application URL, never an inferred platform."""
    target=profile['targets'].get(target_id);source=profile['sources'].get(source_id,{})
    site_origin=origin(url)
    if (not target or source.get('kind')!='student_statement' or urlsplit(url).fragment
            or not (site_origin.startswith('https://') or site_origin in {'http://127.0.0.1:8765','http://localhost:8765'})):
        raise ProfileError('explicit_authorized_application_site_required')
    site={'origin':site_origin,'entry_url':url,'source_id':source_id}
    if target.get('application_site') and target['application_site']!=site:
        raise ProfileError('application_site_change_requires_review')
    target['application_site']=site


def validate(page):
    tag=page.get('generic_form',{});scope=tag.get('scope',{});destination=tag.get('destination',{})
    if (set(tag)-{'dialog','record_collections','view','views'}!={'schema','scope','instructions_sha256','destination'} or tag['schema']!='generic-form/1'
            or not re.fullmatch('[a-f0-9]{64}',tag.get('instructions_sha256',''))
            or set(scope)!={'selector','selector_count','selector_index'} or not isinstance(scope['selector'],str)
            or not scope['selector'] or scope['selector_count']!=1 or scope['selector_index']!=0
            or set(destination)!={'action','method'} or destination['method'] not in {'get','post'}
            or origin(destination['action'])!=origin(page['url']) or page.get('scope') or page.get('frames_present')
            or page.get('generic_context',{}).get('instructions') is None
            or digest(page['generic_context']['instructions'])!=tag.get('instructions_sha256')
            or any(k in page for k in ('common_factual','common_ielts','common_academic','common_school','common_current','uc_factual','uc_course_editor','mit_coursework'))):
        raise ProfileError('observed_single_native_form_required')
    dialog=tag.get('dialog')
    view=tag.get('view')
    views=tag.get('views')
    if views is not None and (dialog or not isinstance(views,list) or not 1<=len(views)<=25 or any(not isinstance(v,str) or not 1<=len(v.strip())<=300 for v in views) or len(set(views))!=len(views)
            or view is not None and (not isinstance(view,dict) or view.get('name') not in views)):
        raise ProfileError('bounded_observed_form_views_required')
    if view is not None and (dialog or not isinstance(view,dict) or set(view)!={'name'} or not isinstance(view['name'],str) or not 1<=len(view['name'].strip())<=300):
        raise ProfileError('observed_selected_form_view_required')
    if dialog is not None and (not isinstance(dialog,dict) or set(dialog)!={'name','selector','selector_count'}
            or not isinstance(dialog['name'],str) or not dialog['name'].strip()
            or not isinstance(dialog['selector'],str) or not dialog['selector'] or dialog['selector_count']!=1):
        raise ProfileError('unique_named_native_dialog_required')
    tables=tag.get('record_collections',[])
    if not isinstance(tables,list) or len(tables)>20 or dialog and tables:raise ProfileError('bounded_parent_record_summaries_required')
    for c in tables:
        if (not isinstance(c,dict) or set(c)!={'key','headers','rows','caption','selector','selector_count'}
                or not isinstance(c['headers'],list) or not 2<=len(c['headers'])<=30 or not all(isinstance(h,str) and h for h in c['headers'])
                or not isinstance(c['rows'],list) or not 1<=len(c['rows'])<=100 or not isinstance(c['caption'],str)
                or c['key']!='rc:'+digest({k:c[k] for k in ('headers','caption')})[:24]
                or not isinstance(c['selector'],str) or not c['selector'] or c['selector_count']!=1
                or any(not isinstance(r,list) or len(r)!=len(c['headers']) or any(not isinstance(s,str) or len(s)>2000 for s in r) for r in c['rows'])):
            raise ProfileError('observed_rectangular_record_summary_required')
    if len({c['key'] for c in tables})!=len(tables):raise ProfileError('unique_record_summary_required')
    for f in page['fields']:
        expected='g:'+digest({k:f[k] for k in ('label','group','control','required')})[:24]
        if f['key']!=expected:raise ProfileError('observed_semantic_field_identity_required')
        if f['control'] in {'select','radio'}:
            for o in f['options']:
                if o['value']!=digest({'label':o['label'],'group':o.get('group','')}) or not isinstance(o.get('native_value'),str):
                    raise ProfileError('observed_semantic_option_identity_required')


def manual(field):
    return bool(MANUAL.search(field['label']+' '+field.get('group','')) or MANUAL_EXTRA.search(field['label']+' '+field.get('group','')))


def textarea_allowed(item):
    ref=item.get('ref','');purpose=item.get('purpose')
    return ((purpose=='academic_name' and ref.startswith('psr:') and ref.rsplit(':',1)[-1] in {'description','course_description'})
        or (purpose=='name' and re.fullmatch(r'personal\.(legal_given_name|legal_family_name|middle_name)',ref) is not None)
        or (purpose=='address' and re.fullmatch(r'address\.(permanent|mailing)\.(street|street_1|street_2|line_1|line_2|city|postal_code)',ref) is not None))


def validate_exam_component(profile,record):
    exam=profile['exams'].get(record.get('ref','').removeprefix('exam-record:'),{})
    component=record.get('component')
    prefix=exam.get('score_fact_id','').rsplit('.',1)[0]
    allowed=[prefix+'.'+c for c in ('score','listening','reading','writing','speaking')] if exam.get('system')=='IELTS' else (
        [prefix+'.ab_subscore'] if exam.get('system')=='AP' and exam.get('name')=='AP Calculus BC' else [])
    if (component not in allowed
            or component not in profile['facts'] or 'path' in record):
        raise ProfileError('canonical_exam_component_record_required')
    if exam.get('system')=='AP':
        metadata_value(profile,record['ref']+':ab_subscore')


def active_parent(profile,target_id,page,analysis,*,exclude=None):
    """One declared exam child may run inside a frozen selected-view date stage."""
    active={k:c for k,c in profile['checkpoints'].items() if k!=exclude and transaction_active(c)}
    key=(analysis or {}).get('parent_checkpoint_id')
    if not active and not key:return None
    parent=active.get(key);record=(analysis or {}).get('record')
    if (not parent or set(active)!={key} or not page.get('generic_form',{}).get('dialog')
            or not record or record not in parent.get('semantic_analysis',{}).get('child_records',[])
            or parent['target_id']!=target_id or parent['page_key']!=page['url']
            or parent.get('state')!='prepared' or parent.get('journal') is None
            or parent.get('generic_stage_controller',{}).get('purpose')!='date'
            or not parent.get('prepared_plan',{}).get('generic_stage')
            or not parent['prepared_plan']['generic_form'].get('view')
            or parent['semantic_analysis'].get('parent_checkpoint_id') or (analysis or {}).get('child_records')
            or profile['academic_sha256']!=parent.get('generic_academic_sha256') or not directory_unchanged(profile,parent)
            or source_fingerprint(profile,parent['semantic_analysis'])!=parent.get('generic_nested_source_sha256')):
        raise ProfileError('pending_transaction_requires_recovery')
    permitted=set(dependencies(record['ref'],profile))|{record.get('component')}
    if any(i.get('role')=='factual' and not (i.get('ref') in permitted or i.get('ref','').startswith(record['ref']+':')) for i in analysis.get('fields',[])):
        raise ProfileError('nested_exam_field_record_scope_required')
    return key


def analysis_for(profile,target,page,analysis=None):
    fresh=analysis is not None
    if analysis is None:
        candidates=[cp for cp in profile['checkpoints'].values() if cp['target_id']==target['target_id'] and cp['page_key']==page['url']
            and digest(structure(page))==digest(cp.get('observed_structure'))]
        if len(candidates)!=1:raise ProfileError('fresh_semantic_analysis_required')
        previous=candidates[0]
        if digest(structure(page))!=digest(previous.get('observed_structure')):raise ProfileError('fresh_semantic_analysis_required')
        analysis=previous.get('semantic_analysis')
    if (not isinstance(analysis,dict) or set(analysis)-{'policy_refs','record','record_collections','record_action','record_view','parent_checkpoint_id','child_records','save_mode'}!={'schema','observation_sha256','fields'}
            or analysis['schema']!='form-semantics/1' or not isinstance(analysis['fields'],list)
            or fresh and analysis['observation_sha256']!=digest(page)):
        raise ProfileError('observation_bound_semantic_analysis_required')
    policies=analysis.get('policy_refs',[])
    if (not isinstance(policies,list) or any(not isinstance(p,str) for p in policies)
            or len(policies)!=len(set(policies)) or not set(policies)<={'address.application_address_policy'}):
        raise ProfileError('supported_applicant_policy_reference_required')
    fields={f['key']:f for f in page['fields']};items={}
    record=analysis.get('record')
    if record is not None:
        if (not page['generic_form'].get('dialog') or not isinstance(record,dict) or set(record)-{'path','component'}!={'ref'}
                or not isinstance(record['ref'],str) or not (FACT_ID.fullmatch(record['ref']) or re.fullmatch(r'(?:psr-(?:school:[^:]+|course:.+)|exam-record:exam:[a-f0-9]+)',record['ref']))):
            raise ProfileError('canonical_dialog_record_reference_required')
        if 'path' in record:validate_path(record['path'])
        if 'component' in record:validate_exam_component(profile,record)
    if page['generic_form'].get('dialog') and record is None:raise ProfileError('canonical_dialog_record_reference_required')
    if 'record_view' in analysis and (not record or analysis['record_view']!=page['generic_form'].get('dialog',{}).get('name')):
        raise ProfileError('observed_record_view_required')
    if 'record_action' in analysis and (analysis['record_action']!='add_draft' or not record or not page['generic_form'].get('dialog')):
        raise ProfileError('explicit_dialog_draft_record_add_required')
    if 'save_mode' in analysis and (analysis['save_mode']!='stay' or not page['generic_form'].get('view')):
        raise ProfileError('explicit_selected_view_stationary_save_required')
    if 'child_records' in analysis:
        children=analysis['child_records']
        if (record or not page['generic_form'].get('view') or not isinstance(children,list) or not 1<=len(children)<=25
                or len({digest(r) for r in children})!=len(children)):
            raise ProfileError('bounded_selected_view_child_records_required')
        for child in children:
            if not isinstance(child,dict) or set(child)-{'component'}!={'ref'} or not isinstance(child['ref'],str) or not child['ref'].startswith('exam-record:'):
                raise ProfileError('canonical_exam_child_record_required')
            metadata_value(profile,child['ref']+':name')
            if 'component' in child:validate_exam_component(profile,child)
    for item in analysis['fields']:
        if (not isinstance(item,dict) or set(item)-{'choice','source_path'}!={'key','label','group','control','role','ref','purpose','format','reason'}
                or item['key'] in items or item['key'] not in fields
                or item['role'] not in {'factual','manual','unsupported','skip_optional'}
                or item['format'] not in FORMATS or not isinstance(item['reason'],str) or not item['reason'].strip()):
            raise ProfileError('complete_semantic_field_classification_required')
        f=fields[item['key']]
        if any(item[k]!=f[k] for k in ('label','group','control')):raise ProfileError('semantic_field_evidence_changed')
        if item['role']=='factual':
            ref=item['ref']
            if (item['purpose'] not in PURPOSES or not isinstance(ref,str)
                    or not(ref.startswith('psr:') or is_metadata(ref) or FACT_ID.fullmatch(ref))):raise ProfileError('source_reference_binding_required')
            if 'source_path' in item:
                if ref.startswith('psr:') or is_metadata(ref):raise ProfileError('canonical_fact_path_only')
                validate_path(item['source_path'])
            if record and ref==record['ref'] and 'path' in record and item.get('source_path',[])[:len(record['path'])]!=record['path']:
                raise ProfileError('dialog_field_record_scope_mismatch')
            if record and record['ref'].startswith('psr-school:') and ref.startswith('psr-school:') and not ref.startswith(record['ref']+':'):
                raise ProfileError('dialog_field_record_scope_mismatch')
            if record and record['ref'].startswith('psr-school:') and ref.startswith('school-directory:') and ref.split(':')[1]!=record['ref'].split(':')[1]:
                raise ProfileError('dialog_field_record_scope_mismatch')
            if record and record['ref'].startswith('psr-course:'):
                rid=record['ref'][len('psr-course:'):]
                if (ref.startswith('psr:') and ref[4:].rsplit(':',1)[0]!=rid
                        or ref.startswith('psr-course:') and ref[len('psr-course:'):].rsplit(':',1)[0]!=rid):
                    raise ProfileError('dialog_field_record_scope_mismatch')
            if record and record['ref'].startswith('exam-record:'):
                if (ref.startswith('exam-record:') and not ref.startswith(record['ref']+':')
                        or ref.startswith('exams.') and ref not in [*dependencies(record['ref'],profile),record.get('component')]):
                    raise ProfileError('dialog_field_record_scope_mismatch')
            if is_metadata(ref):
                expected='date' if ref.endswith((':admit_date',':withdrawal_date',':completion_date',':result_release_date',':date')) else 'name' if ref.endswith(':name') and not ref.startswith('exam-record:') else 'fact'
                if item['purpose']!=expected:raise ProfileError('original_psr_metadata_purpose_required')
            academic=ref.startswith('psr:')
            columns={'academic_name':{'description','course_description'},'academic_mark':{'school_percent','school_grade_symbol','final_result'},'academic_credit':{'credits'}}
            if academic!=(item['purpose'] in columns) or academic and ref.rsplit(':',1)[-1] not in columns[item['purpose']]:
                raise ProfileError('original_academic_column_purpose_required')
            if academic and item['format'] not in ({'identity','whitespace','catalogue_label','observed_label'} if item['purpose']=='academic_name' else {'identity'}):
                raise ProfileError('academic_conversion_excluded')
            if item['format'] in {'date_year','date_month_name'} and item['purpose']!='date':raise ProfileError('date_component_purpose_required')
            if item['format']=='decimal_fixed_2' and (item['purpose']!='fact' or not ref.startswith('psr-average:') or f['control'] not in {'text','number'}):
                raise ProfileError('lossless_derived_percentage_display_required')
            if item['format']=='observed_label':
                choice=item.get('choice',{})
                name_alias=academic and item['purpose']=='academic_name' and record and record['ref']=='psr-course:'+ref[4:].rsplit(':',1)[0]
                keys={'source_value','label','level'} if name_alias else {'source_value','label'}
                if (item['purpose']!='fact' and not name_alias or f['control'] not in {'select','radio'} or set(choice)!=keys
                        or not choice_source_allowed(choice['source_value'],ref)
                        or len([o for o in f['options'] if o['label']==choice['label'] and not o['disabled']])!=1):
                    raise ProfileError('source_bound_observed_label_required')
                if name_alias:
                    level_ref='psr-course:'+ref[4:].rsplit(':',1)[0]+':level'
                    if choice['level']!=metadata_value(profile,level_ref) or not any(i.get('role')=='factual' and i.get('ref')==level_ref for i in analysis['fields']):
                        raise ProfileError('separate_original_course_level_binding_required')
            elif item['format']=='catalogue_label':
                choice=item.get('choice',{})
                if (not academic or item['purpose']!='academic_name' or f['control'] not in {'select','radio'} or set(choice)-{'level'}!={'label'}
                        or len([o for o in f['options'] if o['label']==choice['label'] and not o['disabled']])!=1):raise ProfileError('exact_original_course_catalogue_label_required')
                if 'level' in choice:
                    level_ref='psr-course:'+ref[4:].rsplit(':',1)[0]+':level'
                    if (choice['level']!=metadata_value(profile,level_ref) or not any(
                            i.get('role')=='factual' and i.get('ref')==level_ref for i in analysis['fields'])):
                        raise ProfileError('separate_original_course_level_binding_required')
            elif 'choice' in item:raise ProfileError('unexpected_choice_mapping')
            if f.get('widget',{}).get('kind')=='calendar' and (item['purpose']!='date' or item['format']!='date_dmy'):
                raise ProfileError('calendar_complete_date_binding_required')
            if f['control']=='textarea' and not textarea_allowed(item):raise ProfileError('generic_narrative_control_excluded')
            if manual(f):raise ProfileError('manual_question_cannot_become_factual')
        elif item['ref'] is not None or item['purpose'] is not None or item['format']!='identity':
            raise ProfileError('nonfactual_classification_cannot_bind_answers')
        elif 'choice' in item or 'source_path' in item:raise ProfileError('nonfactual_classification_cannot_bind_answers')
        if item['role']=='skip_optional' and f['required']:raise ProfileError('required_question_cannot_be_skipped')
        items[item['key']]=item
    if set(items)!=set(fields):raise ProfileError('every_visible_field_requires_classification')
    return copy.deepcopy(analysis),items


class SemanticAdapter:
    def __init__(self,profile,target,page,analysis=None):
        validate(page);site=target.get('application_site',{})
        section=' '.join((page.get('title',''),page.get('generic_context',{}).get('instructions',''),page['generic_form'].get('dialog',{}).get('name','')))
        if MANUAL.search(section) or MANUAL_EXTRA.search(section):raise ProfileError('manual_application_section_excluded')
        if site.get('origin')!=origin(page['url']):raise ProfileError('target_application_site_mismatch')
        self.system=target['system'];self.application_origin=site['origin'];self.target_id=target['target_id']
        self.profile=profile
        self.view=page['generic_form'].get('view')
        self.analysis,self.items=analysis_for(profile,target,page,analysis)
        self.collection_review_blockers=[]
        try:self.reviewed_collection_actions=collection_actions(profile,self.target_id,page,self.analysis)
        except ProfileError as exc:
            self.reviewed_collection_actions=set();self.collection_review_blockers.append({'reason':str(exc)})

    def binding_for_page(self,field,target,profile,page):return self.items[field['key']]['ref']
    def checkpoint_instance(self):
        return 'generic-record:'+digest(self.analysis['record'])+(':'+digest(self.analysis['record_view']) if 'record_view' in self.analysis else '') if 'record' in self.analysis else 'generic-view:'+digest(self.view) if self.view else None
    def required_for_page(self,field,page):return bool(field['required'])
    def collection_policy(self,profile,page):
        refs=[i['ref'] for i in self.items.values() if i['role']=='factual']+self.analysis.get('policy_refs',[])
        if self.analysis.get('record'):refs.append(self.analysis['record']['ref'])
        if self.analysis.get('record',{}).get('component'):refs.append(self.analysis['record']['component'])
        refs += [r['ref'] for r in self.analysis.get('child_records',[])]+[r['component'] for r in self.analysis.get('child_records',[]) if r.get('component')]
        refs += [d for ref in list(refs) for d in dependencies(ref,profile)]
        return {'allowed':not page.get('collections'),'fact_ids':list(dict.fromkeys(r for r in refs if not r.startswith('psr:') and not is_metadata(r)))}
    def dependent_field_keys(self,page,writes):return []
    def fact_blockers(self,profile,page):
        from .pages import resolve,encode
        blockers=list(self.collection_review_blockers)
        for child in self.analysis.get('child_records',[]):
            candidates=[c for c in profile['checkpoints'].values() if c['target_id']==self.target_id and c['page_key']==page['url']
                and c.get('semantic_analysis',{}).get('record')==child]
            if not any((c['state']=='verified' and c.get('verified_source_sha256')==source_fingerprint(profile,c['semantic_analysis'])
                    or readback_skipped(profile) and c['state']=='saved_unverified_user_skipped' and c.get('save_receipt',{}).get('save_performed') is True
                    and c.get('acknowledged_source_sha256')==source_fingerprint(profile,c['semantic_analysis'])) for c in candidates):
                blockers.append({'reason':'declared_exam_child_requires_saved_receipt','record':child})
        record=self.analysis.get('record')
        if record:
            try:
                if record['ref'].startswith(('psr-school:','psr-course:','exam-record:')):
                    metadata_value(profile,record['ref']+':name')
                elif record['ref'] in profile['facts']:
                    selected=profile['facts'][record['ref']]['value']
                    if 'path' in record:selected=select_path(selected,record['path'])
                    if not isinstance(selected,dict):raise ProfileError('canonical_record_object_required')
            except ProfileError as exc:blockers.append({'reason':str(exc)})
        for f in page['fields']:
            i=self.items[f['key']]
            if i['role']=='factual' and (f['readonly'] or f['disabled']):
                try:
                    raw,_=resolve(profile,i['ref'])
                    if encode(f,self.display_value(f,i['ref'],raw))!=f['value']:raise ProfileError('readonly_factual_value_mismatch')
                except ProfileError as exc:blockers.append({'field_key':f['key'],'reason':str(exc)})
        return blockers
    def recommendations(self,field,ref):return []
    def skip_optional_unsupported(self,field):return self.items[field['key']]['role']=='skip_optional' and not manual(field)
    def skip_blank_optional_manual(self,field,page):return False
    def manual(self,field):return self.items[field['key']]['role']=='manual' or manual(field)
    def save_action(self,page):
        candidates=[a for a in page['actions'] if not a['disabled'] and (DRAFT.fullmatch(a['label'].strip()) or self.draft_add(a)) and a.get('selector')]
        if self.analysis.get('save_mode')=='stay':
            stationary=[a for a in candidates if a['label'].strip().lower() in {'save','save draft','save changes'}]
            return stationary[0] if len(stationary)==1 else None
        if readback_skipped(self.profile):
            advancing=[a for a in candidates if re.search(r'(?:and|&)\s*(?:next|continue)$',a['label'].strip(),re.I)]
            if len(advancing)==1:return advancing[0]
        # Prefer a unique stay-on-page draft Save when the form also offers a
        # next-section action. This choice never discards an observed action.
        stationary=[a for a in candidates if a['label'].strip().lower() in {'save','save draft','save changes'}]
        if len(stationary)==1:return stationary[0]
        return candidates[0] if len(candidates)==1 else None
    def draft_add(self,action):return self.analysis.get('record_action')=='add_draft' and action['label'].strip()=='Add'
    def page_blockers(self,page):
        blockers=[]
        if not page['fields']:blockers.append({'reason':'generic_empty_form_requires_review'})
        if not any(i['role']=='factual' for i in self.items.values()):blockers.append({'reason':'generic_no_selected_facts'})
        if any(a['key'] not in getattr(self,'reviewed_collection_actions',set()) and not DRAFT.fullmatch(a['label'].strip()) and not self.draft_add(a) and a['label'].strip().lower() not in {'cancel','back','reset'} for a in page['actions']):
            blockers.append({'reason':'generic_nonfield_action_requires_capability'})
        text=page.get('title','')+' '+page.get('generic_context',{}).get('instructions','')
        if MANUAL.search(text) or MANUAL_EXTRA.search(text):blockers.append({'reason':'manual_application_section'})
        if page.get('state_metadata'):blockers.append({'reason':'generic_navigation_state_requires_migration'})
        for f in page['fields']:
            item=self.items[f['key']]
            status_witness=(item.get('ref') or '').startswith('psr-course:') and (item.get('ref') or '').endswith((':result_status',':result_pending'))
            status_witness |= bool(self.analysis.get('record',{}).get('component') and (item.get('ref') or '').startswith(self.analysis['record']['ref']+':') and (item.get('ref') or '').endswith('_name'))
            if item['role']=='unsupported' or item['role']=='factual' and (f['control'] not in {'text','textarea','email','tel','number','date','select','radio','checkbox'} or f['disabled'] and not status_witness):
                blockers.append({'field_key':f['key'],'reason':'generic_control_capability_unavailable'})
            if f['control']=='textarea' and item['role'] not in {'factual','manual'}:
                blockers.append({'field_key':f['key'],'reason':'generic_narrative_control_requires_review'})
            if f['required'] and not f['label']:blockers.append({'field_key':f['key'],'reason':'observed_question_meaning_required'})
        # A mark/credit binding must have a name witness for that same original
        # record and observed field group. It cannot silently address another row.
        for item in self.items.values():
            if item['role']=='factual' and item['purpose'] in {'academic_mark','academic_credit'}:
                record=item['ref'][4:].rsplit(':',1)[0]
                scoped_dialog=page['generic_form'].get('dialog') and self.analysis.get('record',{}).get('ref')=='psr-course:'+record
                if not (item['group'] or scoped_dialog) or not any(n['purpose']=='academic_name' and n['group']==item['group'] and n['ref'][4:].rsplit(':',1)[0]==record for n in self.items.values() if n['role']=='factual' and n['ref'].startswith('psr:')):
                    blockers.append({'field_key':item['key'],'reason':'same_group_original_course_name_required'})
        return blockers
    def display_value(self,field,ref,value):
        return display_source_value(self.items[field['key']],ref,value)


def display_source_value(item,ref,value):
    if 'source_path' in item:value=select_path(value,item['source_path'])
    fmt=item['format']
    if fmt=='identity':return value
    if fmt=='decimal_fixed_2':
        try:
            number=Decimal(str(value));fixed=number.quantize(Decimal('.01'))
            if not number.is_finite() or fixed!=number:raise ValueError()
            return str(fixed)
        except (ValueError,InvalidOperation) as exc:raise ProfileError('lossless_derived_percentage_display_required') from exc
    if fmt=='catalogue_label':
        label=item['choice']['label']
        normalized=lambda s:re.sub(r'\s+',' ',s).strip().casefold()
        if not isinstance(value,str):raise ProfileError('original_course_title_catalogue_mismatch')
        title=normalized(value)
        if 'level' in item['choice']:title=re.sub(r'\s+'+re.escape(item['choice']['level'])+r'[a-z]?$', '',title)
        if title!=normalized(label):raise ProfileError('original_course_title_catalogue_mismatch')
        return label
    if fmt=='observed_label':
        choice=item['choice']
        if type(value) is not type(choice['source_value']) or value!=choice['source_value']:raise ProfileError('observed_label_source_value_changed')
        return choice['label']
    if fmt in {'phone_nanp_area','phone_nanp_line'}:
        if ref!='contact.mobile' or not isinstance(value,str):raise ProfileError('explicit_nanp_mobile_required')
        normalized=re.sub(r'[\s()\-]','',value)
        if not re.fullmatch(r'\+1[2-9]\d{2}[2-9]\d{6}',normalized):raise ProfileError('explicit_nanp_mobile_required')
        return normalized[2:5] if fmt=='phone_nanp_area' else normalized[5:]
    if fmt in {'phone_e164_area','phone_e164_number'}:
        if ref not in {'contact.primary_phone','contact.mobile'} or not isinstance(value,str):raise ProfileError('explicit_mobile_phone_required')
        normalized=re.sub(r'[\s()\-]','',value)
        if re.fullmatch(r'\+861[3-9]\d{9}',normalized):return '' if fmt=='phone_e164_area' else normalized[3:]
        if re.fullmatch(r'\+1[2-9]\d{2}[2-9]\d{6}',normalized):return normalized[2:5] if fmt=='phone_e164_area' else normalized[5:]
        raise ProfileError('explicit_supported_mobile_segmentation_required')
    if fmt=='whitespace':
        if not isinstance(value,str):raise ProfileError('text_format_requires_original_string')
        return re.sub(r'\s+',' ',re.sub(r'-\r?\n\s*','-',value)).strip()
    if not isinstance(value,str):raise ProfileError('explicit_iso_date_required')
    if fmt in {'date_year','date_month_name'}:
        if not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?',value):raise ProfileError('explicit_year_month_required')
        try:d=date.fromisoformat(value+'-01' if len(value)==7 else value)
        except ValueError as exc:raise ProfileError('explicit_year_month_required') from exc
        months=('January','February','March','April','May','June','July','August','September','October','November','December')
        return str(d.year) if fmt=='date_year' else months[d.month-1]
    try:d=date.fromisoformat(value)
    except ValueError as exc:raise ProfileError('explicit_iso_date_required') from exc
    months=('January','February','March','April','May','June','July','August','September','October','November','December')
    return d.isoformat() if fmt=='iso_date' else d.strftime('%d-%m-%Y') if fmt=='date_dmy' else months[d.month-1]+' '+str(d.day)+', '+str(d.year)


def adapter_for(profile,target,page,analysis=None):
    if 'generic_form' in page:return SemanticAdapter(profile,target,page,analysis)
    from .adapters import get_adapter
    return get_adapter(target['system'])


def permission(profile,target,page,context):
    if (context.get('target_id')!=target['target_id'] or context.get('application_authorized') is not True
            or context.get('authorized_origin')!=target.get('application_site',{}).get('origin')
            or context.get('authorized_origin')!=origin(page['url'])):
        raise ProfileError('target_origin_bound_application_authorization_required')
    if context.get('real_account_test') or context.get('restore_after_test'):
        raise ProfileError('generic_real_state_recovery_unverified')


def plan_details(profile,page,adapter,gate,blockers):
    questions=[];unavailable=[]
    for ref in dict.fromkeys(gate['missing_fact_ids']+gate['conflicted_fact_ids']):
        uses=[{'field_key':i['key'],'label':i['label'],'group':i['group']} for i in adapter.items.values() if i['ref']==ref]
        availability=profile['facts'].get('education.course_prediction_availability',{}).get('value',{})
        if ref in gate['missing_fact_ids'] and ref not in gate['conflicted_fact_ids'] and ref.startswith('education.course_predictions.') and isinstance(availability,dict) and availability.get(ref[len('education.course_predictions.'):]) is False:
            from .checkpoints import page_requirements
            if page_requirements(profile,fact_ids=['education.course_prediction_availability'])['data_ready']:
                unavailable.append({'fact_id':ref,'reason':'school_prediction_not_provided','uses':uses})
                continue
        questions.append({'fact_id':ref,'reason':'conflict' if ref in gate['conflicted_fact_ids'] else 'missing','uses':uses})
    return {'target_id':adapter.target_id,'generic_form':page['generic_form'],'semantic_bindings':[i for i in adapter.items.values() if i['role']=='factual'],
        'saved_page_readback':not readback_skipped(profile),
        **({'record_action':{'kind':'add_draft','record':adapter.analysis['record']}} if adapter.analysis.get('record_action') else {}),
        'questions':questions,'unavailable_facts':unavailable,'implementation_gaps':[b for b in blockers if b.get('reason') in {'generic_control_capability_unavailable','generic_empty_form_requires_review','generic_nonfield_action_requires_capability','generic_narrative_control_requires_review','unmapped_required_factual_field','observed_question_meaning_required','same_group_original_course_name_required'}]}


def acknowledge_save(profile,checkpoint_id,receipt):
    """Record a draft Save receipt, without asserting saved values were verified."""
    cp=profile['checkpoints'].get(checkpoint_id,{})
    plan=cp.get('prepared_plan',{})
    if (cp.get('state')!='prepared' or not cp.get('semantic_analysis') or cp.get('journal') is None
            or cp.get('generic_stage_controller') or plan.get('generic_stage')
            or plan.get('saved_page_readback') is not False or not readback_skipped(profile)):
        raise ProfileError('explicit_readback_opt_out_and_prepared_whole_page_required')
    from .checkpoints import page_requirements
    gate=page_requirements(profile,fact_ids=cp['required_fact_ids'],course_ids=cp['required_course_ids'],record_columns=cp.get('required_record_columns'))
    if (not gate['data_ready'] or not directory_unchanged(profile,cp) or profile['academic_sha256']!=cp['generic_academic_sha256']
            or any(digest(profile['facts'].get(ref))!=sha for ref,sha in cp['generic_fact_hashes'].items())):
        raise ProfileError('generic_save_acknowledgement_source_changed')
    expected={'schema':'generic-draft-save/1','save_performed':True,'revisited_after_save':False,
        'verification_required':True,'target_id':cp['target_id'],'page_url':cp['page_key'],
        'structure_sha256':plan['structure_sha256'],'expected_values_sha256':plan['expected_values_sha256'],
        'save_action_key':plan['save_action']['key']}
    if receipt!=expected:raise ProfileError('matching_observed_draft_save_receipt_required')
    cp.update(state='saved_unverified_user_skipped',readback_skipped_at=now(),
        acknowledged_source_sha256=source_fingerprint(profile,cp['semantic_analysis']),save_receipt=copy.deepcopy(receipt))
    cp.pop('verified_source_sha256',None);cp.pop('last_verified_at',None)
    cp.pop('prepared_plan',None)
    _event(profile,'draft_saved_readback_skipped_by_student',[checkpoint_id,READBACK_POLICY])
    return {'saved':True,'verified':False,'readback_skipped':True,'state':cp['state'],
        'checkpoint_id':checkpoint_id,'full_application_complete':False}


def preview(profile,requests):
    from .pages import build_plan
    if not isinstance(requests,list) or not 1<=len(requests)<=25:raise ProfileError('bounded_semantic_requests_required')
    active=[{'checkpoint_id':key,'target_id':cp['target_id'],'page_url':cp['page_key'],'kind':'generic_form' if cp.get('semantic_analysis') else 'other'}
        for key,cp in profile['checkpoints'].items() if transaction_active(cp)]
    if active:return {'schema':'generic-intake/1','ready':False,'recovery_required':active,'pages':[],'questions':[],
        'profile_changed':False,'website_actions_performed':False,'full_application_complete':False}
    working=copy.deepcopy(profile);questions={};pages=[]
    for request in requests:
        if set(request)!={'target_id','page','analysis'}:raise ProfileError('observed_semantic_request_required')
        plan=build_plan(working,request['target_id'],request['page'],semantic_analysis=request['analysis'])
        if 'generic_form' not in plan:raise ProfileError('generic_form_required')
        pages.append({'target_id':request['target_id'],'page_url':plan['page_url'],'ready':plan['ready'],
            'write_count':len(plan['writes']),'implementation_gaps':plan['implementation_gaps'],'blockers':plan['blockers']})
        for q in plan['questions']:
            item=questions.setdefault(q['fact_id'],{'fact_id':q['fact_id'],'reason':q['reason'],'uses':[]})
            item['uses'].extend({'target_id':request['target_id'],'page_url':plan['page_url'],**u} for u in q['uses'])
    return {'schema':'generic-intake/1','ready':all(p['ready'] for p in pages),'pages':pages,'questions':list(questions.values()),
        'profile_changed':False,'website_actions_performed':False,'full_application_complete':False}


def prepare_stage(profile,target_id,page,analysis,context,controller_key,*,resume_key=None,reaffirm_native_select=False):
    """Journal one explicit branch choice. This plan cannot authorize Save.

    Branch discovery may replace currently inapplicable questions. All answers
    for the resulting whole page are required by accept_stage before draft Save.
    """
    from .browser import validate_observation,permission_gate
    from .checkpoints import create_checkpoint,page_requirements
    from .pages import resolve,encode
    active_parent(profile,target_id,page,analysis,exclude=resume_key)
    previous=profile['checkpoints'].get(resume_key) if resume_key else None
    if resume_key and (not previous or not transaction_active(previous) or previous.get('journal') is None or previous['target_id']!=target_id
            or previous['page_key']!=page['url'] or not previous.get('semantic_analysis')
            or profile['academic_sha256']!=previous.get('generic_academic_sha256') or not directory_unchanged(profile,previous)
            or any(digest(profile['facts'].get(r))!=h for r,h in previous.get('generic_fact_hashes',{}).items())):
        raise ProfileError('generic_restart_source_and_journal_required')
    validate_observation(page)
    target=profile['targets'].get(target_id)
    if not target:raise ProfileError('student_selected_target_required')
    permission(profile,target,page,context);permission_gate(context,page,target['application_site']['origin'])
    adapter=SemanticAdapter(profile,target,page,analysis)
    if previous and any(adapter.analysis.get(k)!=previous['semantic_analysis'].get(k) for k in ('record','record_view')):
        raise ProfileError('generic_record_context_changed')
    field=next((f for f in page['fields'] if f['key']==controller_key),None)
    item=adapter.items.get(controller_key,{})
    count_control=field and field['control'] in {'text','number'} and item.get('format')=='identity' and item.get('purpose')=='fact'
    date_control=field and field.get('widget',{}).get('kind')=='calendar' and item.get('format')=='date_dmy' and item.get('purpose')=='date'
    if (not field or field['control'] not in {'select','radio','checkbox'} and not (count_control or date_control) or field['readonly'] or field['disabled']
            or item.get('role')!='factual' or item.get('purpose')!='fact' and not date_control or item['ref'].startswith('psr:') or manual(field)):
        raise ProfileError('explicit_factual_branch_controller_required')
    dependency_refs=dependencies(item['ref'],profile)
    gate=page_requirements(profile,fact_ids=dependency_refs if is_metadata(item['ref']) else [item['ref'],*dependency_refs])
    if not gate['data_ready']:
        if previous and gate['missing_fact_ids'] and not gate['conflicted_fact_ids'] and not gate['source_issues']:
            previous['generic_pending_fact_ids']=list(gate['missing_fact_ids'])
            _event(profile,'generic_branch_controller_answer_needed',[resume_key,*gate['missing_fact_ids']])
            return {'ready':False,'questions':[{'fact_id':r,'reason':'missing','uses':[{'field_key':field['key'],'label':field['label'],'group':field['group']}]} for r in gate['missing_fact_ids']], 'website_actions_performed':False}
        raise ProfileError('branch_controller_source_gate_failed')
    raw,_=resolve(profile,item['ref']);desired=encode(field,adapter.display_value(field,item['ref'],raw))
    if count_control and (type(raw) is not int or not 0<=raw<=999):raise ProfileError('bounded_explicit_count_controller_required')
    if desired==field['value'] and not reaffirm_native_select and not count_control:raise ProfileError('branch_controller_already_matches')
    if reaffirm_native_select and (field['control']!='select' or field.get('widget',{}).get('kind')!='owned_native_select' or desired!=field['value']):
        raise ProfileError('matching_owned_native_select_required')
    key=resume_key or create_checkpoint(profile,target_id,page['url'],fact_ids=dependency_refs if is_metadata(item['ref']) else [item['ref'],*dependency_refs],instance_key=adapter.checkpoint_instance())
    plan={'schema':'page-plan/1','checkpoint_id':key,'ready':True,'target_id':target_id,'system':target['system'],
        'allowed_origin':target['application_site']['origin'],'page_url':page['url'],'generic_form':page['generic_form'],
        'generic_stage':True,'semantic_bindings':[copy.deepcopy(item)],'observation_sha256':digest(page),
        'structure_sha256':digest(structure(page)),'expected_values_sha256':digest({**values(page),controller_key:desired}),
        'writes':[{'field_key':controller_key,'fact_ref':item['ref'],'value':desired,**({'native_event':True} if reaffirm_native_select else {}),**({'count_input':True} if count_control else {})}], 'save_action':None}
    cp=profile['checkpoints'][key]
    if not previous:
        cp.update(journal=copy.deepcopy(values(page)),generic_original_structure_sha256=digest(structure(page)),original_values_sha256=digest(values(page)),
            generic_original_invalid_fields=sorted(f['key'] for f in page['fields'] if f['invalid']),
            generic_fact_hashes={},generic_academic_sha256=profile['academic_sha256'],generic_directory_sha256=digest(profile.get('school_directory')))
    cp.update(state='prepared',context=copy.deepcopy(context),prepared_at=now(),
        source_gate=gate,semantic_analysis=copy.deepcopy(analysis),observed_structure=structure(page),
        observation_sha256=digest(page),prepared_plan=copy.deepcopy(plan),generic_stage_controller=copy.deepcopy(item))
    if not is_metadata(item['ref']):cp['generic_fact_hashes'][item['ref']]=digest(profile['facts'][item['ref']])
    cp['generic_fact_hashes'].update({r:digest(profile['facts'][r]) for r in dependency_refs})
    if analysis.get('child_records'):cp['generic_nested_source_sha256']=source_fingerprint(profile,analysis)
    _event(profile,'generic_branch_prepared',[key,item['ref']]);return plan


def restart_stage(profile,key,page,analysis,controller_key,*,reaffirm_native_select=False):
    cp=profile['checkpoints'].get(key)
    if not cp:raise ProfileError('prepared_generic_checkpoint_required')
    return prepare_stage(profile,cp['target_id'],page,analysis,cp['context'],controller_key,resume_key=key,reaffirm_native_select=reaffirm_native_select)


def switch_view(profile,key,previous_page,page,analysis,*,controller_key=None):
    """Carry one unsaved native-form journal across its observed accordion views."""
    from .browser import validate_observation
    from .pages import build_plan,prepare
    cp=profile['checkpoints'].get(key)
    if (not cp or not transaction_active(cp) or cp.get('journal') is None or not readback_skipped(profile)
            or cp.get('generic_stage_controller') or cp.get('semantic_analysis',{}).get('parent_checkpoint_id')
            or any(k!=key and transaction_active(c) for k,c in profile['checkpoints'].items())):
        raise ProfileError('ready_same_form_view_handover_required')
    plan=cp.get('prepared_plan',{});before=previous_page.get('generic_form',{});after=page.get('generic_form',{})
    for observed in (previous_page,page):
        validate_observation(observed);permission(profile,profile['targets'][cp['target_id']],observed,cp['context'])
    if (page['url']!=cp['page_key'] or previous_page['url']!=cp['page_key'] or before.get('dialog') or after.get('dialog')
            or not before.get('view') or not after.get('view') or before['view']==after['view']
            or before.get('views')!=after.get('views') or before['scope']!=after['scope'] or before['destination']!=after['destination']
            or before['view']!=plan.get('generic_form',{}).get('view')
            or digest(structure(previous_page))!=plan.get('structure_sha256') or digest(values(previous_page))!=plan.get('expected_values_sha256')
            or profile['academic_sha256']!=cp.get('generic_academic_sha256') or not directory_unchanged(profile,cp)
            or any(digest(profile['facts'].get(r))!=h for r,h in cp.get('generic_fact_hashes',{}).items())):
        raise ProfileError('same_native_form_frozen_view_sources_required')
    working=copy.deepcopy(profile);working['checkpoints'][key].update(state='collecting',journal=None)
    if controller_key:
        next_plan=prepare_stage(working,cp['target_id'],page,analysis,cp['context'],controller_key)
    else:
        next_plan=build_plan(working,cp['target_id'],page,semantic_analysis=analysis)
        if not next_plan['ready']:return next_plan
        next_plan=prepare(working,next_plan['checkpoint_id'],page,cp['context'])
    fresh=copy.deepcopy(working['checkpoints'][next_plan['checkpoint_id']])
    history=copy.deepcopy(cp.get('generic_view_history',[]))
    history.append({k:copy.deepcopy(cp[k]) for k in ('journal','semantic_analysis','observed_structure','prepared_plan','generic_fact_hashes')})
    old_hashes=copy.deepcopy(cp['generic_fact_hashes']);cp.clear();cp.update(fresh)
    next_plan['checkpoint_id']=key;cp['checkpoint_id']=key;cp['prepared_plan']=copy.deepcopy(next_plan)
    cp['generic_view_history']=history;cp['generic_fact_hashes']={**old_hashes,**cp['generic_fact_hashes']}
    _event(profile,'same_form_view_journal_carried_forward',[key])
    return next_plan


def accept_stage(profile,key,page,analysis):
    from .browser import validate_observation
    from .pages import build_plan,resolve,encode
    cp=profile['checkpoints'].get(key)
    if not cp or not cp.get('generic_stage_controller') or cp.get('journal') is None:raise ProfileError('prepared_generic_branch_required')
    validate_observation(page);permission(profile,profile['targets'][cp['target_id']],page,cp['context'])
    if page['url']!=cp['page_key'] or profile['academic_sha256']!=cp['generic_academic_sha256'] or not directory_unchanged(profile,cp) or any(digest(profile['facts'].get(r))!=h for r,h in cp['generic_fact_hashes'].items()):
        raise ProfileError('generic_branch_source_or_page_changed')
    old=cp['generic_stage_controller'];adapter=SemanticAdapter(profile,profile['targets'][cp['target_id']],page,analysis)
    if any(adapter.analysis.get(k)!=cp['semantic_analysis'].get(k) for k in ('record','record_view')):raise ProfileError('generic_record_context_changed')
    current=adapter.items.get(old['key']);field=next((f for f in page['fields'] if f['key']==old['key']),None)
    if current!=old or not field:raise ProfileError('generic_branch_controller_meaning_changed')
    raw,_=resolve(profile,old['ref'])
    if field['value']!=encode(field,adapter.display_value(field,old['ref'],raw)):raise ProfileError('generic_branch_choice_not_observed')
    before=cp['observed_structure']['generic_form'];after=structure(page)['generic_form']
    if before['scope']!=after['scope'] or before['destination']!=after['destination']:raise ProfileError('generic_branch_destination_changed')
    working=copy.deepcopy(profile)
    working['checkpoints'][key].update(state='collecting',journal=None)
    plan=build_plan(working,cp['target_id'],page,semantic_analysis=analysis);plan['checkpoint_id']=key
    if not plan['ready']:
        cp['generic_pending_fact_ids']=[q['fact_id'] for q in plan['questions'] if q['reason']=='missing']
        _event(profile,'generic_branch_answers_needed',[key,*cp['generic_pending_fact_ids']]);return plan
    fresh=working['checkpoints'][key]
    for name in ('observed_structure','observation_sha256','required_fact_ids','required_course_ids','required_record_columns','source_gate','semantic_analysis','save_action','optional_keys'):
        if name in fresh:cp[name]=copy.deepcopy(fresh[name])
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan),expected_values_sha256=plan['expected_values_sha256'])
    cp['generic_fact_hashes'].update({r:digest(profile['facts'].get(r)) for r in cp['required_fact_ids']})
    cp.pop('generic_stage_controller',None);cp.pop('generic_pending_fact_ids',None)
    _event(profile,'generic_branch_whole_page_prepared',[key]);return plan


def resume(profile,key,page,analysis=None):
    from .pages import build_plan
    from .browser import validate_observation
    cp=profile['checkpoints'].get(key)
    if not cp or not transaction_active(cp) or cp.get('journal') is None or not cp.get('semantic_analysis'):raise ProfileError('prepared_generic_checkpoint_required')
    active_parent(profile,cp['target_id'],page,analysis or cp['semantic_analysis'],exclude=key)
    validate_observation(page);target=profile['targets'][cp['target_id']];permission(profile,target,page,cp['context'])
    if page['url']!=cp['page_key'] or profile['academic_sha256']!=cp['generic_academic_sha256'] or not directory_unchanged(profile,cp):
        raise ProfileError('generic_resume_context_changed')
    if any(digest(profile['facts'].get(ref))!=sha for ref,sha in cp['generic_fact_hashes'].items()):raise ProfileError('generic_resume_source_changed')
    old={i['key']:i for i in cp['semantic_analysis']['fields']};current={f['key']:f for f in page['fields']}
    if not set(old)<=set(current):raise ProfileError('generic_removed_fields_require_cancel_or_review')
    before={f['key']:f for f in cp['observed_structure']['fields']}
    after={f['key']:f for f in structure(page)['fields']}
    scope={k:page['generic_form']['scope'][k] for k in ('selector_count','selector_index')}
    if (any(after[k]!=before[k] for k in before) or scope!=cp['observed_structure']['generic_form']['scope']
            or page['generic_form']['instructions_sha256']!=cp['observed_structure']['generic_form']['instructions_sha256']
            or page['generic_form']['destination']!=cp['observed_structure']['generic_form']['destination']):
        raise ProfileError('generic_existing_field_meaning_changed')
    if analysis is None:
        if digest(structure(page))!=digest(cp['observed_structure']):raise ProfileError('fresh_semantic_analysis_required')
        analysis={**cp['semantic_analysis'],'observation_sha256':digest(page)}
    proposed,items=analysis_for(profile,target,page,analysis)
    if any(proposed.get(k)!=cp['semantic_analysis'].get(k) for k in ('record','record_view')):raise ProfileError('generic_record_context_changed')
    if any(items[k]!=item and not (item.get('format')=='identity' and items[k].get('format')=='decimal_fixed_2'
            and item.get('ref','').startswith('psr-average:') and {**item,'format':'decimal_fixed_2'}==items[k]) for k,item in old.items()):
        raise ProfileError('generic_existing_binding_changed')
    working=copy.deepcopy(profile);working['checkpoints'][key].update(state='collecting',journal=None)
    plan=build_plan(working,cp['target_id'],page,semantic_analysis=proposed)
    plan['checkpoint_id']=key
    if not plan['ready']:
        cp['generic_pending_fact_ids']=[q['fact_id'] for q in plan['questions'] if q['reason']=='missing']
        _event(profile,'generic_conditional_answers_needed',[key,*cp['generic_pending_fact_ids']])
        return plan
    fresh=working['checkpoints'][key]
    for name in ('observed_structure','observation_sha256','required_fact_ids','required_course_ids','required_record_columns','source_gate','semantic_analysis'):
        if name in fresh:cp[name]=copy.deepcopy(fresh[name])
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan),expected_values_sha256=plan['expected_values_sha256'])
    cp.pop('generic_pending_fact_ids',None)
    cp['generic_fact_hashes'].update({r:digest(profile['facts'].get(r)) for r in cp['required_fact_ids']})
    _event(profile,'generic_page_resumed',[key]);return plan


def recovery(profile,key,page):
    from .browser import validate_observation
    cp=profile['checkpoints'].get(key)
    if not cp or not transaction_active(cp) or cp.get('journal') is None or not cp.get('semantic_analysis'):raise ProfileError('prepared_generic_checkpoint_required')
    validate_observation(page);permission(profile,profile['targets'][cp['target_id']],page,cp['context'])
    if page['url']!=cp['page_key']:raise ProfileError('generic_recovery_page_mismatch')
    return {'plan':copy.deepcopy(cp['prepared_plan']),'analysis':copy.deepcopy(cp['semantic_analysis']),
        'context':{**cp['context'],'journal_persisted':True},'recovery_kind':'unsaved_cancel_or_intended_resume'}


def verify_matching(profile,target_id,baseline,saved,context,*,revisited_saved_draft,analysis=None):
    from .pages import build_plan
    from .browser import validate_observation,permission_gate
    if any(transaction_active(c) for c in profile['checkpoints'].values()):raise ProfileError('pending_transaction_requires_recovery')
    target=profile['targets'].get(target_id)
    if not target:raise ProfileError('student_selected_target_required')
    for page in (baseline,saved):
        validate_observation(page);permission(profile,target,page,context);permission_gate(context,page,target['application_site']['origin'])
    if (revisited_saved_draft is not True or baseline['url']!=saved['url'] or structure(baseline)!=structure(saved)
            or values(baseline)!=values(saved) or any(f['invalid'] for p in (baseline,saved) for f in p['fields'])):
        return {'verified':False,'reason':'independent_saved_draft_match_required','website_actions_performed':False}
    proposed,_=analysis_for(profile,target,baseline,analysis)
    working=copy.deepcopy(profile)
    first=build_plan(working,target_id,baseline,semantic_analysis={**proposed,'observation_sha256':digest(baseline)})
    second=build_plan(working,target_id,saved,semantic_analysis={**proposed,'observation_sha256':digest(saved)})
    if not first['ready'] or first['writes'] or not second['ready'] or second['writes']:
        return {'verified':False,'reason':'source_ready_unchanged_matching_plan_required','website_actions_performed':False}
    cp=working['checkpoints'][second['checkpoint_id']]
    cp.update(state='verified',journal=None,context=copy.deepcopy(context),verification_kind='read_only_saved_match',
        expected_values_sha256=digest(values(saved)),last_verified_at=now(),verified_source_sha256=source_fingerprint(profile,proposed))
    _event(working,'generic_saved_match_verified_without_input',[cp['checkpoint_id']]);profile.clear();profile.update(working)
    return {'verified':True,'checkpoint_id':cp['checkpoint_id'],'verification_kind':'read_only_saved_match',
        'fields':len(saved['fields']),'website_actions_performed':False,'full_application_complete':False}


def pending_fact_append_allowed(previous,updated,*,explicit_new_fact_ids=()):
    """Append recorded answers, or explicitly named new student facts, to a journal.

    Existing facts, source evidence, original journals and all other applicant
    state remain frozen. This is checked inside the atomic store lock.
    """
    active=[c for c in previous['checkpoints'].values() if transaction_active(c)]
    if len(active)!=1 or not active[0].get('semantic_analysis'):return False
    if (not isinstance(explicit_new_fact_ids,(list,tuple,set,frozenset)) or any(
            not isinstance(r,str) or not FACT_ID.fullmatch(r) for r in explicit_new_fact_ids)):return False
    allowed=set(active[0].get('generic_pending_fact_ids',[]))|set(explicit_new_fact_ids)
    if not allowed:return False
    for key in set(previous)|set(updated):
        if key in {'facts','sources','events'}:continue
        if previous.get(key)!=updated.get(key):return False
    if updated['events'][:len(previous['events'])]!=previous['events']:return False
    if any(updated['facts'].get(k)!=v for k,v in previous['facts'].items()):return False
    added=set(updated['facts'])-set(previous['facts'])
    if not added or not added<=allowed:return False
    if not set(explicit_new_fact_ids)<=added:return False
    if any(updated['sources'].get(k)!=v for k,v in previous['sources'].items()):return False
    new_sources=set(updated['sources'])-set(previous['sources']);used=set()
    for key in added:
        fact=updated['facts'][key]
        if fact['verification']!='student_reported' or fact.get('evidence') is not None:return False
        for ref in fact['source_refs']:
            if updated['sources'][ref]['kind']!='student_statement':return False
            used.add(ref)
    return new_sources<=used


def cancel(profile,key,page,*,revisited_saved_draft):
    from .browser import validate_observation
    cp=profile['checkpoints'].get(key)
    if not cp or not transaction_active(cp) or not cp.get('semantic_analysis') or cp.get('journal') is None:raise ProfileError('prepared_generic_checkpoint_required')
    if cp.get('generic_view_history'):raise ProfileError('same_form_history_requires_intended_resume_or_manual_recovery')
    validate_observation(page)
    old_form=cp.get('prepared_plan',{}).get('generic_form',{})
    if (revisited_saved_draft is True and page['url']==cp['page_key'] and old_form.get('view')
            and 'views' in page['generic_form'] and old_form['view']['name'] not in page['generic_form']['views']
            and cp.get('generic_stage_controller',{}).get('purpose')=='date' and cp.get('semantic_analysis',{}).get('child_records')
            and all(v=='' for v in cp['journal'].values())
            and old_form['scope']==page['generic_form']['scope'] and old_form['destination']==page['generic_form']['destination']
            and not any(c.get('semantic_analysis',{}).get('parent_checkpoint_id')==key for c in profile['checkpoints'].values())):
        cp.update(state='discarded_missing_view',canceled_at=now())
        _event(profile,'empty_date_stage_lost_after_session_expiry',[key])
        return {'restored':False,'draft_discarded':True,'state':cp['state'],'missing_view':old_form['view']['name']}
    okay=(revisited_saved_draft is True and page['url']==cp['page_key'] and values(page)==cp['journal']
        and digest(structure(page))==cp['generic_original_structure_sha256']
        and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['generic_original_invalid_fields'])
    if not okay and revisited_saved_draft is True and page['url']==cp['page_key'] and values(page)==cp['journal']:
        # A canceled new editor can retain a disabled, unchecked optional status
        # checkbox from an earlier date branch. Prove that this single flag is
        # the only drift; retain history and never claim exact restoration.
        original_shape=copy.deepcopy(page)
        candidates=[f for f in original_shape['fields'] if f['control']=='checkbox' and not f['required'] and f['value'] is False and f['disabled']]
        if len(candidates)==1:
            candidates[0]['disabled']=False
            if (digest(structure(original_shape))==cp['generic_original_structure_sha256']
                    and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['generic_original_invalid_fields']):
                cp.update(state='canceled_ui_drift',canceled_at=now())
                cp.pop('generic_pending_fact_ids',None)
                _event(profile,'generic_unsaved_discarded_with_inactive_checkbox_drift',[key])
                return {'restored':False,'draft_discarded':True,'state':cp['state'],'original_values_preserved':True,'inactive_checkbox_drift':True}
    if not okay:cp['state']='needs_restore';return {'restored':False,'state':'needs_restore'}
    cp.update(state='restored',journal=None)
    for name in ('prepared_plan','generic_original_invalid_fields','generic_original_structure_sha256','generic_fact_hashes','generic_academic_sha256','generic_directory_sha256','generic_pending_fact_ids','generic_stage_controller'):
        cp.pop(name,None)
    _event(profile,'generic_unsaved_canceled',[key]);return {'restored':True,'restore_save_performed':False}
