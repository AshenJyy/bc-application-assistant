"""Staged creation of source-backed Common App grade transcripts, without attestation."""
import copy
import json
import re
from importlib.resources import files
from urllib.parse import urlsplit

from .academic import compile_report,HEADERS
from .browser import digest,structure,values,validate_observation,permission_gate
from .checkpoints import create_checkpoint,transaction_active
from .common_pages import state_matches
from .profile import ProfileError,_event,now

CONTRACT=json.loads(files('bc_application').joinpath('data/common_academic.json').read_text(encoding='utf-8'))
HEADER_IDS={'school_name':'schoolName','school_year':'schoolYear','grading_scale':'gradingScale','schedule':'schedule'}
TERM_LABELS={v:k for k,v in CONTRACT['terms'].items()}


def empty(field):
    return field['value'] is False if field['control']=='checkbox' else field['value'] in {'','Select'}


def layout(page):
    groups={}
    for field in page['fields']:
        header=re.fullmatch(r'Transcript (\d+) (School Name|School Year|Grading Scale|Schedule)',field['label'])
        row=re.fullmatch(r'Transcript (\d+), Course (\d+), (.*)',field['label'])
        if header:
            number=int(header[1]);item=groups.setdefault(number,{'headers':{},'rows':{}})
            name=next(key for key,label in CONTRACT['headers'].items() if label==header[2])
            if name in item['headers']:raise ProfileError('ambiguous_academic_header')
            item['headers'][name]=field
        elif row:
            number,index=int(row[1]),int(row[2]);item=groups.setdefault(number,{'headers':{},'rows':{}})
            course=item['rows'].setdefault(index,{'grades':{},'credits':{}});part=row[3]
            basic={'Subject':'subject','Course Nameundefined':'name','Course Level':'level','Credits not applicable':'na'}
            if part in basic:kind=basic[part];dest=course
            else:
                match=re.fullmatch(r'(Semester [12]|Final)(undefined| Grade| Credit| Credits)',part)
                if not match:raise ProfileError('unknown_academic_course_control')
                kind=TERM_LABELS[match[1]];dest=course['credits' if 'Credit' in match[2] else 'grades']
            if kind in dest:raise ProfileError('ambiguous_academic_course_control')
            dest[kind]=field
        else:raise ProfileError('unknown_academic_form_field')
    return groups


def validate_layout(page):
    """Called by the generic observation validator; never recursively validates it."""
    parsed=urlsplit(page['url']);scope=page.get('scope',{});tag=page.get('common_academic',{})
    if (parsed.scheme+'://'+parsed.netloc not in {CONTRACT['origin'],'http://127.0.0.1:8765','http://localhost:8765'}
            or parsed.path not in CONTRACT['paths'].values() or parsed.query or parsed.fragment
            or page['title']!=CONTRACT['title'] or page.get('frames_present') or page.get('collections')
            or scope.get('kind')!='common_app_grade_creation' or scope.get('name')!='Courses & Grades'
            or tag.get('schema')!='common-academic-page/1' or set(tag)!={'schema','pending_rows','instructions'}
            or tag['instructions']!=CONTRACT['instructions']):
        raise ProfileError('observed_common_academic_contract_required')
    groups=layout(page)
    if not groups or list(groups)!=list(range(1,len(groups)+1)) or len(groups)>25:
        raise ProfileError('contiguous_academic_transcripts_required')
    pending=[]
    for number,item in groups.items():
        if set(item['headers'])!=HEADERS or not item['rows'] or list(item['rows'])!=list(range(1,len(item['rows'])+1)) or len(item['rows'])>100:
            raise ProfileError('complete_academic_transcript_controls_required')
        for part,f in item['headers'].items():
            if f['key']!=f'i:{HEADER_IDS[part]}Control{number}' or f['control']!='material_select' or not f['required']:
                raise ProfileError('observed_academic_header_identity_required')
        schedule=item['headers']['schedule']['value'];scale=item['headers']['grading_scale']['value']
        for index,row in item['rows'].items():
            if not {'subject','name','level'}<=set(row):raise ProfileError('complete_academic_course_controls_required')
            for part,prefix,control in [('subject','subject','material_select'),('name','courseName','text'),('level','level','material_select')]:
                f=row[part]
                if f['key']!=f'i:{prefix}Control_T{number}C{index}' or f['control']!=control or not f['required']:
                    raise ProfileError('observed_academic_course_identity_required')
            partial=not row['grades'] or not row['credits'] or 'na' not in row
            if partial:
                if schedule not in {'','Select'} and scale not in {'','Select'}:
                    raise ProfileError('academic_term_controls_not_ready')
                pending.append(f'T{number}C{index}')
            else:
                if schedule not in CONTRACT['schedules'] or scale not in CONTRACT['scales']:
                    raise ProfileError('academic_schedule_or_scale_unsupported')
                terms=CONTRACT['schedules'][schedule]
                if list(row['grades'])!=terms or list(row['credits'])!=terms:
                    raise ProfileError('observed_academic_term_layout_required')
                na=row['na']
                if na['key']!=f'i:creditNA_T{number}C{index}-input' or na['control']!='checkbox':
                    raise ProfileError('observed_academic_credit_mode_required')
                for f in row['grades'].values():
                    if f['control']!=('text' if scale=='Other' else 'material_select'):
                        raise ProfileError('original_scale_academic_control_required')
                for kind in ('grades','credits'):
                    for term,f in row[kind].items():
                        suffix=f'_T{number}C{index}'
                        if kind=='grades' and scale=='Other':
                            offset=terms.index(term)
                            expected=f'i:gradeControl{suffix}'+(f'@{offset}' if len(terms)>1 else '')
                            if (f['key']!=expected or f.get('selector_count',1)!=len(terms)
                                    or f.get('selector_index',0)!=offset):
                                raise ProfileError('observed_academic_term_identity_required')
                        else:
                            stem=('grade' if kind=='grades' else 'credit')+{'semester_1':'1','semester_2':'2','final':'Final'}[term]
                            if f['key']!=f'i:{stem}Control{suffix}':
                                raise ProfileError('observed_academic_term_identity_required')
                # Saved Common App rows can retain enabled, blank credit inputs
                # while N/A is checked. Do not invent a disabled-state invariant.
                if any(f['control'] not in {'text','number'} or ((f['disabled'] or f['readonly']) and not na['value']) for f in row['credits'].values()):
                    raise ProfileError('observed_academic_credit_applicability_required')
    if tag['pending_rows']!=pending:raise ProfileError('observed_academic_pending_rows_required')
    native=page.get('academic_layout',{})
    if native.get('schema')!='common-academic-layout/1' or not isinstance(native.get('transcripts'),list) or len(native['transcripts'])!=len(groups):
        raise ProfileError('observed_academic_action_owners_required')
    for number,meta in enumerate(native['transcripts'],1):
        if (meta.get('number')!=number or meta.get('selector')!=f'ca-cng-transcript:has([id="schoolNameControl{number}"])'
                or meta.get('selector_count')!=1 or len(meta.get('rows',[]))!=len(groups[number]['rows'])):
            raise ProfileError('observed_academic_action_owners_required')
        for index,row in enumerate(meta['rows'],1):
            if (row.get('number')!=index or row.get('selector')!=f'ca-cng-course:has([id="courseNameControl_T{number}C{index}"])'
                    or row.get('selector_count')!=1 or (index>1 and row.get('remove_label')!=f'Remove transcript {number}, course {index} of {len(meta["rows"])}, Opens dialog')):
                raise ProfileError('observed_academic_action_owners_required')
    for f in page['fields']:
        if (f['group'] or not f['selector'] or f.get('selector_count',1)<1
                or ((f['disabled'] or f['readonly']) and not f['label'].endswith((' Credit',' Credits')))):
            raise ProfileError('observed_academic_editable_fields_required')
    if not any(a['key']=='i:changePreferencesClose' and a['label']=='Close dialog' and not a['disabled'] for a in page['actions']):
        raise ProfileError('observed_academic_cancel_required')
    if len([a for a in page['actions'] if a['label']==CONTRACT['save'] and not a['disabled']])!=1:
        raise ProfileError('observed_academic_draft_save_required')


def _desired(row,wanted):
    result={row['subject']['key']:wanted['subject'],row['level']['key']:wanted['level'],
        row['name']['key']:re.sub(r'\s+',' ',re.sub(r'-\r?\n\s*','-',wanted['name'])).strip()}
    if 'na' in row:result[row['na']['key']]=wanted['credits_na']
    for kind,ref in [('grades','grade_terms'),('credits','credit_terms')]:
        for term,field in row[kind].items():
            result[field['key']]=str(wanted[ref][term]) if term in wanted[ref] else field['value'] if empty(field) else ''
    return result


def _compile(profile,target,report_ref,page):
    validate_observation(page)
    if profile['targets'].get(target,{}).get('system')!='common_app':raise ProfileError('student_selected_common_target_required')
    compiled=compile_report(profile,report_ref)
    if not compiled['ready']:return compiled
    if CONTRACT['paths'].get(compiled['grade'])!=urlsplit(page['url']).path:raise ProfileError('academic_report_grade_mismatch')
    identities=[]
    for transcript in compiled['transcripts']:
        headers=transcript['headers'];schedule=headers['schedule'];scale=headers['grading_scale']
        if schedule not in CONTRACT['schedules'] or scale not in CONTRACT['scales']:
            raise ProfileError('academic_schedule_or_scale_unsupported')
        identities.append(tuple(headers[key] for key in sorted(HEADERS)))
        for row in transcript['courses']:
            if (not set(row['grade_terms'])<=set(CONTRACT['schedules'][schedule]) or not set(row['credit_terms'])<=set(CONTRACT['schedules'][schedule])
                    or set(row['grade_columns'].values())!={CONTRACT['scales'][scale]}):
                raise ProfileError('original_scale_or_term_placement_mismatch')
    if len(identities)!=len(set(identities)):raise ProfileError('duplicate_academic_transcript_identity')
    return compiled


def _step(page,compiled):
    groups=layout(page);target=compiled['transcripts'];choices=page.get('choice_observations',{})
    def step(kind,**extra):return {'stage':kind,**extra}
    if len(groups)>len(target):raise ProfileError('unplanned_existing_academic_transcript')
    # Inspect every existing value before planning even an earlier Add/header
    # action. A conflicting saved row must never cause a duplicate to be added.
    for number,item in groups.items():
        wanted=target[number-1]
        for part,field in item['headers'].items():
            if not empty(field) and field['value']!=wanted['headers'][part]:
                raise ProfileError('conflicting_existing_academic_header')
        for index,row in item['rows'].items():
            fields=[row['subject'],row['name'],row['level'],*row['grades'].values(),*row['credits'].values(),*([row['na']] if 'na' in row else [])]
            if index>len(wanted['courses']):
                if any(not empty(f) for f in fields):raise ProfileError('populated_academic_record_removal_forbidden')
                continue
            expected=_desired(row,wanted['courses'][index-1])
            if any(not empty(f) and f['value']!=expected[f['key']] for f in fields):
                raise ProfileError('conflicting_existing_academic_record')
    for number,wanted in enumerate(target,1):
        if number not in groups:return step('add_transcript',transcript=number)
        item=groups[number]
        for part in ('school_name','school_year','grading_scale','schedule'):
            field=item['headers'][part];value=wanted['headers'][part]
            if field['value']==value:continue
            if not empty(field):raise ProfileError('conflicting_existing_academic_header')
            if field['key'] not in choices:return step('choices',choice_keys=[field['key']])
            from .pages import encode
            encode({**field,'choices':choices[field['key']]},value)
            return step('header',writes=[{'field_key':field['key'],'value':value}],transcript=number)
        count=len(wanted['courses']);rows=item['rows']
        if len(rows)<count:return step('add_course',transcript=number,row=len(rows)+1)
        if len(rows)>count:
            last=rows[len(rows)]
            if any(not empty(f) for f in [last['subject'],last['name'],last['level'],*last['grades'].values(),*last['credits'].values(),*([last['na']] if 'na' in last else [])]):
                raise ProfileError('populated_academic_record_removal_forbidden')
            return step('remove_placeholder',transcript=number,row=len(rows))
        for index,wanted_row in enumerate(wanted['courses'],1):
            row=rows[index]
            if 'na' not in row:raise ProfileError('academic_term_controls_not_ready')
            if row['na']['value']!=wanted_row['credits_na']:
                if row['na']['value']:raise ProfileError('conflicting_existing_academic_credit_mode')
                return step('credit_mode',writes=[{'field_key':row['na']['key'],'value':wanted_row['credits_na']}],transcript=number,row=index)
    desired=values(page);writes=[];needed=[]
    for number,wanted in enumerate(target,1):
        for index,wanted_row in enumerate(wanted['courses'],1):
            row=groups[number]['rows'][index];expected=_desired(row,wanted_row)
            for field in [row['subject'],row['level'],row['name'],*row['grades'].values(),*row['credits'].values(),row['na']]:
                value=expected[field['key']];desired[field['key']]=value
                if field['value']==value:continue
                if not empty(field):raise ProfileError('conflicting_existing_academic_record')
                if field['disabled']:raise ProfileError('academic_expected_value_not_editable')
                if field['control']=='material_select':
                    if field['key'] not in choices:needed.append(field['key']);continue
                    from .pages import encode
                    encode({**field,'choices':choices[field['key']]},value)
                writes.append({'field_key':field['key'],'value':value})
    if needed:return step('choices',choice_keys=needed)
    return step('fields',writes=writes,expected_values_sha256=digest(desired),structure_sha256=digest(structure(page)))


def preview(profile,target,report_ref,page):
    if any(transaction_active(c) for c in profile['checkpoints'].values()):raise ProfileError('pending_transaction_requires_recovery')
    compiled=_compile(profile,target,report_ref,page)
    if not compiled['ready']:return {**compiled,'website_actions_performed':False,'profile_changed':False}
    step=_step(page,compiled)
    return {'ready':step['stage']!='choices','source_ready':True,'next':step,'required_fact_ids':compiled['required_fact_ids'],
        'source_gate':compiled['source_gate'],'source_fingerprint':compiled['source_fingerprint'],
        'website_actions_performed':False,'profile_changed':False}


def prepare(profile,target,report_ref,page,context):
    report=preview(profile,target,report_ref,page)
    permission_gate(context,page,CONTRACT['origin'])
    if context.get('real_account_test') or context.get('restore_after_test'):raise ProfileError('academic_creation_intended_update_only')
    if not report['ready']:return report
    compiled=_compile(profile,target,report_ref,page)
    key=create_checkpoint(profile,target,page['url'],fact_ids=compiled['required_fact_ids'],course_ids=compiled['required_course_ids'],record_columns=compiled['required_record_columns'])
    cp=profile['checkpoints'][key]
    cp.update(kind='common_academic_creation',state='prepared',journal=values(page),context=copy.deepcopy(context),
        observed_structure=structure(page),original_parent=copy.deepcopy(page['editor_state']),report_ref=report_ref,
        source_fingerprint=compiled['source_fingerprint'],prepared_at=now(),
        protected_keys=[f['key'] for f in page['fields'] if not empty(f)],
        original_invalid_fields=sorted(f['key'] for f in page['fields'] if f['invalid']))
    cp.pop('verification_kind',None)
    _event(profile,'academic_record_creation_prepared',[key])
    return advance(profile,key,page)


def _active(profile,key,page):
    cp=profile['checkpoints'].get(key)
    if not cp or cp.get('kind')!='common_academic_creation' or cp.get('journal') is None or not transaction_active(cp):
        raise ProfileError('prepared_academic_creation_required')
    if any(k!=key and transaction_active(c) for k,c in profile['checkpoints'].items()):raise ProfileError('pending_transaction_requires_recovery')
    permission_gate(cp['context'],page,CONTRACT['origin'])
    current=values(page);old={f['key']:f for f in cp['observed_structure']['fields']}
    fresh={f['key']:f for f in structure(page)['fields']}
    if any(current.get(key)!=cp['journal'][key] or fresh.get(key)!=old[key] for key in cp['protected_keys']):
        raise ProfileError('original_academic_record_changed')
    if not state_matches(cp['original_parent']['state_metadata'],page['state_metadata'],page['state_metadata']['current_page_key'],'secondaryNavItem13',resume=True):
        raise ProfileError('unrelated_academic_navigation_state_changed')
    compiled=_compile(profile,cp['target_id'],cp['report_ref'],page)
    if not compiled['ready'] or compiled['source_fingerprint']!=cp['source_fingerprint']:
        raise ProfileError('academic_resume_source_gate_failed')
    return cp,compiled


def advance(profile,key,page):
    cp,compiled=_active(profile,key,page);step=_step(page,compiled)
    if step['stage']=='choices':
        cp.pop('prepared_plan',None)
        return {'ready':False,'source_ready':True,'checkpoint_id':key,**step}
    plan={'schema':'common-academic-step/1','system':'common_app','ready':True,'checkpoint_id':key,
        'page_url':page['url'],'observation_sha256':digest(page),'choice_observations':copy.deepcopy(page.get('choice_observations',{})),**step}
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan))
    return {'ready':True,'checkpoint_id':key,'stage':step['stage'],'plan':plan}


def verify(profile,key,page,*,revisited_after_save):
    cp,compiled=_active(profile,key,page);step=_step(page,compiled)
    counts=[{'complete':len(t['courses']),'incomplete':0} for t in compiled['transcripts']]
    okay=(revisited_after_save is True and step['stage']=='fields' and not step['writes']
        and not any(f['invalid'] for f in page['fields']) and page['editor_state'].get('counts')==counts
        and not (cp['original_parent']['completion_checked'] is False and page['editor_state']['completion_checked'] is True))
    if not okay:
        cp['state']='needs_restore'
        return {'verified':False,'state':'needs_restore','reason':'saved_academic_records_mismatch'}
    cp.update(state='verified',journal=None,last_verified_at=now(),verification_kind='academic_records_saved',
        observed_structure=structure(page),saved_values_sha256=digest(values(page)),saved_parent_sha256=digest(page['editor_state']))
    for field in ('prepared_plan','original_parent','protected_keys','original_invalid_fields'):cp.pop(field,None)
    _event(profile,'academic_created_records_verified',[key])
    return {'verified':True,'factual_records_verified':True,'transcripts':len(compiled['transcripts']),
        'courses':sum(len(t['courses']) for t in compiled['transcripts']),
        'student_completion_action_required':page['editor_state']['completion_checked'] is False}


def cancel(profile,key,page,*,revisited_saved_draft):
    cp=profile['checkpoints'].get(key)
    if not cp or cp.get('kind')!='common_academic_creation' or cp.get('journal') is None:
        raise ProfileError('prepared_academic_creation_required')
    validate_observation(page);permission_gate(cp['context'],page,CONTRACT['origin'])
    okay=(revisited_saved_draft is True and values(page)==cp['journal'] and digest(structure(page))==digest(cp['observed_structure'])
        and page['editor_state']==cp['original_parent']
        and sorted(f['key'] for f in page['fields'] if f['invalid'])==cp['original_invalid_fields'])
    if not okay:
        cp['state']='needs_restore';return {'restored':False,'state':'needs_restore'}
    cp.update(state='restored',journal=None,last_verified_at=now())
    for field in ('prepared_plan','original_parent','protected_keys','original_invalid_fields'):cp.pop(field,None)
    _event(profile,'academic_unsaved_creation_canceled',[key])
    return {'restored':True,'restore_save_performed':False}
